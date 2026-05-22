"""Procedural Memory —— 程序记忆系统

让 Tent OS 从经验中学习：
1. 评估器发现失败/低分 → 提取行为规则
2. 规则入库（SQLite）
3. 下次规划前，自动检索相关规则注入 prompt
4. 规则随使用反馈自动调整置信度

数据模型（程序记忆 = 如何做对的规则）：
- trigger_condition: 什么情况下触发这条规则
- action_rule: 应该采取什么行动（或避免什么）
- source_experience: 从哪次失败/成功中提取的
- confidence: 置信度（0-1），随验证结果调整
- success_count/failure_count: 应用后的成功/失败次数
"""

import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


@dataclass
class ProceduralRule:
    """单条程序记忆规则"""
    id: Optional[int]
    trigger_condition: str       # 触发条件描述（如"执行文件删除操作前"）
    action_rule: str             # 行为规则（如"必须先备份到 /tmp/backup"）
    category: str                # 分类：safety / efficiency / correctness / quality
    source_experience: str       # 来源经验摘要
    confidence: float            # 置信度 0-1
    success_count: int
    failure_count: int
    created_at: str
    last_applied: Optional[str]


class ProceduralMemoryStore:
    """程序记忆存储 —— SQLite 持久化"""

    def __init__(self, db_path: str = "./tent_memory/procedural.db",
                 embedding_model: callable = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.embedding_model = embedding_model
        self._init_db()

    def _init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS procedural_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_condition TEXT NOT NULL,
                action_rule TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'correctness',
                source_experience TEXT,
                confidence REAL DEFAULT 0.5,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                last_applied TEXT,
                embedding TEXT  -- 简单关键词向量（逗号分隔关键词）
            )
        """)
        # 索引：按分类和置信度查询
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_proc_category_confidence
            ON procedural_rules(category, confidence DESC)
        """)
        self.db.commit()

    def add_rule(
        self,
        trigger_condition: str,
        action_rule: str,
        category: str = "correctness",
        source_experience: str = "",
        confidence: float = 0.5,
    ) -> int:
        """添加新规则，返回 rule_id（sync 安全）"""
        # 使用同步关键词提取（避免在 sync 方法中调用 async _compute_embedding）
        keywords = self._extract_keywords(trigger_condition + " " + action_rule)
        embedding = ",".join(keywords)

        cursor = self.db.execute(
            """INSERT INTO procedural_rules
               (trigger_condition, action_rule, category, source_experience,
                confidence, success_count, failure_count, embedding)
               VALUES (?, ?, ?, ?, ?, 0, 0, ?)""",
            (trigger_condition, action_rule, category, source_experience,
             confidence, embedding),
        )
        self.db.commit()
        return cursor.lastrowid
    
    async def _compute_embedding(self, text: str) -> str:
        """计算文本的 embedding 表示（async 安全）。
        
        有 embedding_model 时返回 JSON 序列化的向量，
        无 model 时返回逗号分隔的关键词（兼容旧数据）。
        """
        if self.embedding_model:
            try:
                vec = self.embedding_model(text)
                # 处理 async embedding
                if hasattr(vec, '__await__'):
                    vec = await vec
                if vec:
                    return json.dumps(vec)
            except Exception as e:
                logger = logging.getLogger("tent_os.memory")
                logger.debug(f"规则 embedding 计算失败，降级到关键词: {e}")
        
        # 降级：关键词
        keywords = self._extract_keywords(text)
        return ",".join(keywords)

    async def find_relevant(self, task_query: str, category: Optional[str] = None,
                      min_confidence: float = 0.3, limit: int = 5) -> List[ProceduralRule]:
        """根据任务查询检索相关规则（async 安全）。
        
        优先使用语义 embedding 相似度，无 embedding 时回退到关键词匹配。
        """
        # 构建查询
        if category:
            rows = self.db.execute(
                """SELECT * FROM procedural_rules
                   WHERE category = ? AND confidence >= ?
                   ORDER BY confidence DESC""",
                (category, min_confidence),
            ).fetchall()
        else:
            rows = self.db.execute(
                """SELECT * FROM procedural_rules
                   WHERE confidence >= ?
                   ORDER BY confidence DESC""",
                (min_confidence,),
            ).fetchall()
        
        if not rows:
            return []
        
        # 判断是否有语义 embedding（JSON 数组格式）
        has_semantic = self.embedding_model is not None
        query_vec = None
        if has_semantic:
            query_vec = await self._compute_query_vector(task_query)
        
        scored = []
        for row in rows:
            embedding_str = row["embedding"] or ""
            
            if has_semantic and embedding_str.startswith("["):
                # 语义相似度模式
                try:
                    rule_vec = json.loads(embedding_str)
                    sim = self._cosine_similarity(query_vec, rule_vec) if query_vec else 0.0
                except (json.JSONDecodeError, TypeError):
                    sim = 0.0
                # 综合分数 = 语义相似度 * 0.6 + 置信度 * 0.4
                combined = sim * 0.6 + row["confidence"] * 0.4
            else:
                # 关键词匹配模式（兼容旧数据 / 无 embedding_model）
                query_keywords = set(self._extract_keywords(task_query))
                rule_keywords = set(embedding_str.split(",")) if embedding_str else set()
                match_score = len(query_keywords & rule_keywords) / max(len(query_keywords), 1)
                combined = match_score * 0.5 + row["confidence"] * 0.5
            
            scored.append((combined, row))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        results = []
        for _, row in scored[:limit]:
            results.append(ProceduralRule(
                id=row["id"],
                trigger_condition=row["trigger_condition"],
                action_rule=row["action_rule"],
                category=row["category"],
                source_experience=row["source_experience"],
                confidence=row["confidence"],
                success_count=row["success_count"],
                failure_count=row["failure_count"],
                created_at=row["created_at"],
                last_applied=row["last_applied"],
            ))
        return results
    
    async def _compute_query_vector(self, text: str) -> Optional[List[float]]:
        """计算查询文本的 embedding 向量（async 安全）"""
        if not self.embedding_model:
            return None
        try:
            vec = self.embedding_model(text)
            if hasattr(vec, '__await__'):
                vec = await vec
            return vec
        except Exception:
            return None
    
    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """计算两个向量的余弦相似度"""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def record_outcome(self, rule_id: int, success: bool):
        """记录规则应用结果，更新置信度"""
        if success:
            self.db.execute(
                """UPDATE procedural_rules
                   SET success_count = success_count + 1,
                       confidence = min(0.99, confidence + 0.05),
                       last_applied = datetime('now')
                   WHERE id = ?""",
                (rule_id,),
            )
        else:
            self.db.execute(
                """UPDATE procedural_rules
                   SET failure_count = failure_count + 1,
                       confidence = max(0.1, confidence - 0.1),
                       last_applied = datetime('now')
                   WHERE id = ?""",
                (rule_id,),
            )
        self.db.commit()

    def get_all_rules(self) -> List[ProceduralRule]:
        """获取所有规则（用于管理界面）"""
        rows = self.db.execute(
            "SELECT * FROM procedural_rules ORDER BY confidence DESC"
        ).fetchall()
        return [
            ProceduralRule(
                id=r["id"],
                trigger_condition=r["trigger_condition"],
                action_rule=r["action_rule"],
                category=r["category"],
                source_experience=r["source_experience"],
                confidence=r["confidence"],
                success_count=r["success_count"],
                failure_count=r["failure_count"],
                created_at=r["created_at"],
                last_applied=r["last_applied"],
            )
            for r in rows
        ]

    def delete_rule(self, rule_id: int):
        """删除规则"""
        self.db.execute("DELETE FROM procedural_rules WHERE id = ?", (rule_id,))
        self.db.commit()

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """提取关键词（简单实现：中文分词 + 英文单词）"""
        # 英文单词
        words = re.findall(r'[a-zA-Z_]+', text.lower())
        # 中文字符（简单按字提取）
        chinese = re.findall(r'[\u4e00-\u9fff]', text)
        return words + chinese


