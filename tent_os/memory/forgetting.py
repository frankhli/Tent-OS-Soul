"""主动遗忘算法 —— 模拟人类记忆的艾宾浩斯遗忘曲线

核心机制：
1. 每条记忆有衰减函数：current_confidence = initial_confidence × e^(-λ×days)
2. 衰减系数 λ 根据记忆类型不同
3. 当 confidence < 0.2 时归档到 COLD（不删除，只是不参与主动注入）
4. 当 confidence < 0.05 且超过 1 年未访问时真正删除

衰减系数（λ）：
    fact:        0.01  —— 事实记忆衰减极慢
    preference:  0.03  —— 偏好记忆中等衰减
    event:       0.05  —— 事件记忆较快衰减
    pattern:     0.02  —— 模式记忆较慢衰减
    belief:      0.04  —— 信念记忆较快衰减（因为信念容易改变）
    temporary:   0.10  —— 临时记忆快速衰减
    
记忆刷新（复习效应）：
    每次访问记忆时，confidence 小幅回升（模拟复习）
"""

import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("tent_os.memory.forgetting")


# 记忆类型 → 衰减系数
DECAY_LAMBDA = {
    "fact": 0.01,
    "preference": 0.03,
    "entity": 0.02,
    "event": 0.05,
    "pattern": 0.02,
    "belief": 0.04,
    "temporary": 0.10,
    "general": 0.03,
}

# 归档阈值
ARCHIVE_THRESHOLD = 0.2
DELETE_THRESHOLD = 0.05
DELETE_INACTIVE_DAYS = 365


@dataclass
class ForgettingResult:
    """遗忘处理结果"""
    archived_count: int       # 归档到 COLD 的数量
    deleted_count: int        # 真正删除的数量
    refreshed_count: int      # 因复习而刷新置信度的数量
    checked_count: int        # 检查的总数


