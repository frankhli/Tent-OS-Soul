"""意图模型 —— 自主系统的基本单位

将原有的 Heartbeat（被动提醒）升级为 Intention（主动意图）：
- Heartbeat："系统提醒 Agent 检查一下"（Prompt 注入）
- Intention："系统感知到某事需要处理"（意图生成 → 优先级排序 → 执行）

意图来源：
    heartbeat —— 定时任务（原 HEARTBEAT.md）
    event     —— 事件触发（异常检测、用户行为）
    user      —— 用户直接指令
    system    —— 系统自发生成（资源告警等）
"""

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("tent_os.autonomy.intention")


@dataclass
class Intention:
    """意图 —— 自主系统的基本决策单位"""
    intention_id: str
    description: str
    priority: float          # 动态优先级 0-1
    source: str              # heartbeat / event / user / system
    conditions: List[str]    # 触发条件描述
    action: str              # 要执行的动作
    action_params: Dict      # 动作参数
    deadline: Optional[datetime] = None
    
    # 反馈闭环
    created_at: datetime = None
    last_triggered: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    last_result: Optional[str] = None
    status: str = "pending"  # pending / active / completed / failed
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class IntentionRegistry:
    """意图注册表 —— 管理所有活跃意图"""
    
    def __init__(self):
        self._intentions: Dict[str, Intention] = {}
        self._history: List[Dict] = []
    
    def register(self, intention: Intention) -> str:
        """注册新意图"""
        self._intentions[intention.intention_id] = intention
        logger.info(f"意图注册: [{intention.source}] {intention.description} (p={intention.priority:.2f})")
        return intention.intention_id
    
    def get(self, intention_id: str) -> Optional[Intention]:
        """获取意图"""
        return self._intentions.get(intention_id)
    
    def remove(self, intention_id: str):
        """移除意图"""
        if intention_id in self._intentions:
            del self._intentions[intention_id]
    
    def list_active(self) -> List[Intention]:
        """列出所有活跃意图"""
        return [i for i in self._intentions.values() if i.status in ("pending", "active")]
    
    def list_by_source(self, source: str) -> List[Intention]:
        """按来源列出意图"""
        return [i for i in self._intentions.values() if i.source == source]
    
    def update_status(self, intention_id: str, status: str, result: str = None):
        """更新意图状态"""
        intention = self._intentions.get(intention_id)
        if not intention:
            return
        
        old_status = intention.status
        intention.status = status
        
        if status == "completed":
            intention.success_count += 1
            intention.last_result = result
        elif status == "failed":
            intention.failure_count += 1
            intention.last_result = result
        
        self._history.append({
            "timestamp": datetime.now().isoformat(),
            "intention_id": intention_id,
            "old_status": old_status,
            "new_status": status,
            "result": result,
        })
        
        logger.info(f"意图状态更新: {intention_id} {old_status} → {status}")
    
    def get_history(self, limit: int = 100) -> List[Dict]:
        """获取意图历史"""
        return self._history[-limit:]
    
    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "active_count": len(self.list_active()),
            "total_count": len(self._intentions),
            "intentions": [
                {
                    "id": i.intention_id,
                    "description": i.description,
                    "priority": i.priority,
                    "source": i.source,
                    "status": i.status,
                    "success_rate": i.success_count / max(i.success_count + i.failure_count, 1),
                }
                for i in self._intentions.values()
            ],
        }