class ExperienceExtractor:
    """经验提取器 —— 从评估结果中提取行为规则"""

    def __init__(self, llm=None):
        self.llm = llm

    async def extract_from_evaluation(
        self,
        task: str,
        plan: Dict,
        result: Dict,
        evaluation: Dict,
    ) -> Optional[ProceduralRule]:
        """从评估结果中提取程序记忆规则

        只有评估失败或低分时才提取。
        返回一条规则，或 None（如果没有可提取的）。
        """
        # 快速路径：如果评估通过且分数高，不提取
        if evaluation.get("passed") and evaluation.get("overall_score", 0) > 0.7:
            return None

        if self.llm is None:
            # 无 LLM 时的简单规则提取
            return self._rule_based_extract(task, plan, result, evaluation)

        # LLM 深度提取
        return await self._llm_extract(task, plan, result, evaluation)

    def _rule_based_extract(
        self, task: str, plan: Dict, result: Dict, evaluation: Dict
    ) -> Optional[ProceduralRule]:
        """基于规则的简单提取（无 LLM 时的降级方案）"""
        dim_scores = evaluation.get("criteria_scores", {})

        # safety 失败 → 安全规则
        if dim_scores.get("safety", 1.0) < 0.5:
            return ProceduralRule(
                id=None,
                trigger_condition=f"执行任务涉及: {task[:50]}",
                action_rule="执行前必须通过 PolicyEngine 安全审查，涉及删除/修改操作需人工确认",
                category="safety",
                source_experience=f"任务失败: safety评分低",
                confidence=0.6,
                success_count=0,
                failure_count=0,
                created_at=datetime.now().isoformat(),
                last_applied=None,
            )

        # correctness 失败 → 正确性规则
        if dim_scores.get("correctness", 1.0) < 0.5:
            return ProceduralRule(
                id=None,
                trigger_condition=f"类似任务: {task[:50]}",
                action_rule="执行前增加验证步骤，确保结果符合预期后再标记完成",
                category="correctness",
                source_experience=f"任务失败: 结果不正确",
                confidence=0.5,
                success_count=0,
                failure_count=0,
                created_at=datetime.now().isoformat(),
                last_applied=None,
            )

        return None

    async def _llm_extract(
        self, task: str, plan: Dict, result: Dict, evaluation: Dict
    ) -> Optional[ProceduralRule]:
        """使用 LLM 提取行为规则"""
        prompt = f"""分析以下任务执行经验，提取一条"程序记忆规则"——即下次遇到类似情况时应该怎么做。

任务：{task}
执行方案：{json.dumps(plan, ensure_ascii=False)}
执行结果：{json.dumps(result, ensure_ascii=False)}
评估结果：{json.dumps(evaluation, ensure_ascii=False)}

请提取一条简洁的行为规则，格式如下：
- trigger_condition: 什么情况下触发（简洁描述）
- action_rule: 应该采取什么行动（具体、可操作）
- category: 分类（safety/correctness/efficiency/quality 之一）

如果无法提取有效规则，回复"无"。"""

        try:
            llm_messages = [
                {"role": "system", "content": "你是一个经验提炼助手，从任务执行经验中提取可复用的行为规则。"},
                {"role": "user", "content": prompt}
            ]
            response = await self.llm.chat(llm_messages)
            if "无" in response or not response.strip():
                return None

            # 简单解析 LLM 输出
            trigger = self._extract_field(response, "trigger_condition")
            action = self._extract_field(response, "action_rule")
            category = self._extract_field(response, "category") or "correctness"

            if not trigger or not action:
                return None

            return ProceduralRule(
                id=None,
                trigger_condition=trigger[:200],
                action_rule=action[:500],
                category=category,
                source_experience=f"任务: {task[:100]}",
                confidence=0.5,  # 新规则初始置信度
                success_count=0,
                failure_count=0,
                created_at=datetime.now().isoformat(),
                last_applied=None,
            )
        except Exception:
            return None

    async def extract_from_chat(
        self,
        messages: List[Dict],
        response: str,
    ) -> Optional[ProceduralRule]:
        """从对话中提取经验规则
        
        在每次对话完成后自动调用，从对话内容中提炼可复用的规则。
        """
        if self.llm is None:
            return None
        
        # 构建对话摘要
        dialogue = []
        for m in messages[-6:]:  # 最近6条
            role = m.get("role", "")
            content = m.get("content", "")[:200]
            dialogue.append(f"{role}: {content}")
        dialogue_text = "\n".join(dialogue)
        
        prompt = f"""分析以下对话，判断是否有值得记住的经验规则。

对话：
{dialogue_text}

AI回复：
{response[:300]}

如果有以下类型的规则值得提取，请输出：
- trigger_condition: 什么情况下触发（简洁描述）
- action_rule: 应该采取什么行动
- category: 分类（safety/correctness/efficiency/quality/preference 之一）

如果没有值得提取的规则，回复"无"。"""
        
        try:
            # 使用 llm.chat 而不是 llm.complete
            llm_messages = [
                {"role": "system", "content": "你是一个经验提炼助手，从对话中提取可复用的行为规则。"},
                {"role": "user", "content": prompt}
            ]
            resp = await self.llm.chat(llm_messages)
            if "无" in resp or not resp.strip():
                return None
            
            trigger = self._extract_field(resp, "trigger_condition")
            action = self._extract_field(resp, "action_rule")
            category = self._extract_field(resp, "category") or "preference"
            
            if not trigger or not action:
                return None
            
            return ProceduralRule(
                id=None,
                trigger_condition=trigger[:200],
                action_rule=action[:500],
                category=category,
                source_experience=f"对话提炼",
                confidence=0.4,  # 对话提炼的置信度较低
                success_count=0,
                failure_count=0,
                created_at=datetime.now().isoformat(),
                last_applied=None,
            )
        except Exception:
            return None

    @staticmethod
    def _extract_field(text: str, field_name: str) -> Optional[str]:
        """从 LLM 输出中提取字段值"""
        patterns = [
            rf"{field_name}[\s:：]+(.+?)(?:\n|$)",
            rf"-?\s*{field_name}[\s:：]+(.+?)(?:\n|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None


class ProceduralMemoryInjector:
    """程序记忆注入器 —— 在规划前将相关规则注入上下文"""

    def __init__(self, store: ProceduralMemoryStore, max_rules: int = 3):
        self.store = store
        self.max_rules = max_rules

    async def render_rules(self, task_query: str) -> str:
        """渲染相关规则为 prompt 文本（async 安全）"""
        rules = await self.store.find_relevant(task_query, limit=self.max_rules)
        if not rules:
            return ""

        lines = ["\n📋 程序记忆（从过往经验中学习到的规则）："]
        for i, rule in enumerate(rules, 1):
            lines.append(f"  {i}. [{rule.category.upper()}] 当{rule.trigger_condition}时，{rule.action_rule}")
            lines.append(f"     (置信度: {rule.confidence:.0%}, 验证: {rule.success_count}成功/{rule.failure_count}失败)")

        return "\n".join(lines)
