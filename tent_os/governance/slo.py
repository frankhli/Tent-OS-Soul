"""SLO (Service Level Objective) 与错误预算系统

核心概念：
- SLO: 服务质量目标（如"任务成功率 > 99%"）
- SLI: 服务级别指标（实际测量的指标）
- Error Budget: 错误预算 = (1 - SLO) * 总请求数

工作流程：
1. 每次任务完成后，记录结果到 slo_metrics
2. 定期计算滚动窗口内的 SLI
3. 对比 SLI 和 SLO，计算剩余错误预算
4. 预算低于阈值时触发自动降级
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SLORule:
    """SLO 规则定义"""
    name: str              # 规则名称
    target: float          # 目标值（0-1）
    window_hours: int      # 滚动窗口（小时）
    metric: str            # 指标类型：success_rate / latency_p99 / throughput
    warning_threshold: float = 0.5   # 预算消耗 50% 时警告
    critical_threshold: float = 0.9  # 预算消耗 90% 时严重告警


@dataclass
class SLIResult:
    """SLI 计算结果"""
    rule_name: str
    current_value: float
    target_value: float
    budget_remaining: float   # 剩余预算比例（0-1）
    status: str               # ok / warning / critical / breached
    total_tasks: int
    failed_tasks: int
    avg_latency_ms: float


class SLOTracker:
    """SLO 跟踪器 —— 记录任务指标并计算 SLI"""

    DEFAULT_RULES = [
        SLORule("任务成功率", 0.99, 24, "success_rate", 0.5, 0.9),
        SLORule("平均延迟", 0.95, 24, "latency_p99", 0.5, 0.9),
    ]

    def __init__(self, db_path: str = "./tent_scheduler.db", rules: List[SLORule] = None):
        self.db_path = Path(db_path)
        self.rules = rules or self.DEFAULT_RULES
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS slo_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                session_id TEXT,
                executor_id TEXT,
                action TEXT,
                status TEXT,           -- completed / failed / timeout / cancelled
                latency_ms REAL,       -- 执行延迟（毫秒）
                error_type TEXT,       -- 错误类型分类
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_slo_created_at
            ON slo_metrics(created_at)
        """)
        self.db.commit()

    def record_task(self, task_id: str, session_id: str, executor_id: str,
                    action: str, status: str, latency_ms: float = 0,
                    error_type: str = None):
        """记录单次任务指标"""
        self.db.execute(
            """INSERT INTO slo_metrics
               (task_id, session_id, executor_id, action, status, latency_ms, error_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task_id, session_id, executor_id, action, status, latency_ms, error_type),
        )
        self.db.commit()

    def calculate_sli(self, rule: SLORule) -> SLIResult:
        """计算单个 SLO 规则的 SLI"""
        # 统一使用 UTC 时间，避免时区问题
        window_start = (datetime.utcnow() - timedelta(hours=rule.window_hours)).strftime("%Y-%m-%d %H:%M:%S")

        rows = self.db.execute(
            """SELECT status, latency_ms FROM slo_metrics
               WHERE created_at >= ?""",
            (window_start,),
        ).fetchall()

        total = len(rows)
        if total == 0:
            return SLIResult(
                rule_name=rule.name,
                current_value=1.0,
                target_value=rule.target,
                budget_remaining=1.0,
                status="ok",
                total_tasks=0,
                failed_tasks=0,
                avg_latency_ms=0.0,
            )

        failed = sum(1 for r in rows if r["status"] != "completed")
        success_rate = (total - failed) / total
        avg_latency = sum(r["latency_ms"] or 0 for r in rows) / total

        # 计算错误预算消耗
        if rule.metric == "success_rate":
            current_value = success_rate
            error_budget_total = (1 - rule.target) * total
            error_budget_used = failed - error_budget_total * rule.target
            # 修正：预算消耗 = 实际错误数 / 预算总数
            error_budget_total = max(1, (1 - rule.target) * total)
            budget_used_ratio = min(failed / error_budget_total, 2.0)
        elif rule.metric == "latency_p99":
            # 简化：用平均延迟代替 P99
            latencies = sorted([r["latency_ms"] or 0 for r in rows])
            p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) > 0 else 0
            current_value = 1.0 if p99 <= 5000 else max(0, 1.0 - (p99 - 5000) / 5000)
            budget_used_ratio = 1.0 - current_value
        else:
            current_value = success_rate
            budget_used_ratio = 0.0

        budget_remaining = max(0, 1.0 - budget_used_ratio)

        # 状态判断
        if current_value < rule.target:
            status = "breached"
        elif budget_used_ratio >= rule.critical_threshold:
            status = "critical"
        elif budget_used_ratio >= rule.warning_threshold:
            status = "warning"
        else:
            status = "ok"

        return SLIResult(
            rule_name=rule.name,
            current_value=current_value,
            target_value=rule.target,
            budget_remaining=budget_remaining,
            status=status,
            total_tasks=total,
            failed_tasks=failed,
            avg_latency_ms=avg_latency,
        )

    def get_all_sli(self) -> List[SLIResult]:
        """计算所有 SLO 规则的 SLI"""
        return [self.calculate_sli(rule) for rule in self.rules]

    def get_summary(self) -> Dict:
        """获取 SLO 摘要报告"""
        slis = self.get_all_sli()
        return {
            "timestamp": datetime.now().isoformat(),
            "rules": [
                {
                    "name": s.rule_name,
                    "target": s.target_value,
                    "current": round(s.current_value, 4),
                    "budget_remaining": round(s.budget_remaining, 4),
                    "status": s.status,
                    "total_tasks": s.total_tasks,
                    "failed_tasks": s.failed_tasks,
                }
                for s in slis
            ],
            "overall_status": max(
                [s.status for s in slis],
                key=lambda x: {"ok": 0, "warning": 1, "critical": 2, "breached": 3}.get(x, 0),
            ),
        }

    def cleanup_old_metrics(self, retain_hours: int = 168):
        """清理旧指标（默认保留 7 天）"""
        cutoff = (datetime.utcnow() - timedelta(hours=retain_hours)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.db.execute("DELETE FROM slo_metrics WHERE created_at < ?", (cutoff,))
        self.db.commit()
        return cursor.rowcount


class AutoThrottle:
    """自动限流 —— 基于错误预算的渐进式降级"""

    THROTTLE_LEVELS = {
        "ok": {"action": "normal", "max_risk_score": 1.0},
        "warning": {"action": "caution", "max_risk_score": 0.7, "require_approval_above": 0.3},
        "critical": {"action": "throttle", "max_risk_score": 0.5, "require_approval_above": 0.1, "delay_ms": 1000},
        "breached": {"action": "reject_new", "max_risk_score": 0.0},
    }

    def __init__(self, slo_tracker: SLOTracker):
        self.slo = slo_tracker

    def check_task_allowed(self, risk_score: float = 0.0) -> Dict:
        """检查是否允许执行任务

        Returns:
            {"allowed": bool, "action": str, "reason": str}
        """
        summary = self.slo.get_summary()
        overall = summary["overall_status"]
        level = self.THROTTLE_LEVELS.get(overall, self.THROTTLE_LEVELS["ok"])

        if level["action"] == "reject_new":
            return {"allowed": False, "action": "reject", "reason": f"SLO 已突破: {overall}"}

        if risk_score > level.get("max_risk_score", 1.0):
            return {"allowed": False, "action": "reject", "reason": f"风险分数 {risk_score} 超过阈值 {level['max_risk_score']}"}

        if risk_score > level.get("require_approval_above", 1.0):
            return {"allowed": True, "action": "require_approval", "reason": f"预算紧张 ({overall})，高风险任务需审批"}

        return {"allowed": True, "action": level["action"], "reason": f"状态: {overall}"}
