from abc import ABC, abstractmethod
from typing import Dict, Any


class Plugin(ABC):
    @abstractmethod
    def name(self) -> str: pass
    
    @abstractmethod
    def version(self) -> str: pass
    
    @abstractmethod
    async def initialize(self, config: Dict) -> None: pass


class ExecutorPlugin(Plugin):
    @abstractmethod
    def supported_actions(self) -> list: pass
    
    @abstractmethod
    async def execute(self, action: str, params: Dict) -> Dict: pass
    
    @abstractmethod
    async def get_status(self, task_id: str) -> Dict: pass
