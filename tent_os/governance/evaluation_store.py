"""Evaluation 结果存储 —— 元认知仪表盘的数据源

核心设计：
1. 内存环形缓存：最近 100 条 evaluation，用于实时仪表盘
2. SQLite 持久化：跨会话保留，支持趋势分析
3. 按 persona 聚合：每个 persona 有独立的评估历史

去AI化原则：
- 不是让 AI 更聪明，而是让 AI 的"自我评价"可见
- 用户可以看到 AI 知道自己做得好不好
"""

import json
import logging
import sqlite3
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("tent_os.evaluation")


@dataclass
class EvaluationRecord:
    """单条评估记录"""
    id: str
    timestamp: str
    session_id: str
    user_id: str
    persona: str
    task_summary: str
    passed: bool
    overall_score: float
    criteria_scores: Dict[str, float]
    feedback: str
    retry_recommended: bool
    retry_count: int


class EvaluationStore:
    """评估结果存储器
    
    双存储策略：
    - 内存：最近 100 条，O(1) 读取，服务重启丢失
    - SQLite：全部历史，用于趋势分析和持久化
    """
    
    def __init__(self, storage_path: str = "./tent_memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.db_path = self.storage_path / "evaluations.db"
        self._memory_cache: deque = deque(maxlen=100)
        self._init_db()
    
    def _init_db(self):
        """初始化评估数据库"""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evaluations (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                session_id TEXT,
                user_id TEXT,
                persona TEXT,
                task_summary TEXT,
                passed INTEGER,
                overall_score REAL,
                criteria_scores TEXT,
                feedback TEXT,
                retry_recommended INTEGER,
                retry_count INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_time ON evaluations(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_persona ON evaluations(persona)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_session ON evaluations(session_id)")
        conn.commit()
        conn.close()
    
    def save(self, record: EvaluationRecord):
        """保存评估记录到内存缓存和 SQLite"""
        # 1. 内存缓存
        self._memory_cache.append(record)
        
        # 2. SQLite 持久化
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                """INSERT OR REPLACE INTO evaluations
                   (id, timestamp, session_id, user_id, persona, task_summary,
                    passed, overall_score, criteria_scores, feedback,
                    retry_recommended, retry_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.timestamp,
                    record.session_id,
                    record.user_id,
                    record.persona,
                    record.task_summary,
                    int(record.passed),
                    record.overall_score,
                    json.dumps(record.criteria_scores),
                    record.feedback,
                    int(record.retry_recommended),
                    record.retry_count,
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[EVAL] 持久化评估记录失败: {e}")
    
    def get_recent(self, limit: int = 20, persona: str = None) -> List[EvaluationRecord]:
        """获取最近评估记录
        
        优先从内存缓存读取（更快），如果不够再从 SQLite 补充。
        """
        records = []
        
        # 从内存缓存过滤
        for rec in reversed(self._memory_cache):
            if persona and rec.persona != persona:
                continue
            records.append(rec)
            if len(records) >= limit:
                return records
        
        # 如果内存不够，从 SQLite 补充
        if len(records) < limit:
            try:
                conn = sqlite3.connect(str(self.db_path))
                if persona:
                    cursor = conn.execute(
                        "SELECT * FROM evaluations WHERE persona = ? ORDER BY timestamp DESC LIMIT ?",
                        (persona, limit)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM evaluations ORDER BY timestamp DESC LIMIT ?",
                        (limit,)
                    )
                for row in cursor.fetchall():
                    db_rec = EvaluationRecord(
                        id=row[0],
                        timestamp=row[1],
                        session_id=row[2],
                        user_id=row[3],
                        persona=row[4],
                        task_summary=row[5],
                        passed=bool(row[6]),
                        overall_score=row[7],
                        criteria_scores=json.loads(row[8]) if row[8] else {},
                        feedback=row[9],
                        retry_recommended=bool(row[10]),
                        retry_count=row[11],
                    )
                    # 避免重复（如果已在内存中）
                    if not any(r.id == db_rec.id for r in records):
                        records.append(db_rec)
                        if len(records) >= limit:
                            break
                conn.close()
            except Exception as e:
                logger.warning(f"[EVAL] 读取历史评估记录失败: {e}")
        
        return records[:limit]
    
    def get_summary(self, days: int = 7, persona: str = None) -> Dict[str, Any]:
        """获取评估统计摘要
        
        Returns:
            {
                "total_evaluations": int,
                "passed_count": int,
                "failed_count": int,
                "avg_score": float,
                "criteria_averages": Dict[str, float],
                "retry_count": int,
                "by_persona": Dict[str, Dict],
            }
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            since = (datetime.now() - timedelta(days=days)).isoformat()
            
            # 基础统计
            if persona:
                cursor = conn.execute(
                    "SELECT COUNT(*), SUM(passed), AVG(overall_score), SUM(retry_recommended) FROM evaluations WHERE timestamp >= ? AND persona = ?",
                    (since, persona)
                )
            else:
                cursor = conn.execute(
                    "SELECT COUNT(*), SUM(passed), AVG(overall_score), SUM(retry_recommended) FROM evaluations WHERE timestamp >= ?",
                    (since,)
                )
            row = cursor.fetchone()
            total = row[0] or 0
            passed = row[1] or 0
            avg_score = row[2] or 0.0
            retries = row[3] or 0
            
            # 各维度平均分
            criteria_avgs = {}
            if total > 0:
                cursor = conn.execute(
                    "SELECT criteria_scores FROM evaluations WHERE timestamp >= ?" + (" AND persona = ?" if persona else ""),
                    (since, persona) if persona else (since,)
                )
                criteria_sums = {}
                criteria_counts = {}
                for row in cursor.fetchall():
                    scores = json.loads(row[0]) if row[0] else {}
                    for key, val in scores.items():
                        criteria_sums[key] = criteria_sums.get(key, 0.0) + val
                        criteria_counts[key] = criteria_counts.get(key, 0) + 1
                criteria_avgs = {
                    k: round(criteria_sums[k] / criteria_counts[k], 2)
                    for k in criteria_sums
                }
            
            # 按 persona 分组
            by_persona = {}
            cursor = conn.execute(
                "SELECT persona, COUNT(*), SUM(passed), AVG(overall_score) FROM evaluations WHERE timestamp >= ? GROUP BY persona",
                (since,)
            )
            for row in cursor.fetchall():
                by_persona[row[0]] = {
                    "count": row[1],
                    "passed": row[2] or 0,
                    "avg_score": round(row[3] or 0, 2),
                }
            
            conn.close()
            
            return {
                "total_evaluations": total,
                "passed_count": int(passed),
                "failed_count": int(total - passed),
                "avg_score": round(avg_score, 2),
                "criteria_averages": criteria_avgs,
                "retry_count": int(retries),
                "by_persona": by_persona,
            }
        except Exception as e:
            logger.warning(f"[EVAL] 统计摘要生成失败: {e}")
            return {
                "total_evaluations": 0,
                "passed_count": 0,
                "failed_count": 0,
                "avg_score": 0.0,
                "criteria_averages": {},
                "retry_count": 0,
                "by_persona": {},
            }
    
    def get_trends(self, days: int = 7, persona: str = None) -> List[Dict]:
        """获取每日评估趋势
        
        Returns:
            [
                {"date": "2026-05-01", "count": 3, "avg_score": 0.85, "passed": 2, "failed": 1},
                ...
            ]
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            since = (datetime.now() - timedelta(days=days)).isoformat()
            
            if persona:
                cursor = conn.execute(
                    """SELECT date(timestamp) as day, COUNT(*), AVG(overall_score), SUM(passed)
                       FROM evaluations WHERE timestamp >= ? AND persona = ?
                       GROUP BY date(timestamp) ORDER BY day""",
                    (since, persona)
                )
            else:
                cursor = conn.execute(
                    """SELECT date(timestamp) as day, COUNT(*), AVG(overall_score), SUM(passed)
                       FROM evaluations WHERE timestamp >= ?
                       GROUP BY date(timestamp) ORDER BY day""",
                    (since,)
                )
            
            results = []
            for row in cursor.fetchall():
                count = row[1] or 0
                passed = row[3] or 0
                results.append({
                    "date": row[0],
                    "count": count,
                    "avg_score": round(row[2] or 0, 2),
                    "passed": int(passed),
                    "failed": int(count - passed),
                })
            conn.close()
            return results
        except Exception as e:
            logger.warning(f"[EVAL] 趋势数据生成失败: {e}")
            return []
    
    def to_dict_list(self, records: List[EvaluationRecord]) -> List[Dict]:
        """将记录列表转为字典列表（用于 JSON 序列化）"""
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp,
                "session_id": r.session_id,
                "user_id": r.user_id,
                "persona": r.persona,
                "task_summary": r.task_summary,
                "passed": r.passed,
                "overall_score": r.overall_score,
                "criteria_scores": r.criteria_scores,
                "feedback": r.feedback,
                "retry_recommended": r.retry_recommended,
                "retry_count": r.retry_count,
            }
            for r in records
        ]
