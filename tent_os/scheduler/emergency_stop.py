"""Kill Switch 紧急停止系统 —— 物理执行者的安全底线

设计原则（来自微软 AGT + 物理安全最佳实践）：
1. 秒级响应：从触发到执行 < 1 秒
2. 不可绕过：紧急停止命令最高优先级，覆盖所有其他状态
3. 区域控制：支持按区域/类型批量停止
4. 审计追踪：所有紧急停止操作必须记录
5. 手动复位：紧急停止后必须人工确认才能恢复

使用场景：
- 机器人失控/路径冲突
- 人类执行者遇到危险
- 检测到未授权操作
- 系统异常需要立即停止所有物理动作
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("tent_os.emergency")


@dataclass
class EmergencyEvent:
    """紧急事件记录"""
    event_id: str
    timestamp: str
    triggered_by: str  # 谁触发的（用户/系统/自动检测）
    reason: str
    target_executors: List[str]
    affected_zones: List[str]
    resolved: bool = False
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


class KillSwitch:
    """紧急停止控制器
    
    架构：
    - KillSwitch 本身是无状态的，通过 NATS 发布命令
    - 各 Worker 订阅 emergency.stop 主题执行停止
    - 所有操作记录到 SQLite 审计日志
    """
    
    def __init__(self, bus, router, db_path: str = "./tent_scheduler.db"):
        self.bus = bus
        self.router = router
        self.db_path = db_path
        self._init_db()
        self._active_emergencies: Dict[str, EmergencyEvent] = {}
        self._global_stop_active = False
    
    def _init_db(self):
        import sqlite3
        db = sqlite3.connect(self.db_path)
        db.execute("""
            CREATE TABLE IF NOT EXISTS emergency_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT,
                triggered_by TEXT,
                reason TEXT,
                target_executors TEXT,
                affected_zones TEXT,
                resolved INTEGER DEFAULT 0,
                resolved_at TEXT,
                resolved_by TEXT
            )
        """)
        db.commit()
        db.close()
    
    async def start(self):
        """启动 Kill Switch 监听"""
        await self.bus.subscribe("emergency.stop", "emergency-stop", self._handle_stop)
        await self.bus.subscribe("emergency.stop.zone", "emergency-stop-zone", self._handle_zone_stop)
        await self.bus.subscribe("emergency.reset", "emergency-reset", self._handle_reset)
        logger.info("Kill Switch 已启动，监听 emergency.stop / emergency.stop.zone / emergency.reset")
    
    async def _handle_stop(self, msg):
        """处理紧急停止命令"""
        data = json.loads(msg.data)
        reason = data.get("reason", "未指定原因")
        triggered_by = data.get("triggered_by", "unknown")
        target_ids = data.get("executor_ids", [])
        
        await self.stop(target_ids, reason, triggered_by)
    
    async def _handle_zone_stop(self, msg):
        """处理区域紧急停止"""
        data = json.loads(msg.data)
        zones = data.get("zones", [])
        reason = data.get("reason", "区域紧急停止")
        triggered_by = data.get("triggered_by", "unknown")
        
        # 获取区域内的物理执行者
        target_ids = [
            eid for eid, state in self.router.executors.items()
            if state.is_physical and getattr(state, 'zone', None) in zones
        ]
        
        await self.stop(target_ids, reason, triggered_by, zones=zones)
    
    async def _handle_reset(self, msg):
        """处理复位命令"""
        data = json.loads(msg.data)
        executor_id = data.get("executor_id")
        reset_by = data.get("reset_by", "unknown")
        
        if executor_id == "ALL":
            await self.reset_all(reset_by)
        elif executor_id:
            await self.reset(executor_id, reset_by)
    
    async def stop(self, executor_ids: List[str], reason: str, triggered_by: str,
                   zones: List[str] = None) -> EmergencyEvent:
        """紧急停止指定执行者
        
        Args:
            executor_ids: 要停止的执行者 ID 列表
            reason: 停止原因
            triggered_by: 触发者标识
            zones: 受影响区域（可选）
        
        Returns:
            EmergencyEvent 记录
        """
        event_id = f"EMRG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hash(reason) % 10000:04d}"
        
        # 1. 通过 Router 标记执行者为 EMERGENCY_STOP
        stopped = []
        for eid in executor_ids:
            if self.router.emergency_stop(eid):
                stopped.append(eid)
        
        # 2. 通过 NATS 广播停止命令（物理执行者直接监听此命令）
        await self.bus.publish("executor.emergency_stop", json.dumps({
            "event_id": event_id,
            "executor_ids": stopped,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }).encode())
        
        # 3. 记录事件
        event = EmergencyEvent(
            event_id=event_id,
            timestamp=datetime.now().isoformat(),
            triggered_by=triggered_by,
            reason=reason,
            target_executors=stopped,
            affected_zones=zones or [],
        )
        self._active_emergencies[event_id] = event
        self._global_stop_active = True
        
        # 4. 写入审计日志
        self._log_event(event)
        
        logger.critical(
            f"🚨 紧急停止已触发 [{event_id}]\n"
            f"   原因: {reason}\n"
            f"   触发者: {triggered_by}\n"
            f"   已停止: {stopped}"
        )
        
        return event
    
    async def stop_all_physical(self, reason: str = "全局紧急停止", triggered_by: str = "system") -> EmergencyEvent:
        """停止所有物理执行者"""
        stopped = self.router.emergency_stop_all_physical()
        return await self.stop(stopped, reason, triggered_by)
    
    async def reset(self, executor_id: str, reset_by: str) -> bool:
        """复位单个执行者（人工确认后）
        
        安全要求：
        - 必须人工确认物理环境安全
        - 记录复位操作者和时间
        - 复位后执行者进入 IDLE 状态
        """
        state = self.router.executors.get(executor_id)
        if not state:
            logger.warning(f"复位失败: 执行者 {executor_id} 不存在")
            return False
        
        if state.status.value != "emergency_stop":
            logger.warning(f"复位失败: 执行者 {executor_id} 状态为 {state.status.value}，不是 emergency_stop")
            return False
        
        # 强制重置状态
        state.status = self.router.__class__.__mro__[0]  # 获取 Enum 类型
        # 正确的方式：
        from tent_os.scheduler.router import ExecutorStatus
        state.status = ExecutorStatus.IDLE
        state.consecutive_failures = 0
        state.current_task_id = None
        state.current_action = None
        
        logger.info(f"✅ 执行者 {executor_id} 已复位（操作者: {reset_by}）")
        
        # 发布复位事件
        await self.bus.publish("executor.reset", json.dumps({
            "executor_id": executor_id,
            "reset_by": reset_by,
            "timestamp": datetime.now().isoformat(),
        }).encode())
        
        return True
    
    async def reset_all(self, reset_by: str) -> int:
        """复位所有紧急停止的执行者"""
        reset_count = 0
        from tent_os.scheduler.router import ExecutorStatus
        for eid, state in self.router.executors.items():
            if state.status == ExecutorStatus.EMERGENCY_STOP:
                if await self.reset(eid, reset_by):
                    reset_count += 1
        
        if reset_count > 0:
            self._global_stop_active = False
            logger.info(f"✅ 已复位 {reset_count} 个执行者（操作者: {reset_by}）")
        
        return reset_count
    
    def _log_event(self, event: EmergencyEvent):
        """写入审计日志"""
        import sqlite3
        db = sqlite3.connect(self.db_path)
        db.execute(
            """INSERT INTO emergency_events 
               (event_id, timestamp, triggered_by, reason, target_executors, affected_zones)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event.event_id, event.timestamp, event.triggered_by, event.reason,
             json.dumps(event.target_executors), json.dumps(event.affected_zones))
        )
        db.commit()
        db.close()
    
    def is_global_stop_active(self) -> bool:
        """是否有全局紧急停止处于活动状态"""
        return self._global_stop_active
    
    def get_active_emergencies(self) -> List[EmergencyEvent]:
        """获取所有未解决的紧急事件"""
        return [e for e in self._active_emergencies.values() if not e.resolved]
