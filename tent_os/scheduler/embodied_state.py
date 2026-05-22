"""具身状态 —— 物理执行者的"身体感知"

让物理执行者（机器人、机械臂、无人机等）知道自己：
1. 在哪里（位置、朝向）
2. 能做什么（能力边界）
3. 当前状态（电量、温度、负载）
4. 周围环境（障碍物、工作空间）
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("tent_os.scheduler.embodied")


@dataclass
class EmbodiedState:
    """具身状态 —— 物理执行者的身体感知"""
    executor_id: str
    
    # 物理位置
    position: Optional[Tuple[float, float, float]] = None      # 3D 坐标 (x, y, z)
    orientation: Optional[Tuple[float, float, float]] = None   # 欧拉角 (roll, pitch, yaw)
    
    # 身体状态
    battery_level: Optional[float] = None    # 电量 0-1
    temperature: Optional[float] = None      # 温度（摄氏度）
    motor_temperatures: Dict[str, float] = None  # 各电机温度
    
    # 能力边界
    max_reach: Optional[float] = None        # 最大臂展（米）
    max_load: Optional[float] = None         # 最大负载（千克）
    max_speed: Optional[float] = None        # 最大速度（米/秒）
    supported_grippers: List[str] = None     # 支持的夹具类型
    
    # 当前状态
    current_gripper: Optional[str] = None
    holding_object: Optional[str] = None     # 当前持有的物体
    current_action: Optional[str] = None     # 正在执行的动作
    
    # 环境感知
    nearby_obstacles: List[Dict] = None      # 附近障碍物 [{"type": "box", "position": (x,y,z), "size": (w,h,d)}]
    workspace_bounds: Optional[Tuple] = None  # 工作空间边界
    floor_type: Optional[str] = None         # 地面类型
    lighting_level: Optional[float] = None   # 光照水平 0-1
    
    # 安全状态
    emergency_stop_active: bool = False
    safety_zone_violations: int = 0
    collision_count: int = 0
    
    # 时间戳
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        if self.motor_temperatures is None:
            self.motor_temperatures = {}
        if self.supported_grippers is None:
            self.supported_grippers = []
        if self.nearby_obstacles is None:
            self.nearby_obstacles = []
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "executor_id": self.executor_id,
            "position": self.position,
            "orientation": self.orientation,
            "battery_level": self.battery_level,
            "temperature": self.temperature,
            "max_reach": self.max_reach,
            "max_load": self.max_load,
            "current_gripper": self.current_gripper,
            "holding_object": self.holding_object,
            "current_action": self.current_action,
            "emergency_stop_active": self.emergency_stop_active,
            "collision_count": self.collision_count,
            "updated_at": self.updated_at,
        }
    
    def is_capable_of(self, action: str, params: Dict) -> bool:
        """检查是否具备执行某动作的能力"""
        # 检查电量
        if self.battery_level is not None and self.battery_level < 0.1:
            logger.warning(f"执行者 {self.executor_id} 电量不足 ({self.battery_level:.0%})")
            return False
        
        # 检查温度
        if self.temperature is not None and self.temperature > 80:
            logger.warning(f"执行者 {self.executor_id} 温度过高 ({self.temperature}°C)")
            return False
        
        # 检查夹具
        if "gripper" in params:
            required_gripper = params["gripper"]
            if required_gripper not in self.supported_grippers:
                logger.warning(f"执行者 {self.executor_id} 不支持夹具 {required_gripper}")
                return False
        
        # 检查负载
        if "weight" in params and self.max_load is not None:
            if params["weight"] > self.max_load:
                logger.warning(f"执行者 {self.executor_id} 负载超限 ({params['weight']} > {self.max_load})")
                return False
        
        # 检查紧急停止
        if self.emergency_stop_active:
            logger.warning(f"执行者 {self.executor_id} 紧急停止中")
            return False
        
        return True
    
    def get_health_score(self) -> float:
        """获取健康评分 0-1"""
        scores = []
        
        if self.battery_level is not None:
            scores.append(self.battery_level)
        
        if self.temperature is not None:
            temp_score = max(0, 1.0 - (self.temperature - 40) / 60)  # 40°C 以下满分，100°C 零分
            scores.append(temp_score)
        
        if self.collision_count is not None:
            collision_score = max(0, 1.0 - self.collision_count * 0.1)
            scores.append(collision_score)
        
        if not scores:
            return 1.0
        
        return sum(scores) / len(scores)
    
    def update_from_sensor_data(self, sensor_data: Dict):
        """从传感器数据更新状态"""
        if "position" in sensor_data:
            self.position = tuple(sensor_data["position"])
        if "orientation" in sensor_data:
            self.orientation = tuple(sensor_data["orientation"])
        if "battery" in sensor_data:
            self.battery_level = sensor_data["battery"]
        if "temperature" in sensor_data:
            self.temperature = sensor_data["temperature"]
        if "obstacles" in sensor_data:
            self.nearby_obstacles = sensor_data["obstacles"]
        if "holding" in sensor_data:
            self.holding_object = sensor_data["holding"]
        
        self.updated_at = datetime.now().isoformat()


class EmbodiedStateManager:
    """具身状态管理器 —— 管理多个物理执行者的状态"""
    
    def __init__(self):
        self._states: Dict[str, EmbodiedState] = {}
    
    def register(self, executor_id: str, state: EmbodiedState):
        """注册执行者"""
        self._states[executor_id] = state
        logger.info(f"具身状态注册: {executor_id}")
    
    def get(self, executor_id: str) -> Optional[EmbodiedState]:
        """获取执行者状态"""
        return self._states.get(executor_id)
    
    def update(self, executor_id: str, sensor_data: Dict):
        """更新执行者状态"""
        state = self._states.get(executor_id)
        if state:
            state.update_from_sensor_data(sensor_data)
    
    def get_all_states(self) -> Dict[str, EmbodiedState]:
        """获取所有执行者状态"""
        return dict(self._states)
    
    def get_summary(self) -> Dict:
        """获取状态摘要"""
        return {
            executor_id: {
                "health": state.get_health_score(),
                "battery": state.battery_level,
                "temperature": state.temperature,
                "action": state.current_action,
                "emergency_stop": state.emergency_stop_active,
            }
            for executor_id, state in self._states.items()
        }
