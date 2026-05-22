"""Adaptive Thresholds —— 经验驱动的阈值自适应

Phase 3 设计理念：
- 不是算法拟合，是"肌肉记忆"
- 像老司机：踩多了刹车就知道什么时候该轻踩
- 只收集必要数据，轻量不阻塞

策略：
1. 滑动窗口统计（最近 50 次）—— 避免无限增长
2. 增量更新 —— 每次任务完成后异步更新
3. 保守调整 —— 每次只调 ±0.05，防止震荡
"""

import json
import time
from typing import Dict, Optional
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger("tent_os.adaptive")


@dataclass
class TaskStats:
    """某类任务的统计"""
    total: int = 0
    success: int = 0
    failed: int = 0
    avg_iterations: float = 0.0
    # 审批统计
    approval_asked: int = 0
    approval_given: int = 0
    approval_denied: int = 0
    # 当前自适应阈值
    approval_threshold: float = 0.5
    max_iterations: int = 100
    # 历史迭代次数（用于计算均值）
    iteration_history: list = None
    
    def __post_init__(self):
        if self.iteration_history is None:
            self.iteration_history = []
    
    def record_completion(self, iterations: int, success: bool):
        """记录任务完成"""
        self.total += 1
        if success:
            self.success += 1
        else:
            self.failed += 1
        
        # 滑动窗口：保留最近 50 次迭代次数
        self.iteration_history.append(iterations)
        if len(self.iteration_history) > 50:
            self.iteration_history.pop(0)
        
        # 更新平均迭代次数
        if self.iteration_history:
            self.avg_iterations = sum(self.iteration_history) / len(self.iteration_history)
    
    def record_approval(self, approved: bool):
        """记录审批结果"""
        self.approval_asked += 1
        if approved:
            self.approval_given += 1
        else:
            self.approval_denied += 1
    
    def adapt_approval_threshold(self) -> float:
        """根据审批历史自适应调整阈值
        
        逻辑：
        - 最近 10 次审批中 8+ 通过 → 阈值 +0.05（更信任 AI）
        - 最近 10 次审批中 3- 通过 → 阈值 -0.05（更谨慎）
        - 范围 [0.2, 0.8]
        """
        if self.approval_asked < 5:
            return self.approval_threshold  # 数据不足，不调整
        
        # 计算最近审批通过率（简化：用总量计算，实际应滑动窗口）
        if self.approval_asked == 0:
            return self.approval_threshold
        
        pass_rate = self.approval_given / self.approval_asked
        
        old_threshold = self.approval_threshold
        
        if pass_rate > 0.8:
            self.approval_threshold = min(0.8, self.approval_threshold + 0.05)
            logger.info(f"[ADAPT] approval_threshold ↑ {old_threshold:.2f} → {self.approval_threshold:.2f} (pass_rate={pass_rate:.1%})")
        elif pass_rate < 0.3:
            self.approval_threshold = max(0.2, self.approval_threshold - 0.05)
            logger.info(f"[ADAPT] approval_threshold ↓ {old_threshold:.2f} → {self.approval_threshold:.2f} (pass_rate={pass_rate:.1%})")
        
        return self.approval_threshold
    
    def adapt_max_iterations(self) -> int:
        """根据历史迭代次数自适应调整上限
        
        逻辑：
        - max_iterations = avg_iterations + 2 * std_dev
        - 最小 3，最大 50
        """
        if len(self.iteration_history) < 5:
            return self.max_iterations  # 数据不足
        
        avg = sum(self.iteration_history) / len(self.iteration_history)
        # 简化标准差计算
        variance = sum((x - avg) ** 2 for x in self.iteration_history) / len(self.iteration_history)
        std_dev = variance ** 0.5
        
        old_max = self.max_iterations
        new_max = int(avg + 2 * std_dev)
        new_max = max(3, min(50, new_max))
        
        if new_max != old_max:
            self.max_iterations = new_max
            logger.info(f"[ADAPT] max_iterations {old_max} → {new_max} (avg={avg:.1f}, std={std_dev:.1f})")
        
        return self.max_iterations


class AdaptiveThresholdManager:
    """阈值自适应管理器
    
    像人的肌肉记忆：
    - 第一次做某事：凭本能（默认阈值）
    - 做了 10 次后：知道大概要几步，知道老板信不信任自己
    - 阈值自然调整，不需要公式提醒
    """
    
    def __init__(self, state_store=None):
        self._state_store = state_store
        self._stats: Dict[str, TaskStats] = {}
        self._load_stats()
    
    def _key(self, task_type: str) -> str:
        return f"adaptive_stats:{task_type}"
    
    def _load_stats(self):
        """从 Redis 加载统计"""
        if not self._state_store or not hasattr(self._state_store, '_redis'):
            return
        try:
            redis = self._state_store._redis
            # 加载所有 task_type 的统计
            keys = redis.keys("adaptive_stats:*")
            for key in keys:
                data = redis.get(key)
                if data:
                    task_type = key.decode().split(":")[1] if isinstance(key, bytes) else key.split(":")[1]
                    self._stats[task_type] = self._deserialize(data)
        except Exception as e:
            logger.debug(f"加载自适应统计失败: {e}")
    
    def _save_stats(self, task_type: str):
        """保存统计到 Redis"""
        if not self._state_store or not hasattr(self._state_store, '_redis'):
            return
        try:
            redis = self._state_store._redis
            stats = self._stats.get(task_type)
            if stats:
                redis.setex(self._key(task_type), 86400 * 7, self._serialize(stats))  # 7 天过期
        except Exception as e:
            logger.debug(f"保存自适应统计失败: {e}")
    
    def _serialize(self, stats: TaskStats) -> str:
        """序列化统计"""
        data = asdict(stats)
        return json.dumps(data)
    
    def _deserialize(self, data) -> TaskStats:
        """反序列化统计"""
        if isinstance(data, bytes):
            data = data.decode()
        d = json.loads(data)
        return TaskStats(**{k: v for k, v in d.items() if k in TaskStats.__dataclass_fields__})
    
    def get_or_create(self, task_type: str) -> TaskStats:
        """获取或创建某类任务的统计"""
        if task_type not in self._stats:
            self._stats[task_type] = TaskStats()
        return self._stats[task_type]
    
    def record_task_completion(self, task_type: str, iterations: int, success: bool):
        """记录任务完成"""
        stats = self.get_or_create(task_type)
        stats.record_completion(iterations, success)
        stats.adapt_max_iterations()
        self._save_stats(task_type)
    
    def record_approval(self, task_type: str, approved: bool):
        """记录审批结果"""
        stats = self.get_or_create(task_type)
        stats.record_approval(approved)
        stats.adapt_approval_threshold()
        self._save_stats(task_type)
    
    def get_approval_threshold(self, task_type: str = "default") -> float:
        """获取当前审批阈值"""
        return self.get_or_create(task_type).approval_threshold
    
    def get_max_iterations(self, task_type: str = "default") -> int:
        """获取当前最大迭代次数"""
        return self.get_or_create(task_type).max_iterations
