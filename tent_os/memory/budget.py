"""记忆预算管理 —— 控制记忆总量，避免无限增长

核心设计：
1. 用户可配置每种类型的记忆上限
2. 当接近上限时，遗忘引擎加速运行
3. 优先保留：高置信度 + 高频访问 + 近期 + 情绪强烈

默认预算：
    fact:       1000  —— 事实记忆最多 1000 条
    preference:  100  —— 偏好记忆最多 100 条
    entity:      500  —— 实体记忆最多 500 条
    event:       300  —— 事件记忆最多 300 条
    pattern:     200  —— 模式记忆最多 200 条
    belief:      100  —— 信念记忆最多 100 条
    temporary:   500  —— 临时记忆最多 500 条（但衰减最快）
"""

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("tent_os.memory.budget")


# 默认记忆预算（每种类型最大条目数）
DEFAULT_BUDGET = {
    "fact": 1000,
    "preference": 100,
    "entity": 500,
    "event": 300,
    "pattern": 200,
    "belief": 100,
    "temporary": 500,
    "general": 500,
}

# 当使用率达到此阈值时，触发加速遗忘
COMPACT_THRESHOLD = 0.85
# 紧急阈值（使用率超过此值时，更激进地遗忘）
EMERGENCY_THRESHOLD = 0.95


@dataclass
class BudgetStatus:
    """预算状态"""
    memory_type: str
    current: int           # 当前数量
    limit: int             # 上限
    usage_ratio: float     # 使用率 0-1
    status: str            # "ok" / "warning" / "critical"


class MemoryBudget:
    """记忆预算管理器"""
    
    def __init__(self, budget_config: Optional[Dict[str, int]] = None,
                 graph_db_path: str = "./tent_memory/graph.db"):
        self.budget = {**DEFAULT_BUDGET, **(budget_config or {})}
        self.graph_db_path = graph_db_path
    
    def check_budget(self) -> List[BudgetStatus]:
        """检查当前记忆使用状态
        
        Returns:
            List[BudgetStatus]: 每种记忆类型的状态
        """
        if not Path(self.graph_db_path).exists():
            return []
        
        conn = sqlite3.connect(self.graph_db_path)
        try:
            statuses = []
            
            for mem_type, limit in self.budget.items():
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM nodes WHERE memory_type = ?",
                    (mem_type,)
                ).fetchone()
                current = row["cnt"] if row else 0
                ratio = current / limit if limit > 0 else 0
                
                if ratio >= EMERGENCY_THRESHOLD:
                    status = "critical"
                elif ratio >= COMPACT_THRESHOLD:
                    status = "warning"
                else:
                    status = "ok"
                
                statuses.append(BudgetStatus(
                    memory_type=mem_type,
                    current=current,
                    limit=limit,
                    usage_ratio=round(ratio, 3),
                    status=status
                ))
            
            return statuses
        finally:
            conn.close()
    
    def is_over_budget(self, memory_type: str) -> bool:
        """检查某种记忆类型是否超出预算"""
        status_list = self.check_budget()
        for s in status_list:
            if s.memory_type == memory_type:
                return s.status in ("warning", "critical")
        return False
    
    def get_eviction_candidates(self, memory_type: str, 
                                 count: int = 10) -> List[str]:
        """获取应该被淘汰的记忆候选（按优先级排序）
        
        淘汰优先级（越靠前越优先淘汰）：
        1. 置信度最低
        2. 访问次数最少
        3. 最久未访问
        4. 最旧创建
        
        Returns:
            List[str]: 节点 ID 列表
        """
        if not Path(self.graph_db_path).exists():
            return []
        
        conn = sqlite3.connect(self.graph_db_path)
        try:
            rows = conn.execute(
                """SELECT id, confidence, access_count, 
                          COALESCE(last_accessed, created_at) as last_touch,
                          created_at
                   FROM nodes
                   WHERE memory_type = ?
                   ORDER BY 
                       confidence ASC,
                       access_count ASC,
                       last_touch ASC,
                       created_at ASC
                   LIMIT ?""",
                (memory_type, count)
            ).fetchall()
            
            return [r["id"] for r in rows]
        finally:
            conn.close()
    
    def compact_if_needed(self, memory_type: Optional[str] = None) -> int:
        """如果需要，执行压缩（淘汰超预算的记忆）
        
        Returns:
            int: 淘汰的记忆数量
        """
        if not Path(self.graph_db_path).exists():
            return 0
        
        statuses = self.check_budget()
        evicted = 0
        
        for status in statuses:
            if memory_type and status.memory_type != memory_type:
                continue
            
            if status.status == "ok":
                continue
            
            # 计算需要淘汰的数量
            if status.status == "critical":
                # 紧急：降到 80%
                target = int(status.limit * 0.8)
            else:  # warning
                # 警告：降到 90%
                target = int(status.limit * 0.9)
            
            to_evict = status.current - target
            if to_evict <= 0:
                continue
            
            candidates = self.get_eviction_candidates(status.memory_type, to_evict + 5)
            
            # 删除候选
            conn = sqlite3.connect(self.graph_db_path)
            try:
                for node_id in candidates[:to_evict]:
                    # 先删除边
                    conn.execute(
                        "DELETE FROM edges WHERE source_id = ? OR target_id = ?",
                        (node_id, node_id)
                    )
                    # 再删除节点
                    conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
                    evicted += 1
                
                conn.commit()
                logger.info(
                    f"记忆压缩: {status.memory_type} 淘汰 {to_evict} 条 "
                    f"({status.current} -> {status.current - to_evict})"
                )
            finally:
                conn.close()
        
        return evicted
    
    def get_budget_summary(self) -> Dict:
        """获取预算摘要"""
        statuses = self.check_budget()
        total_current = sum(s.current for s in statuses)
        total_limit = sum(s.limit for s in statuses)
        
        return {
            "total_current": total_current,
            "total_limit": total_limit,
            "overall_usage": round(total_current / total_limit, 3) if total_limit > 0 else 0,
            "by_type": [
                {
                    "type": s.memory_type,
                    "current": s.current,
                    "limit": s.limit,
                    "usage": s.usage_ratio,
                    "status": s.status,
                }
                for s in statuses
            ],
        }
