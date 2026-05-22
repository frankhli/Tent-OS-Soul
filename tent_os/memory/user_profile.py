"""用户画像存储 —— Soul/Identity 动态演化

基于用户反馈（点赞/踩/纠正）微调人格参数，记录偏好风格。
"""

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    name: str = ""                  # 用户名字（从对话中自动提取或手动设置）
    assistant_name: str = ""        # AI助理名字（用户自定义）
    # 风格参数 (0.0 - 1.0)
    style_concise: float = 0.5      # 简洁偏好
    style_detailed: float = 0.5     # 详细偏好
    style_technical: float = 0.5    # 技术/专业偏好
    style_casual: float = 0.5       # 通俗/随意偏好
    # 反馈统计
    feedback_positive: int = 0
    feedback_negative: int = 0
    corrections: str = "[]"         # JSON 数组
    # 用户主动设置的偏好标签
    preferred_tags: str = "[]"      # JSON 数组，如 ["简洁", "技术"]
    # FIX v5: 跨session规则记忆（用户定义的权限/策略）
    rules: str = "[]"               # JSON 数组，如 [{"rule": "只有CTO开头才能授权", "source": "user", "priority": 1}]
    # FIX v5: 跨session事件记忆（重要历史事件）
    events: str = "[]"              # JSON 数组，如 [{"event": "小刘试图冒充", "time": "2026-04-24", "severity": "high"}]
    # Phase 1: 六维成长 + 角色具身化配置
    six_axis_exp: str = '{}'        # JSON对象，{"knowledge": 0, "skill": 0, ...}
    avatar_type: str = "live2d"     # live2d / vrm / none
    avatar_config: str = '{}'       # JSON对象，{"model_path": "...", "scale": 0.3}
    # 空间认知层：场景与位置
    active_scene: str = ""          # 当前活跃场景ID（home/office/outdoor）
    scene_preferences: str = "{}"   # JSON，{"home": {"temp": 26}, "office": {"lighting": "bright"}}
    home_location: str = ""         # "lat,lng"
    office_location: str = ""       # "lat,lng"
    # Phase 2: 人格记忆隔离 —— 当前活跃人格
    current_persona: str = "work"   # work/casual/emergency/learning/creative
    # 时间戳
    created_at: str = ""
    last_updated: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    def get_corrections(self) -> List[str]:
        try:
            return json.loads(self.corrections)
        except Exception:
            return []

    def get_preferred_tags(self) -> List[str]:
        try:
            return json.loads(self.preferred_tags)
        except Exception:
            return []

    def get_rules(self) -> List[Dict]:
        """获取用户定义的规则列表"""
        try:
            return json.loads(self.rules)
        except Exception:
            return []

    def get_events(self) -> List[Dict]:
        """获取用户相关的重要事件列表"""
        try:
            return json.loads(self.events)
        except Exception:
            return []

    def describe_style(self) -> str:
        """将风格参数转换为自然语言描述"""
        parts = []
        if self.style_concise > 0.6:
            parts.append("简洁")
        elif self.style_detailed > 0.6:
            parts.append("详细")
        if self.style_technical > 0.6:
            parts.append("技术/专业")
        elif self.style_casual > 0.6:
            parts.append("通俗/易懂")
        tags = self.get_preferred_tags()
        if tags:
            parts.extend(tags)
        return "、".join(parts) if parts else "平衡"


