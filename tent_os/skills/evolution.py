"""Skill 进化器 —— 让 Skill 自我改进

核心能力：
1. 根据效果指标自动改进 Skill（prompt 优化、示例补充）
2. A/B 测试两种 Skill 版本
3. 依赖管理（Skill 之间的调用关系）

改进策略：
- 成功率低 → 修改 prompt，增加边界示例
- 用户经常纠正 → 补充边界情况说明
- 执行时间长 → 优化工具调用流程
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from tent_os.skills.metrics import SkillMetrics, SkillMetricsStore

logger = logging.getLogger("tent_os.skills.evolution")


@dataclass
class SkillUpdate:
    """Skill 更新建议"""
    skill_name: str
    change_type: str           # "prompt_enhance" / "add_example" / "simplify" / "boundary_clarify"
    reason: str
    old_version: str
    new_version: str
    confidence: float          # 改进建议的置信度
    estimated_improvement: float  # 预计改进幅度


class SkillEvolution:
    """Skill 进化引擎"""
    
    def __init__(self, metrics_store: SkillMetricsStore, llm=None):
        self.metrics_store = metrics_store
        self.llm = llm
    
    def analyze_skill(self, skill_name: str) -> Optional[Dict]:
        """分析 Skill 的表现，生成诊断报告"""
        metrics = self.metrics_store.get_metrics(skill_name)
        if not metrics:
            return None
        
        issues = []
        
        # 成功率低
        if metrics.success_rate() < 0.5:
            issues.append({
                "type": "low_success_rate",
                "severity": 1 - metrics.success_rate(),
                "message": f"成功率仅 {metrics.success_rate():.0%}",
            })
        
        # 用户纠正多
        if metrics.user_corrections > metrics.invocation_count * 0.2:
            issues.append({
                "type": "high_correction_rate",
                "severity": metrics.user_corrections / max(metrics.invocation_count, 1),
                "message": f"用户纠正率 {(metrics.user_corrections / max(metrics.invocation_count, 1)):.0%}",
            })
        
        # 重试次数多
        if metrics.avg_retry_count > 1:
            issues.append({
                "type": "high_retry_rate",
                "severity": min(1.0, metrics.avg_retry_count / 3),
                "message": f"平均重试 {metrics.avg_retry_count:.1f} 次",
            })
        
        # 满意度低
        if metrics.user_ratings_count > 0 and metrics.user_satisfaction < 3:
            issues.append({
                "type": "low_satisfaction",
                "severity": (5 - metrics.user_satisfaction) / 5,
                "message": f"用户满意度 {metrics.user_satisfaction:.1f}/5",
            })
        
        # 执行时间长
        if metrics.avg_execution_time > 30:
            issues.append({
                "type": "slow_execution",
                "severity": min(1.0, metrics.avg_execution_time / 60),
                "message": f"平均执行时间 {metrics.avg_execution_time:.1f}s",
            })
        
        issues.sort(key=lambda x: x["severity"], reverse=True)
        
        return {
            "skill_name": skill_name,
            "overall_score": metrics.overall_score(),
            "metrics": {
                "invocations": metrics.invocation_count,
                "success_rate": metrics.success_rate(),
                "satisfaction": metrics.user_satisfaction,
                "avg_retries": metrics.avg_retry_count,
                "avg_time": metrics.avg_execution_time,
            },
            "issues": issues,
            "recommendations": self._generate_recommendations(issues),
        }
    
    def _generate_recommendations(self, issues: List[Dict]) -> List[str]:
        """根据问题生成改进建议"""
        recommendations = []
        
        for issue in issues:
            issue_type = issue["type"]
            
            if issue_type == "low_success_rate":
                recommendations.append("增加边界情况示例和错误处理说明")
                recommendations.append("检查工具调用参数是否正确")
            
            elif issue_type == "high_correction_rate":
                recommendations.append("补充用户常见纠正场景的说明")
                recommendations.append("增加对输出格式的明确要求")
            
            elif issue_type == "high_retry_rate":
                recommendations.append("优化执行步骤，减少不必要的重试")
                recommendations.append("增加前置条件检查")
            
            elif issue_type == "low_satisfaction":
                recommendations.append("增加结果解释和上下文说明")
                recommendations.append("调整输出风格以匹配用户期望")
            
            elif issue_type == "slow_execution":
                recommendations.append("优化工具调用流程，减少冗余操作")
                recommendations.append("考虑增加并行执行能力")
        
        # 去重
        seen = set()
        unique = []
        for r in recommendations:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        
        return unique[:5]
    
    async def evolve_skill(self, skill_name: str, current_prompt: str,
                           current_tools: List[str]) -> Optional[SkillUpdate]:
        """进化 Skill —— 生成改进版本
        
        如果配置了 LLM，使用 LLM 生成改进建议。
        否则基于规则生成简单改进。
        """
        diagnosis = self.analyze_skill(skill_name)
        if not diagnosis:
            return None
        
        issues = diagnosis["issues"]
        if not issues:
            logger.info(f"Skill {skill_name} 表现良好，无需改进")
            return None
        
        # 规则驱动改进
        if not self.llm:
            return self._rule_based_evolve(skill_name, current_prompt, issues)
        
        # LLM 驱动改进
        return await self._llm_based_evolve(skill_name, current_prompt, issues)
    
    def _rule_based_evolve(self, skill_name: str, current_prompt: str,
                           issues: List[Dict]) -> Optional[SkillUpdate]:
        """基于规则的 Skill 改进"""
        # 简单策略：在 prompt 末尾追加改进说明
        additions = []
        
        for issue in issues:
            if issue["type"] == "low_success_rate":
                additions.append("\n\n注意：执行前检查所有参数的有效性，遇到错误时详细说明原因。")
            elif issue["type"] == "high_correction_rate":
                additions.append("\n\n注意：严格按照用户要求的格式输出，不确定时先确认再执行。")
            elif issue["type"] == "high_retry_rate":
                additions.append("\n\n注意：每个步骤执行后立即检查结果，避免不必要的重复。")
        
        if not additions:
            return None
        
        new_prompt = current_prompt + "\n".join(additions)
        
        return SkillUpdate(
            skill_name=skill_name,
            change_type="prompt_enhance",
            reason="基于规则的性能优化",
            old_version=current_prompt,
            new_version=new_prompt,
            confidence=0.6,
            estimated_improvement=0.1,
        )
    
    async def _llm_based_evolve(self, skill_name: str, current_prompt: str,
                                issues: List[Dict]) -> Optional[SkillUpdate]:
        """基于 LLM 的 Skill 改进"""
        issues_text = "\n".join(f"- {i['message']} ({i['type']})" for i in issues[:3])
        
        prompt = f"""分析以下 Skill 的问题，优化其 prompt 以提升表现。

