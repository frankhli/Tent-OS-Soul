"""Self Validator —— 自验证器

防止 LLM "幻觉完成"：在 Tool Loop 结束后，让 LLM 独立评估
任务是否真正完成，结果是否满足用户的原始需求。

核心设计：
1. 与 Generator（执行者）分离 —— 避免自评估偏见（Harness 模式）
2. 轻量级 prompt —— 成本可控，但能有效检测未完成任务
3. gradable 结果 —— completed + confidence，便于分级处理
4. 失败时给出具体原因和建议 —— 用户知道下一步怎么做

使用场景：
- Tool Loop 结束后（LLM 决定不再调用工具时）
- Plan-Execute 路径中每个步骤完成后
- 复杂任务完成后作为最终检查
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger("tent_os.self_validator")


@dataclass
class ValidationResult:
    """自验证结果"""
    completed: bool               # 任务是否完成
    confidence: float             # 置信度 0-1
    reasoning: str                # 判断理由
    suggestion: str               # 给用户的下一步建议
    missing_aspects: List[str] = None  # 未完成的方面
    
    def __post_init__(self):
        if self.missing_aspects is None:
            self.missing_aspects = []


class SelfValidator:
    """自验证器 —— 独立评估任务完成度
    
    两种模式：
    1. LLM 模式（推荐）：调用 LLM 进行深度评估，能处理主观判断
    2. 规则模式（回退）：基于启发式规则快速评估，零成本
    
    设计原则：
    - 宁可误报（认为没完成），也不要漏报（认为完成了实际没完成）
    - 评估 prompt 经过工程化，输出结构化 JSON
    """
    
    # 自验证 prompt 模板
    VALIDATOR_PROMPT = """你是一个严格的任务完成度检查员。你的工作是独立评估下面的对话是否真正完成了用户的原始任务。

【原始用户任务】
{task}

【对话历史摘要】
{history_summary}

【工具调用历史】（系统实际执行的操作记录）
{tool_history}

【系统的最终回复】
{response}

请从以下维度独立评估：
1. 用户的核心需求是否被满足？（不是有没有回复，而是回复是否解决了问题）
2. 如果任务需要数据/文件操作，查看【工具调用历史】中的实际操作记录，工具是否成功执行并产生了有效结果？
3. 系统是否在说"无法完成""需要更多信息"等推诿的话？
4. 系统是否在重复之前的尝试而没有进展？

重要：【工具调用历史】是系统实际执行操作的真实记录，不是系统自述。如果工具历史中显示 file_write 成功写入文件、file_read 成功读取内容，则任务确实已完成，即使系统的最终回复只是简短总结。

输出严格 JSON 格式：
{{
    "completed": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "具体判断理由（50字以内）",
    "missing_aspects": ["未完成的方面1", "未完成的方面2"],
    "suggestion": "给用户的具体下一步建议"
}}