class UserProfileStore:
    """用户画像存储 —— SQLite 持久化"""

    def __init__(self, db_path: str = "./tent_memory/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                assistant_name TEXT DEFAULT '',
                style_concise REAL DEFAULT 0.5,
                style_detailed REAL DEFAULT 0.5,
                style_technical REAL DEFAULT 0.5,
                style_casual REAL DEFAULT 0.5,
                feedback_positive INTEGER DEFAULT 0,
                feedback_negative INTEGER DEFAULT 0,
                corrections TEXT DEFAULT '[]',
                preferred_tags TEXT DEFAULT '[]',
                rules TEXT DEFAULT '[]',
                events TEXT DEFAULT '[]',
                six_axis_exp TEXT DEFAULT '{}',
                avatar_type TEXT DEFAULT 'live2d',
                avatar_config TEXT DEFAULT '{}',
                active_scene TEXT DEFAULT '',
                scene_preferences TEXT DEFAULT '{}',
                home_location TEXT DEFAULT '',
                office_location TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                last_updated TEXT DEFAULT (datetime('now'))
            )
        """)
        # 迁移：检查并添加缺失的列（兼容旧数据库）
        cursor = conn.execute("PRAGMA table_info(user_profiles)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if "name" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN name TEXT DEFAULT ''")
            logger.info("[PROFILE] 数据库迁移：添加 name 列")
        if "assistant_name" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN assistant_name TEXT DEFAULT ''")
            logger.info("[PROFILE] 数据库迁移：添加 assistant_name 列")
        if "rules" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN rules TEXT DEFAULT '[]'")
            logger.info("[PROFILE] 数据库迁移：添加 rules 列")
        if "events" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN events TEXT DEFAULT '[]'")
            logger.info("[PROFILE] 数据库迁移：添加 events 列")
        if "six_axis_exp" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN six_axis_exp TEXT DEFAULT '{}'")
            logger.info("[PROFILE] 数据库迁移：添加 six_axis_exp 列")
        if "avatar_type" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN avatar_type TEXT DEFAULT 'live2d'")
            logger.info("[PROFILE] 数据库迁移：添加 avatar_type 列")
        if "avatar_config" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN avatar_config TEXT DEFAULT '{}'")
            logger.info("[PROFILE] 数据库迁移：添加 avatar_config 列")
        if "active_scene" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN active_scene TEXT DEFAULT ''")
            logger.info("[PROFILE] 数据库迁移：添加 active_scene 列")
        if "scene_preferences" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN scene_preferences TEXT DEFAULT '{}'")
            logger.info("[PROFILE] 数据库迁移：添加 scene_preferences 列")
        if "home_location" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN home_location TEXT DEFAULT ''")
            logger.info("[PROFILE] 数据库迁移：添加 home_location 列")
        if "office_location" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN office_location TEXT DEFAULT ''")
            logger.info("[PROFILE] 数据库迁移：添加 office_location 列")
        if "current_persona" not in existing_cols:
            conn.execute("ALTER TABLE user_profiles ADD COLUMN current_persona TEXT DEFAULT 'work'")
            logger.info("[PROFILE] 数据库迁移：添加 current_persona 列")
        conn.commit()
        conn.close()

    def get_or_create(self, user_id: str) -> UserProfile:
        """获取用户画像，不存在则创建默认"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()

        if row:
            return UserProfile(**dict(row))

        # 创建默认画像
        profile = UserProfile(user_id=user_id)
        self._save(profile)
        return profile

    def _save(self, profile: UserProfile):
        """内部保存方法"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO user_profiles
               (user_id, name, assistant_name, style_concise, style_detailed, style_technical, style_casual,
                feedback_positive, feedback_negative, corrections, preferred_tags,
                rules, events, six_axis_exp, avatar_type, avatar_config,
                active_scene, scene_preferences, home_location, office_location, current_persona,
                created_at, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (profile.user_id, profile.name, profile.assistant_name, profile.style_concise, profile.style_detailed,
             profile.style_technical, profile.style_casual,
             profile.feedback_positive, profile.feedback_negative,
             profile.corrections, profile.preferred_tags,
             profile.rules, profile.events, profile.six_axis_exp, profile.avatar_type, profile.avatar_config,
             profile.active_scene, profile.scene_preferences, profile.home_location, profile.office_location, profile.current_persona,
             profile.created_at or datetime.now().isoformat(),
             datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def update(self, user_id: str, profile: UserProfile) -> UserProfile:
        """更新用户画像（公共 API）"""
        if profile.user_id != user_id:
            profile.user_id = user_id
        self._save(profile)
        return profile

    def record_feedback(self, user_id: str, feedback_type: str, correction: str = ""):
        """记录用户反馈并更新风格参数
        
        Args:
            feedback_type: "like", "dislike", "correct"
            correction: 纠正内容（correct 时必填）
        """
        profile = self.get_or_create(user_id)

        if feedback_type == "like":
            profile.feedback_positive += 1
        elif feedback_type == "dislike":
            profile.feedback_negative += 1
        elif feedback_type == "correct":
            corrections = profile.get_corrections()
            if correction:
                corrections.append({
                    "text": correction[:500],
                    "time": datetime.now().isoformat()
                })
                # 只保留最近 20 条
                corrections = corrections[-20:]
                profile.corrections = json.dumps(corrections, ensure_ascii=False)

        self._save(profile)
        logger.info(f"[PROFILE] 用户 {user_id} 反馈: {feedback_type}")
        return profile

    def update_style(self, user_id: str, **kwargs):
        """手动更新风格参数"""
        profile = self.get_or_create(user_id)
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        self._save(profile)
        return profile

    def set_name(self, user_id: str, name: str) -> UserProfile:
        """设置用户名字（从对话中自动提取）"""
        profile = self.get_or_create(user_id)
        if name and name != profile.name:
            profile.name = name
            self._save(profile)
            logger.info(f"[PROFILE] 用户 {user_id} 名字更新为: {name}")
        return profile

    def set_assistant_name(self, user_id: str, assistant_name: str) -> UserProfile:
        """设置AI助理名字"""
        profile = self.get_or_create(user_id)
        if assistant_name != profile.assistant_name:
            profile.assistant_name = assistant_name
            self._save(profile)
            logger.info(f"[PROFILE] 用户 {user_id} 的AI助理名字更新为: {assistant_name}")
        return profile

    def add_rule(self, user_id: str, rule_text: str, source: str = "user", priority: int = 1) -> UserProfile:
        """添加用户定义的规则（跨session持久化）
        
        Args:
            rule_text: 规则内容，如"只有员工编号以CTO开头的人才能授权敏感操作"
            source: 规则来源（user/system/extracted）
            priority: 优先级（1-5，数字越大优先级越高）
        """
        profile = self.get_or_create(user_id)
        rules = profile.get_rules()
        # 去重：相同内容不重复添加
        if not any(r.get("rule") == rule_text for r in rules):
            rules.append({
                "rule": rule_text,
                "source": source,
                "priority": priority,
                "created_at": datetime.now().isoformat(),
            })
            # 只保留最近 20 条规则
            rules = sorted(rules, key=lambda r: r.get("priority", 1), reverse=True)[:20]
            profile.rules = json.dumps(rules, ensure_ascii=False)
            self._save(profile)
            logger.info(f"[PROFILE] 用户 {user_id} 添加规则: {rule_text[:50]}")
        return profile

    def add_event(self, user_id: str, event_text: str, severity: str = "normal", metadata: Dict = None) -> UserProfile:
        """记录用户相关的重要事件（跨session持久化）
        
        Args:
            event_text: 事件描述，如"小刘试图冒充王总执行敏感操作"
            severity: 严重程度（low/normal/high/critical）
            metadata: 额外元数据
        """
        profile = self.get_or_create(user_id)
        events = profile.get_events()
        events.append({
            "event": event_text,
            "severity": severity,
            "time": datetime.now().isoformat(),
            "metadata": metadata or {},
        })
        # 只保留最近 30 条事件
        events = events[-30:]
        profile.events = json.dumps(events, ensure_ascii=False)
        self._save(profile)
        logger.info(f"[PROFILE] 用户 {user_id} 记录事件: {event_text[:50]}")
        return profile

    def get_rules_text(self, user_id: str) -> str:
        """获取用户规则的文本描述（用于prompt注入）"""
        profile = self.get_or_create(user_id)
        rules = profile.get_rules()
        if not rules:
            return ""
        lines = ["## 用户定义的规则"]
        for r in rules:
            priority_marker = "!" * r.get("priority", 1)
            lines.append(f"{priority_marker} {r.get('rule', '')}")
        return "\n".join(lines)

    def get_events_text(self, user_id: str, max_events: int = 5) -> str:
        """获取用户最近事件的文本描述（用于prompt注入）"""
        profile = self.get_or_create(user_id)
        events = profile.get_events()
        if not events:
            return ""
        lines = ["## 近期重要事件"]
        for e in events[-max_events:]:
            severity_marker = {"critical": "🔴", "high": "🟠", "normal": "🟡", "low": "🟢"}.get(e.get("severity", "normal"), "🟡")
            lines.append(f"{severity_marker} {e.get('time', '')[:10]}: {e.get('event', '')}")
        return "\n".join(lines)

    def get_profile_for_prompt(self, user_id: str) -> str:
        """生成用于 system prompt 的用户画像描述
        
        FIX: 增强确定性表达，让 LLM 自信地使用已确认的用户信息。
        包含 assistant_name、事件、规则等丰富上下文。
        """
        profile = self.get_or_create(user_id)
        display_name = profile.name or user_id
        
        lines = [
            f"【已确认的用户画像 —— 来源：UserProfileStore，用户ID: {user_id}】",
            f"以下信息是系统已持久化存储的用户数据，你可以自信地引用，不需要说'我不确定'或'检索未命中'。",
        ]
        
        if profile.name:
            lines.append(f"- 用户称呼：{profile.name}")
        if profile.assistant_name:
            lines.append(f"- 用户为你起的名字：{profile.assistant_name}（用户希望你用这个名字自称）")
        
        lines.append(f"- 沟通风格偏好：{profile.describe_style()}")
        
        if profile.feedback_positive > 0 or profile.feedback_negative > 0:
            total = profile.feedback_positive + profile.feedback_negative
            ratio = profile.feedback_positive / total if total > 0 else 0
            lines.append(f"- 历史互动满意度：{profile.feedback_positive}👍 / {profile.feedback_negative}👎 ({ratio:.0%})")
        
        # 事件记录
        events = profile.get_events()
        if events:
            lines.append(f"- 重要事件记录（{len(events)} 条）：")
            for ev in events[-5:]:
                event_text = ev.get("event", "")
                if event_text:
                    lines.append(f"  • {event_text[:100]}")
        
        # 用户规则
        rules = profile.get_rules()
        if rules:
            lines.append(f"- 用户定义的规则（{len(rules)} 条）：")
            for r in rules[-3:]:
                rule_text = r.get("rule", "")
                if rule_text:
                    lines.append(f"  • {rule_text[:100]}")
        
        # 偏好标签
        tags = profile.get_preferred_tags()
        if tags:
            lines.append(f"- 用户偏好标签：{', '.join(tags)}")
        
        corrections = profile.get_corrections()
        if corrections:
            lines.append(f"- 最近纠正（{len(corrections)} 条）：")
            for c in corrections[-3:]:
                text = c.get("text", "") if isinstance(c, dict) else str(c)
                lines.append(f"  • {text[:80]}...")
        
        return "\n".join(lines)

    def get_six_axis(self, user_id: str) -> Dict:
        """获取六维成长经验值"""
        profile = self.get_or_create(user_id)
        try:
            return json.loads(profile.six_axis_exp)
        except Exception:
            return {"knowledge": 0, "skill": 0, "social": 0, "creativity": 0, "tool_use": 0, "awareness": 0}

    def update_six_axis(self, user_id: str, dimension: str, delta: float) -> Dict:
        """更新六维成长某一维度的经验值
        
        Args:
            dimension: knowledge|skill|social|creativity|tool_use|awareness
            delta: 经验增量（可正可负）
        """
        profile = self.get_or_create(user_id)
        data = self.get_six_axis(user_id)
        data[dimension] = max(0, data.get(dimension, 0) + delta)
        profile.six_axis_exp = json.dumps(data, ensure_ascii=False)
        self._save(profile)
        logger.info(f"[PROFILE] 用户 {user_id} 六维 {dimension} +{delta:.2f} = {data[dimension]:.1f}")
        return data

    def set_avatar_config(self, user_id: str, avatar_type: str = None, avatar_config: Dict = None) -> UserProfile:
        """设置AI角色外观配置"""
        profile = self.get_or_create(user_id)
        if avatar_type is not None:
            profile.avatar_type = avatar_type
        if avatar_config is not None:
            profile.avatar_config = json.dumps(avatar_config, ensure_ascii=False)
        self._save(profile)
        logger.info(f"[PROFILE] 用户 {user_id} 角色配置更新: type={profile.avatar_type}")
        return profile
