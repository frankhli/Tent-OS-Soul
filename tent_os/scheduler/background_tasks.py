"""Cron 调度器 —— 持久化后台任务调度

替代原 HEARTBEAT.md 轮询方案：
- 任务持久化到 SQLite
- 支持 CRUD API
- 精确到分钟的调度
- 执行历史记录

HEARTBEAT.md 仍然支持：启动时会自动导入其中的 cron 任务。
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from tent_os.scheduler.cron_store import CronStore
from tent_os.logging_config import get_logger

logger = get_logger()


class CronScheduler:
    """持久化 Cron 调度器"""
    
    def __init__(self, db_path: str = "./tent_scheduler.db", heartbeat_path: str = "./HEARTBEAT.md"):
        self.store = CronStore(db_path)
        self.heartbeat_path = Path(heartbeat_path)
        self._running = False
        self._import_heartbeat_tasks()
    
    def _import_heartbeat_tasks(self):
        """从 HEARTBEAT.md 导入初始任务（仅首次）"""
        if not self.heartbeat_path.exists():
            return
        
        content = self.heartbeat_path.read_text()
        pattern = r'- \[[ x]\] (.+?) \(cron: (.+?)\)'
        imported = 0
        
        for match in re.finditer(pattern, content):
            name = match.group(1).strip()
            cron = match.group(2).strip()
            
            # 避免重复导入
            existing = self.store.list_tasks()
            if any(t.name == name and t.cron == cron for t in existing):
                continue
            
            self.store.add_task(name=name, cron=cron, command=name)
            imported += 1
        
        if imported > 0:
            logger.info(f"[CRON] 从 HEARTBEAT.md 导入 {imported} 个任务")
    
    async def run(self, bus):
        """主调度循环 —— 每分钟检查一次"""
        self._running = True
        logger.info("[CRON] 调度器启动")
        
        while self._running:
            try:
                due_tasks = self.store.get_due_tasks()
                for task in due_tasks:
                    if not task.enabled:
                        continue
                    
                    logger.info(f"[CRON] 触发任务: {task.name} ({task.cron})")
                    
                    # 发布到治理进程执行
                    await bus.publish("governance.background_task", json.dumps({
                        "task": task.command,
                        "task_id": task.task_id,
                        "timestamp": datetime.now().isoformat(),
                    }).encode())
                    
                    # 标记已执行
                    self.store.mark_executed(task.task_id, status="completed")
                
            except Exception as e:
                logger.error(f"[CRON] 调度循环异常: {e}")
            
            await asyncio.sleep(60)
    
    def stop(self):
        self._running = False


# 兼容旧接口名
BackgroundTaskScheduler = CronScheduler
