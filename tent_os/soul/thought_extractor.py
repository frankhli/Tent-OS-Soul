"""思维特征提取器 —— 轻量级快速路径（不调用LLM）

注意：深度人格分析由 PersonaProfiler 负责（LLM驱动）。
ThoughtExtractor 仅作为：
1. 快速路径：不消耗LLM Token的轻量启发式分析
2. 向后兼容：保留数值化画像供旧接口使用
3. 实时反馈：给前端提供即时的完成度指标

所有硬编码关键词已改为可配置，支持从外部文件加载。
"""

import json
import sqlite3
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from tent_os.logging_config import get_logger

logger = get_logger()

# ========== 可配置的关键词库 ==========
# 从环境变量或配置文件加载，避免硬编码。如果未配置，使用默认的通用词库。

def _load_keyword_config(env_var: str, defaults: List[str]) -> List[str]:
    """从环境变量加载关键词列表，逗号分隔"""
    val = os.environ.get(env_var, "")
    if val:
        return [w.strip() for w in val.split(",") if w.strip()]
    return defaults

# 决策风格关键词
CONSERVATIVE_WORDS = _load_keyword_config(
    "TENT_PERSONA_CONSERVATIVE",
    ["稳妥", "保守", "安全第一", "不要冒险", "谨慎", "慢慢", "再想想", "不行",
     "稳妥起见", "稳妥一点", "慎重", "稳妥起见", "再考虑", "再看看", "不着急"]
)
RISKY_WORDS = _load_keyword_config(
    "TENT_PERSONA_RISKY",
    ["直接干", "冲", "赌一把", "试一下", "不怕", "立刻", "马上", "果断",
     "干了", "搞起", "冲就完", "怕什么", "直接上", "别犹豫", "先做了再说"]
)

# 语言风格关键词
CASUAL_WORDS = _load_keyword_config(
    "TENT_PERSONA_CASUAL",
    ["哈哈", "嗯", "呢", "吧", "啦", "随便", "还行", "挺好的",
     "对吧", "是吧", "哈哈哈", "嘿嘿", "无所谓", "就那样", "差不多"]
)
FORMAL_WORDS = _load_keyword_config(
    "TENT_PERSONA_FORMAL",
    ["您好", "谢谢", "请", "认为", "建议", "方案", "评估", "因此", "综上所述",
     "谨此", "敬请", "恳请", "鉴于", " accordingly", "furthermore"]
)

# 情绪触发词
POSITIVE_WORDS = _load_keyword_config(
    "TENT_PERSONA_POSITIVE",
    ["开心", "喜欢", "满意", "棒", "好", "优秀", "爱", "感谢", "赞",
     "不错", "挺好", "完美", "舒服", "享受", "期待", "兴奋", "高兴"]
)
NEGATIVE_WORDS = _load_keyword_config(
    "TENT_PERSONA_NEGATIVE",
    ["讨厌", "烦", "生气", "失望", "差", "烂", "恨", "累", "郁闷",
     "烦人", "糟糕", "难受", "痛苦", "焦虑", "担心", "害怕", "愤怒"]
)


