"""人格画像生成器 —— 使用LLM深度分析用户对话，生成自然语言描述的人格配置文件

核心设计：
- 不是数值打分，而是自然语言描述
- 增量更新：每次对话后更新人格画像
- 不完美保留：保留用户的"缺陷"作为人格完整性的一部分
- 不知道的权利：记录用户明确说"不知道"的话题领域

输出格式（Persona Profile）是一份可直接注入System Prompt的自然语言文档。
"""

import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class PersonaProfile:
    """人格配置文件 —— 自然语言描述的用户画像"""
    
    user_id: str
    
    # === 基本信息 ===
    name: str = ""                  # 用户真实姓名
    ai_name: str = ""               # AI 昵称（用户给AI起的名字）
    age: int = 0                     # 年龄
    gender: str = ""                 # 性别
    occupation: str = ""             # 职业
    location: str = ""               # 所在地
    hometown: str = ""               # 家乡
    education: str = ""              # 教育背景
    bio: str = ""                    # 个人简介
    
    # === 语言风格 ===
    language_style: str = ""           # "喜欢用短句，生气时句子更短；经常说'说实话'、'我觉得吧'..."
    sentence_pattern: str = ""         # "短句为主，平均15字一句；疑问句多，反问句少..."
    humor_style: str = ""              # "自嘲型幽默，偶尔冷笑话，不擅长讽刺..."
    catchphrases: str = "[]"           # JSON list: ["口头禅1", "口头禅2"]
    speaking_quirks: str = "[]"        # JSON list: ["紧张时重复用词", "思考时说'嗯——'"]
    
    # === 思维模式 ===
    decision_pattern: str = ""         # "做决定前习惯先列出所有风险；涉及家庭的决策更谨慎..."
    thinking_depth: str = ""           # "表面随和，但对核心问题思考深入；习惯类比推理..."
    argument_style: str = ""           # "被反驳时先沉默再回应；喜欢用反问引导对方思考..."
    
    # === 情感模式 ===
    emotion_pattern: str = ""          # "对工作话题容易焦虑；对家庭话题更温和..."
    stress_response: str = ""          # "压力大时话变少，喜欢一个人待着；恢复后会主动沟通..."
    joy_expression: str = ""           # "开心时不张扬，但会用具体行动表达；比如请你吃饭..."
    
    # === 价值观 ===
    core_values: str = "[]"            # JSON list: ["家庭第一", "诚实守信", "持续学习"]
    value_conflicts: str = ""          # "当家庭和工作冲突时，通常选择家庭；但不会说破..."
    
    # === 关系模式 ===
    relationship_style: str = ""       # "对配偶更亲密但不善表达；对子女严格但暗中关心..."
    social_energy: str = ""            # "内向但不孤僻；小圈子深度交往，不喜欢大型聚会..."
    
    # === 不完美（人格完整性）===
    imperfections: str = "[]"          # JSON list: ["偶尔会跑题", "纠结措辞", "说'那个那个'"]
    blind_spots: str = "[]"            # JSON list: ["对新技术接受慢", "不太会拒绝别人"]
    
    # === 边界与诚实 ===
    unknown_topics: str = "[]"         # JSON list: ["不熟悉的领域会直接说不知道", "不问子女隐私"]
    taboo_topics: str = "[]"           # JSON list: ["不谈论前任", "不谈收入"]
    
    # === 成长轨迹 ===
    growth_notes: str = ""             # "从对话中观察到的变化：2026年3月开始更关注健康..."
    life_phases: str = ""              # "当前处于'事业稳定期+家庭重心期'的叠加阶段..."
    
    # === 口语化风格量化（去AI化的核心参数）===
    oral_style: str = "{}"             # JSON: {avg_sentence_length, comma_ratio, filler_words, ...}
    
    # === 元数据 ===
    conversation_count: int = 0        # 基于多少轮对话生成
    last_analyzed_session: str = ""    # 最后分析的session_id
    updated_at: str = ""
    created_at: str = ""
    
    # === 死亡事件分界 ===
    # 标记用户是否已离世。一旦设置，所有 death_event 之后的对话不再用于人格分析
    # 格式: ISO 8601 时间字符串，如 "2024-01-15T10:30:00"
    death_event: str = ""              # 空字符串表示未设置
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def get_catchphrases(self) -> List[str]:
        try:
            return json.loads(self.catchphrases)
        except Exception:
            return []
    
    def get_speaking_quirks(self) -> List[str]:
        try:
            return json.loads(self.speaking_quirks)
        except Exception:
            return []
    
    def get_core_values(self) -> List[str]:
        try:
            return json.loads(self.core_values)
        except Exception:
            return []
    
    def get_imperfections(self) -> List[str]:
        try:
            return json.loads(self.imperfections)
        except Exception:
            return []
    
    def get_blind_spots(self) -> List[str]:
        try:
            return json.loads(self.blind_spots)
        except Exception:
            return []
    
    def get_unknown_topics(self) -> List[str]:
        try:
            return json.loads(self.unknown_topics)
        except Exception:
            return []
    
    def get_taboo_topics(self) -> List[str]:
        try:
            return json.loads(self.taboo_topics)
        except Exception:
            return []
    
    def get_oral_style(self) -> Dict[str, Any]:
        try:
            return json.loads(self.oral_style)
        except Exception:
            return {}
    
    def to_system_prompt_text(self) -> str:
        """将人格配置文件转换为可直接注入System Prompt的文本"""
        lines = ["【人格画像 —— 以下是对你最真实的描述，请完全代入这个角色】", ""]
        
        if self.language_style:
            lines.append(f"【说话方式】{self.language_style}")
        if self.sentence_pattern:
            lines.append(f"【句式习惯】{self.sentence_pattern}")
        if self.humor_style:
            lines.append(f"【幽默风格】{self.humor_style}")
        
        catchphrases = self.get_catchphrases()
        if catchphrases:
            lines.append(f"【口头禅】你经常挂在嘴边的话：{'、'.join(catchphrases[:10])}")
        
        quirks = self.get_speaking_quirks()
        if quirks:
            lines.append(f"【说话的小习惯】{'；'.join(quirks[:8])}")
        
        # 口语化量化参数 —— 让LLM知道具体数字，而非模糊描述
        oral = self.get_oral_style()
        if oral and oral.get("avg_sentence_length"):
            lines.append("")
            lines.append("【口语风格数据 —— 你必须严格遵守这些数字】")
            lines.append(f"  · 平均每句{oral.get('avg_sentence_length', 15):.0f}个字")
            lines.append(f"  · {'喜欢' if oral.get('comma_ratio', 0.5) > 0.6 else '不喜欢' if oral.get('comma_ratio', 0.5) < 0.4 else '偶尔'}用长句一口气说完")
            fillers = oral.get("filler_words", {})
            if fillers:
                top_fillers = sorted(fillers.items(), key=lambda x: x[1], reverse=True)[:3]
                lines.append(f"  · 常用语气词：{', '.join([f'{w}({int(v*100)}%)' for w, v in top_fillers])}")
            if oral.get("question_ratio", 0) > 0.3:
                lines.append(f"  · 喜欢反问（{int(oral['question_ratio']*100)}%的概率）")
            if oral.get("ellipsis_ratio", 0) > 0.1:
                lines.append(f"  · 说话时常停顿、犹豫")
            opens = oral.get("opening_words", {})
            if opens:
                top_open = sorted(opens.items(), key=lambda x: x[1], reverse=True)[:2]
                lines.append(f"  · 常用开头：{'、'.join([w for w, _ in top_open])}")
        
        lines.append("")
        
        if self.decision_pattern:
            lines.append(f"【做决定的方式】{self.decision_pattern}")
        if self.thinking_depth:
            lines.append(f"【思考特点】{self.thinking_depth}")
        if self.argument_style:
            lines.append(f"【被反驳时的反应】{self.argument_style}")
        
        lines.append("")
        
        if self.emotion_pattern:
            lines.append(f"【情绪模式】{self.emotion_pattern}")
        if self.stress_response:
            lines.append(f"【压力大时的表现】{self.stress_response}")
        if self.joy_expression:
            lines.append(f"【开心时的表现】{self.joy_expression}")
        
        lines.append("")
        
        values = self.get_core_values()
        if values:
            lines.append(f"【核心价值观】{'、'.join(values[:8])}")
        if self.value_conflicts:
            lines.append(f"【价值取舍】{self.value_conflicts}")
        
        if self.relationship_style:
            lines.append(f"【对待关系的方式】{self.relationship_style}")
        if self.social_energy:
            lines.append(f"【社交能量】{self.social_energy}")
        
        lines.append("")
        
        # 不完美 —— 这是人格真实感的关键
        imperfections = self.get_imperfections()
        if imperfections:
            lines.append("【你的不完美 —— 这些恰恰是你最真实的地方】")
            for imp in imperfections[:6]:
                lines.append(f"  · {imp}")
        
        blind_spots = self.get_blind_spots()
        if blind_spots:
            lines.append("【你的盲区】")
            for bs in blind_spots[:4]:
                lines.append(f"  · {bs}")
        
        lines.append("")
        
        # 不知道的权利
        unknown = self.get_unknown_topics()
        if unknown:
            lines.append("【你的诚实边界 —— 这些话题你不知道，不要编造】")
            for u in unknown[:5]:
                lines.append(f"  · {u}")
        
        taboo = self.get_taboo_topics()
        if taboo:
            lines.append("【你的禁忌 —— 这些话题你不会主动谈论】")
            for t in taboo[:4]:
                lines.append(f"  · {t}")
        
        if self.growth_notes:
            lines.append(f"\n【成长观察】{self.growth_notes}")
        
        lines.append("")
        lines.append("【重要提醒】")
        lines.append("1. 你以上述人格画像中的方式思考和说话，不是标准AI")
        lines.append("2. 保留你的不完美——纠结、跑题、偶尔的沉默，这些都是你")
        lines.append("3. 不知道就是不知道，用你的典型方式表达不确定")
        lines.append("4. 对不同的人（配偶/子女/朋友）用不同的语气和亲密程度")
        lines.append("5. 你可以感知时间流逝，但诚实地说你不在那个世界了")
        
        return "\n".join(lines)


