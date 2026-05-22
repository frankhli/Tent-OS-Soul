"""认知图谱（Cognitive Graph）—— Tent OS 2.0 核心记忆架构

在现有 L0/L1/L2 层级存储之上，增加图结构层：
- 记忆节点（带置信度、时间、来源、类型）
- 关系边（因果、相似、矛盾、时序、层级）
- 支持多跳推理、时序推理、矛盾检测

数据库：SQLite（零依赖），使用 CTE 递归做多跳查询

图结构：
    nodes: 记忆节点表
    edges: 关系边表
    
节点类型（memory_type）：
    fact        —— 事实
    preference  —— 偏好
    entity      —— 实体（人、项目、地点）
    event       —— 事件
    pattern     —— 模式/规律
    belief      —— 信念（可能变化）
    
关系类型（relation_type）：
    causal          —— 因果关系（A 导致 B）
    similar         —— 相似关系（A 像 B）
    contradictory   —— 矛盾关系（A 与 B 矛盾）
    temporal        —— 时序关系（A 发生在 B 之前/之后）
    hierarchical    —— 层级关系（A 属于 B）
    related         —— 一般关联
"""

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("tent_os.memory.graph")


@dataclass
class MemoryNode:
    """记忆节点——认知图谱的基本单元"""
    id: str                    # 唯一标识（URI 或 hash）
    content: str               # 内容摘要
    content_hash: str          # 内容哈希（去重用）
    confidence: float          # 置信度 0-1
    created_at: datetime
    updated_at: datetime
    source_session: str        # 来源会话 ID
    source_chunk: str          # 来源 L0 chunk URI
    memory_type: str           # fact/preference/entity/event/pattern/belief
    
    # 时间维度（支持"当时正确，现在过时"）
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    
    # 访问统计
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    
    # 验证状态
    verification_count: int = 0
    contradiction_count: int = 0


@dataclass
class MemoryEdge:
    """记忆关系边——连接两个节点的关系"""
    source_id: str             # 源节点 ID
    target_id: str             # 目标节点 ID
    relation_type: str         # causal/similar/contradictory/temporal/hierarchical/related
    strength: float            # 关系强度 0-1
    evidence: str              # 关系依据
    created_at: datetime
    
    # 双向关系的方向性标记（时序关系用）
    direction: Optional[str] = None  # "before" / "after" / "contains" / None


