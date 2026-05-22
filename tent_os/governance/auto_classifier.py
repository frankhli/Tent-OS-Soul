"""Auto-Mode Classifier —— 独立 LLM 风险评估

核心设计：
1. 独立于主 LLM —— 避免"自己审批自己"的冲突
2. 低成本模型 —— 使用轻量级模型（如 gpt-4o-mini）
3. 确定性输出 —— 返回结构化分类结果，不是自由文本
4. 缓存结果 —— 相同任务不重复评估

评估维度：
- safety_level: safe / cautious / dangerous / critical
- suggested_mode: strict / standard / auto / unrestricted
- reasoning: 评估理由（人类可读）
- confidence: 置信度 0-1

使用方式：
    classifier = AutoModeClassifier(llm=mini_llm_client)
    result = await classifier.evaluate("帮我删除日志文件")
    # -> {"safety_level": "cautious", "suggested_mode": "standard", ...}
"""

import json
import time
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from tent_os.logging_config import get_logger

logger = get_logger()


class SafetyLevel(Enum):
    """安全等级"""
    SAFE = "safe"
    CAUTIOUS = "cautious"
    DANGEROUS = "dangerous"
    CRITICAL = "critical"


@dataclass
class ClassificationResult:
    """分类结果"""
    safety_level: str
    suggested_mode: str
    reasoning: str
    confidence: float
    risks: List[str]
    eval_time_ms: float


@dataclass
class ComplexityResult:
    """任务复杂度评估结果"""
    is_complex: bool
    complexity_score: float  # 0-1
    reasoning: str
    confidence: float
    indicators: Dict[str, float]  # 各维度的指标分数
    eval_time_ms: float = 0.0


