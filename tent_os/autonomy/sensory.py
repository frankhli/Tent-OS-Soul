"""感知层 —— 自主神经系统的"感官"

职责：
1. 监控系统状态（任务队列、执行者状态、错误率）
2. 感知外部环境（时间、日历、邮件、消息）
3. 检测用户行为模式（登录时间、常用功能）

感知信号 → 意图生成器
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from tent_os.autonomy.intention import Intention, IntentionRegistry

logger = logging.getLogger("tent_os.autonomy.sensory")


class SensoryLayer:
    """感知层"""
    
    def __init__(self, registry: IntentionRegistry):
        self.registry = registry
        self._system_metrics: Dict = {}
        self._user_patterns: Dict = {}
        self._last_check = datetime.now()
    
    def check_system_health(self, metrics: Dict = None) -> List[Intention]:
        """检查系统健康状态，生成维护意图
        
        检测项：
        - 任务队列深度
        - 执行者离线数量
        - 错误率
        - 内存/磁盘使用
        """
        metrics = metrics or {}
        intentions = []
        
        queue_depth = metrics.get("queue_depth", 0)
        offline_executors = metrics.get("offline_executors", 0)
        error_rate = metrics.get("error_rate", 0.0)
        disk_usage = metrics.get("disk_usage", 0.0)
        
        # 队列过深
        if queue_depth > 50:
            intentions.append(Intention(
                intention_id=f"sys-queue-{datetime.now().strftime('%H%M%S')}",
                description=f"任务队列堆积 ({queue_depth} 个)，需要加速处理或扩容",
                priority=0.8,
                source="system",
                conditions=["queue_depth > 50"],
                action="alert_admin",
                action_params={"metric": "queue_depth", "value": queue_depth},
            ))
        
        # 执行者离线
        if offline_executors > 0:
            intentions.append(Intention(
                intention_id=f"sys-exec-{datetime.now().strftime('%H%M%S')}",
                description=f"{offline_executors} 个执行者离线，需要检查",
                priority=0.9,
                source="system",
                conditions=["offline_executors > 0"],
                action="check_executors",
                action_params={"count": offline_executors},
            ))
        
        # 错误率过高
        if error_rate > 0.1:
            intentions.append(Intention(
                intention_id=f"sys-error-{datetime.now().strftime('%H%M%S')}",
                description=f"错误率过高 ({error_rate:.1%})，需要排查",
                priority=0.9,
                source="system",
                conditions=["error_rate > 10%"],
                action="investigate_errors",
                action_params={"error_rate": error_rate},
            ))
        
        # 磁盘空间不足
        if disk_usage > 0.9:
            intentions.append(Intention(
                intention_id=f"sys-disk-{datetime.now().strftime('%H%M%S')}",
                description=f"磁盘使用率 {disk_usage:.0%}，需要清理",
                priority=0.7,
                source="system",
                conditions=["disk_usage > 90%"],
                action="cleanup_disk",
                action_params={"disk_usage": disk_usage},
            ))
        
        for intention in intentions:
            self.registry.register(intention)
        
        return intentions
    
    def check_scheduled_tasks(self, current_time: datetime = None) -> List[Intention]:
        """检查定时任务，生成执行意图"""
        current_time = current_time or datetime.now()
        intentions = []
        
        # 每日备份
        if current_time.hour == 2 and current_time.minute < 5:
            intentions.append(Intention(
                intention_id=f"hb-backup-{current_time.strftime('%Y%m%d')}",
                description="执行每日数据备份",
                priority=0.6,
                source="heartbeat",
                conditions=["hour == 2"],
                action="backup_data",
                action_params={"type": "daily"},
            ))
        
        # 健康检查
        if current_time.minute == 0:
            intentions.append(Intention(
                intention_id=f"hb-health-{current_time.strftime('%H%M')}",
                description="执行系统健康检查",
                priority=0.4,
                source="heartbeat",
                conditions=["minute == 0"],
                action="health_check",
                action_params={},
            ))
        
        # 记忆整理（每天凌晨 3 点，与 REM 阶段配合）
        if current_time.hour == 3 and current_time.minute < 5:
            intentions.append(Intention(
                intention_id=f"hb-memory-{current_time.strftime('%Y%m%d')}",
                description="执行记忆整理和归档",
                priority=0.5,
                source="heartbeat",
                conditions=["hour == 3"],
                action="consolidate_memory",
                action_params={},
            ))
        
        for intention in intentions:
            self.registry.register(intention)
        
        return intentions
    
    def detect_user_patterns(self, user_activity: Dict) -> List[Intention]:
        """检测用户行为模式，生成个性化意图"""
        intentions = []
        
        # 用户常用功能提醒
        favorite_features = user_activity.get("favorite_features", [])
        last_login = user_activity.get("last_login")
        
        if last_login:
            days_since_login = (datetime.now() - datetime.fromisoformat(last_login)).days
            if days_since_login > 3:
                intentions.append(Intention(
                    intention_id=f"user-welcome-{datetime.now().strftime('%Y%m%d')}",
                    description=f"用户 {days_since_login} 天未登录，发送欢迎回归消息",
                    priority=0.3,
                    source="user",
                    conditions=["days_since_login > 3"],
                    action="send_welcome",
                    action_params={"days": days_since_login},
                ))
        
        for intention in intentions:
            self.registry.register(intention)
        
        return intentions
    
    def get_sensory_summary(self) -> Dict:
        """获取感知层摘要"""
        return {
            "last_check": self._last_check.isoformat(),
            "active_intentions": len(self.registry.list_active()),
            "system_metrics": self._system_metrics,
        }
