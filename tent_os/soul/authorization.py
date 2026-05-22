"""授权管理引擎 —— 改造自治理进程的隐私授权与遗嘱管理"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from tent_os.logging_config import get_logger

logger = get_logger()


class AuthorizationEngine:
    """
    授权管理引擎（改造自治理进程）
    
    管理：
    - 继承人设置
    - 可问主题白名单/黑名单
    - 激活条件（离世后/指定日期）
    - 所有交互审计日志
    """
    
    def __init__(self, storage_path: str = "./tent_memory/soul"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "authorization.db"
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS wills (
                    user_id TEXT PRIMARY KEY,
                    heirs TEXT DEFAULT '[]',
                    topic_whitelist TEXT DEFAULT '[]',
                    topic_blacklist TEXT DEFAULT '[]',
                    activation_condition TEXT DEFAULT 'after_death',
                    activation_date TEXT,
                    farewell_letter TEXT DEFAULT '',
                    access_code TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS access_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    heir_id TEXT,
                    action TEXT,
                    topic TEXT,
                    allowed INTEGER,
                    reason TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS heir_profiles (
                    heir_id TEXT PRIMARY KEY,
                    name TEXT,
                    relationship TEXT,
                    contact TEXT,
                    auth_token_hash TEXT,
                    permissions TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
            """)
            # 迁移：为旧表添加 farewell_letter 和 access_code 列
            cursor = conn.execute("PRAGMA table_info(wills)")
            columns = [row[1] for row in cursor.fetchall()]
            if "farewell_letter" not in columns:
                conn.execute("ALTER TABLE wills ADD COLUMN farewell_letter TEXT DEFAULT ''")
            if "access_code" not in columns:
                conn.execute("ALTER TABLE wills ADD COLUMN access_code TEXT DEFAULT ''")
    
    def set_will(self, user_id: str, will_data: Dict) -> Dict:
        """设置/更新遗嘱"""
        heirs = json.dumps(will_data.get("heirs", []), ensure_ascii=False)
        whitelist = json.dumps(will_data.get("topic_whitelist", []), ensure_ascii=False)
        blacklist = json.dumps(will_data.get("topic_blacklist", []), ensure_ascii=False)
        activation = will_data.get("activation_condition", "after_death")
        activation_date = will_data.get("activation_date")
        farewell_letter = will_data.get("farewell_letter", "") or ""
        access_code = will_data.get("access_code", "") or ""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO wills (user_id, heirs, topic_whitelist, topic_blacklist, activation_condition, activation_date, farewell_letter, access_code, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    heirs = excluded.heirs,
                    topic_whitelist = excluded.topic_whitelist,
                    topic_blacklist = excluded.topic_blacklist,
                    activation_condition = excluded.activation_condition,
                    activation_date = excluded.activation_date,
                    farewell_letter = excluded.farewell_letter,
                    access_code = excluded.access_code,
                    updated_at = datetime('now')
            """, (user_id, heirs, whitelist, blacklist, activation, activation_date, farewell_letter, access_code))
        
        logger.info(f"[SOUL] 遗嘱已更新 [{user_id}]")
        return {"status": "ok", "user_id": user_id}
    
    def get_will(self, user_id: str) -> Optional[Dict]:
        """获取用户遗嘱"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM wills WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return None
            return {
                "user_id": row["user_id"],
                "heirs": json.loads(row["heirs"]),
                "topic_whitelist": json.loads(row["topic_whitelist"]),
                "topic_blacklist": json.loads(row["topic_blacklist"]),
                "activation_condition": row["activation_condition"],
                "activation_date": row["activation_date"],
                "farewell_letter": row["farewell_letter"] if "farewell_letter" in row.keys() else "",
                "access_code": row["access_code"] if "access_code" in row.keys() else "",
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
    
    def check_access(self, user_id: str, heir_id: str, topic: str = None) -> Dict:
        """检查继承人是否有权访问"""
        will = self.get_will(user_id)
        if not will:
            return {"allowed": False, "reason": "未找到遗嘱设置"}
        
        if not will["is_active"] and will["activation_condition"] == "after_death":
            return {"allowed": False, "reason": "遗嘱尚未激活（用户仍在世）"}
        
        heirs = will["heirs"]
        heir = next((h for h in heirs if h.get("id") == heir_id), None)
        if not heir:
            return {"allowed": False, "reason": "非授权继承人"}
        
        # 检查主题白名单/黑名单
        whitelist = will["topic_whitelist"]
        blacklist = will["topic_blacklist"]
        
        if whitelist and topic and topic not in whitelist:
            self._log_access(user_id, heir_id, "chat", topic, False, "主题不在白名单中")
            return {"allowed": False, "reason": "该主题不在可访问白名单中"}
        
        if blacklist and topic and topic in blacklist:
            self._log_access(user_id, heir_id, "chat", topic, False, "主题在黑名单中")
            return {"allowed": False, "reason": "该主题被明确禁止"}
        
        self._log_access(user_id, heir_id, "chat", topic, True, "授权通过")
        return {"allowed": True, "reason": "授权通过"}
    
    def _log_access(self, user_id: str, heir_id: str, action: str, topic: str, allowed: bool, reason: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO access_logs (user_id, heir_id, action, topic, allowed, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, heir_id, action, topic, int(allowed), reason)
            )
    
    def deactivate_will(self, user_id: str) -> Dict:
        """停用遗嘱（用户生前可随时撤销）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE wills SET is_active = 0, updated_at = datetime('now') WHERE user_id = ?",
                (user_id,)
            )
        logger.info(f"[SOUL] 遗嘱已停用 [{user_id}]")
        return {"status": "ok", "activated": False, "user_id": user_id}
    
    def verify_heir(self, user_id: str, heir_name: str, access_code: str = "") -> Dict:
        """验证继承人身份。匹配姓名 + 可选访问验证码"""
        will = self.get_will(user_id)
        if not will:
            return {"valid": False, "reason": "未找到遗嘱设置"}
        if not will["is_active"]:
            return {"valid": False, "reason": "遗嘱尚未激活"}
        
        # Check access code if set
        stored_code = will.get("access_code", "")
        if stored_code and stored_code != access_code:
            return {"valid": False, "reason": "访问验证码错误"}
        
        heirs = will["heirs"]
        for h in heirs:
            if h.get("name") == heir_name:
                return {
                    "valid": True,
                    "heir_id": h.get("id"),
                    "heir_name": h.get("name"),
                    "relationship": h.get("relationship"),
                    "user_id": user_id,
                }
        return {"valid": False, "reason": "姓名不匹配任何继承人"}
    
    def get_access_logs(self, user_id: str, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM access_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]
    
    def activate_will(self, user_id: str) -> Dict:
        """激活遗嘱（用户离世后由系统或管理员触发）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE wills SET is_active = 1, updated_at = datetime('now') WHERE user_id = ?",
                (user_id,)
            )
            if conn.total_changes > 0:
                logger.info(f"[SOUL] 遗嘱已激活 [{user_id}]")
                return {"status": "ok", "message": "遗嘱已激活", "activated": True}
            # 可能遗嘱已经激活，查询确认
            row = conn.execute(
                "SELECT is_active FROM wills WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if row and row[0] == 1:
                return {"status": "ok", "message": "遗嘱已激活", "activated": True}
            return {"status": "error", "message": "未找到遗嘱", "activated": False}
