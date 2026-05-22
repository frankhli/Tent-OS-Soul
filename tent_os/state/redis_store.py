import asyncio
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

import redis.asyncio as redis

from tent_os.state.interface import SessionStateStore


class RedisSessionStateStore(SessionStateStore):
    """Redis + SQLite 混合会话状态存储
    
    设计：
    - Redis 作为高速缓存（TTL 7 天），支持实时读写
    - SQLite 作为持久化备份，Redis miss 时自动回退
    - 解决原 Redis TTL 1 小时导致会话丢失的问题
    - FIX: 每 session 一个 asyncio.Lock，避免并发 RMW race
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", ttl: int = 604800,
                 db_path: str = "./tent_scheduler.db"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.ttl = ttl  # 7 天（604800 秒）
        self.db_path = db_path
        self._init_sqlite()
        # FIX: 每 session 一个锁，避免 Read-Modify-Write race
        self._locks: Dict[str, asyncio.Lock] = {}
    
    def _init_sqlite(self):
        """初始化 SQLite 备份表"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                images TEXT,
                timestamp TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_messages_session_id 
            ON session_messages(session_id)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_snapshots (
                session_id TEXT PRIMARY KEY,
                task TEXT,
                plan TEXT,
                step INTEGER DEFAULT 1,
                user_id TEXT,
                title TEXT,
                created_at TEXT,
                updated_at TEXT,
                snapshot_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def _key(self, session_id: str) -> str:
        return f"tent:session:{session_id}"
    
    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """获取 session 级别的写锁，防止并发 RMW race"""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]
    
    async def create(self, session_id: str, task: str = "", tools: List[Dict] = None,
                     user_id: str = None, title: str = None) -> None:
        now = datetime.now().isoformat()
        state = {
            "task": task,
            "tools": tools or [],
            "step": 1,
            "plan": None,
            "user_id": user_id,
            "title": title or task[:30] if task else "新会话",
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        # 1. 先持久化到 SQLite（作为事实来源）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_backup_snapshot, session_id, state)
        
        # 2. 再写入 Redis（缓存层）
        await self.redis.setex(self._key(session_id), self.ttl, json.dumps(state, ensure_ascii=False))
        # 索引：用户会话列表
        if user_id:
            await self.redis.zadd(f"tent:user_sessions:{user_id}", {session_id: datetime.now().timestamp()})
            await self.redis.expire(f"tent:user_sessions:{user_id}", self.ttl * 7)
    
    async def load(self, session_id: str) -> Dict:
        data = await self.redis.get(self._key(session_id))
        if data:
            return json.loads(data)
        
        # Redis miss，尝试从 SQLite 回退
        loop = asyncio.get_event_loop()
        snapshot = await loop.run_in_executor(None, self._sync_load_snapshot_from_sqlite, session_id)
        if snapshot:
            # 恢复到 Redis（延长生命周期）
            await self.redis.setex(self._key(session_id), self.ttl,
                                   json.dumps(snapshot, ensure_ascii=False))
            return snapshot
        
        raise KeyError(f"会话不存在或已过期: {session_id}")
    
    async def update_plan(self, session_id: str, plan: Dict, step: int = 1) -> None:
        async with self._get_lock(session_id):
            state = await self.load(session_id)
            state["plan"] = plan
            state["step"] = step
            state["updated_at"] = datetime.now().isoformat()
            # 1. 先持久化到 SQLite（事实来源）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_backup_snapshot, session_id, state)
            # 2. 再写入 Redis（缓存层）
            await self.redis.setex(self._key(session_id), self.ttl, json.dumps(state, ensure_ascii=False))
    
    async def advance_step(self, session_id: str) -> int:
        async with self._get_lock(session_id):
            state = await self.load(session_id)
            state["step"] = state.get("step", 1) + 1
            state["updated_at"] = datetime.now().isoformat()
            # 1. 先持久化到 SQLite（事实来源）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_backup_snapshot, session_id, state)
            # 2. 再写入 Redis（缓存层）
            await self.redis.setex(self._key(session_id), self.ttl, json.dumps(state, ensure_ascii=False))
            return state["step"]
    
    async def get_step(self, session_id: str) -> int:
        state = await self.load(session_id)
        return state.get("step", 1)
    
    async def get_plan(self, session_id: str) -> Optional[Dict]:
        state = await self.load(session_id)
        return state.get("plan")
    
    async def delete(self, session_id: str) -> None:
        state = await self.load(session_id)
        user_id = state.get("user_id")
        await self.redis.delete(self._key(session_id))
        if user_id:
            await self.redis.zrem(f"tent:user_sessions:{user_id}", session_id)
    
    def _sync_backup_message(self, session_id: str, role: str, content: str,
                              images: List[str], timestamp: str) -> bool:
        """同步备份消息到 SQLite（在线程池中执行）"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO session_messages (session_id, role, content, images, timestamp) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content,
                 json.dumps(images, ensure_ascii=False) if images else None,
                 timestamp)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"SQLite 消息备份失败 [{session_id}]: {e}")
            return False
    
    def _sync_backup_snapshot(self, session_id: str, state: Dict) -> bool:
        """同步备份会话快照到 SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO session_snapshots 
                   (session_id, task, plan, step, user_id, title, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id,
                 state.get("task", ""),
                 json.dumps(state.get("plan"), ensure_ascii=False) if state.get("plan") else None,
                 state.get("step", 1),
                 state.get("user_id"),
                 state.get("title"),
                 state.get("created_at"),
                 state.get("updated_at"))
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"SQLite 快照备份失败 [{session_id}]: {e}")
            return False
    
    def _sync_load_messages_from_sqlite(self, session_id: str, limit: int = 100) -> List[Dict]:
        """从 SQLite 加载消息"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT role, content, images, timestamp FROM session_messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            conn.close()
            msgs = []
            for row in reversed(rows):
                msg = {
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["timestamp"]
                }
                if row["images"]:
                    try:
                        msg["images"] = json.loads(row["images"])
                    except json.JSONDecodeError:
                        pass
                msgs.append(msg)
            return msgs
        except Exception:
            return []
    
    def _sync_load_snapshot_from_sqlite(self, session_id: str) -> Optional[Dict]:
        """从 SQLite 加载会话快照"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM session_snapshots WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                plan = None
                if row["plan"]:
                    try:
                        plan = json.loads(row["plan"])
                    except json.JSONDecodeError:
                        pass
                return {
                    "task": row["task"] or "",
                    "tools": [],
                    "step": row["step"] or 1,
                    "plan": plan,
                    "user_id": row["user_id"],
                    "title": row["title"] or "未命名会话",
                    "messages": self._sync_load_messages_from_sqlite(session_id),
                    "created_at": row["created_at"] or datetime.now().isoformat(),
                    "updated_at": row["updated_at"] or datetime.now().isoformat(),
                }
            return None
        except Exception:
            return None
    
    async def append_message(self, session_id: str, role: str, content: str, images: List[str] = None) -> None:
        async with self._get_lock(session_id):
            state = await self.load(session_id)
            state["messages"] = state.get("messages", [])
            timestamp = datetime.now().isoformat()
            msg = {
                "role": role,
                "content": content or "",
                "timestamp": timestamp
            }
            if images:
                msg["images"] = images
            state["messages"].append(msg)
            state["updated_at"] = timestamp
            
            # 1. 先持久化到 SQLite（事实来源）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_backup_message,
                                       session_id, role, content, images, timestamp)
            await loop.run_in_executor(None, self._sync_backup_snapshot, session_id, state)
            
            # 2. 再写入 Redis（缓存层）
            await self.redis.setex(self._key(session_id), self.ttl, json.dumps(state, ensure_ascii=False))
    
    async def get_messages(self, session_id: str, limit: int = 100) -> List[Dict]:
        try:
            state = await self.load(session_id)
            msgs = state.get("messages", [])
            return msgs[-limit:] if len(msgs) > limit else msgs
        except KeyError:
            # Redis miss，从 SQLite 回退
            loop = asyncio.get_event_loop()
            msgs = await loop.run_in_executor(None, self._sync_load_messages_from_sqlite, session_id, limit)
            if msgs:
                return msgs
            raise
    
    async def update_title(self, session_id: str, title: str) -> None:
        async with self._get_lock(session_id):
            state = await self.load(session_id)
            state["title"] = title
            state["updated_at"] = datetime.now().isoformat()
            # 1. 先持久化到 SQLite（事实来源）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_backup_snapshot, session_id, state)
            # 2. 再写入 Redis（缓存层）
            await self.redis.setex(self._key(session_id), self.ttl, json.dumps(state, ensure_ascii=False))
    
    async def update(self, session_id: str, updates: Dict) -> None:
        async with self._get_lock(session_id):
            state = await self.load(session_id)
            state.update(updates)
            state["updated_at"] = datetime.now().isoformat()
            # 1. 先持久化到 SQLite（事实来源）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_backup_snapshot, session_id, state)
            # 2. 再写入 Redis（缓存层）
            await self.redis.setex(self._key(session_id), self.ttl, json.dumps(state, ensure_ascii=False))
    
    async def list_sessions(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        if not user_id:
            return []
        session_ids = await self.redis.zrevrange(f"tent:user_sessions:{user_id}", 0, limit - 1)
        sessions = []
        for sid in session_ids:
            try:
                state = await self.load(sid)
                sessions.append({
                    "session_id": sid,
                    "title": state.get("title", "未命名会话"),
                    "updated_at": state.get("updated_at", state.get("created_at")),
                    "message_count": len(state.get("messages", [])),
                })
            except KeyError:
                pass  # 会话已过期
        return sessions
    
    async def ping(self) -> bool:
        try:
            return await self.redis.ping()
        except Exception:
            return False
    
    async def get_retry_count(self, session_id: str) -> int:
        """从 Redis 获取重试计数（治理进程完全无状态化）"""
        try:
            data = await self.redis.get(f"tent:retry:{session_id}")
            return int(data) if data else 0
        except Exception:
            return 0
    
    async def set_retry_count(self, session_id: str, count: int) -> None:
        """写入 Redis 重试计数（TTL 1 小时，任务期间有效）"""
        try:
            await self.redis.setex(f"tent:retry:{session_id}", 3600, str(count))
        except Exception:
            pass
    
    async def clear_retry_count(self, session_id: str) -> None:
        """清除 Redis 重试计数"""
        try:
            await self.redis.delete(f"tent:retry:{session_id}")
        except Exception:
            pass