class ThoughtExtractor:
    """
    轻量级思维特征提取器（快速路径，不调用LLM）
    
    深度分析请使用 PersonaProfiler。
    """
    
    def __init__(self, storage_path: str = "./tent_memory/soul"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "thought_features.db"
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS thought_profiles (
                    user_id TEXT PRIMARY KEY,
                    decision_style REAL DEFAULT 0.5,  -- 0=保守, 1=冒险
                    language_style REAL DEFAULT 0.5,  -- 0=随意, 1=正式
                    core_values TEXT DEFAULT '[]',
                    catchphrases TEXT DEFAULT '[]',
                    emotion_patterns TEXT DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS conversation_annotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    annotation_type TEXT,  -- decision, value, emotion, style
                    content TEXT,
                    confidence REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS style_templates (
                    user_id TEXT PRIMARY KEY,
                    static_segments TEXT DEFAULT '{}',
                    updated_at TEXT DEFAULT (datetime('now'))
                );
            """)
    
    async def extract_from_conversation(self, user_id: str, session_id: str,
                                        messages: List[Dict]) -> Dict:
        """从一次对话中提取思维特征（轻量启发式，不调用LLM）"""
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return {}
        
        all_text = " ".join([m.get("content", "") for m in user_messages])
        
        features = {
            "decision_bias": self._analyze_decision_style(all_text),
            "language_formality": self._analyze_language_style(all_text),
            "catchphrases": self._extract_catchphrases(all_text),
            "emotion_triggers": self._extract_emotion_triggers(all_text),
        }
        
        # 存入标注
        self._save_annotation(user_id, session_id, "style", json.dumps(features, ensure_ascii=False), 0.6)
        
        # 更新累计画像
        self._update_profile(user_id, features)
        
        logger.info(f"[ThoughtExtractor] 轻量提取完成 [{user_id}]: decision={features['decision_bias']:.2f}")
        return features
    
    def _analyze_decision_style(self, text: str) -> float:
        """分析决策风格：0=保守, 1=冒险（可配置关键词）"""
        c_score = sum(1 for w in CONSERVATIVE_WORDS if w in text)
        r_score = sum(1 for w in RISKY_WORDS if w in text)
        total = c_score + r_score
        if total == 0:
            return 0.5
        return r_score / total
    
    def _analyze_language_style(self, text: str) -> float:
        """分析语言风格：0=随意, 1=正式（可配置关键词）"""
        ca_score = sum(1 for w in CASUAL_WORDS if w in text)
        f_score = sum(1 for w in FORMAL_WORDS if w in text)
        total = ca_score + f_score
        if total == 0:
            return 0.5
        return f_score / total
    
    def _extract_catchphrases(self, text: str) -> List[str]:
        """提取可能的口头禅（基于重复频率，非硬编码）"""
        import re
        from collections import Counter
        # 提取2-4字的重复短语（中文）
        phrases = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        counts = Counter(phrases)
        # 过滤掉常见非口头禅词（从外部可配置）
        exclude = _load_keyword_config(
            "TENT_PERSONA_CATCHPHRASE_EXCLUDE",
            ["我们", "我的", "他们", "这个", "那个", "什么", "怎么", "因为", "所以", "然后", "但是"]
        )
        return [p for p, c in counts.most_common(5) if c >= 2 and len(p) >= 2 and p not in exclude]
    
    def _extract_emotion_triggers(self, text: str) -> Dict[str, float]:
        """提取情绪触发词（可配置关键词）"""
        triggers = {}
        p_score = sum(1 for w in POSITIVE_WORDS if w in text)
        n_score = sum(1 for w in NEGATIVE_WORDS if w in text)
        if p_score + n_score > 0:
            triggers["positive_ratio"] = p_score / (p_score + n_score)
        return triggers
    
    def _save_annotation(self, user_id: str, session_id: str, anno_type: str,
                         content: str, confidence: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversation_annotations (user_id, session_id, annotation_type, content, confidence) VALUES (?, ?, ?, ?, ?)",
                (user_id, session_id, anno_type, content, confidence)
            )
    
    def _update_profile(self, user_id: str, features: Dict):
        """滑动窗口更新用户画像"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT decision_style, language_style FROM thought_profiles WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            
            alpha = 0.3  # 新数据权重
            new_decision = features.get("decision_bias", 0.5)
            new_language = features.get("language_formality", 0.5)
            
            if row:
                old_decision, old_language = row
                new_decision = old_decision * (1 - alpha) + new_decision * alpha
                new_language = old_language * (1 - alpha) + new_language * alpha
                conn.execute(
                    "UPDATE thought_profiles SET decision_style = ?, language_style = ?, updated_at = datetime('now') WHERE user_id = ?",
                    (new_decision, new_language, user_id)
                )
            else:
                conn.execute(
                    "INSERT INTO thought_profiles (user_id, decision_style, language_style) VALUES (?, ?, ?)",
                    (user_id, new_decision, new_language)
                )
    
    def get_profile(self, user_id: str) -> Optional[Dict]:
        """获取用户当前思维画像"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM thought_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "user_id": row["user_id"],
                "decision_style": row["decision_style"],
                "language_style": row["language_style"],
                "core_values": json.loads(row["core_values"]),
                "catchphrases": json.loads(row["catchphrases"]),
                "emotion_patterns": json.loads(row["emotion_patterns"]),
                "updated_at": row["updated_at"],
            }
    
    def update_profile_manual(self, user_id: str, updates: Dict) -> bool:
        """用户手动修正画像"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM thought_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            
            fields = []
            values = []
            if "decision_style" in updates:
                fields.append("decision_style = ?")
                values.append(updates["decision_style"])
            if "language_style" in updates:
                fields.append("language_style = ?")
                values.append(updates["language_style"])
            if "core_values" in updates:
                fields.append("core_values = ?")
                values.append(json.dumps(updates["core_values"], ensure_ascii=False))
            if "catchphrases" in updates:
                fields.append("catchphrases = ?")
                values.append(json.dumps(updates["catchphrases"], ensure_ascii=False))
            
            if not fields:
                return False
            
            values.append(user_id)
            sql = f"UPDATE thought_profiles SET {', '.join(fields)}, updated_at = datetime('now') WHERE user_id = ?"
            conn.execute(sql, values)
            return conn.total_changes > 0
    
    def get_soul_completeness(self, user_id: str) -> Dict[str, float]:
        """计算灵魂完成度（思维/声纹/形象）"""
        profile = self.get_profile(user_id)
        thought_score = 0.0
        if profile:
            has_decision = profile.get("decision_style", 0.5) != 0.5
            has_language = profile.get("language_style", 0.5) != 0.5
            has_values = len(profile.get("core_values", [])) > 0
            thought_score = (0.3 * (1 if has_decision else 0) +
                           0.3 * (1 if has_language else 0) +
                           0.4 * (1 if has_values else 0))
        
        # Phase 1: 声纹和形象用占位数据
        voice_samples = list((self.storage_path / "voice_samples").glob("*.wav")) if (self.storage_path / "voice_samples").exists() else []
        appearance_samples = list((self.storage_path / "appearance_samples").glob("*.jpg")) if (self.storage_path / "appearance_samples").exists() else []
        
        voice_score = min(1.0, len(voice_samples) / 10)
        appearance_score = min(1.0, len(appearance_samples) / 10)
        
        return {
            "thought": round(thought_score, 2),
            "voice": round(voice_score, 2),
            "appearance": round(appearance_score, 2),
            "overall": round((thought_score + voice_score + appearance_score) / 3, 2),
        }
