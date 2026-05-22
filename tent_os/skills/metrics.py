"""Skill 效果指标 —— 追踪 Skill 的使用情况和效果

指标维度：
1. 使用统计：调用次数、成功率、执行时间
2. 用户反馈：满意度评分、纠正次数
3. 任务效果：完成率、重试次数
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("tent_os.skills.metrics")


@dataclass
class SkillMetrics:
    """Skill 效果指标"""
    skill_name: str
    
    # 使用统计
    invocation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_execution_time: float = 0.0
    
    # 用户反馈
    user_satisfaction: float = 0.0   # 用户评分均值 0-5
    user_ratings_count: int = 0
    user_corrections: int = 0        # 用户纠正次数
    
    # 任务效果
    task_completion_rate: float = 0.0
    avg_retry_count: float = 0.0
    
    # 时间分布
    last_invoked: Optional[str] = None
    first_invoked: Optional[str] = None
    
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total
    
    def overall_score(self) -> float:
        """综合评分 0-1"""
        weights = {
            "success_rate": 0.3,
            "completion_rate": 0.2,
            "satisfaction": 0.2,
            "efficiency": 0.15,  # 基于执行时间和重试次数
            "frequency": 0.15,   # 使用频率
        }
        
        success = self.success_rate()
        completion = self.task_completion_rate
        satisfaction = self.user_satisfaction / 5 if self.user_ratings_count > 0 else 0.5
        efficiency = max(0, 1.0 - self.avg_retry_count * 0.2)
        frequency = min(1.0, self.invocation_count / 50)
        
        return (success * weights["success_rate"] +
                completion * weights["completion_rate"] +
                satisfaction * weights["satisfaction"] +
                efficiency * weights["efficiency"] +
                frequency * weights["frequency"])


class SkillMetricsStore:
    """Skill 指标存储"""
    
    def __init__(self, db_path: str = "./tent_memory/skill_metrics.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_metrics (
                skill_name TEXT PRIMARY KEY,
                invocation_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                total_execution_time REAL DEFAULT 0,
                user_satisfaction_sum REAL DEFAULT 0,
                user_ratings_count INTEGER DEFAULT 0,
                user_corrections INTEGER DEFAULT 0,
                task_completion_count INTEGER DEFAULT 0,
                task_total_count INTEGER DEFAULT 0,
                retry_count_sum INTEGER DEFAULT 0,
                last_invoked TEXT,
                first_invoked TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def record_invocation(self, skill_name: str, success: bool, 
                          execution_time: float = 0, retry_count: int = 0):
        """记录一次 Skill 调用"""
        now = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        try:
            # 检查是否已有记录
            row = conn.execute(
                "SELECT * FROM skill_metrics WHERE skill_name = ?",
                (skill_name,)
            ).fetchone()
            
            if row:
                # 更新
                conn.execute(
                    """UPDATE skill_metrics SET
                        invocation_count = invocation_count + 1,
                        success_count = success_count + ?,
                        failure_count = failure_count + ?,
                        total_execution_time = total_execution_time + ?,
                        retry_count_sum = retry_count_sum + ?,
                        last_invoked = ?,
                        updated_at = ?
                    WHERE skill_name = ?""",
                    (1 if success else 0, 0 if success else 1,
                     execution_time, retry_count, now, now, skill_name)
                )
            else:
                # 插入
                conn.execute(
                    """INSERT INTO skill_metrics
                        (skill_name, invocation_count, success_count, failure_count,
                         total_execution_time, retry_count_sum, last_invoked,
                         first_invoked, updated_at)
                    VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                    (skill_name, 1 if success else 0, 0 if success else 1,
                     execution_time, retry_count, now, now, now)
                )
            
            conn.commit()
        finally:
            conn.close()
    
    def record_user_feedback(self, skill_name: str, rating: float = None,
                             corrected: bool = False):
        """记录用户反馈"""
        conn = sqlite3.connect(self.db_path)
        try:
            if rating is not None:
                conn.execute(
                    """UPDATE skill_metrics SET
                        user_satisfaction_sum = user_satisfaction_sum + ?,
                        user_ratings_count = user_ratings_count + 1,
                        updated_at = ?
                    WHERE skill_name = ?""",
                    (rating, datetime.now().isoformat(), skill_name)
                )
            
            if corrected:
                conn.execute(
                    """UPDATE skill_metrics SET
                        user_corrections = user_corrections + 1,
                        updated_at = ?
                    WHERE skill_name = ?""",
                    (datetime.now().isoformat(), skill_name)
                )
            
            conn.commit()
        finally:
            conn.close()
    
    def record_task_completion(self, skill_name: str, completed: bool):
        """记录任务完成状态"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """UPDATE skill_metrics SET
                    task_completion_count = task_completion_count + ?,
                    task_total_count = task_total_count + 1,
                    updated_at = ?
                WHERE skill_name = ?""",
                (1 if completed else 0, datetime.now().isoformat(), skill_name)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_metrics(self, skill_name: str) -> Optional[SkillMetrics]:
        """获取 Skill 指标"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM skill_metrics WHERE skill_name = ?",
                (skill_name,)
            ).fetchone()
            
            if not row:
                return None
            
            invocation_count = row["invocation_count"] or 0
            avg_time = (row["total_execution_time"] or 0) / max(invocation_count, 1)
            
            ratings_count = row["user_ratings_count"] or 0
            avg_satisfaction = (row["user_satisfaction_sum"] or 0) / max(ratings_count, 1) if ratings_count > 0 else 0
            
            task_total = row["task_total_count"] or 0
            completion_rate = (row["task_completion_count"] or 0) / max(task_total, 1) if task_total > 0 else 0
            
            avg_retries = (row["retry_count_sum"] or 0) / max(invocation_count, 1)
            
            return SkillMetrics(
                skill_name=skill_name,
                invocation_count=invocation_count,
                success_count=row["success_count"] or 0,
                failure_count=row["failure_count"] or 0,
                avg_execution_time=avg_time,
                user_satisfaction=avg_satisfaction,
                user_ratings_count=ratings_count,
                user_corrections=row["user_corrections"] or 0,
                task_completion_rate=completion_rate,
                avg_retry_count=avg_retries,
                last_invoked=row["last_invoked"],
                first_invoked=row["first_invoked"],
            )
        finally:
            conn.close()
    
    def get_all_metrics(self) -> Dict[str, SkillMetrics]:
        """获取所有 Skill 指标"""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT skill_name FROM skill_metrics").fetchall()
            return {
                row[0]: self.get_metrics(row[0])
                for row in rows
            }
        finally:
            conn.close()
    
    def get_underperforming_skills(self, threshold: float = 0.5) -> List[str]:
        """获取表现不佳的 Skill"""
        all_metrics = self.get_all_metrics()
        underperforming = []
        
        for name, metrics in all_metrics.items():
            if metrics and metrics.overall_score() < threshold:
                underperforming.append(name)
        
        return underperforming