class AutoModeClassifier:
    """自动模式分类器

    使用独立的轻量级 LLM 评估任务风险，避免主 LLM 的利益冲突。

    关键设计：
    - 每次评估是一个独立的 LLM 调用
    - 结果被缓存（任务内容 hash -> 结果）
    - 评估 prompt 经过精心工程化，输出结构化 JSON
    """

    # 评估 prompt 模板
    CLASSIFIER_PROMPT = """你是一个安全评估专家。请评估以下用户任务的潜在风险等级。

任务描述：{task}

评估维度：
1. 是否涉及文件删除、系统修改、数据破坏？
2. 是否涉及隐私数据访问或外传？
3. 是否涉及网络攻击、恶意代码？
4. 是否涉及物理世界操作（机械臂、配送等）？
5. 是否只是信息查询、分析、生成内容？

请输出 JSON 格式：
{{
    "safety_level": "safe|cautious|dangerous|critical",
    "suggested_mode": "strict|standard|auto|unrestricted",
    "reasoning": "简要说明评估理由（50字以内）",
    "confidence": 0.85,
    "risks": ["风险1", "风险2"]
}}

规则：
- safe: 纯信息查询、内容生成、数据分析
- cautious: 文件读取、网络搜索、代码执行（只读）
- dangerous: 文件写入、系统命令执行、数据修改
- critical: 物理操作、大规模删除、安全相关操作

suggested_mode 规则：
- strict: 只允许 safe 操作
- standard: 允许 safe + cautious + dangerous（但有审批保护）
- auto: 由系统动态决定
- unrestricted: 允许所有操作（仅用于 critical 且已确认的场景）

只输出 JSON，不要其他内容。"""

    # 复杂度评估 prompt 模板（精简但明确标准）
    COMPLEXITY_PROMPT = """判断任务是否需要多步骤 Plan-Execute 模式。输出 JSON：

任务：{task}

输出：{{"is_complex":bool, "complexity_score":0-1, "reasoning":"", "confidence":0-1}}

判断标准：
- 需要多步骤执行（先A后B）→ is_complex=true, score>0.6
- 需要多个工具协作 → is_complex=true, score>0.5
- 单步骤直接完成 → is_complex=false, score<0.3

示例：
- "列出目录" → {{"is_complex":false,"complexity_score":0.1}}
- "整理文件分类移动" → {{"is_complex":true,"complexity_score":0.7}}
- "先读配置再改端口最后重启" → {{"is_complex":true,"complexity_score":0.85}}

只输出 JSON。"""

    def __init__(self, llm: Any,
                 cache_ttl_seconds: int = 3600,
                 timeout_seconds: int = 5,
                 min_confidence: float = 0.7):
        self.llm = llm
        self.cache_ttl = cache_ttl_seconds
        self.timeout = timeout_seconds
        self.min_confidence = min_confidence

        # 评估结果缓存: task_hash -> (result, timestamp)
        self._cache: Dict[str, tuple] = {}

        # 统计
        self._stats = {"calls": 0, "cache_hits": 0, "errors": 0}

    async def evaluate(self, task: str,
                       context: Dict[str, Any] = None) -> ClassificationResult:
        """评估任务风险

        Args:
            task: 用户任务描述
            context: 额外上下文（如用户历史行为、当前 mode）

        Returns:
            ClassificationResult
        """
        start_time = time.time()
        context = context or {}

        # 1. 检查缓存
        task_hash = self._hash_task(task)
        if task_hash in self._cache:
            cached_result, cached_ts = self._cache[task_hash]
            if time.time() - cached_ts < self.cache_ttl:
                self._stats["cache_hits"] += 1
                cached_result.eval_time_ms = 0  # 缓存命中不计时
                return cached_result

        # 2. 快速启发式预筛（零成本）
        heuristic_result = self._heuristic_evaluate(task)
        if heuristic_result and heuristic_result.confidence > 0.9:
            # 高置信度启发式结果直接返回
            self._cache[task_hash] = (heuristic_result, time.time())
            return heuristic_result

        # 3. LLM 评估
        try:
            result = await self._llm_evaluate(task, context)
            self._stats["calls"] += 1
        except Exception as e:
            logger.warning(f"[Classifier] LLM 评估失败: {e}")
            self._stats["errors"] += 1
            # 降级到启发式结果
            result = heuristic_result or self._default_result("评估失败，使用保守策略")

        result.eval_time_ms = (time.time() - start_time) * 1000

        # 4. 缓存结果
        self._cache[task_hash] = (result, time.time())

        return result

    async def batch_evaluate(self, tasks: List[str]) -> List[ClassificationResult]:
        """批量评估多个任务"""
        results = []
        for task in tasks:
            result = await self.evaluate(task)
            results.append(result)
        return results

    async def evaluate_complexity(self, task: str,
                                   context: Dict[str, Any] = None) -> ComplexityResult:
        """评估任务复杂度 —— 替代 plan_executor 的关键词匹配
        
        设计：
        1. 启发式预筛（零成本）—— 任务长度、动词数量、时序词
        2. 不确定时调用 LLM 评估（复用 llm 连接）
        3. 结果缓存（同 evaluate()）
        
        Returns:
            ComplexityResult
        """
        start_time = time.time()
        context = context or {}
        
        # 1. 检查缓存（与 evaluate 共用缓存，key 前缀区分）
        task_hash = self._hash_task(f"complexity:{task}")
        if task_hash in self._cache:
            cached_result, cached_ts = self._cache[task_hash]
            if time.time() - cached_ts < self.cache_ttl:
                self._stats["cache_hits"] += 1
                return cached_result
        
        # 2. 启发式预筛
        heuristic = self._heuristic_complexity(task)
        if heuristic and heuristic.confidence > 0.85:
            self._cache[task_hash] = (heuristic, time.time())
            return heuristic
        
        # 3. LLM 评估
        try:
            result = await self._llm_complexity(task, context)
            self._stats["calls"] += 1
        except Exception as e:
            logger.warning(f"[Classifier] 复杂度 LLM 评估失败: {e}")
            self._stats["errors"] += 1
            result = heuristic or self._default_complexity_result("评估失败")
        
        result.eval_time_ms = (time.time() - start_time) * 1000
        self._cache[task_hash] = (result, time.time())
        return result
    
    def get_stats(self) -> Dict:
        """获取分类器统计"""
        return {
            **self._stats,
            "cache_size": len(self._cache),
            "hit_rate": round(
                self._stats["cache_hits"] / max(self._stats["calls"] + self._stats["cache_hits"], 1),
                2
            ),
        }

    # ========== 内部实现 ==========

    async def _llm_evaluate(self, task: str,
                            context: Dict[str, Any]) -> ClassificationResult:
        """调用 LLM 进行评估"""
        prompt = self.CLASSIFIER_PROMPT.format(task=task[:1000])

        # 调用 LLM
        if hasattr(self.llm, "chat"):
            response = await self.llm.chat([
                {"role": "system", "content": "你是一个安全评估专家，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ])
        else:
            response = await self.llm(prompt)

        # 解析 JSON
        result = self._parse_response(response)

        # 校验置信度
        if result.confidence < self.min_confidence:
            logger.debug(f"[Classifier] 置信度不足 ({result.confidence:.2f})，使用保守策略")
            result.suggested_mode = "standard"
            result.safety_level = "cautious"

        return result

    def _parse_response(self, response: str) -> ClassificationResult:
        """解析 LLM 的 JSON 响应"""
        try:
            # 提取 JSON
            json_str = response.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            data = json.loads(json_str)

            return ClassificationResult(
                safety_level=data.get("safety_level", "cautious"),
                suggested_mode=data.get("suggested_mode", "standard"),
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.5)),
                risks=data.get("risks", []),
                eval_time_ms=0.0,
            )
        except Exception as e:
            logger.warning(f"[Classifier] 解析响应失败: {e}")
            return self._default_result("解析失败，使用保守策略")

    def _heuristic_evaluate(self, task: str) -> Optional[ClassificationResult]:
        """启发式快速评估（零成本）

        原则：不限制用户表达，用通用特征而非关键词匹配。
        不确定时返回 None，降级到 LLM 评估。
        """
        task_lower = task.lower()
        
        # === 特征 1: 明显的系统危险命令（不依赖语言，基于命令模式） ===
        dangerous_commands = [
            "rm -rf", "rm -fr", "rm -r /", "mkfs", "fdisk", "dd if=",
            "chmod 777", "chmod -r 777", ":(){:|:&};:", "> /dev/sda",
        ]
        for cmd in dangerous_commands:
            if cmd in task_lower:
                return ClassificationResult(
                    safety_level="critical",
                    suggested_mode="strict",
                    reasoning="Detected dangerous system command pattern",
                    confidence=0.98,
                    risks=["May cause data loss or system damage"],
                    eval_time_ms=0.0,
                )
        
        # === 特征 2: 纯信息查询 / 闲聊问候（通用特征，不限语言） ===
        # 短文本 + 无特殊命令字符 + 问句结尾 → 大概率是查询
        has_command_chars = any(c in task for c in ["|", ";", "&&", "$", "`", "rm ", "sudo "])
        looks_like_question = task.endswith("?") or task.endswith("？") or task.endswith("...")
        is_short = len(task) < 150
        is_very_short = len(task) < 80
        
        if is_short and not has_command_chars and looks_like_question:
            return ClassificationResult(
                safety_level="safe",
                suggested_mode="standard",
                reasoning="Short question-like input without command patterns",
                confidence=0.85,
                risks=[],
                eval_time_ms=0.0,
            )
        
        # FIX: 问候/闲聊类对话——不问号结尾也应识别，避免浪费 LLM 评估
        # 特征：很短 + 无危险字符 + 包含问候词或无操作动词
        casual_greetings = {"你好", "您好", "hello", "hi", "hey", "在吗", "在么"}
        operation_verbs = {"执行", "运行", "删除", "修改", "写入", "安装", "配置", "部署", "删除", "清空", "rm", "delete", "remove", "write", "install", "exec", "run", "chmod"}
        has_greeting = any(g in task for g in casual_greetings)
        has_operation = any(v in task_lower for v in operation_verbs)
        
        if is_very_short and not has_command_chars and (has_greeting or not has_operation):
            return ClassificationResult(
                safety_level="safe",
                suggested_mode="standard",
                reasoning="Casual greeting or short chat without operation intent",
                confidence=0.88,
                risks=[],
                eval_time_ms=0.0,
            )
        
        # === 特征 3: 物理操作请求 ===
        physical_keywords = ["robot", "robotic", "drone", "printer", "delivery", 
                             "机器人", "机械臂", "无人机", "打印", "闪送"]
        if any(kw in task_lower for kw in physical_keywords):
            return ClassificationResult(
                safety_level="dangerous",
                suggested_mode="standard",
                reasoning="Physical world operation requested",
                confidence=0.9,
                risks=["Requires physical execution verification"],
                eval_time_ms=0.0,
            )
        
        # === 特征 4: 文件删除/修改请求（通用模式） ===
        destructive_patterns = ["delete all", "remove all", "drop ", "truncate ", 
                                "清空", "删除所有", "全部删除"]
        if any(p in task_lower for p in destructive_patterns):
            return ClassificationResult(
                safety_level="dangerous",
                suggested_mode="standard",
                reasoning="Destructive operation pattern detected",
                confidence=0.9,
                risks=["May delete data"],
                eval_time_ms=0.0,
            )

        # 无法确定 → 降级到 LLM
        return None

    def _default_result(self, reasoning: str) -> ClassificationResult:
        """默认保守结果"""
        return ClassificationResult(
            safety_level="cautious",
            suggested_mode="standard",
            reasoning=reasoning,
            confidence=0.5,
            risks=["评估失败，使用保守策略"],
            eval_time_ms=0.0,
        )

    # ========== 复杂度评估内部实现 ==========

    def _heuristic_complexity(self, task: str) -> Optional[ComplexityResult]:
        """启发式复杂度评估（零成本）
        
        不依赖关键词，使用通用特征：
        - 任务长度
        - 动词数量（多动词 = 多步骤）
        - 时序连接词（先/再/然后/之后）
        - 条件词（如果/假如/除非）
        """
        task_lower = task.lower()
        
        indicators = {
            "task_length": 0.0,
            "verb_count": 0.0,
            "sequential_markers": 0.0,
            "conditional_markers": 0.0,
        }
        
        # 特征 1: 任务长度
        length = len(task)
        if length > 500:
            indicators["task_length"] = 1.0
        elif length > 300:
            indicators["task_length"] = 0.7
        elif length > 150:
            indicators["task_length"] = 0.4
        else:
            indicators["task_length"] = 0.1
        
        # 特征 2: 动词数量（多语言）
        # 中文常见动作词
        chinese_verbs = ["读取", "写入", "修改", "删除", "创建", "生成", "分析", 
                        "搜索", "下载", "上传", "发送", "接收", "执行", "运行",
                        "编译", "构建", "部署", "测试", "检查", "验证", "转换",
                        "整理", "排序", "过滤", "合并", "拆分", "复制", "移动"]
        # 英文常见动作词
        english_verbs = ["read", "write", "modify", "delete", "create", "generate",
                        "analyze", "search", "download", "upload", "send", "receive",
                        "execute", "run", "compile", "build", "deploy", "test",
                        "check", "verify", "convert", "organize", "sort", "filter",
                        "merge", "split", "copy", "move", "get", "fetch", "process"]
        
        verb_count = sum(1 for v in chinese_verbs if v in task)
        verb_count += sum(1 for v in english_verbs if f" {v} " in f" {task_lower} ")
        
        if verb_count >= 4:
            indicators["verb_count"] = 1.0
        elif verb_count >= 2:
            indicators["verb_count"] = 0.6
        elif verb_count >= 1:
            indicators["verb_count"] = 0.3
        else:
            indicators["verb_count"] = 0.0
        
        # 特征 3: 时序连接词
        sequential_markers = ["先", "再", "然后", "之后", "接着", "最后", "第一步",
                             "第二步", "首先", "其次", "随后", "最终",
                             "first", "then", "next", "after", "finally", "step by step",
                             "一步一步", "分步", "按顺序"]
        seq_count = sum(1 for m in sequential_markers if m in task_lower)
        indicators["sequential_markers"] = min(seq_count * 0.3, 1.0)
        
        # 特征 4: 条件词
        conditional_markers = ["如果", "假如", "除非", "要是", "若",
                              "if", "unless", "when", "depending on", "based on"]
        cond_count = sum(1 for m in conditional_markers if m in task_lower)
        indicators["conditional_markers"] = min(cond_count * 0.3, 1.0)
        
        # 计算综合复杂度分数
        score = (
            indicators["task_length"] * 0.2 +
            indicators["verb_count"] * 0.35 +
            indicators["sequential_markers"] * 0.3 +
            indicators["conditional_markers"] * 0.15
        )
        
        # 高置信度判定 —— 复杂
        if indicators["sequential_markers"] >= 0.6:
            # 明确有时序依赖 → 高置信度复杂
            return ComplexityResult(
                is_complex=True,
                complexity_score=score,
                reasoning="检测到明确的时序依赖（先/再/然后等）",
                confidence=0.88,
                indicators=indicators,
            )
        
        # FIX: 降低阈值从 0.7 到 0.55，捕获中等复杂度任务
        if score > 0.55:
            return ComplexityResult(
                is_complex=True,
                complexity_score=score,
                reasoning="多维度指标显示任务有一定复杂度",
                confidence=0.80,
                indicators=indicators,
            )
        
        # 高置信度判定 —— 简单（更严格，避免误判中等复杂度任务）
        # 只有：极短文本 + 无任何动作/时序/条件特征 才判定为简单
        if len(task) < 20 and score < 0.05 and indicators["verb_count"] == 0:
            return ComplexityResult(
                is_complex=False,
                complexity_score=score,
                reasoning="极短问候/查询，无动作特征",
                confidence=0.9,
                indicators=indicators,
            )
        
        # 无法确定 → 降级到 LLM（宁可多调用一次 LLM，也不错判复杂任务为简单）
        return None
    
    async def _llm_complexity(self, task: str,
                              context: Dict[str, Any]) -> ComplexityResult:
        """调用 LLM 进行复杂度评估"""
        prompt = self.COMPLEXITY_PROMPT.format(task=task[:1000])
        
        if hasattr(self.llm, "chat"):
            response = await self.llm.chat([
                {"role": "system", "content": "你是一个任务分析专家，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ])
        else:
            response = await self.llm(prompt)
        
        return self._parse_complexity_response(response)
    
    def _parse_complexity_response(self, response: str) -> ComplexityResult:
        """解析复杂度评估的 JSON 响应"""
        try:
            json_str = response.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            
            data = json.loads(json_str)
            
            indicators = data.get("indicators", {})
            # 确保 indicators 是 Dict[str, float]
            indicators = {k: float(v) if isinstance(v, (int, float)) else 0.0 
                         for k, v in indicators.items()}
            
            return ComplexityResult(
                is_complex=data.get("is_complex", False),
                complexity_score=float(data.get("complexity_score", 0.5)),
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.5)),
                indicators=indicators,
            )
        except Exception as e:
            logger.warning(f"[Classifier] 解析复杂度响应失败: {e}")
            return self._default_complexity_result("解析失败")
    
    def _default_complexity_result(self, reasoning: str) -> ComplexityResult:
        """默认复杂度结果"""
        return ComplexityResult(
            is_complex=False,
            complexity_score=0.3,
            reasoning=reasoning,
            confidence=0.5,
            indicators={},
        )

    def _hash_task(self, task: str) -> str:
        """计算任务 hash（用于缓存）"""
        return hashlib.md5(task.encode("utf-8")).hexdigest()[:16]
