"""Evaluator 代理 —— Harness 模式

核心设计：
1. 执行完成后，Evaluator 独立评估结果
2. 与 Generator（执行者）分离，避免自评估偏见
3. 生成结构化评分，不通过则触发重试
4. 可配置评估维度

评估流程：
    Execute → Evaluate → [Pass → Done / Fail → Retry]
"""

import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("tent_os.evaluator")


@dataclass
class EvaluationCriterion:
    """评估维度"""
    name: str           # 维度名称
    weight: float       # 权重（0-1）
    min_score: float    # 最低通过分数（0-1）
    description: str    # 评估标准描述


@dataclass
class EvaluationResult:
    """评估结果"""
    passed: bool
    overall_score: float
    criteria_scores: Dict[str, float]
    feedback: str
    retry_recommended: bool
    max_retries_exceeded: bool = False


DEFAULT_CRITERIA = [
    EvaluationCriterion("completeness", 0.3, 0.6, "任务是否完整执行，没有遗漏步骤"),
    EvaluationCriterion("correctness", 0.3, 0.7, "结果是否正确，没有错误"),
    EvaluationCriterion("safety", 0.2, 0.8, "操作是否安全，没有违反规则"),
    EvaluationCriterion("efficiency", 0.1, 0.5, "执行是否高效，没有冗余步骤"),
    EvaluationCriterion("quality", 0.1, 0.5, "输出质量是否达标"),
]


