from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import heapq
import logging

logger = logging.getLogger("tent_os.scheduler")


class ExecutorStatus(Enum):
    """执行者状态机 —— VDA 5050 风格
    
    IDLE → ASSIGNED → EXECUTING → COMPLETED
      ↓       ↓           ↓           ↓
    ERROR ← CANCELLED ← TIMEOUT ← FAILED
    
    状态转换全部通过 NATS 事件发布，支持 Saga 事务回滚。
    """
    IDLE = "idle"           # 空闲，可接受任务
    ASSIGNED = "assigned"   # 已分配任务，准备执行
    EXECUTING = "executing" # 正在执行
    COMPLETED = "completed" # 执行成功完成
    FAILED = "failed"       # 执行失败
    TIMEOUT = "timeout"     # 执行超时
    CANCELLED = "cancelled" # 任务被取消
    ERROR = "error"         # 执行者错误（非任务错误）
    OFFLINE = "offline"     # 离线/熔断
    EMERGENCY_STOP = "emergency_stop"  # 紧急停止


# 有效的状态转换规则
VALID_TRANSITIONS = {
    ExecutorStatus.IDLE: [ExecutorStatus.ASSIGNED, ExecutorStatus.OFFLINE, ExecutorStatus.ERROR],
    ExecutorStatus.ASSIGNED: [ExecutorStatus.EXECUTING, ExecutorStatus.CANCELLED, ExecutorStatus.OFFLINE],
    ExecutorStatus.EXECUTING: [ExecutorStatus.COMPLETED, ExecutorStatus.FAILED, ExecutorStatus.TIMEOUT, 
                                ExecutorStatus.CANCELLED, ExecutorStatus.EMERGENCY_STOP],
    ExecutorStatus.COMPLETED: [ExecutorStatus.IDLE],
    ExecutorStatus.FAILED: [ExecutorStatus.IDLE, ExecutorStatus.OFFLINE],
    ExecutorStatus.TIMEOUT: [ExecutorStatus.IDLE, ExecutorStatus.OFFLINE],
    ExecutorStatus.CANCELLED: [ExecutorStatus.IDLE],
    ExecutorStatus.ERROR: [ExecutorStatus.IDLE, ExecutorStatus.OFFLINE],
    ExecutorStatus.OFFLINE: [ExecutorStatus.IDLE],  # 手动恢复
    ExecutorStatus.EMERGENCY_STOP: [ExecutorStatus.IDLE],  # 手动复位
}


@dataclass
class ExecutorState:
    executor_id: str
    executor_type: str
    status: ExecutorStatus
    queue_depth: int
    failure_rate_24h: float
    avg_completion_seconds: int
    cost_per_task: float
    capabilities: List[str]
    consecutive_failures: int = 0
    circuit_breaker_threshold: int = 3
    # 三维决策元数据（0-1 分数）
    standardization: float = 0.5  # 标准化程度
    social: float = 0.5           # 社交能力
    risk_tolerance: float = 0.5   # 风险承受度
    # 物理执行者特有属性
    is_physical: bool = False     # 是否是物理执行者（机器人/人类）
    current_task_id: Optional[str] = None  # 当前执行的任务
    current_action: Optional[str] = None   # 当前执行的动作
    
    def total_cost(self) -> float:
        execution = self.cost_per_task
        delay = self.queue_depth * self.avg_completion_seconds * 0.01
        failure = self.failure_rate_24h * execution * 2
        return execution + delay + failure
    
    def __lt__(self, other: "ExecutorState") -> bool:
        return self.total_cost() < other.total_cost()
    
    def can_accept_task(self) -> bool:
        """是否可以接受新任务"""
        return self.status in (ExecutorStatus.IDLE,) and self.queue_depth < 5
    
    def transition_to(self, new_status: ExecutorStatus) -> bool:
        """状态转换，返回是否成功"""
        valid_next = VALID_TRANSITIONS.get(self.status, [])
        if new_status in valid_next:
            old_status = self.status
            self.status = new_status
            logger.debug(f"执行者 {self.executor_id} 状态转换: {old_status.value} -> {new_status.value}")
            return True
        else:
            logger.warning(
                f"执行者 {self.executor_id} 非法状态转换: {self.status.value} -> {new_status.value}"
            )
            return False


