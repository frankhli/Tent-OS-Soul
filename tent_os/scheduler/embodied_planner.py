"""具身规划器 —— 执行前做物理规划

在发送命令给物理执行者之前：
1. 检查动作是否在能力边界内
2. 规划运动路径（简单避障）
3. 评估执行风险
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from tent_os.scheduler.embodied_state import EmbodiedState

logger = logging.getLogger("tent_os.scheduler.planner")


@dataclass
class MotionPlan:
    """运动规划"""
    waypoints: List[Tuple[float, float, float]]  # 路径点
    estimated_time: float                          # 预计时间（秒）
    risk_level: float                              # 风险等级 0-1
    alternatives: int                              # 备选路径数


@dataclass
class FeasibilityResult:
    """可行性检查结果"""
    feasible: bool
    reason: str
    risk_level: float
    recommendations: List[str]


class EmbodiedPlanner:
    """具身规划器"""
    
    def plan_motion(self, target: Tuple[float, float, float],
                    state: EmbodiedState) -> MotionPlan:
        """规划运动路径
        
        简化实现：直接路径 + 障碍物检测
        """
        if not state.position:
            return MotionPlan(
                waypoints=[target],
                estimated_time=10.0,
                risk_level=0.5,
                alternatives=0,
            )
        
        start = state.position
        
        # 检查障碍物
        obstacles = state.nearby_obstacles or []
        risk = 0.0
        
        for obs in obstacles:
            obs_pos = obs.get("position", (0, 0, 0))
            distance = self._distance(start, obs_pos)
            if distance < 0.5:  # 50cm 内有障碍物
                risk += 0.3
        
        risk = min(1.0, risk)
        
        # 简单路径：起点 → 目标点
        # 实际应用中应使用 RRT* / A* 等路径规划算法
        waypoints = [start, target]
        
        # 估算时间（假设速度 0.1m/s）
        distance = self._distance(start, target)
        estimated_time = distance / 0.1 if distance > 0 else 1.0
        
        return MotionPlan(
            waypoints=waypoints,
            estimated_time=estimated_time,
            risk_level=risk,
            alternatives=1 if risk > 0.3 else 0,
        )
    
    def check_feasibility(self, action: str, params: Dict,
                          state: EmbodiedState) -> FeasibilityResult:
        """检查动作是否在能力边界内"""
        recommendations = []
        
        # 1. 基础能力检查
        if not state.is_capable_of(action, params):
            return FeasibilityResult(
                feasible=False,
                reason="超出能力边界",
                risk_level=1.0,
                recommendations=["更换执行者或调整任务参数"],
            )
        
        # 2. 电量检查
        risk = 0.0
        if state.battery_level is not None:
            if state.battery_level < 0.2:
                risk += 0.3
                recommendations.append("电量较低，建议先充电")
            elif state.battery_level < 0.1:
                risk += 0.5
        
        # 3. 温度检查
        if state.temperature is not None:
            if state.temperature > 60:
                risk += 0.2
                recommendations.append("温度偏高，建议降温")
            elif state.temperature > 80:
                risk += 0.5
        
        # 4. 工作空间检查
        if state.workspace_bounds and "position" in params:
            target_pos = params["position"]
            if not self._is_in_bounds(target_pos, state.workspace_bounds):
                return FeasibilityResult(
                    feasible=False,
                    reason="目标位置超出工作空间",
                    risk_level=1.0,
                    recommendations=["调整目标位置到工作空间内"],
                )
        
        # 5. 路径风险
        if "position" in params:
            plan = self.plan_motion(tuple(params["position"]), state)
            risk = max(risk, plan.risk_level)
            if plan.risk_level > 0.5:
                recommendations.append("路径风险较高，建议人工确认")
        
        feasible = risk < 0.7
        
        return FeasibilityResult(
            feasible=feasible,
            reason="" if feasible else "风险过高",
            risk_level=risk,
            recommendations=recommendations,
        )
    
    def _distance(self, a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
        """计算欧氏距离"""
        return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
    
    def _is_in_bounds(self, position: Tuple, bounds: Tuple) -> bool:
        """检查位置是否在工作空间边界内"""
        # bounds: (min_x, min_y, min_z, max_x, max_y, max_z)
        if len(bounds) != 6 or len(position) != 3:
            return True  # 无法判断，默认通过
        
        return (bounds[0] <= position[0] <= bounds[3] and
                bounds[1] <= position[1] <= bounds[4] and
                bounds[2] <= position[2] <= bounds[5])
