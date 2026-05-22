"""消息渠道基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ChannelMessage:
    """统一消息格式"""
    channel: str          # 渠道标识: feishu, slack, webhook...
    user_id: str          # 用户唯一 ID
    user_name: str        # 用户显示名
    text: str             # 消息文本
    raw: Dict[str, Any]   # 原始 payload
    thread_id: Optional[str] = None  # 会话线程 ID
    attachments: Optional[list] = None  # 附件


@dataclass
class ChannelReply:
    """统一回复格式"""
    text: str
    markdown: Optional[str] = None
    buttons: Optional[list] = None
    thread_id: Optional[str] = None


class MessageChannel(ABC):
    """消息渠道抽象基类"""
    
    name: str = ""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("enabled", True)
    
    @abstractmethod
    async def initialize(self):
        """初始化（验证配置、建立连接等）"""
        pass
    
    @abstractmethod
    async def parse_incoming(self, payload: Dict[str, Any]) -> Optional[ChannelMessage]:
        """解析外部 webhook payload → 统一消息格式"""
        pass
    
    @abstractmethod
    async def send_reply(self, message: ChannelMessage, reply: ChannelReply) -> bool:
        """发送回复到渠道"""
        pass
    
    def describe(self) -> str:
        return f"{self.name} channel"
