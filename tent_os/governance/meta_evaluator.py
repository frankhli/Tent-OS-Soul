"""元评估器 —— 评估"评估是否准确"

核心思想：
1. 评估器打分后，元评估器检查这个打分是否准确
2. 通过用户反馈和实际结果来验证评估
3. 检测假阳性（评估说通过但实际失败）和假阴性（评估说失败但实际成功）

反馈闭环：
    任务执行 → Evaluator 打分 → MetaEvaluator 验证 → MetaLearner 学习
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.governance.evaluator import EvaluationResult

logger = logging.getLogger("tent_os.meta.evaluator")


@dataclass
class MetaEvaluationResult:
    """元评估结果"""
    original_task: str
    evaluation_correct: bool       # 评估是否正确
    evaluation_type: str           # "true_positive" / "true_negative" / "false_positive" / "false_negative"
    confidence_delta: float        # 评估置信度与实际结果的差异
    detected_bias: Optional[str]   # 检测到的偏差类型
    recommendation: str            # 改进建议


class MetaEvaluator:
    """元评估器 —— 对评估进行再评估"""
    
    def __init__(self, db_path: str = "./tent_memory/meta_eval.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化元评估数据库"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT,
                evaluation_passed INTEGER,
                evaluation_score REAL,
                user_feedback TEXT,
                actual_outcome TEXT,
                evaluation_type TEXT,
                confidence_delta REAL,
                detected_bias TEXT,
                recommendation TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def evaluate_evaluation(self,
                           original_task: str,
                           evaluation_result: EvaluationResult,
                           user_feedback: Optional[str] = None,
                           actual_outcome: Optional[str] = None) -> MetaEvaluationResult:
        """元评估 —— 检查评估是否准确
        
        判断逻辑：
        - 评估说"通过" + 用户反馈差评/实际失败 → 假阳性
        - 评估说"失败" + 用户反馈好评/实际成功 → 假阴性
        - 评估说"通过" + 用户反馈好评/实际成功 → 真阳性
        - 评估说"失败" + 用户反馈差评/实际失败 → 真阴性
        """
        eval_passed = evaluation_result.passed
        eval_score = evaluation_result.overall_score
        
        # 解析用户反馈
        user_positive = self._is_feedback_positive(user_feedback) if user_feedback else None
        outcome_positive = self._is_outcome_positive(actual_outcome) if actual_outcome else None
        
        # 综合判断
        ground_truth = None
        if user_positive is not None:
            ground_truth = user_positive
        elif outcome_positive is not None:
            ground_truth = outcome_positive
        
        if ground_truth is None:
            # 无法验证
            return MetaEvaluationResult(
                original_task=original_task,
                evaluation_correct=True,  # 默认正确
                evaluation_type="unverified",
                confidence_delta=0.0,
                detected_bias=None,
                recommendation="需要更多反馈来验证评估准确性"
            )
        
        # 判断评估类型
        if eval_passed and ground_truth:
            eval_type = "true_positive"
            correct = True
        elif not eval_passed and not ground_truth:
            eval_type = "true_negative"
            correct = True
        elif eval_passed and not ground_truth:
            eval_type = "false_positive"
            correct = False
        else:  # not eval_passed and ground_truth
            eval_type = "false_negative"
            correct = False
        
        # 计算置信度差异
        if ground_truth:
            confidence_delta = eval_score - 0.6  # 期望高分
        else:
            confidence_delta = 0.6 - eval_score  # 期望低分
        
        # 检测偏差
        bias = self._detect_single_bias(evaluation_result, eval_type)
        
        # 生成建议
        recommendation = self._generate_recommendation(eval_type, evaluation_result, bias)
        
        result = MetaEvaluationResult(
            original_task=original_task,
            evaluation_correct=correct,
            evaluation_type=eval_type,
            confidence_delta=confidence_delta,
            detected_bias=bias,
            recommendation=recommendation,
        )
        
        # 保存记录
        self._save_meta_evaluation(result)
        
        if not correct:
            logger.warning(
                f"元评估发现错误: {eval_type} (task={original_task[:50]}, "
                f"eval_score={eval_score:.2f}, bias={bias})"
            )
        
        return result
    
    def _is_feedback_positive(self, feedback: str) -> bool:
        """判断用户反馈是否正面"""
        if not feedback:
            return True
        
        feedback_lower = feedback.lower()
        
        positive_signals = ["好", "棒", "赞", "满意", "完美", "ok", "good", "great", "excellent", "perfect", "👍", "✅"]
        negative_signals = ["差", "烂", "不行", "失败", "不满意", "错误", "bad", "wrong", "error", "fail", "terrible", "👎", "❌"]
        
        pos_count = sum(1 for s in positive_signals if s in feedback_lower)
        neg_count = sum(1 for s in negative_signals if s in feedback_lower)
        
        if neg_count > pos_count:
            return False
        elif pos_count > neg_count:
            return True
        return True  # 默认正面
    
    def _is_outcome_positive(self, outcome: str) -> bool:
        """判断实际结果是否正面"""
        if not outcome:
            return True
        
        outcome_lower = outcome.lower()
        
        negative_signals = ["error", "fail", "exception", "timeout", "crash", "错误", "失败", "异常", "超时"]
        
        return not any(s in outcome_lower for s in negative_signals)
    
    def _detect_single_bias(self, evaluation: EvaluationResult, eval_type: str) -> Optional[str]:
        """检测单次评估中的偏差"""
        scores = evaluation.criteria_scores
        
        if eval_type == "false_positive":
            # 评估通过但实际失败 → 可能某些维度打分偏高
            if scores.get("safety", 1.0) > 0.8 and scores.get("correctness", 1.0) < 0.5:
                return "safety_inflation"  # safety 打分膨胀
            if scores.get("completeness", 0) > 0.7 and scores.get("correctness", 0) < 0.5:
                return "completeness_over_correctness"  # 完整性优先于正确性
            return "overly_optimistic"
        
        elif eval_type == "false_negative":
            # 评估失败但实际成功 → 可能某些维度打分偏低
            if scores.get("efficiency", 0) < 0.5:
                return "efficiency_overemphasis"  # 效率要求过高
            if scores.get("quality", 0) < 0.5:
                return "quality_overemphasis"
            return "overly_pessimistic"
        
        return None
    
    def _generate_recommendation(self, eval_type: str, evaluation: EvaluationResult, bias: Optional[str]) -> str:
        """生成改进建议"""
        if eval_type == "true_positive":
            return "评估准确，继续保持"
        elif eval_type == "true_negative":
            return "评估准确，失败检测有效"
        elif eval_type == "false_positive":
            if bias == "safety_inflation":
                return "建议提高 safety 维度的评估标准"
            elif bias == "completeness_over_correctness":
                return "建议降低 completeness 权重，提高 correctness 权重"
            return "建议整体提高评估严格度"
        elif eval_type == "false_negative":
            if bias == "efficiency_overemphasis":
                return "建议降低 efficiency 维度的最低阈值"
            return "建议适当放宽评估标准"
        return "暂无建议"
    
    def _save_meta_evaluation(self, result: MetaEvaluationResult):
        """保存元评估记录"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO meta_evaluations
                (task, evaluation_passed, evaluation_score, evaluation_type,
                 confidence_delta, detected_bias, recommendation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (result.original_task[:200], None, None,
             result.evaluation_type, result.confidence_delta,
             result.detected_bias, result.recommendation, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    def get_accuracy_stats(self, days: int = 30) -> Dict:
        """获取评估准确性统计"""
        cutoff = (datetime.now() - __import__('datetime').timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT evaluation_type, COUNT(*) as cnt FROM meta_evaluations WHERE created_at >= ? GROUP BY evaluation_type",
                (cutoff,)
            ).fetchall()
            
            counts = {r["evaluation_type"]: r["cnt"] for r in rows}
            
            tp = counts.get("true_positive", 0)
            tn = counts.get("true_negative", 0)
            fp = counts.get("false_positive", 0)
            fn = counts.get("false_negative", 0)
            total = tp + tn + fp + fn
            
            if total == 0:
                return {"total": 0, "accuracy": 0}
            
            return {
                "total": total,
                "true_positive": tp,
                "true_negative": tn,
                "false_positive": fp,
                "false_negative": fn,
                "accuracy": round((tp + tn) / total, 3),
                "precision": round(tp / max(tp + fp, 1), 3),
                "recall": round(tp / max(tp + fn, 1), 3),
            }
        finally:
            conn.close()