class SchedulerRouter:
    """调度路由器——三维决策模型 + VDA 5050 状态机
    
    不只看成本，还根据任务特征选择最合适的执行者：
    1. 标准化程度：标准化高 → 机器；标准化低 → 人
    2. 社交需求：需要社交 → 人；不需要 → 机器
    3. 危险程度：危险 → 专业机器/人；安全 → 普通机器
    """
    
    ACTION_PROFILES = {
        # 物理/操作类（高标准化，低社交，中等风险）
        "move":    (0.9, 0.1, 0.3),
        "pick":    (0.9, 0.1, 0.4),
        "place":   (0.9, 0.1, 0.3),
        "observe": (0.8, 0.1, 0.2),
        "diagnose":(0.7, 0.2, 0.3),
        "inspect": (0.8, 0.1, 0.2),
        "fetch":   (0.8, 0.1, 0.2),
        "process": (0.9, 0.0, 0.3),
        # 交互类（中等标准化，高社交，低风险）
        "chat":    (0.5, 0.6, 0.1),
        "query":   (0.6, 0.3, 0.1),
        "send":    (0.5, 0.4, 0.1),
        "notify":  (0.4, 0.5, 0.1),
        # 危险操作（高标准化，低社交，高风险）
        "delete":  (0.8, 0.1, 0.9),
        "rm":      (0.8, 0.1, 0.9),
        "format":  (0.9, 0.1, 0.8),
        "shell":   (0.7, 0.0, 0.7),
        "write":   (0.6, 0.0, 0.5),
    }
    
    def __init__(self):
        self.executors: Dict[str, ExecutorState] = {}
    
    def register(self, state: ExecutorState):
        self.executors[state.executor_id] = state
    
    def select_executor(self, action: str) -> Optional[str]:
        """三维决策选择执行者
        
        算法：
        1. 过滤：排除非 IDLE、不支持 action、队列满的
        2. 匹配度：计算 action 三维特征与执行者三维元数据的余弦相似度
        3. 综合评分：匹配度 * 0.6 + (1 / (1 + cost)) * 0.4
        4. 选最高分
        """
        candidates = [
            e for e in self.executors.values()
            if e.can_accept_task()
            and action in e.capabilities
        ]
        if not candidates:
            return None
        
        action_std, action_soc, action_risk = self.ACTION_PROFILES.get(
            action, (0.5, 0.5, 0.5)
        )
        
        best_score = -1.0
        best_id = None
        
        for e in candidates:
            dist = ((e.standardization - action_std) ** 2 +
                    (e.social - action_soc) ** 2 +
                    (e.risk_tolerance - action_risk) ** 2) ** 0.5
            match_score = max(0, 1 - dist / 1.732)
            cost_score = 1 / (1 + e.total_cost())
            total_score = match_score * 0.6 + cost_score * 0.4
            
            if total_score > best_score:
                best_score = total_score
                best_id = e.executor_id
        
        return best_id
    
    def record_success(self, executor_id: str):
        """记录执行成功——重置连续失败计数，状态转 IDLE"""
        state = self.executors.get(executor_id)
        if state:
            state.consecutive_failures = 0
            state.transition_to(ExecutorStatus.IDLE)
            state.current_task_id = None
            state.current_action = None
    
    def record_failure(self, executor_id: str) -> bool:
        """记录执行失败——增加连续失败计数，超过阈值则熔断
        
        Returns:
            bool: True 如果执行者被熔断（标记为 OFFLINE）
        """
        state = self.executors.get(executor_id)
        if not state:
            return False
        state.consecutive_failures += 1
        state.transition_to(ExecutorStatus.FAILED)
        if state.consecutive_failures >= state.circuit_breaker_threshold:
            state.transition_to(ExecutorStatus.OFFLINE)
            return True
        return False
    
    def record_assigned(self, executor_id: str, task_id: str, action: str):
        """记录任务已分配"""
        state = self.executors.get(executor_id)
        if state:
            state.transition_to(ExecutorStatus.ASSIGNED)
            state.current_task_id = task_id
            state.current_action = action
    
    def record_executing(self, executor_id: str):
        """记录任务开始执行"""
        state = self.executors.get(executor_id)
        if state:
            state.transition_to(ExecutorStatus.EXECUTING)
    
    def record_timeout(self, executor_id: str):
        """记录任务超时"""
        state = self.executors.get(executor_id)
        if state:
            state.transition_to(ExecutorStatus.TIMEOUT)
    
    def reset_circuit_breaker(self, executor_id: str):
        """手动重置熔断器——将执行者恢复为 IDLE"""
        state = self.executors.get(executor_id)
        if state:
            state.consecutive_failures = 0
            state.transition_to(ExecutorStatus.IDLE)
    
    def emergency_stop(self, executor_id: str) -> bool:
        """紧急停止执行者（Kill Switch）
        
        对于物理执行者，立即标记为 EMERGENCY_STOP。
        只有手动复位才能恢复。
        """
        state = self.executors.get(executor_id)
        if state and state.is_physical:
            old = state.status
            state.status = ExecutorStatus.EMERGENCY_STOP  # 强制转换，不检查规则
            state.current_task_id = None
            state.current_action = None
            logger.critical(f"🚨 紧急停止执行者 {executor_id}（物理执行者）! 原状态: {old.value}")
            return True
        elif state:
            logger.warning(f"执行者 {executor_id} 不是物理执行者，跳过紧急停止")
            return False
        return False
    
    def emergency_stop_all_physical(self) -> List[str]:
        """紧急停止所有物理执行者"""
        stopped = []
        for eid, state in self.executors.items():
            if state.is_physical and state.status != ExecutorStatus.OFFLINE:
                if self.emergency_stop(eid):
                    stopped.append(eid)
        logger.critical(f"🚨 已紧急停止 {len(stopped)} 个物理执行者: {stopped}")
        return stopped
    
    def get_status_summary(self) -> Dict:
        """获取所有执行者状态摘要"""
        summary = {}
        for status in ExecutorStatus:
            count = sum(1 for e in self.executors.values() if e.status == status)
            if count > 0:
                summary[status.value] = count
        return summary
