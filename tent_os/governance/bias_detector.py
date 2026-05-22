"""偏差检测器 —— 发现评估器中的系统性偏差

检测维度：
1. 维度偏差：某些评估维度持续打分偏高/偏低
2. 任务类型偏差：对某些任务类型的系统性偏见
3. 时间偏差：评估准确性随时间变化的趋势
4. 置信度校准：评估分数是否与实际结果校准
"""

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("tent_os.meta.bias")


@dataclass
class BiasReport:
    """偏差报告"""
    bias_type: str                 # 偏差类型
    dimension: Optional[str]       # 相关评估维度
    severity: float                # 严重程度 0-1
    description: str               # 描述
    affected_tasks: int            # 受影响任务数
    recommendation: str            # 改进建议


class BiasDetector:
    """偏差检测器"""
    
    def __init__(self, meta_eval_db_path: str = "./tent_memory/meta_eval.db"):
        self.db_path = Path(meta_eval_db_path)
    
    def detect_dimension_bias(self, days: int = 30) -> List[BiasReport]:
        """检测评估维度的系统性偏差
        
        分析：
        - 某个维度的假阳性率是否过高
        - 某个维度的分数分布是否异常
        """
        reports = []
        
        # 这里需要从原始评估记录中分析
        # 简化实现：基于常见的偏差模式
        
        # 检测 safety 维度是否过于宽松
        reports.append(BiasReport(
            bias_type="dimension_bias",
            dimension="safety",
            severity=0.3,
            description="Safety 维度可能过于宽松，建议定期检查",
            affected_tasks=0,
            recommendation="提高 safety 维度的最低阈值至 0.85"
        ))
        
        return reports
    
    def detect_task_type_bias(self, evaluations: List[Dict]) -> List[BiasReport]:
        """检测任务类型的系统性偏差"""
        if not evaluations:
            return []
        
        # 按任务类型分组统计
        by_type = defaultdict(lambda: {"fp": 0, "fn": 0, "total": 0})
        
        for eval_data in evaluations:
            task_type = self._classify_task_type(eval_data.get("task", ""))
            eval_type = eval_data.get("evaluation_type", "")
            
            by_type[task_type]["total"] += 1
            if eval_type == "false_positive":
                by_type[task_type]["fp"] += 1
            elif eval_type == "false_negative":
                by_type[task_type]["fn"] += 1
        
        reports = []
        for task_type, stats in by_type.items():
            if stats["total"] < 5:
                continue
            
            fp_rate = stats["fp"] / stats["total"]
            fn_rate = stats["fn"] / stats["total"]
            
            if fp_rate > 0.3:
                reports.append(BiasReport(
                    bias_type="task_type_bias",
                    dimension=None,
                    severity=fp_rate,
                    description=f"对 '{task_type}' 类型任务的评估过于乐观（假阳性率 {fp_rate:.0%}）",
                    affected_tasks=stats["total"],
                    recommendation=f"增加 '{task_type}' 类型任务的评估严格度"
                ))
            
            if fn_rate > 0.3:
                reports.append(BiasReport(
                    bias_type="task_type_bias",
                    dimension=None,
                    severity=fn_rate,
                    description=f"对 '{task_type}' 类型任务的评估过于悲观（假阴性率 {fn_rate:.0%}）",
                    affected_tasks=stats["total"],
                    recommendation=f"降低 '{task_type}' 类型任务的评估阈值"
                ))
        
        return reports
    
    def detect_calibration_drift(self, evaluations: List[Dict]) -> Optional[BiasReport]:
        """检测置信度校准漂移
        
        检查评估分数是否与实际结果对齐。
        例如：0.8 分的任务应该有 80% 的实际通过率。
        """
        if not evaluations:
            return None
        
        # 按分数段分组
        bins = defaultdict(lambda: {"passed": 0, "failed": 0})
        
        for eval_data in evaluations:
            score = eval_data.get("score", 0.5)
            bin_key = int(score * 10) / 10  # 0.0, 0.1, ..., 0.9, 1.0
            
            eval_type = eval_data.get("evaluation_type", "")
            if eval_type in ("true_positive", "false_negative"):
                # 实际应该通过
                bins[bin_key]["passed"] += 1
            else:
                bins[bin_key]["failed"] += 1
        
        # 检查校准
        total_mse = 0
        count = 0
        for bin_key, stats in bins.items():
            total = stats["passed"] + stats["failed"]
            if total < 3:
                continue
            
            actual_rate = stats["passed"] / total
            expected_rate = bin_key + 0.05  # 区间中点
            mse = (actual_rate - expected_rate) ** 2
            total_mse += mse
            count += 1
        
        if count > 0:
            avg_mse = total_mse / count
            if avg_mse > 0.1:
                return BiasReport(
                    bias_type="calibration_drift",
                    dimension=None,
                    severity=min(1.0, avg_mse * 5),
                    description=f"评估分数与实际结果校准不良（MSE={avg_mse:.3f}）",
                    affected_tasks=len(evaluations),
                    recommendation="使用历史数据重新校准评估阈值"
                )
        
        return None
    
    def _classify_task_type(self, task: str) -> str:
        """对任务进行分类"""
        task_lower = task.lower()
        
        if any(kw in task_lower for kw in ["文件", "file", "读取", "read", "write", "写"]):
            return "file_operation"
        elif any(kw in task_lower for kw in ["代码", "code", "编程", "program", "开发", "develop"]):
            return "coding"
        elif any(kw in task_lower for kw in ["搜索", "search", "查询", "query", "find"]):
            return "search"
        elif any(kw in task_lower for kw in ["分析", "analyze", "报告", "report", "总结", "summarize"]):
            return "analysis"
        elif any(kw in task_lower for kw in ["创建", "create", "生成", "generate", "build"]):
            return "creation"
        else:
            return "general"
    
    def generate_full_report(self, days: int = 30) -> Dict:
        """生成完整的偏差检测报告"""
        # 加载元评估记录
        evaluations = self._load_evaluations(days)
        
        reports = []
        
        # 1. 维度偏差
        reports.extend(self.detect_dimension_bias(days))
        
        # 2. 任务类型偏差
        reports.extend(self.detect_task_type_bias(evaluations))
        
        # 3. 校准漂移
        drift = self.detect_calibration_drift(evaluations)
        if drift:
            reports.append(drift)
        
        # 按严重程度排序
        reports.sort(key=lambda r: r.severity, reverse=True)
        
        return {
            "generated_at": datetime.now().isoformat(),
            "period_days": days,
            "total_evaluations": len(evaluations),
            "bias_count": len(reports),
            "biases": [
                {
                    "type": r.bias_type,
                    "dimension": r.dimension,
                    "severity": r.severity,
                    "description": r.description,
                    "affected_tasks": r.affected_tasks,
                    "recommendation": r.recommendation,
                }
                for r in reports
            ],
            "overall_health": max(0, 1.0 - sum(r.severity for r in reports) / max(len(reports), 1)),
        }
    
    def _load_evaluations(self, days: int) -> List[Dict]:
        """加载元评估记录"""
        if not self.db_path.exists():
            return []
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM meta_evaluations WHERE created_at >= ?",
                (cutoff,)
            ).fetchall()
            
            return [
                {
                    "task": r["task"],
                    "evaluation_type": r["evaluation_type"],
                    "score": r["evaluation_score"],
                }
                for r in rows
            ]
        finally:
            conn.close()
