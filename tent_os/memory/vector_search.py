"""纯 Python 向量检索——绕过 sqlite-vec 扩展限制

关键设计（修复 OpenViking #1549）：
- 只搜索 L0 索引层，绝不直接返回 L2 内容
- 返回结果包含 L1 概览（如果可用）
- L2 只通过 TieredMemoryStore.read_l2_content(uri) 按需读取
"""

import struct
import sqlite3
from typing import List, Dict, Optional
import numpy as np


class PurePythonVectorSearch:
    """纯 Python 向量语义搜索 —— 只搜 L0 层"""
    
    def __init__(self, db: sqlite3.Connection):
        self.db = db
    
    def search(self, query_vector: List[float], limit: int = 5,
               memory_type: str = None, days: int = None, persona: str = None) -> List[Dict]:
        """语义搜索：计算查询向量与所有 L0 存储向量的余弦相似度
        
        返回结果只包含 L0 摘要 + L1 概览，绝不包含 L2 完整内容。
        """
        query_vec = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        
        conditions = ["l0.embedding IS NOT NULL"]
        params = []
        if memory_type:
            conditions.append("l0.memory_type = ?")
            params.append(memory_type)
        if days:
            conditions.append(f"l0.created_at >= datetime('now', '-{days} days')")
        if persona:
            conditions.append("(l0.persona = ? OR l0.persona = '__shared__' OR l0.persona IS NULL)")
            params.append(persona)
        
        where_clause = " AND ".join(conditions)
        
        # 只搜 L0，JOIN L1 获取概览，绝不返回 L2 内容
        cursor = self.db.execute(
            f"""SELECT l0.uri, l0.abstract, l0.memory_type, l0.created_at,
                       l1.overview
                FROM l0_index l0
                LEFT JOIN l1_index l1 ON l0.uri = l1.uri
                WHERE {where_clause}""",
            params
        )
        
        results = []
        for row in cursor.fetchall():
            uri, abstract, mem_type, created_at, overview = row
            
            # 获取 L0 的 embedding（从 l0_index 的 embedding 字段）
            emb_cursor = self.db.execute(
                "SELECT embedding FROM l0_index WHERE uri = ?", (uri,)
            )
            emb_row = emb_cursor.fetchone()
            if not emb_row or not emb_row[0]:
                continue
            
            stored_vec = self._deserialize_vector(emb_row[0])
            if stored_vec is None or len(stored_vec) != len(query_vector):
                continue
            
            stored_np = np.array(stored_vec, dtype=np.float32)
            stored_norm = np.linalg.norm(stored_np)
            if stored_norm == 0:
                continue
            
            similarity = float(np.dot(query_vec, stored_np) / (query_norm * stored_norm))
            
            results.append({
                "uri": uri,
                "abstract": abstract,
                "overview": overview or "",
                "memory_type": mem_type,
                "created_at": created_at,
                "score": similarity,
                "level": "l0",  # 明确标记：只返回 L0 层
            })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def _deserialize_vector(self, blob: bytes) -> Optional[List[float]]:
        if blob is None:
            return None
        try:
            count = len(blob) // 4
            return list(struct.unpack(f"{count}f", blob))
        except Exception:
            return None


def serialize_vector(vec: List[float]) -> bytes:
    """将 float 列表序列化为 BLOB"""
    return struct.pack(f"{len(vec)}f", *vec)
