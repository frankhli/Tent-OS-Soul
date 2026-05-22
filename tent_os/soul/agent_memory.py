"""Agent 独立记忆存储 —— 每个 Agent 有自己的 L0/L1/L2 记忆体系"""

import sqlite3
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from tent_os.logging_config import get_logger

logger = get_logger()


class AgentMemoryStore:
    """Agent 专用记忆存储

    架构同 TieredMemoryStore，但按 agent_id 隔离：
    - L0: 摘要层（abstract + embedding）
    - L1: 结构化概览
    - L2: 完整内容文件存储
    """

    def __init__(self, agent_id: str, base_path: str = "./tent_memory/agents"):
        self.agent_id = agent_id
        self.storage_path = Path(base_path) / agent_id
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "memory.db"
        self._init_db()

    def _init_db(self):
        """初始化记忆数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS l0_index (
                    uri TEXT PRIMARY KEY,
                    abstract TEXT,
                    content_hash TEXT,
                    memory_type TEXT DEFAULT 'conversation',
                    created_at TEXT,
                    metadata JSON
                );
                CREATE INDEX IF NOT EXISTS idx_l0_type ON l0_index(memory_type);
                CREATE INDEX IF NOT EXISTS idx_l0_hash ON l0_index(content_hash);

                CREATE TABLE IF NOT EXISTS l1_index (
                    uri TEXT PRIMARY KEY,
                    overview TEXT,
                    overview_tokens INTEGER DEFAULT 0,
                    file_path TEXT,
                    created_at TEXT
                );
            """)

    async def ingest(self, content: str, uri: str, memory_type: str = "conversation",
                     metadata: Dict = None) -> None:
        """摄入内容到记忆"""
        chunk_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        # 检查重复
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT uri FROM l0_index WHERE content_hash = ? LIMIT 1", (chunk_hash,)
            ).fetchone()
            if existing:
                return

            # L0: 提取式摘要
            l0 = self._extract_abstract(content)

            # L2: 存储完整内容
            l2_path = self.storage_path / "full" / f"{uri.replace('/', '_')}.txt"
            l2_path.parent.mkdir(exist_ok=True)
            l2_path.write_text(content, encoding="utf-8")

            # 写入 L0
            conn.execute(
                "INSERT OR REPLACE INTO l0_index (uri, abstract, content_hash, memory_type, created_at, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                (uri, l0, chunk_hash, memory_type, datetime.now().isoformat(),
                 json.dumps(metadata or {}, ensure_ascii=False))
            )

            # 写入 L1（简化版，暂不调用 LLM）
            conn.execute(
                "INSERT OR REPLACE INTO l1_index (uri, overview, file_path, created_at) VALUES (?, ?, ?, ?)",
                (uri, l0[:200], str(l2_path), datetime.now().isoformat())
            )

        logger.debug(f"[AgentMemory:{self.agent_id}] 摄入记忆: {uri}")

    def _extract_abstract(self, text: str, max_len: int = 200) -> str:
        """提取式摘要"""
        text = text.strip()
        if len(text) <= max_len:
            return text
        # 简单策略：取前 max_len-3 字符 + "..."
        return text[:max_len - 3] + "..."

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """关键词搜索记忆"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # 简单的 LIKE 搜索（后续可升级向量搜索）
            pattern = f"%{query}%"
            rows = conn.execute(
                """SELECT l0.uri, l0.abstract, l1.overview, l0.memory_type, l0.created_at
                   FROM l0_index l0
                   LEFT JOIN l1_index l1 ON l0.uri = l1.uri
                   WHERE l0.abstract LIKE ? OR l1.overview LIKE ?
                   ORDER BY l0.created_at DESC LIMIT ?""",
                (pattern, pattern, limit)
            ).fetchall()
            return [
                {
                    "uri": r["uri"],
                    "abstract": r["abstract"],
                    "overview": r["overview"] or r["abstract"],
                    "memory_type": r["memory_type"],
                    "created_at": r["created_at"],
                } for r in rows
            ]

    def get_recent(self, limit: int = 10) -> List[Dict]:
        """获取最近记忆"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT uri, abstract, memory_type, created_at FROM l0_index
                   ORDER BY created_at DESC LIMIT ?""", (limit,)
            ).fetchall()
            return [
                {"uri": r["uri"], "abstract": r["abstract"],
                 "memory_type": r["memory_type"], "created_at": r["created_at"]}
                for r in rows
            ]

    def get_stats(self) -> Dict:
        """获取记忆统计"""
        with sqlite3.connect(self.db_path) as conn:
            l0_count = conn.execute("SELECT COUNT(*) FROM l0_index").fetchone()[0]
            l1_count = conn.execute("SELECT COUNT(*) FROM l1_index").fetchone()[0]
            return {"l0_count": l0_count, "l1_count": l1_count}
