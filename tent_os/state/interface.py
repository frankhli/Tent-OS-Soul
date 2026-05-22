from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class SessionStateStore(ABC):
    """会话状态存储抽象接口
    
    状态外存到 Redis，治理进程无状态。
    对话历史通过 messages 字段持久化，支持多轮对话。
    """
    
    @abstractmethod
    async def create(self, session_id: str, task: str = "", tools: List[Dict] = None, 
                     user_id: str = None, title: str = None) -> None:
        """创建新会话状态"""
        pass
    
    @abstractmethod
    async def load(self, session_id: str) -> Dict:
        """加载会话状态"""
        pass
    
    @abstractmethod
    async def update_plan(self, session_id: str, plan: Dict, step: int = 1) -> None:
        """更新Plan和当前步骤"""
        pass
    
    @abstractmethod
    async def advance_step(self, session_id: str) -> int:
        """前进到下一步，返回新的step"""
        pass
    
    @abstractmethod
    async def get_step(self, session_id: str) -> int:
        """获取当前步骤"""
        pass
    
    @abstractmethod
    async def get_plan(self, session_id: str) -> Optional[Dict]:
        """获取Plan"""
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """删除会话状态"""
        pass
    
    # === 对话历史扩展（Phase 1）===
    
    @abstractmethod
    async def append_message(self, session_id: str, role: str, content: str, images: List[str] = None) -> None:
        """追加一条对话消息
        
        Args:
            images: base64 编码的图片列表（多模态），为空表示纯文本
        """
        pass
    
    @abstractmethod
    async def get_messages(self, session_id: str, limit: int = 100) -> List[Dict]:
        """获取最近N条对话消息
        
        返回格式: [{"role": str, "content": str, "images": [str], "timestamp": str}, ...]
        """
        pass
    
    @abstractmethod
    async def update_title(self, session_id: str, title: str) -> None:
        """更新会话标题"""
        pass
    
    @abstractmethod
    async def update(self, session_id: str, updates: Dict) -> None:
        """更新会话的任意字段
        
        Args:
            session_id: 会话 ID
            updates: 要更新的字段字典，会合并到现有状态中
        """
        pass
    
    @abstractmethod
    async def list_sessions(self, user_id: str = None, limit: int = 50) -> List[Dict]:
        """列出会话（按更新时间倒序）"""
        pass
    
    async def ping(self) -> bool:
        """健康检查"""
        return True
    
    # === 进程级无状态化扩展（Phase 1）===
    
    async def get_retry_count(self, session_id: str) -> int:
        """获取任务重试计数（治理进程无状态化）"""
        return 0
    
    async def set_retry_count(self, session_id: str, count: int) -> None:
        """设置任务重试计数（治理进程无状态化）"""
        pass
    
    async def clear_retry_count(self, session_id: str) -> None:
        """清除任务重试计数（治理进程无状态化）"""
        pass
