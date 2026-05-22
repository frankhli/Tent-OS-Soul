"""元学习器 —— 从评估历史中学习如何更好地评估

核心能力：
1. 学习用户偏好：用户在意哪些维度
2. 自动调整评估权重
3. 生成新的评估规则写入程序记忆
4. 校准评估阈值

学习信号：
- 元评估结果（真阳性/假阳性/真阴性/假阴性）
- 用户反馈
- 任务成功率
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from tent_os.governance.evaluator import DEFAULT_CRITERIA, EvaluationCriterion
from tent_os.memory.procedural import ProceduralMemoryStore, ProceduralRule

logger = logging.getLogger("tent_os.meta.learner")


class MetaLearner:
    """元学习器"""
    
    def __init__(self, meta_eval_db_path: str = "./tent_memory/meta_eval.db",
                 procedural_store: ProceduralMemoryStore = None):
        self.db_path = Path(meta_eval_db_path)
        self.procedural_store = procedural_store
        
        # 评估维度权重（可学习的）
        self.dimension_weights = {
            "completeness": 0.3,
            "correctness": 0.3,
            "safety": 0.2,
            "efficiency": 0.1,
            "quality": 0.1,
        }
        
        # 维度阈值（可学习的）
        self.dimension_thresholds = {
            "completeness": 0.6,
            "correctness": 0.7,
            "safety": 0.8,
            "efficiency": 0.5,
            "quality": 0.5,
        }
    
    def learn_from_history(self, days: int = 30) -> Dict[str, float]:
        """从元评估历史中学习
        
        Returns:
            Dict: 应用的调整
        """
        if not self.db_path.exists():
            return {}
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM meta_evaluations WHERE created_at >= ?",
                (cutoff,)
            ).fetchall()
        finally:
            conn.close()
        
        if not rows:
            return {}
        
        # 分析假阳性和假阴性
        fp_count = sum(1 for r in rows if r["evaluation_type"] == "false_positive")
        fn_count = sum(1 for r in rows if r["evaluation_type"] == "false_negative")
        total = len(rows)
        
        adjustments = {}
        
        # 1. 假阳性过多 → 整体提高严格度（降低阈值）
        if fp_count / total > 0.2:
            for dim in self.dimension_thresholds:
                old = self.dimension_thresholds[dim]
                new = min(0.95, old + 0.05)
                self.dimension_thresholds[dim] = new
                adjustments[f"{dim}_threshold"] = round(new - old, 3)
            logger.info(f"元学习：假阳性率 {(fp_count/total):.1%}，提高严格度")
        
        # 2. 假阴性过多 → 整体降低严格度（提高阈值）
        elif fn_count / total > 0.2:
            for dim in self.dimension_thresholds:
                old = self.dimension_thresholds[dim]
                new = max(0.3, old - 0.05)
                self.dimension_thresholds[dim] = new
                adjustments[f"{dim}_threshold"] = round(new - old, 3)
            logger.info(f"元学习：假阴性率 {(fn_count/total):.1%}，降低严格度")
        
        # 3. 学习维度权重偏好
        # 如果用户经常纠正 completeness 但很少纠正 correctness
        # → 降低 completeness 权重，提高 correctness 权重
        # （简化实现：基于偏差检测调整）
        
        # 4. 生成新的程序记忆规则
        if adjustments:
            self._generate_rules_from_adjustments(adjustments)
        
        return adjustments
    
    def learn_from_user_feedback(self, dimension: str, 
                                 user_importance: float) -> float:
        """从用户反馈学习维度重要性
        
        Args:
            dimension: 维度名称
            user_importance: 用户认为的重要性 0-1
            
        Returns:
            float: 调整后的权重
        """
        if dimension not in self.dimension_weights:
            return 0.0
        
        current = self.dimension_weights[dimension]
        # 缓慢向用户偏好靠拢
        new_weight = current * 0.8 + user_importance * 0.2
        new_weight = max(0.05, min(0.5, new_weight))
        
        self.dimension_weights[dimension] = new_weight
        
        # 重新归一化
        total = sum(self.dimension_weights.values())
        for dim in self.dimension_weights:
            self.dimension_weights[dim] /= total
        
        logger.info(f"元学习：{dimension} 权重 {current:.2f} → {self.dimension_weights[dimension]:.2f}")
        return self.dimension_weights[dimension]
    
    def _generate_rules_from_adjustments(self, adjustments: Dict[str, float]):
        """从调整生成程序记忆规则"""
        if not self.procedural_store:
            return
        
        for key, delta in adjustments.items():
            if "threshold" in key:
                dim = key.replace("_threshold", "")
                if delta > 0:
                    # 提高了阈值
                    rule = ProceduralRule(
                        id=None,
                        trigger_condition=f"评估任务时",
                        action_rule=f"{dim} 维度的评估标准应更严格（阈值提升 {delta:.2f}）",
                        category="correctness",
                        source_experience="元学习：假阳性过多",
                        confidence=0.6,
                        success_count=0,
                        failure_count=0,
                        created_at=datetime.now().isoformat(),
                        last_applied=None,
                    )
                else:
                    # 降低了阈值
                    rule = ProceduralRule(
                        id=None,
                        trigger_condition=f"评估任务时",
                        action_rule=f"{dim} 维度的评估标准应更宽松（阈值降低 {abs(delta):.2f}）",
                        category="correctness",
                        source_experience="元学习：假阴性过多",
                        confidence=0.6,
                        success_count=0,
                        failure_count=0,
                        created_at=datetime.now().isoformat(),
                        last_applied=None,
                    )
                
                self.procedural_store.add_rule(
                    trigger_condition=rule.trigger_condition,
                    action_rule=rule.action_rule,
                    category=rule.category,
                    source_experience=rule.source_experience,
                    confidence=rule.confidence,
                )
                logger.info(f"元学习生成规则: {rule.action_rule}")
    
    def get_optimized_criteria(self) -> List[EvaluationCriterion]:
        """获取优化后的评估维度"""
        criteria = []
        for c in DEFAULT_CRITERIA:
            weight = self.dimension_weights.get(c.name, c.weight)
            threshold = self.dimension_thresholds.get(c.name, c.min_score)
            criteria.append(EvaluationCriterion(
                name=c.name,
                weight=weight,
                min_score=threshold,
                description=c.description,
            ))
        return criteria
    
    def get_learning_stats(self) -> Dict:
        """获取学习统计"""
        return {
            "dimension_weights": self.dimension_weights,
            "dimension_thresholds": self.dimension_thresholds,
            "total_adjustments": 0,  # TODO: 追踪调整次数
        }