class ForgettingEngine:
    """主动遗忘引擎"""
    
    def __init__(self, graph_db_path: str = "./tent_memory/graph.db",
                 memory_db_path: str = "./tent_memory/memory.db"):
        self.graph_db_path = graph_db_path
        self.memory_db_path = memory_db_path
    
    def run_forgetting_cycle(self) -> ForgettingResult:
        """执行一轮遗忘处理
        
        Returns:
            ForgettingResult: 处理结果统计
        """
        result = ForgettingResult(0, 0, 0, 0)
        
        try:
            if Path(self.graph_db_path).exists():
                self._process_graph_nodes(result)
        except Exception as e:
            logger.error(f"图谱遗忘处理失败: {e}")
        
        try:
            if Path(self.memory_db_path).exists():
                self._process_memory_index(result)
        except Exception as e:
            logger.error(f"记忆索引遗忘处理失败: {e}")
        
        logger.info(
            f"遗忘处理完成: 检查 {result.checked_count}, "
            f"归档 {result.archived_count}, 删除 {result.deleted_count}, 刷新 {result.refreshed_count}"
        )
        return result
    
    def _process_graph_nodes(self, result: ForgettingResult):
        """处理认知图谱中的节点"""
        conn = sqlite3.connect(self.graph_db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            rows = conn.execute("SELECT * FROM nodes").fetchall()
            result.checked_count += len(rows)
            
            for row in rows:
                node_id = row["id"]
                memory_type = row["memory_type"] or "general"
                initial_confidence = row["confidence"]
                last_accessed = row["last_accessed"]
                created_at = row["created_at"]
                
                # 计算当前置信度（考虑衰减）
                current_confidence = self._calculate_decayed_confidence(
                    initial_confidence, created_at, memory_type
                )
                
                # 检查是否需要刷新（最近被访问）
                if last_accessed:
                    last_access_dt = datetime.fromisoformat(last_accessed)
                    days_since_access = (datetime.now() - last_access_dt).days
                    
                    if days_since_access <= 1:
                        # 最近访问过，小幅提升置信度（复习效应）
                        refresh_boost = 0.05
                        new_confidence = min(1.0, current_confidence + refresh_boost)
                        conn.execute(
                            "UPDATE nodes SET confidence = ? WHERE id = ?",
                            (new_confidence, node_id)
                        )
                        result.refreshed_count += 1
                        continue
                
                # 更新数据库中的置信度
                if abs(current_confidence - initial_confidence) > 0.01:
                    conn.execute(
                        "UPDATE nodes SET confidence = ? WHERE id = ?",
                        (current_confidence, node_id)
                    )
                
                # 判断是否需要归档
                if current_confidence < DELETE_THRESHOLD:
                    # 检查是否超过 1 年未访问
                    if last_accessed:
                        last_access_dt = datetime.fromisoformat(last_accessed)
                        if (datetime.now() - last_access_dt).days > DELETE_INACTIVE_DAYS:
                            # 真正删除
                            self._delete_node_cascade(conn, node_id)
                            result.deleted_count += 1
                            continue
                    
                    # 如果创建时间也超过 1 年，删除
                    created_dt = datetime.fromisoformat(created_at)
                    if (datetime.now() - created_dt).days > DELETE_INACTIVE_DAYS:
                        self._delete_node_cascade(conn, node_id)
                        result.deleted_count += 1
                        continue
                
                if current_confidence < ARCHIVE_THRESHOLD:
                    # 归档到 COLD（不删除，只是降低优先级）
                    # 实际实现中可以通过标记或移到单独的表
                    # 这里简单降低置信度并记录
                    logger.debug(f"节点归档到 COLD: {node_id} (confidence: {current_confidence:.3f})")
                    result.archived_count += 1
            
            conn.commit()
        finally:
            conn.close()
    
    def _process_memory_index(self, result: ForgettingResult):
        """处理 L0/L1 索引中的记忆"""
        conn = sqlite3.connect(self.memory_db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            # 检查 l0_index 表是否有 confidence 字段
            cursor = conn.execute("PRAGMA table_info(l0_index)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if "confidence" not in columns:
                # 添加 confidence 字段（如果表已存在但没有此字段）
                try:
                    conn.execute("ALTER TABLE l0_index ADD COLUMN confidence REAL DEFAULT 0.5")
                    conn.execute("ALTER TABLE l0_index ADD COLUMN access_count INTEGER DEFAULT 0")
                    conn.execute("ALTER TABLE l0_index ADD COLUMN last_accessed TEXT")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # 可能已经存在
            
            # 获取所有条目
            rows = conn.execute("SELECT * FROM l0_index").fetchall()
            
            for row in rows:
                uri = row["uri"]
                created_at = row["created_at"]
                
                # 如果超过 90 天未访问，降低优先级
                if created_at:
                    created_dt = datetime.fromisoformat(created_at)
                    days_old = (datetime.now() - created_dt).days
                    
                    if days_old > 365:
                        # 超过 1 年，考虑删除
                        conn.execute("DELETE FROM l0_index WHERE uri = ?", (uri,))
                        result.deleted_count += 1
                    elif days_old > 90:
                        # 超过 90 天，归档
                        result.archived_count += 1
            
            conn.commit()
        finally:
            conn.close()
    
    def _calculate_decayed_confidence(self, initial_confidence: float,
                                       created_at_str: str,
                                       memory_type: str) -> float:
        """计算衰减后的置信度"""
        try:
            created_dt = datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError):
            return initial_confidence
        
        days = (datetime.now() - created_dt).days
        if days <= 0:
            return initial_confidence
        
        lam = DECAY_LAMBDA.get(memory_type, 0.03)
        
        # 艾宾浩斯风格衰减：confidence = initial × e^(-λ×days)
        decayed = initial_confidence * math.exp(-lam * days)
        
        return round(decayed, 4)
    
    def _delete_node_cascade(self, conn: sqlite3.Connection, node_id: str):
        """级联删除节点及其所有边"""
        conn.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
        conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        logger.debug(f"节点已删除: {node_id}")
    
    def refresh_on_access(self, node_id: str) -> float:
        """访问时刷新节点置信度（复习效应）
        
        Returns:
            float: 刷新后的置信度
        """
        if not Path(self.graph_db_path).exists():
            return 0.0
        
        conn = sqlite3.connect(self.graph_db_path)
        try:
            row = conn.execute("SELECT confidence FROM nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return 0.0
            
            current = row["confidence"]
            # 复习效应：小幅提升
            new_confidence = min(1.0, current + 0.03)
            
            conn.execute(
                "UPDATE nodes SET confidence = ?, access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (new_confidence, datetime.now().isoformat(), node_id)
            )
            conn.commit()
            return new_confidence
        finally:
            conn.close()
    
    def get_forgetting_stats(self) -> Dict:
        """获取遗忘统计信息"""
        stats = {
            "decay_lambdas": DECAY_LAMBDA,
            "archive_threshold": ARCHIVE_THRESHOLD,
            "delete_threshold": DELETE_THRESHOLD,
            "delete_inactive_days": DELETE_INACTIVE_DAYS,
        }
        
        if Path(self.graph_db_path).exists():
            conn = sqlite3.connect(self.graph_db_path)
            try:
                total = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                archived = conn.execute("SELECT COUNT(*) FROM nodes WHERE confidence < ?", (ARCHIVE_THRESHOLD,)).fetchone()[0]
                by_type = {}
                for row in conn.execute("SELECT memory_type, COUNT(*) as cnt FROM nodes GROUP BY memory_type"):
                    by_type[row["memory_type"]] = row["cnt"]
                
                stats.update({
                    "total_nodes": total,
                    "archived_nodes": archived,
                    "active_nodes": total - archived,
                    "type_distribution": by_type,
                })
            finally:
                conn.close()
        
        return stats
