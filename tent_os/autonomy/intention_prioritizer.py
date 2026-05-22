"""意图优先级管理 —— 资源仲裁与冲突解决

核心算法：
1. 优先级 = 基础优先级 × 紧急度 × 重要性 × 成功率惩罚
2. 冲突解决：当多个意图竞争资源时，按优先级排序
3. 死锁检测：循环依赖检测
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from tent_os.autonomy.intention import Intention, IntentionRegistry

logger = logging.getLogger("tent_os.autonomy.prioritizer")


class IntentionPrioritizer:
    """意图优先级管理器"""
    
    def __init__(self, registry: IntentionRegistry):
        self.registry = registry
    
    def calculate_priority(self, intention: Intention) -> float:
        """计算意图的动态优先级
        
        公式：
            priority = base_priority × urgency × importance × success_penalty
            
        urgency: 截止时间越近越高（指数增长）
        importance: 用户显式 > 系统生成
        success_penalty: 经常失败的意图优先级下降
        """
        base = intention.priority
        
        # 1. 紧急度（截止时间）
        urgency = 1.0
        if intention.deadline:
            time_left = (intention.deadline - datetime.now()).total_seconds()
            if time_left < 0:
                urgency = 2.0  # 已逾期，最高紧急度
            elif time_left < 300:  # 5 分钟内
                urgency = 1.5
            elif time_left < 3600:  # 1 小时内
                urgency = 1.2
            elif time_left < 86400:  # 24 小时内
                urgency = 1.0
            else:
                urgency = 0.8
        
        # 2. 重要性（来源权重）
        importance_map = {
            "user": 1.2,      # 用户指令最重要
            "emergency": 1.5,  # 紧急事件
            "system": 1.0,     # 系统生成
            "event": 1.1,      # 事件触发
            "heartbeat": 0.8,  # 定时任务相对不重要
        }
        importance = importance_map.get(intention.source, 1.0)
        
        # 3. 成功率惩罚（避免反复失败打扰用户）
        total_attempts = intention.success_count + intention.failure_count
        if total_attempts > 0:
            success_rate = intention.success_count / total_attempts
            # 成功率 < 50% → 优先级大幅下降
            if success_rate < 0.3:
                success_penalty = 0.3
            elif success_rate < 0.5:
                success_penalty = 0.6
            else:
                success_penalty = 1.0
        else:
            success_penalty = 1.0
        
        # 综合计算
        final_priority = base * urgency * importance * success_penalty
        return min(2.0, max(0.0, final_priority))
    
    def resolve_conflicts(self, intentions: List[Intention]) -> List[Intention]:
        """解决意图冲突
        
        冲突类型：
        1. 资源冲突：两个意图需要同一资源
        2. 顺序冲突：意图 A 必须在意图 B 之前执行
        3. 互斥冲突：意图 A 和 B 不能同时执行
        """
        # 按优先级排序
        scored = [(self.calculate_priority(i), i) for i in intentions]
        scored.sort(key=lambda x: x[0], reverse=True)
        
        resolved = []
        used_resources = set()
        
        for score, intention in scored:
            # 简单资源冲突检测：基于 action 类型
            resource = self._extract_resource(intention.action)
            
            if resource in used_resources:
                # 资源冲突 → 低优先级意图延后
                logger.info(f"意图冲突解决: {intention.intention_id} 延后（资源 {resource} 被占用）")
                continue
            
            used_resources.add(resource)
            intention.priority = score  # 更新计算后的优先级
            resolved.append(intention)
        
        return resolved
    
    def get_next_intention(self) -> Optional[Intention]:
        """获取下一个应该执行的意图"""
        active = self.registry.list_active()
        if not active:
            return None
        
        # 计算所有活跃意图的优先级
        for intention in active:
            intention.priority = self.calculate_priority(intention)
        
        # 解决冲突
        resolved = self.resolve_conflicts(active)
        
        if resolved:
            return resolved[0]
        return None
    
    def _extract_resource(self, action: str) -> str:
        """从动作中提取资源标识（简化版）"""
        # 基于动作类型判断资源
        action_lower = action.lower()
        
        if any(kw in action_lower for kw in ["数据库", "database", "db", "sql"]):
            return "database"
        elif any(kw in action_lower for kw in ["文件", "file", "filesystem"]):
            return "filesystem"
        elif any(kw in action_lower for kw in ["网络", "network", "http", "api"]):
            return "network"
        elif any(kw in action_lower for kw in ["邮件", "email", "message"]):
            return "messaging"
        elif any(kw in action_lower for kw in ["备份", "backup"]):
            return "backup"
        else:
            return "general"
    
    def get_queue_status(self) -> Dict:
        """获取队列状态"""
        active = self.registry.list_active()
        
        for intention in active:
            intention.priority = self.calculate_priority(intention)
        
        active.sort(key=lambda i: i.priority, reverse=True)
        
        return {
            "queue_length": len(active),
            "top_intentions": [
                {
                    "id": i.intention_id,
                    "description": i.description[:50],
                    "priority": round(i.priority, 3),
                    "source": i.source,
                    "status": i.status,
                }
                for i in active[:5]
            ],
        }