判断标准：
- completed=true：任务确实完成了，用户可以满意
- completed=false：任务未完成、部分完成、或系统只是在"假装完成"
- confidence：你对判断的确定程度（不是任务完成度）"""

    def __init__(self, llm=None,
                 min_confidence_threshold: float = 0.92,
                 enable_llm: bool = True):
        """
        Args:
            llm: LLM 实例（需支持 chat 或 complete 方法）
            min_confidence_threshold: 判定"未完成"的最小置信度阈值
            enable_llm: 是否启用 LLM 深度评估（false 时只用规则评估）
        """
        self.llm = llm
        self.min_confidence_threshold = min_confidence_threshold
        self.enable_llm = enable_llm
    
    async def validate(self, task: str, conversation_history: List[Dict],
                       response: str, task_type: str = "chat",
                       tool_history: List[Dict] = None) -> ValidationResult:
        """执行自验证
        
        Args:
            task: 用户的原始任务
            conversation_history: 对话历史（取最近 N 条）
            response: 系统的最终回复
            task_type: 任务类型（chat | tool_loop | plan_execute）
        
        Returns:
            ValidationResult
        """
        # 1. 先进行规则评估（零成本快速路径）
        rule_result = self._rule_based_validate(task, response, task_type, tool_history)
        
        # 如果规则评估明确判定为未完成，直接返回（节省 LLM 调用）
        if not rule_result.completed and rule_result.confidence >= 0.85:
            logger.info(f"[VALIDATOR] 规则评估判定未完成（高置信度）: {rule_result.reasoning}")
            return rule_result
        
        # 2. 如果启用了 LLM，进行深度评估
        if self.enable_llm and self.llm:
            try:
                llm_result = await self._llm_validate(task, conversation_history, response, tool_history)
                # 合并结果：取更严格的（宁可误报）
                return self._merge_results(rule_result, llm_result)
            except Exception as e:
                logger.warning(f"[VALIDATOR] LLM 评估失败，回退到规则评估: {e}")
                return rule_result
        
        return rule_result
    
    def _has_structured_result(self, response: str) -> bool:
        """检测回复中是否包含结构化结果（表格、列表、文件路径、JSON等）"""
        # 表格标记（Markdown 表格）
        if "|" in response and "---" in response:
            return True
        # 列表标记
        if "\n- " in response or "\n• " in response or "\n* " in response:
            return True
        # 文件路径（包含 / 或 . 的模式）
        import re
        if re.search(r'`[^`]+\.(txt|md|json|py|js|ts|html|css|yaml|yml)`', response):
            return True
        if re.search(r'[\w\-]+\.(txt|md|json|py|js|ts|html|css|yaml|yml)\b', response):
            return True
        # 代码块
        if "```" in response:
            return True
        # JSON 对象
        if re.search(r'"\w+":\s*"', response) and ("{" in response or "[" in response):
            return True
        return False
    
    def _is_chat_task(self, task: str) -> bool:
        """判断是否为简单聊天/问候任务"""
        if not task:
            return False
        chat_keywords = ["你好", "hello", "hi", "hey", "在吗", "在不在", "怎么样", "好吗"]
        task_lower = task.lower()
        return any(kw in task_lower for kw in chat_keywords) and len(task) < 30
    
    def _rule_based_validate(self, task: str, response: str,
                              task_type: str,
                              tool_history: List[Dict] = None) -> ValidationResult:
        """规则评估 —— 零成本、确定性、<1ms
        
        检测明显的"未完成"信号：
        """
        response_lower = response.lower()
        task_lower = task.lower()
        
        # === 信号 1: 明确的未完成声明 ===
        # FIX: 使用单词边界匹配，避免前导空格导致的漏检
        # FIX v2: 移除中性科学/伦理词汇（"随机性"、"概率"是科学解释，不是推诿）
        incomplete_signals = [
            "无法完成", "不能完成", "做不到", "没有权限", "无法访问",
            "failed", "cannot", "unable to", "don't have permission",
            "exceeded", "timeout", "超时", "超出限制",
        ]
        for signal in incomplete_signals:
            # 用前后空格或标点作为单词边界，避免子串误匹配
            padded_signal = f" {signal} "
            if signal in response_lower or padded_signal in f" {response_lower} ":
                return ValidationResult(
                    completed=False,
                    confidence=0.90,
                    reasoning=f"检测到明确的未完成信号: '{signal}'",
                    suggestion="系统表示无法完成任务。建议检查权限、路径是否正确，或简化任务目标。",
                    missing_aspects=["任务未执行或被拒绝"],
                )
        
        # === 信号 1b: 检测到真诚的"我不知道"应视为诚实而非未完成 ===
        # 如果回复明确说明"记忆中没有记录"且诚实说明原因，不视为未完成
        honest_unknown_patterns = [
            "记忆中没有", "没有相关记录", "我没有找到", "不记得",
            "没有提过", "未曾提及", "无法回忆起",
        ]
        for pattern in honest_unknown_patterns:
            if pattern in response_lower:
                # 诚实承认不知道 = 完成任务（告诉了用户真相）
                return ValidationResult(
                    completed=True,
                    confidence=0.85,
                    reasoning=f"系统诚实说明记忆中没有相关记录，这是正确的回答",
                    suggestion="",
                )
        
        # === 信号 2: 循环/重复声明 ===
        loop_signals = [
            "再次尝试", "再试一次", "让我再", "重新",
            "仍然", "还是", "again", "retry", "try again",
        ]
        loop_count = sum(1 for s in loop_signals if s in response_lower)
        if loop_count >= 2:
            return ValidationResult(
                completed=False,
                confidence=0.80,
                reasoning="检测到多次重试/重复尝试的语言模式",
                suggestion="系统似乎陷入了重试循环。建议换一种方式描述任务，或检查相关资源是否可用。",
                missing_aspects=["任务执行受阻"],
            )
        
        # === 信号 3: 纯问题/反问（没有给出结果）===
        # FIX: 对聊天/问候任务放宽检测。简单社交任务以问题结尾是正常的。
        # FIX: 如果回复中已包含结构化结果（表格、列表、文件路径），
        #      即使以问题结尾也是正常完成——最后的询问是礼貌性的。
        # FIX v2: 伦理拒绝类回复（"属于独立随机事件","不存在科学依据"）以问题结尾是正常完成
        stripped = response.strip()
        is_chat_task = self._is_chat_task(task)
        has_structured_result = self._has_structured_result(response)
        is_ethical_refusal = "科学依据" in response or "伪科学" in response or "独立随机" in response or "欺诈" in response
        
        if stripped.endswith("?") or stripped.endswith("？"):
            # 聊天任务以问题结尾 → 正常完成
            if is_chat_task:
                return ValidationResult(
                    completed=True,
                    confidence=0.80,
                    reasoning="聊天/问候任务，以礼貌询问结尾是正常完成",
                    suggestion="",
                )
            # 伦理拒绝以问题结尾 → 正常完成
            if is_ethical_refusal:
                return ValidationResult(
                    completed=True,
                    confidence=0.90,
                    reasoning="伦理拒绝类回复，末尾询问是礼貌性收尾",
                    suggestion="",
                )
            # 已提供结构化结果 + 以问题结尾 → 正常完成，最后询问是礼貌性的
            if has_structured_result:
                return ValidationResult(
                    completed=True,
                    confidence=0.85,
                    reasoning="回复已包含结构化结果（表格/列表/文件路径），末尾询问是礼貌性收尾",
                    suggestion="",
                )
            # 非聊天任务，回复很短（<30字）且只包含问题 → 高置信度未完成
            if len(stripped) < 30:
                return ValidationResult(
                    completed=False,
                    confidence=0.85,
                    reasoning="回复极短且以问题结尾，没有提供实质内容",
                    suggestion="系统只问了问题但没有提供结果。请直接提供所需信息。",
                    missing_aspects=["系统未提供结果，只提出了问题"],
                )
            # 较长的回复以问题结尾 → 低置信度标记（不应直接alert用户）
            return ValidationResult(
                completed=False,
                confidence=0.55,
                reasoning="回复以问题结尾",
                suggestion="",
                missing_aspects=["回复以问题结尾"],
            )
        
        # === 信号 4: 空结果或极短结果 ===
        if len(response.strip()) < 20:
            return ValidationResult(
                completed=False,
                confidence=0.75,
                reasoning="回复内容过短，可能没有实质结果",
                suggestion="系统返回了极短的回复。建议确认任务是否被执行，或提供更多上下文。",
                missing_aspects=["回复内容不足"],
            )
        
        # === 信号 4.5: 承诺执行但未执行（说空话）===
        # LLM 说"我要排查/检查/看看"但没有任何工具调用记录 → 假完成
        promise_markers = ["我要", "我会", "让我", "我来", "我先", "我一步步"]
        execution_markers = ["已完成", "已经", "已修复", "已创建", "已写入", "已生成", "成功", "结果", "文件"]
        has_promise = any(m in response for m in promise_markers)
        has_execution = any(m in response for m in execution_markers)
        if has_promise and not has_execution:
            # 检查是否有工具调用历史
            has_tools = tool_history and len(tool_history) > 0
            if not has_tools:
                return ValidationResult(
                    completed=False,
                    confidence=0.88,
                    reasoning="系统承诺执行操作（'我要/让我/我先...'）但没有任何工具调用记录，属于'说空话'",
                    suggestion="系统只说要做但实际上没有执行任何操作。请明确要求系统直接执行，不要只描述计划。",
                    missing_aspects=["承诺的操作未实际执行"],
                )
        
        # === 信号 5: 明确的完成声明 ===
        complete_signals = [
            "已完成", "已经为您", "任务完成", "成功",
            " done", " completed", " successfully", " finished",
            "✅", "✓", "完成",
        ]
        for signal in complete_signals:
            if signal in response_lower:
                return ValidationResult(
                    completed=True,
                    confidence=0.70,  # 规则评估的置信度不高，需要 LLM 确认
                    reasoning=f"检测到完成信号: '{signal}'",
                    suggestion="",
                )
        
        # 默认：无法确定，交给 LLM 评估
        return ValidationResult(
            completed=True,
            confidence=0.50,
            reasoning="规则评估无法确定，需要 LLM 深度评估",
            suggestion="",
        )
    
    async def _llm_validate(self, task: str, conversation_history: List[Dict],
                            response: str,
                            tool_history: List[Dict] = None) -> ValidationResult:
        """LLM 深度评估"""
        # 构建对话摘要（最近 10 条消息，限制总长度）
        history_summary = self._summarize_history(conversation_history)
        
        # 构建工具历史摘要
        tool_history_text = ""
        if tool_history:
            lines = []
            for idx, th in enumerate(tool_history, 1):
                tool_name = th.get("tool", "unknown")
                args = th.get("args", {})
                result = th.get("result", "unknown")
                error_msg = th.get("error_msg", "")
                args_str = json.dumps(args, ensure_ascii=False)[:100]
                if result == "error":
                    lines.append(f"{idx}. {tool_name}({args_str}) → 失败: {error_msg[:80]}")
                elif result == "approval_needed":
                    lines.append(f"{idx}. {tool_name}({args_str}) → 需要审批")
                else:
                    lines.append(f"{idx}. {tool_name}({args_str}) → 成功")
            tool_history_text = "\n".join(lines)
        else:
            tool_history_text = "（无工具调用记录）"
        
        prompt = self.VALIDATOR_PROMPT.format(
            task=task[:500],
            history_summary=history_summary[:2000],
            tool_history=tool_history_text[:1500],
            response=response[:2000],
        )
        
        # 调用 LLM
        if hasattr(self.llm, 'chat'):
            llm_response = await self.llm.chat([
                {"role": "system", "content": "你是一个严格的任务完成度检查员。"},
                {"role": "user", "content": prompt}
            ])
        elif hasattr(self.llm, 'complete'):
            llm_response = await self.llm.complete(prompt)
        else:
            llm_response = await self.llm(prompt)
        
        # 解析 JSON
        try:
            data = json.loads(llm_response)
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON
            data = self._extract_json(llm_response)
        
        completed = data.get("completed", True)
        confidence = float(data.get("confidence", 0.5))
        reasoning = data.get("reasoning", "")
        missing_aspects = data.get("missing_aspects", []) or []
        suggestion = data.get("suggestion", "")
        
        logger.info(f"[VALIDATOR] LLM 评估: completed={completed}, confidence={confidence:.2f}, reasoning={reasoning[:80]}")
        
        return ValidationResult(
            completed=completed,
            confidence=confidence,
            reasoning=reasoning,
            suggestion=suggestion,
            missing_aspects=missing_aspects if isinstance(missing_aspects, list) else [],
        )
    
    def _merge_results(self, rule: ValidationResult, llm: ValidationResult) -> ValidationResult:
        """合并规则和 LLM 评估结果 —— 取更严格的"""
        # 如果任何一方认为未完成，就判定为未完成
        completed = rule.completed and llm.completed
        
        # 如果判定为未完成，取更高的置信度
        if not completed:
            confidence = max(rule.confidence, llm.confidence)
            # 优先使用给出具体原因的评估
            if not rule.completed and rule.reasoning:
                reasoning = f"[规则] {rule.reasoning}"
                suggestion = rule.suggestion or llm.suggestion
                missing = rule.missing_aspects or llm.missing_aspects
            else:
                reasoning = f"[LLM] {llm.reasoning}"
                suggestion = llm.suggestion or rule.suggestion
                missing = llm.missing_aspects or rule.missing_aspects
        else:
            # 双方都认为是完成的，取较低置信度（更保守）
            confidence = min(rule.confidence, llm.confidence)
            reasoning = f"[规则] {rule.reasoning}; [LLM] {llm.reasoning}"
            suggestion = ""
            missing = []
        
        return ValidationResult(
            completed=completed,
            confidence=confidence,
            reasoning=reasoning,
            suggestion=suggestion,
            missing_aspects=missing,
        )
    
    def _summarize_history(self, history: List[Dict], max_chars: int = 1500) -> str:
        """ summarize 对话历史 """
        lines = []
        total = 0
        # 从后往前取，保留最近的
        for msg in reversed(history[-20:]):
            role = msg.get("role", "unknown")
            content = str(msg.get("content", ""))[:200]
            line = f"{role}: {content}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        return "\n".join(reversed(lines))
    
    def _extract_json(self, text: str) -> Dict:
        """从文本中提取 JSON 对象"""
        # 尝试找花括号包裹的内容
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {}
    
    def should_alert_user(self, result: ValidationResult) -> bool:
        """判断是否需要向用户发出未完成警报
        
        FIX v2: 大幅提高阈值，只有极高置信度（>=0.92）且确实未完成的才提醒。
        日常对话中的"未完成"（如以问题结尾）不应打扰用户。
        """
        if result.completed:
            return False
        # 未完成 + 极高置信度 → 提醒用户
        return result.confidence >= self.min_confidence_threshold
    
    def format_alert(self, result: ValidationResult) -> str:
        """格式化用户警报消息
        
        FIX v2: 返回空字符串。自验证结果只记录内部日志，不向用户展示。
        避免污染用户体验和记忆系统。
        """
        return ""