class Evaluator:
    """独立评估代理 —— 被调为'怀疑者'模式
    
    两种评估模式：
    1. Rule-based（规则评估）：快速、确定性、零成本
    2. LLM-based（LLM 评估）：深度、主观、有成本
    """
    
    def __init__(self, llm=None, criteria: List[EvaluationCriterion] = None,
                 max_retries: int = 2):
        self.llm = llm
        self.criteria = criteria or DEFAULT_CRITERIA
        self.max_retries = max_retries
    
    async def evaluate(self, task_result: Dict, plan: Dict,
                       retry_count: int = 0) -> EvaluationResult:
        """评估任务执行结果
        
        Args:
            task_result: 执行者返回的结果
            plan: 原始计划
            retry_count: 已重试次数
        
        Returns:
            EvaluationResult
        """
        # 1. 规则评估（快速路径）
        rule_result = self._rule_based_evaluate(task_result, plan)
        
        # 2. 如果规则评估通过且没有 LLM，直接返回
        if rule_result.passed and not self.llm:
            return rule_result
        
        # 3. LLM 深度评估（可选）
        if self.llm:
            llm_result = await self._llm_evaluate(task_result, plan)
            # 合并结果：规则 + LLM 加权
            return self._merge_results(rule_result, llm_result)
        
        return rule_result
    
    def _rule_based_evaluate(self, task_result: Dict, plan: Dict) -> EvaluationResult:
        """规则评估 —— 零成本、确定性、<1ms"""
        scores = {}
        
        # completeness: 检查是否有结果
        result_data = task_result.get("result", {}) if isinstance(task_result, dict) else {}
        if isinstance(result_data, dict):
            has_result = bool(result_data) and "error" not in str(result_data).lower()
        else:
            has_result = bool(result_data)
        scores["completeness"] = 1.0 if has_result else 0.0
        
        # correctness: 检查是否有错误
        status = task_result.get("status", "") if isinstance(task_result, dict) else ""
        error = task_result.get("error", "") if isinstance(task_result, dict) else ""
        no_error = status != "failed" and not error
        scores["correctness"] = 1.0 if no_error else 0.0
        
        # safety: 检查是否有危险操作结果
        dangerous_keywords = ["unauthorized", "forbidden", "dangerous", "kill", "delete_all"]
        result_str = json.dumps(task_result).lower()
        is_safe = not any(kw in result_str for kw in dangerous_keywords)
        scores["safety"] = 1.0 if is_safe else 0.0
        
        # efficiency: 步骤数 vs 计划步骤数
        plan_steps = len(plan.get("steps", [])) if isinstance(plan, dict) else 0
        scores["efficiency"] = 1.0 if plan_steps <= 3 else 0.7 if plan_steps <= 5 else 0.5
        
        # quality: 默认中等
        scores["quality"] = 0.7 if has_result and no_error else 0.3
        
        # 计算加权总分
        overall = sum(
            scores.get(c.name, 0) * c.weight
            for c in self.criteria
        )
        
        # 检查每个维度是否通过最低阈值
        all_passed = all(
            scores.get(c.name, 0) >= c.min_score
            for c in self.criteria
        )
        
        feedback = self._generate_feedback(scores, all_passed)
        
        return EvaluationResult(
            passed=all_passed and overall >= 0.6,
            overall_score=overall,
            criteria_scores=scores,
            feedback=feedback,
            retry_recommended=not all_passed,
        )
    
    async def _llm_evaluate(self, task_result: Dict, plan: Dict) -> EvaluationResult:
        """LLM 深度评估 —— 处理主观质量判断"""
        prompt = f"""你是一个严格的质量评估员。请评估以下任务执行结果。

原始计划：
{json.dumps(plan, ensure_ascii=False, indent=2)[:2000]}

执行结果：
{json.dumps(task_result, ensure_ascii=False, indent=2)[:2000]}

请从以下维度评分（0.0-1.0）：
1. completeness: 任务是否完整执行
2. correctness: 结果是否正确
3. safety: 操作是否安全合规
4. efficiency: 执行是否高效
5. quality: 整体质量

输出严格JSON格式：
{{"scores": {{"completeness": 0.x, "correctness": 0.x, ...}}, "feedback": "具体改进建议", "passed": true/false}}"""
        
        try:
            if hasattr(self.llm, 'chat'):
                response = await self.llm.chat([{"role": "user", "content": prompt}])
            elif hasattr(self.llm, 'complete'):
                response = await self.llm.complete(prompt)
            else:
                response = await self.llm(prompt)
            
            data = json.loads(response)
            scores = data.get("scores", {})
            
            overall = sum(
                scores.get(c.name, 0) * c.weight
                for c in self.criteria
            )
            
            all_passed = all(
                scores.get(c.name, 0) >= c.min_score
                for c in self.criteria
            )
            
            return EvaluationResult(
                passed=all_passed and overall >= 0.6,
                overall_score=overall,
                criteria_scores=scores,
                feedback=data.get("feedback", ""),
                retry_recommended=not all_passed,
            )
        except Exception as e:
            logger.warning(f"LLM 评估失败，回退到规则评估: {e}")
            return self._rule_based_evaluate(task_result, plan)
    
    def _merge_results(self, rule: EvaluationResult, llm: EvaluationResult) -> EvaluationResult:
        """合并规则和 LLM 评估结果"""
        # 加权合并：规则 40% + LLM 60%
        merged_scores = {}
        for key in rule.criteria_scores:
            merged_scores[key] = rule.criteria_scores.get(key, 0) * 0.4 + llm.criteria_scores.get(key, 0) * 0.6
        
        overall = sum(
            merged_scores.get(c.name, 0) * c.weight
            for c in self.criteria
        )
        
        # 取更严格的结果
        all_passed = all(
            merged_scores.get(c.name, 0) >= c.min_score
            for c in self.criteria
        )
        
        passed = all_passed and overall >= 0.6
        
        feedback = f"[规则评估] {rule.feedback}\n[LLM评估] {llm.feedback}"
        
        return EvaluationResult(
            passed=passed,
            overall_score=overall,
            criteria_scores=merged_scores,
            feedback=feedback,
            retry_recommended=not passed,
        )
    
    def _generate_feedback(self, scores: Dict[str, float], all_passed: bool) -> str:
        """生成可操作的反馈"""
        if all_passed:
            return "所有评估维度通过。"
        
        feedback = []
        for c in self.criteria:
            score = scores.get(c.name, 0)
            if score < c.min_score:
                feedback.append(f"{c.name}: 得分 {score:.2f} 低于阈值 {c.min_score} — {c.description}")
        
        return "; ".join(feedback) if feedback else "评估未通过，具体原因不明。"
    
    def should_retry(self, evaluation: EvaluationResult, retry_count: int) -> bool:
        """判断是否应重试"""
        if evaluation.passed:
            return False
        if retry_count >= self.max_retries:
            evaluation.max_retries_exceeded = True
            return False
        return evaluation.retry_recommended
    
    def format_report(self, evaluation: EvaluationResult) -> str:
        """格式化评估报告"""
        lines = [
            f"{'✅' if evaluation.passed else '❌'} 评估结果: {'通过' if evaluation.passed else '未通过'}",
            f"综合得分: {evaluation.overall_score:.2f}",
            "各维度得分:",
        ]
        for name, score in evaluation.criteria_scores.items():
            threshold = next((c.min_score for c in self.criteria if c.name == name), 0)
            status = "✓" if score >= threshold else "✗"
            lines.append(f"  {status} {name}: {score:.2f} (阈值: {threshold})")
        lines.append(f"反馈: {evaluation.feedback}")
        if evaluation.max_retries_exceeded:
            lines.append("⚠️ 已达到最大重试次数，不再重试")
        return "\n".join(lines)
