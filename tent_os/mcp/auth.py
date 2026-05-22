"""MCP 认证模块 —— OAuth2.0 Bearer Token 简化实现

为第三方设备接入提供安全认证：
1. 设备注册：获取 client_id + client_secret
2. 获取 Token：用 client_credentials 换取 access_token
3. 调用 MCP：在 Authorization header 中携带 Bearer token
4. Token 失效：支持吊销和过期
"""

import hashlib
import secrets
import time
from typing import Dict, Optional, List
from datetime import datetime, timedelta

from tent_os.logging_config import get_logger

logger = get_logger()


class MCPAuthManager:
    """MCP 认证管理器"""

    def __init__(self, db_path: str = "./tent_memory/mcp_auth.db"):
        self.db_path = db_path
        self._ensure_tables()
        # 内存缓存：token -> auth_context
        self._token_cache: Dict[str, Dict] = {}
        self._token_cache_ttl = 300  # 5 分钟

    def _ensure_tables(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_clients (
                    client_id TEXT PRIMARY KEY,
                    client_secret TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    device_name TEXT,
                    device_type TEXT,
                    permissions TEXT,  -- JSON array
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_tokens (
                    token TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    expires_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    revoked INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT,
                    client_id TEXT,
                    user_id TEXT,
                    method TEXT,
                    tool_name TEXT,
                    success INTEGER,
                    error TEXT,
                    ip_address TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def register_client(self, user_id: str, device_name: str, device_type: str = "robot",
                        permissions: Optional[List[str]] = None) -> Dict:
        """注册第三方设备客户端"""
        client_id = f"mcp_{secrets.token_hex(8)}"
        client_secret = secrets.token_urlsafe(32)
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()

        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO mcp_clients (client_id, client_secret, user_id, device_name, device_type, permissions) VALUES (?, ?, ?, ?, ?, ?)",
                (client_id, secret_hash, user_id, device_name, device_type,
                 __import__('json').dumps(permissions or ["chat", "query_persona", "query_memories", "synthesize_tts"]))
            )

        logger.info(f"[MCP] 客户端注册: {client_id} ({device_name}, {device_type})")
        return {
            "client_id": client_id,
            "client_secret": client_secret,  # 仅返回一次
            "user_id": user_id,
        }

    def authenticate(self, client_id: str, client_secret: str) -> Optional[Dict]:
        """验证客户端凭据并发放 token"""
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()

        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM mcp_clients WHERE client_id = ? AND client_secret = ? AND is_active = 1",
                (client_id, secret_hash)
            ).fetchone()

        if not row:
            return None

        # 生成 access_token
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO mcp_tokens (token, client_id, user_id, expires_at) VALUES (?, ?, ?, ?)",
                (token, client_id, row["user_id"], expires_at)
            )

        auth_context = {
            "client_id": client_id,
            "user_id": row["user_id"],
            "device_name": row["device_name"],
            "device_type": row["device_type"],
            "permissions": __import__('json').loads(row["permissions"] or "[]"),
        }
        self._token_cache[token] = auth_context
        return {"access_token": token, "expires_at": expires_at, **auth_context}

    def verify_token(self, token: str) -> Optional[Dict]:
        """验证 access_token"""
        # 检查内存缓存
        cached = self._token_cache.get(token)
        if cached:
            return cached

        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT t.*, c.device_name, c.device_type, c.permissions FROM mcp_tokens t JOIN mcp_clients c ON t.client_id = c.client_id WHERE t.token = ? AND t.revoked = 0 AND t.expires_at > datetime('now')",
                (token,)
            ).fetchone()

        if not row:
            return None

        auth_context = {
            "client_id": row["client_id"],
            "user_id": row["user_id"],
            "device_name": row["device_name"],
            "device_type": row["device_type"],
            "permissions": __import__('json').loads(row["permissions"] or "[]"),
        }
        self._token_cache[token] = auth_context
        return auth_context

    def revoke_token(self, token: str) -> bool:
        """吊销 token"""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE mcp_tokens SET revoked = 1 WHERE token = ?", (token,))
        self._token_cache.pop(token, None)
        return True

    def revoke_client(self, client_id: str) -> bool:
        """吊销客户端（所有 token 失效）"""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE mcp_clients SET is_active = 0 WHERE client_id = ?", (client_id,))
            conn.execute("UPDATE mcp_tokens SET revoked = 1 WHERE client_id = ?", (client_id,))
        # 清除相关缓存
        self._token_cache = {k: v for k, v in self._token_cache.items() if v.get("client_id") != client_id}
        return True

    def get_clients(self, user_id: str) -> List[Dict]:
        """获取用户的所有注册设备"""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT client_id, user_id, device_name, device_type, permissions, created_at, is_active FROM mcp_clients WHERE user_id = ?",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def audit_log(self, token: str, client_id: str, user_id: str, method: str,
                  tool_name: Optional[str] = None, success: bool = True,
                  error: Optional[str] = None, ip_address: Optional[str] = None):
        """记录审计日志"""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO mcp_audit (token, client_id, user_id, method, tool_name, success, error, ip_address) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (token, client_id, user_id, method, tool_name, int(success), error, ip_address)
            )

    def get_audit_log(self, user_id: str, limit: int = 100) -> List[Dict]:
        """获取审计日志"""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM mcp_audit WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]