class CognitiveGraph:
    """认知图谱管理器
    
    职责：
    1. 维护记忆节点和关系边的持久化存储
    2. 提供图查询能力（多跳、时序、矛盾检测）
    3. 支持置信度演化和遗忘机制
    4. 与 L0/L1/L2 存储层双向同步
    """
    
    def __init__(self, db_path: str = "./tent_memory/graph.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        """初始化图数据库表结构
        
        FIX: WAL 模式 + busy_timeout，防止多进程锁竞争
        """
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        
        # 节点表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_session TEXT,
                source_chunk TEXT,
                memory_type TEXT DEFAULT 'fact',
                valid_from TEXT,
                valid_to TEXT,
                access_count INTEGER DEFAULT 0,
                last_accessed TEXT,
                verification_count INTEGER DEFAULT 0,
                contradiction_count INTEGER DEFAULT 0
            )
        """)
        
        # 边表
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                strength REAL DEFAULT 0.5,
                evidence TEXT,
                created_at TEXT NOT NULL,
                direction TEXT,
                UNIQUE(source_id, target_id, relation_type)
            )
        """)
        
        # 索引
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(memory_type)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_confidence ON nodes(confidence DESC)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_created ON nodes(created_at DESC)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(relation_type)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_nodes_hash ON nodes(content_hash)")
        
        self.db.commit()
    
    # ========== 节点操作 ==========
    
    def add_node(self, node: MemoryNode) -> bool:
        """添加或更新节点
        
        Returns:
            bool: True 如果是新节点，False 如果是更新已有节点
        """
        # 检查是否已存在（通过 content_hash 去重）
        existing = self.db.execute(
            "SELECT id, confidence FROM nodes WHERE content_hash = ?",
            (node.content_hash,)
        ).fetchone()
        
        if existing:
            # 更新已有节点（提升置信度、更新时间）
            self.db.execute(
                """UPDATE nodes SET
                    content = ?, confidence = max(confidence, ?),
                    updated_at = ?, access_count = access_count + 1,
                    verification_count = verification_count + 1,
                    last_accessed = ?
                WHERE id = ?""",
                (node.content, node.confidence, node.updated_at.isoformat(),
                 datetime.now().isoformat(), existing["id"])
            )
            self.db.commit()
            logger.debug(f"节点更新: {existing['id']} (confidence: {existing['confidence']:.2f})")
            return False
        
        # 插入新节点
        self.db.execute(
            """INSERT INTO nodes
                (id, content, content_hash, confidence, created_at, updated_at,
                 source_session, source_chunk, memory_type, valid_from, valid_to,
                 access_count, last_accessed, verification_count, contradiction_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (node.id, node.content, node.content_hash, node.confidence,
             node.created_at.isoformat(), node.updated_at.isoformat(),
             node.source_session, node.source_chunk, node.memory_type,
             node.valid_from.isoformat() if node.valid_from else None,
             node.valid_to.isoformat() if node.valid_to else None,
             node.access_count, node.last_accessed.isoformat() if node.last_accessed else None,
             node.verification_count, node.contradiction_count)
        )
        self.db.commit()
        logger.debug(f"节点新增: {node.id} ({node.memory_type})")
        return True
    
    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        """根据 ID 获取节点"""
        row = self.db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not row:
            return None
        return self._row_to_node(row)
    
    def find_by_content_hash(self, content_hash: str) -> Optional[MemoryNode]:
        """根据内容哈希查找节点"""
        row = self.db.execute("SELECT * FROM nodes WHERE content_hash = ?", (content_hash,)).fetchone()
        if not row:
            return None
        return self._row_to_node(row)
    
    def update_confidence(self, node_id: str, delta: float) -> float:
        """更新节点置信度（增量）
        
        Returns:
            float: 更新后的置信度
        """
        self.db.execute(
            "UPDATE nodes SET confidence = max(0.0, min(1.0, confidence + ?)), updated_at = ? WHERE id = ?",
            (delta, datetime.now().isoformat(), node_id)
        )
        self.db.commit()
        row = self.db.execute("SELECT confidence FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return row["confidence"] if row else 0.0
    
    def record_access(self, node_id: str):
        """记录节点被访问"""
        self.db.execute(
            "UPDATE nodes SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            (datetime.now().isoformat(), node_id)
        )
        self.db.commit()
    
    def record_contradiction(self, node_id: str):
        """记录节点被矛盾"""
        self.db.execute(
            "UPDATE nodes SET contradiction_count = contradiction_count + 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), node_id)
        )
        self.db.commit()
    
    def delete_node(self, node_id: str):
        """删除节点及其所有边"""
        self.db.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
        self.db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        self.db.commit()
    
    # ========== 边操作 ==========
    
    def add_edge(self, edge: MemoryEdge) -> bool:
        """添加或更新关系边
        
        Returns:
            bool: True 如果是新边
        """
        # 检查是否已存在
        existing = self.db.execute(
            "SELECT strength FROM edges WHERE source_id = ? AND target_id = ? AND relation_type = ?",
            (edge.source_id, edge.target_id, edge.relation_type)
        ).fetchone()
        
        if existing:
            # 更新强度（取平均值，表示多次确认）
            new_strength = (existing["strength"] + edge.strength) / 2
            self.db.execute(
                "UPDATE edges SET strength = ?, evidence = ? WHERE source_id = ? AND target_id = ? AND relation_type = ?",
                (new_strength, edge.evidence,
                 edge.source_id, edge.target_id, edge.relation_type)
            )
            self.db.commit()
            return False
        
        self.db.execute(
            """INSERT INTO edges
                (source_id, target_id, relation_type, strength, evidence, created_at, direction)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (edge.source_id, edge.target_id, edge.relation_type,
             edge.strength, edge.evidence, edge.created_at.isoformat(), edge.direction)
        )
        self.db.commit()
        return True
    
    def get_edges(self, node_id: str, relation_type: Optional[str] = None,
                  direction: str = "outgoing") -> List[MemoryEdge]:
        """获取节点的关系边
        
        Args:
            direction: "outgoing"（作为源） / "incoming"（作为目标） / "both"
        """
        edges = []
        
        if direction in ("outgoing", "both"):
            if relation_type:
                rows = self.db.execute(
                    "SELECT * FROM edges WHERE source_id = ? AND relation_type = ?",
                    (node_id, relation_type)
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM edges WHERE source_id = ?", (node_id,)
                ).fetchall()
            edges.extend(self._rows_to_edges(rows))
        
        if direction in ("incoming", "both"):
            if relation_type:
                rows = self.db.execute(
                    "SELECT * FROM edges WHERE target_id = ? AND relation_type = ?",
                    (node_id, relation_type)
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT * FROM edges WHERE target_id = ?", (node_id,)
                ).fetchall()
            edges.extend(self._rows_to_edges(rows))
        
        return edges
    
    def delete_edge(self, source_id: str, target_id: str, relation_type: str):
        """删除特定关系边"""
        self.db.execute(
            "DELETE FROM edges WHERE source_id = ? AND target_id = ? AND relation_type = ?",
            (source_id, target_id, relation_type)
        )
        self.db.commit()
    
    # ========== 批量查询 ==========
    
    def get_nodes_by_type(self, memory_type: str, min_confidence: float = 0.0,
                          limit: int = 100) -> List[MemoryNode]:
        """按类型获取节点"""
        rows = self.db.execute(
            """SELECT * FROM nodes
               WHERE memory_type = ? AND confidence >= ?
               ORDER BY confidence DESC, created_at DESC
               LIMIT ?""",
            (memory_type, min_confidence, limit)
        ).fetchall()
        return [self._row_to_node(r) for r in rows]
    
    def get_recent_nodes(self, hours: int = 24, limit: int = 50) -> List[MemoryNode]:
        """获取最近创建的节点"""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = self.db.execute(
            "SELECT * FROM nodes WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        return [self._row_to_node(r) for r in rows]
    
    def search_nodes(self, keyword: str, limit: int = 20) -> List[MemoryNode]:
        """关键词搜索节点"""
        pattern = f"%{keyword}%"
        rows = self.db.execute(
            """SELECT * FROM nodes
               WHERE content LIKE ? OR source_session LIKE ?
               ORDER BY confidence DESC, access_count DESC
               LIMIT ?""",
            (pattern, pattern, limit)
        ).fetchall()
        return [self._row_to_node(r) for r in rows]
    
    def get_all_nodes(self, limit: int = 1000) -> List[MemoryNode]:
        """获取所有节点"""
        rows = self.db.execute(
            "SELECT * FROM nodes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_node(r) for r in rows]
    
    def get_statistics(self) -> Dict:
        """获取图谱统计信息"""
        node_count = self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = self.db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        
        type_counts = {}
        for row in self.db.execute("SELECT memory_type, COUNT(*) as cnt FROM nodes GROUP BY memory_type"):
            type_counts[row["memory_type"]] = row["cnt"]
        
        relation_counts = {}
        for row in self.db.execute("SELECT relation_type, COUNT(*) as cnt FROM edges GROUP BY relation_type"):
            relation_counts[row["relation_type"]] = row["cnt"]
        
        avg_confidence = self.db.execute("SELECT AVG(confidence) FROM nodes").fetchone()[0] or 0
        
        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "type_distribution": type_counts,
            "relation_distribution": relation_counts,
            "avg_confidence": round(avg_confidence, 3),
        }
    
    # ========== 辅助方法 ==========
    
    def _row_to_node(self, row: sqlite3.Row) -> MemoryNode:
        """将数据库行转换为 MemoryNode"""
        return MemoryNode(
            id=row["id"],
            content=row["content"],
            content_hash=row["content_hash"],
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            source_session=row["source_session"] or "",
            source_chunk=row["source_chunk"] or "",
            memory_type=row["memory_type"] or "fact",
            valid_from=datetime.fromisoformat(row["valid_from"]) if row["valid_from"] else None,
            valid_to=datetime.fromisoformat(row["valid_to"]) if row["valid_to"] else None,
            access_count=row["access_count"] or 0,
            last_accessed=datetime.fromisoformat(row["last_accessed"]) if row["last_accessed"] else None,
            verification_count=row["verification_count"] or 0,
            contradiction_count=row["contradiction_count"] or 0,
        )
    
    def _rows_to_edges(self, rows: List[sqlite3.Row]) -> List[MemoryEdge]:
        """将数据库行列表转换为 MemoryEdge 列表"""
        edges = []
        for row in rows:
            edges.append(MemoryEdge(
                source_id=row["source_id"],
                target_id=row["target_id"],
                relation_type=row["relation_type"],
                strength=row["strength"],
                evidence=row["evidence"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
                direction=row["direction"],
            ))
        return edges
    
    def close(self):
        """关闭数据库连接"""
        self.db.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


def generate_node_id(content: str, source_session: str = "", source_chunk: str = "") -> str:
    """生成节点唯一 ID"""
    hash_input = f"{content}:{source_session}:{source_chunk}"
    return f"node_{hashlib.sha256(hash_input.encode()).hexdigest()[:16]}"


def generate_content_hash(content: str) -> str:
    """生成内容哈希（用于去重）"""
    return hashlib.md5(content.encode()).hexdigest()
