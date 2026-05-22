import asyncio
import random
from typing import Dict, Any

from tent_os.plugins.base import ExecutorPlugin


class MockExecutor(ExecutorPlugin):
    """Mock执行者，用于Phase 1测试和开发调试"""
    
    def __init__(self):
        self.executor_id = "mock"
        self.delay_seconds = 2
        self.fail_rate = 0.0
        self._supported_actions = ["move", "pick", "place", "fetch", "process", "chat"]
    
    def name(self) -> str:
        return "mock"
    
    def version(self) -> str:
        return "1.0.0"
    
    async def initialize(self, config: Dict) -> None:
        self.executor_id = config.get("executor_id", "mock")
        self.delay_seconds = config.get("delay_seconds", 2)
        self.fail_rate = config.get("fail_rate", 0.0)
        self._supported_actions = config.get("supported_actions", ["move", "pick", "place", "fetch", "process", "chat"])
    
    def supported_actions(self) -> list:
        return self._supported_actions
    
    async def execute(self, action: str, params: Dict) -> Dict:
        await asyncio.sleep(self.delay_seconds)
        if random.random() < self.fail_rate:
            return {"status": "failed", "error": "Mock随机失败", "task_id": params.get("task_id")}
        return {"status": "completed", "task_id": params.get("task_id"), "result": {"mock": True, "action": action}}
    
    async def get_status(self, task_id: str) -> Dict:
        return {"task_id": task_id, "status": "completed", "executor": "mock"}