当前 Skill Prompt：
{current_prompt[:1000]}

发现的问题：
{issues_text}

请输出优化后的 prompt（保持原有核心功能，针对问题进行改进）：
"""
        
        try:
            new_prompt = await self.llm.complete(prompt)
            
            if len(new_prompt) < len(current_prompt) * 0.5:
                # LLM 输出可能不完整
                return None
            
            return SkillUpdate(
                skill_name=skill_name,
                change_type="prompt_enhance",
                reason=f"LLM 优化：{issues[0]['message']}",
                old_version=current_prompt,
                new_version=new_prompt,
                confidence=0.7,
                estimated_improvement=0.15,
            )
        except Exception as e:
            logger.warning(f"LLM Skill 进化失败: {e}")
            return None
    
    def get_evolution_report(self) -> Dict:
        """获取进化报告"""
        all_metrics = self.metrics_store.get_all_metrics()
        
        if not all_metrics:
            return {"status": "no_data"}
        
        # 分析所有 Skill
        diagnoses = []
        for skill_name in all_metrics:
            diagnosis = self.analyze_skill(skill_name)
            if diagnosis:
                diagnoses.append(diagnosis)
        
        # 排序
        diagnoses.sort(key=lambda d: d["overall_score"])
        
        return {
            "generated_at": datetime.now().isoformat(),
            "total_skills": len(all_metrics),
            "underperforming": len([d for d in diagnoses if d["overall_score"] < 0.5]),
            "top_issues": [
                {
                    "skill": d["skill_name"],
                    "score": d["overall_score"],
                    "top_issue": d["issues"][0]["message"] if d["issues"] else "无",
                }
                for d in diagnoses[:5]
            ],
            "recommendations": [
                f"改进 {d['skill_name']}: {d['recommendations'][0]}"
                for d in diagnoses[:3] if d["recommendations"]
            ],
        }
