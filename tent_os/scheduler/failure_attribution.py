"""失败归因 —— 分析任务失败的真正原因

分类体系：
    planning_error    —— 规划问题（目标不可达、参数错误）
    execution_error   —— 执行问题（机械故障、通信中断）
    environment_error —— 环境问题（障碍物、光线、地面）
    perception_error  —— 感知问题（识别错误、定位偏差）
    user_error        —— 用户指令问题（模糊、矛盾、超出范围）
    system_error      —— 系统问题（软件 bug、资源不足）

归因方法：
1. 规则匹配（快速）
2. LLM 分析（深度）
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from tent_os.scheduler.embodied_state import EmbodiedState

logger = logging.getLogger("tent_os.scheduler.attribution")


@dataclass
class FailureCause:
    """失败原因"""
    primary_cause: str         # 主要原因类型
    secondary_cause: Optional[str]  # 次要原因
    confidence: float          # 归因置信度
    description: str           # 自然语言描述
    recoverable: bool          # 是否可恢复
    recommendations: List[str]  # 修复建议


class FailureAttribution:
    """失败归因器"""
    
    # 错误关键词映射
    ERROR_PATTERNS = {
        "planning_error": [
            r"unreachable", r"out of range", r"invalid target", r"目标不可达",
            r"超出范围", r"参数错误", r"invalid parameter", r"cannot reach",
            r"超出工作空间",
        ],
        "execution_error": [
            r"motor", r"servo", r"actuator", r"机械故障", r"电机",
            r"timeout", r"通信中断", r"connection lost", r"执行失败",
            r"stuck", r"jammed", r"卡死",
        ],
        "environment_error": [
            r"obstacle", r"collision", r"blocked", r"障碍物", r"碰撞",
            r"slip", r"光线", r"lighting", r"地面", r"floor",
            r"wind", r"vibration", r"振动",
        ],
        "perception_error": [
            r"recognition", r"detection", r"定位", r"识别", r"定位失败",
            r"camera", r"sensor", r"感知", r"传感器",
            r"校准", r"calibration",
        ],
        "user_error": [
            r"ambiguous", r"unclear", r"模糊", r"矛盾", r"conflicting",
            r"超出能力", r"超出范围", r"不可能", r"impossible",
            r"unsafe", r"危险",
        ],
        "system_error": [
            r"bug", r"exception", r"crash", r"内存", r"memory",
            r"cpu", r"disk", r"资源不足", r"out of resource",
            r"software", r"软件",
        ],
    }
    
    def attribute(self, task_result: Dict, plan: Dict,
                  state: EmbodiedState = None, error: str = "") -> FailureCause:
        """归因分析
        
        优先级：
        1. 用户指令问题（最高，因为这是可控的）
        2. 规划问题
        3. 环境问题
        4. 感知问题
        5. 执行问题
        6. 系统问题
        """
        error_text = error or str(task_result.get("error", ""))
        result_text = str(task_result.get("result", ""))
        full_text = f"{error_text} {result_text}".lower()
        
        # 1. 规则匹配
        scores = {}
        for cause_type, patterns in self.ERROR_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    score += 1
            scores[cause_type] = score
        
        # 2. 状态辅助判断
        if state:
            if state.temperature and state.temperature > 80:
                scores["execution_error"] += 2
            if state.battery_level and state.battery_level < 0.1:
                scores["execution_error"] += 1
            if state.collision_count > 0:
                scores["environment_error"] += 2
            if state.emergency_stop_active:
                scores["environment_error"] += 1
        
        # 3. 计划辅助判断
        if plan:
            steps = plan.get("steps", [])
            if len(steps) == 0:
                scores["planning_error"] += 2
            if any("invalid" in str(s).lower() for s in steps):
                scores["planning_error"] += 1
        
        # 4. 确定主要原因
        if max(scores.values()) == 0:
            primary = "unknown"
            confidence = 0.3
        else:
            primary = max(scores, key=scores.get)
            confidence = min(1.0, scores[primary] / 5)
        
        # 5. 确定次要原因
        secondary = None
        sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
        if len(sorted_scores) > 1 and sorted_scores[1][1] > 0:
            secondary = sorted_scores[1][0]
        
        # 6. 生成描述和建议
        description = self._generate_description(primary, secondary, state)
        recoverable = primary not in ("user_error", "system_error")
        recommendations = self._generate_recommendations(primary, state)
        
        return FailureCause(
            primary_cause=primary,
            secondary_cause=secondary,
            confidence=confidence,
            description=description,
            recoverable=recoverable,
            recommendations=recommendations,
        )
    
    def _generate_description(self, primary: str, secondary: Optional[str],
                              state: EmbodiedState) -> str:
        """生成自然语言描述"""
        cause_names = {
            "planning_error": "规划问题",
            "execution_error": "执行问题",
            "environment_error": "环境问题",
            "perception_error": "感知问题",
            "user_error": "用户指令问题",
            "system_error": "系统问题",
            "unknown": "未知原因",
        }
        
        desc = f"主要原因: {cause_names.get(primary, primary)}"
        if secondary:
            desc += f"，次要原因: {cause_names.get(secondary, secondary)}"
        
        if state:
            desc += f" (执行者: {state.executor_id}, 健康度: {state.get_health_score():.0%})"
        
        return desc
    
    def _generate_recommendations(self, primary: str, state: EmbodiedState) -> List[str]:
        """生成修复建议"""
        recommendations = {
            "planning_error": [
                "检查目标参数是否正确",
                "确认目标在工作空间内",
                "简化任务步骤",
            ],
            "execution_error": [
                "检查执行者硬件状态",
                "重启执行者",
                "降低运动速度",
            ],
            "environment_error": [
                "清除工作区域内的障碍物",
                "改善光照条件",
                "检查地面状况",
            ],
            "perception_error": [
                "重新校准传感器",
                "改善识别目标的可视性",
                "使用备用感知方案",
            ],
            "user_error": [
                "请用户提供更明确的指令",
                "确认任务参数在能力范围内",
                "分解复杂任务",
            ],
            "system_error": [
                "检查系统日志",
                "重启相关服务",
                "联系系统管理员",
            ],
            "unknown": [
                "收集更多错误信息",
                "尝试重试",
                "联系技术支持",
            ],
        }
        
        base = recommendations.get(primary, recommendations["unknown"])
        
        if state:
            if state.battery_level and state.battery_level < 0.2:
                base = ["建议先充电"] + base
            if state.temperature and state.temperature > 70:
                base = ["建议先降温"] + base
        
        return base
    
    def get_attribution_stats(self, history: List[Dict]) -> Dict:
        """获取归因统计"""
        if not history:
            return {}
        
        cause_counts = {}
        for h in history:
            cause = h.get("primary_cause", "unknown")
            cause_counts[cause] = cause_counts.get(cause, 0) + 1
        
        total = len(history)
        return {
            "total_failures": total,
            "cause_distribution": {
                cause: {"count": count, "percentage": round(count / total, 3)}
                for cause, count in cause_counts.items()
            },
            "most_common": max(cause_counts, key=cause_counts.get) if cause_counts else None,
            "recoverable_rate": sum(1 for h in history if h.get("recoverable", False)) / total,
        }