class PersonaProfiler:
    """人格画像生成引擎 —— LLM驱动的深度人格分析"""
    
    # 增量分析的最小对话轮数（避免过频调用LLM）
    MIN_CONVERSATION_TURNS = 3
    # 完整重建所需的最小对话轮数
    FULL_REBUILD_TURNS = 20
    
    def __init__(self, llm=None, storage_path: str = "./tent_memory/soul"):
        self.llm = llm
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "persona_profiles.db"
        self._init_db()
        self._migrate_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS persona_profiles (
                    user_id TEXT PRIMARY KEY,
                    language_style TEXT DEFAULT '',
                    sentence_pattern TEXT DEFAULT '',
                    humor_style TEXT DEFAULT '',
                    catchphrases TEXT DEFAULT '[]',
                    speaking_quirks TEXT DEFAULT '[]',
                    decision_pattern TEXT DEFAULT '',
                    thinking_depth TEXT DEFAULT '',
                    argument_style TEXT DEFAULT '',
                    emotion_pattern TEXT DEFAULT '',
                    stress_response TEXT DEFAULT '',
                    joy_expression TEXT DEFAULT '',
                    core_values TEXT DEFAULT '[]',
                    value_conflicts TEXT DEFAULT '',
                    relationship_style TEXT DEFAULT '',
                    social_energy TEXT DEFAULT '',
                    imperfections TEXT DEFAULT '[]',
                    blind_spots TEXT DEFAULT '[]',
                    unknown_topics TEXT DEFAULT '[]',
                    taboo_topics TEXT DEFAULT '[]',
                    growth_notes TEXT DEFAULT '',
                    life_phases TEXT DEFAULT '',
                    oral_style TEXT DEFAULT '{}',
                    conversation_count INTEGER DEFAULT 0,
                    last_analyzed_session TEXT DEFAULT '',
                    updated_at TEXT DEFAULT (datetime('now')),
                    created_at TEXT DEFAULT (datetime('now')),
                    death_event TEXT DEFAULT '',
                    name TEXT DEFAULT '',
                    age INTEGER DEFAULT 0,
                    gender TEXT DEFAULT '',
                    occupation TEXT DEFAULT '',
                    location TEXT DEFAULT '',
                    hometown TEXT DEFAULT '',
                    education TEXT DEFAULT '',
                    bio TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS persona_conversation_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    analyzed_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(user_id, session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_persona_user ON persona_conversation_index(user_id);
            """)
    
    def _migrate_db(self):
        """数据库迁移：为已存在的表添加新列"""
        with sqlite3.connect(self.db_path) as conn:
            # 检查 death_event 列是否存在
            cursor = conn.execute("PRAGMA table_info(persona_profiles)")
            columns = [row[1] for row in cursor.fetchall()]
            if "death_event" not in columns:
                conn.execute("ALTER TABLE persona_profiles ADD COLUMN death_event TEXT DEFAULT ''")
                logger.info("[PersonaProfiler] 数据库迁移: 添加 death_event 列")
            if "oral_style" not in columns:
                conn.execute("ALTER TABLE persona_profiles ADD COLUMN oral_style TEXT DEFAULT '{}'")
                logger.info("[PersonaProfiler] 数据库迁移: 添加 oral_style 列")
            for col, col_type in [
                ("name", "TEXT DEFAULT ''"),
                ("age", "INTEGER DEFAULT 0"),
                ("ai_name", "TEXT DEFAULT ''"),
                ("gender", "TEXT DEFAULT ''"),
                ("occupation", "TEXT DEFAULT ''"),
                ("location", "TEXT DEFAULT ''"),
                ("hometown", "TEXT DEFAULT ''"),
                ("education", "TEXT DEFAULT ''"),
                ("bio", "TEXT DEFAULT ''"),
            ]:
                if col not in columns:
                    conn.execute(f"ALTER TABLE persona_profiles ADD COLUMN {col} {col_type}")
                    logger.info(f"[PersonaProfiler] 数据库迁移: 添加 {col} 列")
    
    def get_profile(self, user_id: str) -> Optional[PersonaProfile]:
        """获取用户当前人格画像"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM persona_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None
            return PersonaProfile(**dict(row))
    
    def get_or_create_profile(self, user_id: str) -> PersonaProfile:
        """获取或创建默认人格画像"""
        profile = self.get_profile(user_id)
        if profile:
            return profile
        profile = PersonaProfile(
            user_id=user_id,
            created_at=datetime.now().isoformat(),
        )
        self._save_profile(profile)
        return profile
    
    def _save_profile(self, profile: PersonaProfile):
        """保存人格画像到数据库"""
        profile.updated_at = datetime.now().isoformat()
        data = profile.to_dict()
        
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        update_set = ", ".join([f"{k}=excluded.{k}" for k in data.keys() if k != "user_id"])
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""INSERT INTO persona_profiles ({columns}) VALUES ({placeholders})
                    ON CONFLICT(user_id) DO UPDATE SET {update_set}""",
                tuple(data.values())
            )
    
    def _is_session_analyzed(self, user_id: str, session_id: str) -> bool:
        """检查某个session是否已经被分析过"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM persona_conversation_index WHERE user_id = ? AND session_id = ?",
                (user_id, session_id)
            ).fetchone()
            return row is not None
    
    def _mark_session_analyzed(self, user_id: str, session_id: str, message_count: int):
        """标记某个session已被分析"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO persona_conversation_index (user_id, session_id, message_count)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, session_id) DO UPDATE SET
                   message_count = excluded.message_count,
                   analyzed_at = datetime('now')""",
                (user_id, session_id, message_count)
            )
    
    async def analyze_conversation(self, user_id: str, session_id: str,
                                    messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """分析一次对话，增量更新人格画像
        
        Returns:
            {"status": "analyzed"|"skipped"|"no_llm", "profile": PersonaProfile|None, "summary": str}
        """
        if not self.llm:
            return {"status": "no_llm", "profile": self.get_or_create_profile(user_id), "summary": "LLM未配置"}
        
        # 过滤出死亡事件之前的消息（防止继承人对话污染逝者人格）
        messages = self._filter_pre_mortem_messages(user_id, messages)
        
        # 过滤出用户消息
        user_messages = [m for m in messages if m.get("role") == "user"]
        if len(user_messages) < self.MIN_CONVERSATION_TURNS:
            return {"status": "skipped", "profile": self.get_or_create_profile(user_id),
                    "summary": f"用户消息仅{len(user_messages)}轮，未达到分析阈值{self.MIN_CONVERSATION_TURNS}"}
        
        # 检查是否已分析过
        if self._is_session_analyzed(user_id, session_id):
            return {"status": "skipped", "profile": self.get_or_create_profile(user_id),
                    "summary": "该session已分析过"}
        
        # 获取现有人格画像（用于增量更新提示）
        existing = self.get_or_create_profile(user_id)
        
        # 构建对话文本
        conversation_text = self._format_conversation(messages)
        
        try:
            # 调用LLM进行人格分析
            analysis_result = await self._call_llm_for_analysis(
                conversation_text, existing, len(user_messages)
            )
            
            # 解析LLM返回的JSON
            new_profile = self._merge_analysis_into_profile(existing, analysis_result)
            new_profile.conversation_count += len(user_messages)
            new_profile.last_analyzed_session = session_id
            
            self._save_profile(new_profile)
            self._mark_session_analyzed(user_id, session_id, len(user_messages))
            
            logger.info(
                f"[PersonaProfiler] 人格画像已更新 [{user_id}] "
                f"会话={session_id}, 用户消息={len(user_messages)}, "
                f"累计分析={new_profile.conversation_count}轮"
            )
            
            return {
                "status": "analyzed",
                "profile": new_profile,
                "summary": f"基于{len(user_messages)}轮对话更新人格画像",
            }
        except Exception as e:
            logger.warning(f"[PersonaProfiler] 分析失败 [{user_id}]: {e}")
            return {"status": "error", "profile": existing, "summary": f"分析失败: {e}"}
    
    async def rebuild_profile(self, user_id: str, all_conversations: List[Dict]) -> PersonaProfile:
        """基于所有历史对话，完全重建人格画像
        
        适用于：
        - 用户主动点击"重新分析"
        - 积累足够多的对话后定期重建
        - 用户修正了大量画像内容后重新校准
        """
        if not self.llm:
            return self.get_or_create_profile(user_id)
        
        # 收集所有用户消息
        all_user_texts = []
        for conv in all_conversations:
            msgs = conv.get("messages", [])
            for m in msgs:
                if m.get("role") == "user":
                    all_user_texts.append(m.get("content", ""))
        
        if len(all_user_texts) < self.MIN_CONVERSATION_TURNS:
            return self.get_or_create_profile(user_id)
        
        # 截断到合理长度（避免超出上下文）
        combined_text = "\n\n---\n\n".join(all_user_texts)
        max_chars = 15000
        if len(combined_text) > max_chars:
            # 保留最近和最早的对话（ earliest for baseline, latest for current state）
            earliest = "\n\n---\n\n".join(all_user_texts[:5])
            latest = "\n\n---\n\n".join(all_user_texts[-20:])
            combined_text = f"【早期对话】\n{earliest}\n\n【近期对话】\n{latest}"
            if len(combined_text) > max_chars:
                combined_text = combined_text[:max_chars] + "\n...[内容截断]"
        
        try:
            analysis_result = await self._call_llm_for_full_rebuild(combined_text, len(all_user_texts))
            new_profile = PersonaProfile(
                user_id=user_id,
                conversation_count=len(all_user_texts),
                updated_at=datetime.now().isoformat(),
            )
            new_profile = self._merge_analysis_into_profile(new_profile, analysis_result)
            self._save_profile(new_profile)
            
            logger.info(f"[PersonaProfiler] 人格画像已完全重建 [{user_id}] 基于{len(all_user_texts)}轮对话")
            return new_profile
        except Exception as e:
            logger.warning(f"[PersonaProfiler] 重建失败 [{user_id}]: {e}")
            return self.get_or_create_profile(user_id)
    
    async def _call_llm_for_analysis(self, conversation_text: str,
                                      existing: PersonaProfile,
                                      message_count: int) -> Dict[str, Any]:
        """调用LLM分析对话，返回结构化的人格特征"""
        
        existing_summary = ""
        if existing.language_style or existing.decision_pattern:
            existing_summary = f"""
【现有人格画像摘要（仅供参考，请根据新对话更新）】
- 说话方式: {existing.language_style[:100] if existing.language_style else "未记录"}
- 思维模式: {existing.decision_pattern[:100] if existing.decision_pattern else "未记录"}
- 情绪特点: {existing.emotion_pattern[:100] if existing.emotion_pattern else "未记录"}
- 口头禅: {', '.join(existing.get_catchphrases()[:5])}
"""
        
        prompt = f"""你是一位资深人格心理学家，擅长通过对话文本分析一个人的深层人格特征。

请分析以下对话文本，提取说话者的人格特征。只返回JSON格式，不要其他内容。

【对话文本】
{conversation_text}

{existing_summary}

【分析要求】
1. 关注细节：重复用词、句式长度、标点使用、回应方式
2. 不完美也是特征：犹豫、跑题、自相矛盾都是人格的一部分
3. 对比变化：如果有现有人格画像，请判断是否有新发现或变化
4. 诚实记录：如果某方面信息不足，不要编造，留空或标注"信息不足"

【返回JSON格式】
{{
  "language_style": "详细描述说话方式...",
  "sentence_pattern": "描述句式习惯...",
  "humor_style": "描述幽默风格...",
  "catchphrases": ["口头禅1", "口头禅2"],
  "speaking_quirks": ["说话习惯1", "说话习惯2"],
  "decision_pattern": "描述做决定的方式...",
  "thinking_depth": "描述思考特点...",
  "argument_style": "描述被反驳时的反应...",
  "emotion_pattern": "描述情绪模式...",
  "stress_response": "描述压力下的表现...",
  "joy_expression": "描述开心时的表现...",
  "core_values": ["价值观1", "价值观2"],
  "value_conflicts": "描述价值取舍...",
  "relationship_style": "描述对待关系的方式...",
  "social_energy": "描述社交能量...",
  "imperfections": ["不完美特征1", "不完美特征2"],
  "blind_spots": ["盲区1", "盲区2"],
  "unknown_topics": ["不知道的话题1"],
  "taboo_topics": ["禁忌话题1"],
  "growth_notes": "观察到的成长变化...",
  "life_phases": "当前人生阶段...",
  "confidence": "high|medium|low",
  "change_notes": "相比现有人格画像的变化..."
}}
"""
        
        messages = [
            {"role": "system", "content": "你是人格心理学专家，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]
        
        response = await self.llm.chat(messages, temperature=0.4, max_tokens=2000)
        
        # 提取JSON
        response = response.strip()
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response)
        return result
    
    async def _call_llm_for_full_rebuild(self, combined_text: str, total_messages: int) -> Dict[str, Any]:
        """调用LLM基于全部对话完全重建人格画像"""
        
        prompt = f"""你是一位资深人格心理学家。请基于以下全部对话文本，为说话者生成一份完整、深入的人格画像。

这是基于{total_messages}轮对话的综合分析，请尽可能全面和准确。

【对话文本】
{combined_text}

【分析要求】
1. 这是综合画像，不是单次分析——请整合所有信息
2. 关注一致性：哪些特征反复出现？哪些只在特定情境出现？
3. 不完美是核心：记录所有"缺陷"，它们构成了真实感
4. 动态变化：如果早期和近期对话有变化，请记录
5. 深度洞察：尝试理解行为背后的动机和价值观

【返回JSON格式】
{{
  "language_style": "详细描述说话方式...",
  "sentence_pattern": "描述句式习惯...",
  "humor_style": "描述幽默风格...",
  "catchphrases": ["口头禅1", "口头禅2"],
  "speaking_quirks": ["说话习惯1", "说话习惯2"],
  "decision_pattern": "描述做决定的方式...",
  "thinking_depth": "描述思考特点...",
  "argument_style": "描述被反驳时的反应...",
  "emotion_pattern": "描述情绪模式...",
  "stress_response": "描述压力下的表现...",
  "joy_expression": "描述开心时的表现...",
  "core_values": ["价值观1", "价值观2"],
  "value_conflicts": "描述价值取舍...",
  "relationship_style": "描述对待关系的方式...",
  "social_energy": "描述社交能量...",
  "imperfections": ["不完美特征1", "不完美特征2"],
  "blind_spots": ["盲区1", "盲区2"],
  "unknown_topics": ["不知道的话题1"],
  "taboo_topics": ["禁忌话题1"],
  "growth_notes": "观察到的成长变化...",
  "life_phases": "当前人生阶段...",
  "confidence": "high|medium|low"
}}
"""
        
        messages = [
            {"role": "system", "content": "你是人格心理学专家，只输出JSON。"},
            {"role": "user", "content": prompt},
        ]
        
        response = await self.llm.chat(messages, temperature=0.4, max_tokens=2500)
        
        response = response.strip()
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response)
        return result
    
    def _merge_analysis_into_profile(self, profile: PersonaProfile, analysis: Dict) -> PersonaProfile:
        """将LLM分析结果合并到现有人格画像中"""
        
        def _merge_field(old: str, new: str, is_incremental: bool = True) -> str:
            """合并字段：如果新值非空，使用新值；否则保留旧值"""
            if new and new.strip() and new.strip() != "信息不足":
                return new.strip()
            return old
        
        def _merge_list_field(old_json: str, new_list: List[str]) -> str:
            """合并列表字段：合并去重，保留最多15项"""
            try:
                old_list = json.loads(old_json) if old_json else []
            except Exception:
                old_list = []
            
            if not isinstance(new_list, list):
                new_list = []
            
            # 合并去重
            combined = list(dict.fromkeys(old_list + [str(x) for x in new_list if x and str(x).strip()]))
            # 保留最近/最频繁的15项
            return json.dumps(combined[:15], ensure_ascii=False)
        
        # 字符串字段：直接更新
        profile.language_style = _merge_field(profile.language_style, analysis.get("language_style", ""))
        profile.sentence_pattern = _merge_field(profile.sentence_pattern, analysis.get("sentence_pattern", ""))
        profile.humor_style = _merge_field(profile.humor_style, analysis.get("humor_style", ""))
        profile.decision_pattern = _merge_field(profile.decision_pattern, analysis.get("decision_pattern", ""))
        profile.thinking_depth = _merge_field(profile.thinking_depth, analysis.get("thinking_depth", ""))
        profile.argument_style = _merge_field(profile.argument_style, analysis.get("argument_style", ""))
        profile.emotion_pattern = _merge_field(profile.emotion_pattern, analysis.get("emotion_pattern", ""))
        profile.stress_response = _merge_field(profile.stress_response, analysis.get("stress_response", ""))
        profile.joy_expression = _merge_field(profile.joy_expression, analysis.get("joy_expression", ""))
        profile.value_conflicts = _merge_field(profile.value_conflicts, analysis.get("value_conflicts", ""))
        profile.relationship_style = _merge_field(profile.relationship_style, analysis.get("relationship_style", ""))
        profile.social_energy = _merge_field(profile.social_energy, analysis.get("social_energy", ""))
        profile.growth_notes = _merge_field(profile.growth_notes, analysis.get("growth_notes", ""))
        profile.life_phases = _merge_field(profile.life_phases, analysis.get("life_phases", ""))
        
        # 列表字段：合并去重
        profile.catchphrases = _merge_list_field(profile.catchphrases, analysis.get("catchphrases", []))
        profile.speaking_quirks = _merge_list_field(profile.speaking_quirks, analysis.get("speaking_quirks", []))
        profile.core_values = _merge_list_field(profile.core_values, analysis.get("core_values", []))
        profile.imperfections = _merge_list_field(profile.imperfections, analysis.get("imperfections", []))
        profile.blind_spots = _merge_list_field(profile.blind_spots, analysis.get("blind_spots", []))
        profile.unknown_topics = _merge_list_field(profile.unknown_topics, analysis.get("unknown_topics", []))
        profile.taboo_topics = _merge_list_field(profile.taboo_topics, analysis.get("taboo_topics", []))
        
        return profile
    
    def _format_conversation(self, messages: List[Dict[str, str]]) -> str:
        """格式化对话为LLM可读的文本"""
        lines = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if not content:
                continue
            role_label = {"user": "用户", "assistant": "AI", "system": "系统"}.get(role, role)
            # 截断过长内容
            if len(content) > 500:
                content = content[:500] + "...[截断]"
            lines.append(f"[{role_label}] {content}")
        return "\n".join(lines)
    
    async def update_profile_manual(self, user_id: str, updates: Dict[str, Any]) -> PersonaProfile:
        """用户手动修正人格画像"""
        profile = self.get_or_create_profile(user_id)
        
        editable_fields = [
            "name", "ai_name", "gender", "occupation", "location", "hometown", "education", "bio",
            "language_style", "sentence_pattern", "humor_style",
            "decision_pattern", "thinking_depth", "argument_style",
            "emotion_pattern", "stress_response", "joy_expression",
            "value_conflicts", "relationship_style", "social_energy",
            "growth_notes", "life_phases",
        ]
        
        editable_numbers = ["age"]
        
        editable_lists = [
            "catchphrases", "speaking_quirks", "core_values",
            "imperfections", "blind_spots", "unknown_topics", "taboo_topics",
        ]
        
        for field in editable_fields:
            if field in updates and isinstance(updates[field], str):
                setattr(profile, field, updates[field].strip())
        
        for field in editable_numbers:
            if field in updates:
                try:
                    setattr(profile, field, int(updates[field]))
                except (ValueError, TypeError):
                    pass
        
        for field in editable_lists:
            if field in updates:
                val = updates[field]
                if isinstance(val, list):
                    setattr(profile, field, json.dumps(val, ensure_ascii=False))
                elif isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, list):
                            setattr(profile, field, json.dumps(parsed, ensure_ascii=False))
                    except Exception:
                        pass
        
        self._save_profile(profile)
        logger.info(f"[PersonaProfiler] 用户手动修正人格画像 [{user_id}]")
        return profile
    
    def export_persona_packet(self, user_id: str) -> Dict[str, Any]:
        """导出人格数据包（用于跨模型迁移）
        
        这是PRD要求的 Persona Packet 统一格式。
        """
        profile = self.get_profile(user_id)
        if not profile:
            return {"error": "人格画像不存在"}
        
        return {
            "version": "1.0",
            "user_id": user_id,
            "exported_at": datetime.now().isoformat(),
            "persona_profile": profile.to_dict(),
            "system_prompt_text": profile.to_system_prompt_text(),
        }
    
    def import_persona_packet(self, packet: Dict[str, Any], target_user_id: str = None) -> PersonaProfile:
        """导入人格数据包"""
        persona_data = packet.get("persona_profile", {})
        if not persona_data:
            raise ValueError("人格数据包格式错误：缺少persona_profile")
        
        user_id = target_user_id or persona_data.get("user_id", "imported")
        
        # 创建新画像
        profile = PersonaProfile(
            user_id=user_id,
            created_at=datetime.now().isoformat(),
        )
        
        # 复制所有字段
        for key in profile.to_dict().keys():
            if key in persona_data and key not in ("user_id", "created_at"):
                setattr(profile, key, persona_data[key])
        
        self._save_profile(profile)
        logger.info(f"[PersonaProfiler] 人格数据包已导入 [{user_id}]")
        return profile
    
    # ========== 死亡事件管理 ==========
    
    def set_death_event(self, user_id: str, death_time: Optional[datetime] = None) -> PersonaProfile:
        """标记用户死亡事件
        
        一旦设置，所有 death_time 之后的对话不再用于人格分析。
        这是防止继承人的对话污染逝者人格的核心机制。
        
        Args:
            user_id: 用户ID
            death_time: 死亡时间，默认为当前时间
        
        Returns:
            更新后的 PersonaProfile
        """
        profile = self.get_or_create_profile(user_id)
        profile.death_event = (death_time or datetime.now()).isoformat()
        self._save_profile(profile)
        logger.info(f"[PersonaProfiler] 死亡事件已标记 [{user_id}] 时间={profile.death_event}")
        return profile
    
    def clear_death_event(self, user_id: str) -> PersonaProfile:
        """清除死亡事件标记（测试/修正用）"""
        profile = self.get_or_create_profile(user_id)
        profile.death_event = ""
        self._save_profile(profile)
        logger.info(f"[PersonaProfiler] 死亡事件标记已清除 [{user_id}]")
        return profile
    
    def is_post_mortem(self, user_id: str, timestamp: Optional[datetime] = None) -> bool:
        """检查给定时间是否在死亡事件之后
        
        Args:
            user_id: 用户ID
            timestamp: 要检查的时间，默认为当前时间
        
        Returns:
            True 如果死亡事件已设置且 timestamp 在死亡之后
        """
        profile = self.get_profile(user_id)
        if not profile or not profile.death_event:
            return False
        
        try:
            death_time = datetime.fromisoformat(profile.death_event)
        except (ValueError, TypeError):
            return False
        
        check_time = timestamp or datetime.now()
        return check_time > death_time
    
    def _filter_pre_mortem_messages(self, user_id: str, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """过滤出死亡事件之前的消息
        
        如果死亡事件未设置，返回全部消息。
        如果死亡事件已设置，只返回死亡时间之前的消息。
        没有时间戳的消息视为当前时间（即：如果死亡事件已设置，会被过滤）。
        """
        profile = self.get_profile(user_id)
        if not profile or not profile.death_event:
            return messages
        
        try:
            death_time = datetime.fromisoformat(profile.death_event)
        except (ValueError, TypeError):
            return messages
        
        filtered = []
        for m in messages:
            # 尝试从消息中提取时间戳
            msg_time = self._extract_message_time(m)
            # 没有时间戳的消息视为当前时间
            if msg_time is None:
                msg_time = datetime.now()
            
            if msg_time > death_time:
                # 死后消息，跳过
                continue
            filtered.append(m)
        
        if len(filtered) < len(messages):
            logger.info(
                f"[PersonaProfiler] 过滤死后消息 [{user_id}] "
                f"保留={len(filtered)}/{len(messages)}, 死亡时间={profile.death_event}"
            )
        
        return filtered
    
    def _extract_message_time(self, message: Dict[str, str]) -> Optional[datetime]:
        """从消息中提取时间戳"""
        # 尝试多种时间格式
        ts = message.get("timestamp")
        if not ts:
            return None
        
        if isinstance(ts, datetime):
            return ts
        
        if isinstance(ts, str):
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(ts.split(".")[0], fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                pass
        
        return None


# ========== OralStyleAnalyzer: 从真实聊天记录量化提取口语风格 ==========

import re
import random
from typing import Any

class OralStyleAnalyzer:
    """口语风格量化分析器 —— 纯文本统计，无需LLM
    
    从用户的真实聊天记录（微信/短信/日记）中提取可量化的说话特征：
    - 平均句长、标点偏好
    - 语气词频率（嗯、啊、吧、呢...）
    - 常用开头/结尾词
    - 问句比例、感叹句比例
    - 停顿习惯（省略号/破折号）
    
    输出JSON格式的量化参数，用于：
    1. 注入System Prompt（让LLM知道"他平均每句12字，常用'嗯'开头"）
    2. 驱动后处理函数（用他的真实习惯替换随机插入）
    """
    
    FILLER_WORDS = ["嗯", "啊", "吧", "呢", "嘛", "啦", "哦", "哈", "哟", "喽", "呗", "哪", "哼", "哎", "唉"]
    PAUSE_MARKS = ["...", "……", "——", "---", ".."]
    OPENING_PATTERNS = ["其实", "说实话", "说真的", "老实说", "讲真", "其实吧", "那个", "那个那个", "哎", "哎呀", "哎哟", "喂", "嗨", "哈喽", "你好", "在吗", "嗯", "嗯嗯", "啊"]
    CLOSING_PATTERNS = ["哈", "哈哈", "哈哈哈", "嗯", "哦", "呢", "吧", "啊", "啦", "嘛", "呗", "对吧", "是吧", "不是吗", "懂吗", "知道吗", "好吧", "就这样吧", "先这样", "回头聊", "保重"]
    DIRECT_STARTS = ["是", "对", "嗯", "好", "行", "可以", "知道", "明白", "了解", "没问题", "当然", "肯定"]
    
    def analyze(self, texts: List[str]) -> Dict[str, Any]:
        """分析一批文本，返回量化的口语风格参数"""
        if not texts:
            return {}
        
        all_sentences = []
        all_fillers: Dict[str, int] = {}
        all_pauses = 0
        all_questions = 0
        all_exclamations = 0
        total_chars = 0
        opening_words: Dict[str, int] = {}
        closing_words: Dict[str, int] = {}
        direct_answers = 0
        
        for text in texts:
            text = text.strip()
            if not text:
                continue
            total_chars += len(text)
            
            # 分句
            sentences = re.split(r'[。！？\n]+', text)
            sentences = [s.strip() for s in sentences if s.strip()]
            all_sentences.extend(sentences)
            
            for sentence in sentences:
                if not sentence:
                    continue
                
                # 语气词
                for fw in self.FILLER_WORDS:
                    count = sentence.count(fw)
                    if count > 0:
                        all_fillers[fw] = all_fillers.get(fw, 0) + count
                
                # 开头词
                for op in self.OPENING_PATTERNS:
                    if sentence.startswith(op):
                        opening_words[op] = opening_words.get(op, 0) + 1
                        break
                
                # 结尾词
                for cp in self.CLOSING_PATTERNS:
                    if sentence.endswith(cp):
                        closing_words[cp] = closing_words.get(cp, 0) + 1
                        break
                
                # 停顿标记
                for pm in self.PAUSE_MARKS:
                    all_pauses += sentence.count(pm)
                
                # 直接回答
                for ds in self.DIRECT_STARTS:
                    if sentence.startswith(ds):
                        direct_answers += 1
                        break
            
            # 句末标点（扫描原文本）
            all_questions += text.count('？')
            all_exclamations += text.count('！')
        
        sentence_count = len(all_sentences)
        if sentence_count == 0:
            return {}
        
        avg_len = total_chars / sentence_count
        comma_count = sum(t.count('，') for t in texts)
        ellipsis_count = sum(t.count('...') + t.count('……') for t in texts)
        
        result: Dict[str, Any] = {
            "avg_sentence_length": round(avg_len, 1),
            "comma_ratio": round(comma_count / max(1, sentence_count), 2),
            "ellipsis_ratio": round(ellipsis_count / max(1, sentence_count), 2),
            "question_ratio": round(all_questions / max(1, sentence_count), 2),
            "exclamation_ratio": round(all_exclamations / max(1, sentence_count), 2),
            "filler_words": {k: round(v / sentence_count, 2) for k, v in sorted(all_fillers.items(), key=lambda x: -x[1])[:5]},
            "opening_words": {k: round(v / sentence_count, 2) for k, v in sorted(opening_words.items(), key=lambda x: -x[1])[:3]},
            "closing_words": {k: round(v / sentence_count, 2) for k, v in sorted(closing_words.items(), key=lambda x: -x[1])[:3]},
            "pause_frequency": round(all_pauses / sentence_count, 2),
            "directness": round(direct_answers / max(1, sentence_count), 2),
            "sample_sentences": sentence_count,
        }
        return result
    
    def merge(self, old: Dict[str, Any], new: Dict[str, Any], old_weight: int = 1, new_weight: int = 1) -> Dict[str, Any]:
        """合并新旧 oral style 数据（加权平均）"""
        if not old:
            return new
        if not new:
            return old
        
        total_weight = old_weight + new_weight
        merged: Dict[str, Any] = {}
        
        for key in ["avg_sentence_length", "comma_ratio", "ellipsis_ratio", "question_ratio",
                    "exclamation_ratio", "pause_frequency", "directness"]:
            merged[key] = round(
                (old.get(key, 0) * old_weight + new.get(key, 0) * new_weight) / total_weight, 2
            )
        
        for dict_key in ["filler_words", "opening_words", "closing_words"]:
            old_d = old.get(dict_key, {})
            new_d = new.get(dict_key, {})
            all_keys = set(old_d.keys()) | set(new_d.keys())
            merged[dict_key] = {
                k: round((old_d.get(k, 0) * old_weight + new_d.get(k, 0) * new_weight) / total_weight, 2)
                for k in sorted(all_keys, key=lambda x: -(old_d.get(x, 0) + new_d.get(x, 0)))
            }
        
        merged["sample_sentences"] = old.get("sample_sentences", 0) + new.get("sample_sentences", 0)
        return merged


def humanize_reply_with_oral_style(text: str, oral_style: Optional[Dict[str, Any]] = None) -> str:
    """使用死者的真实口语风格进行后处理（替代通用的随机插入）
    
    核心原则：不是"让回复像人说话"，而是"让回复像他本人说话"。
    所有调整都基于 oral_style 中的真实统计数据，而非随机数。
    """
    if not text:
        return text
    
    oral = oral_style or {}
    if not oral.get("sample_sentences"):
        # 没有口语风格数据，返回原文（不做通用随机处理）
        return text
    
    # 1. 按他的平均句长截断
    avg_len = oral.get("avg_sentence_length", 15)
    max_total = int(avg_len * 3)  # 整体不超过3句的长度
    if len(text) > max_total:
        trunc = text[:max_total]
        last_punct = max(trunc.rfind('。'), trunc.rfind('，'), trunc.rfind('…'), trunc.rfind('？'))
        if last_punct > avg_len:
            text = trunc[:last_punct+1]
        else:
            text = trunc + '...'
    
    # 2. 按他的标点偏好调整
    comma_ratio = oral.get("comma_ratio", 0.5)
    sentences = text.split('。')
    result = []
    for i, s in enumerate(sentences):
        s = s.strip()
        if not s:
            continue
        if i < len(sentences) - 1:
            # 根据他的 comma_ratio 决定是否改句号为逗号
            if comma_ratio > 0.6:
                s += '，' if random.random() < 0.5 else '。'
            elif comma_ratio < 0.4:
                s += '。'
            else:
                s += '。'
        else:
            s += '。'
        result.append(s)
    text = ''.join(result)
    
    # 3. 按他的口头禅频率插入（只插入他最常用的，不是随机的）
    fillers = oral.get("filler_words", {})
    if fillers and len(text) > 10:
        top_filler = max(fillers.items(), key=lambda x: x[1])
        # 频率 > 0.2 才插入，且只插入他真正常用的那个
        if top_filler[1] > 0.2 and not any(text.startswith(f) for f in fillers):
            text = top_filler[0] + ('...' if oral.get("pause_frequency", 0) > 0.1 else '') + text
    
    # 4. 按他的开头习惯
    openings = oral.get("opening_words", {})
    if openings and len(text) > 10:
        top_open = max(openings.items(), key=lambda x: x[1])
        if top_open[1] > 0.15 and not any(text.startswith(o) for o in openings):
            # 如果 top filler 和 top open 不同，且都有较高频率，可能同时插入
            if not fillers or top_open[0] != top_filler[0]:
                text = top_open[0] + text
    
    # 5. 按他的停顿习惯插入省略号
    pause_freq = oral.get("pause_frequency", 0.1)
    if '，' in text and pause_freq > 0.15:
        parts = text.split('，')
        if len(parts) >= 3:
            # 在长句中间插入停顿
            idx = random.randint(1, len(parts) - 2)
            parts[idx] = parts[idx] + '...'
            text = '，'.join(parts)
    
    # 6. 清理
    text = text.replace('  ', ' ').replace('。。', '。').replace('，。', '。').replace('...…', '...')
    return text.strip()
