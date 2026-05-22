"""渠道管理器 —— 统一管理所有消息渠道"""

from typing import Any, Dict, List, Optional

from tent_os.channels.base import ChannelMessage, ChannelReply, MessageChannel
from tent_os.channels.webhook_channel import WebhookChannel
from tent_os.channels.feishu_channel import FeishuChannel
from tent_os.channels.slack_channel import SlackChannel

CHANNEL_REGISTRY = {
    "webhook": WebhookChannel,
    "feishu": FeishuChannel,
    "slack": SlackChannel,
}


class ChannelManager:
    """消息渠道管理器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.channels: Dict[str, MessageChannel] = {}
    
    async def load_all(self):
        """加载所有已配置的渠道"""
        channels_config = self.config.get("channels", {})
        
        # 默认启用 webhook
        if "webhook" not in channels_config:
            channels_config["webhook"] = {"enabled": True}
        
        for name, cfg in channels_config.items():
            if not cfg.get("enabled", True):
                continue
            
            channel_class = CHANNEL_REGISTRY.get(name)
            if not channel_class:
                continue
            
            channel = channel_class(cfg)
            await channel.initialize()
            
            if channel.enabled:
                self.channels[name] = channel
    
    def get(self, name: str) -> Optional[MessageChannel]:
        return self.channels.get(name)
    
    def list_active(self) -> List[str]:
        return list(self.channels.keys())
    
    async def parse(self, channel_name: str, payload: Dict[str, Any]) -> Optional[ChannelMessage]:
        """解析指定渠道的 incoming message"""
        channel = self.channels.get(channel_name)
        if not channel:
            return None
        return await channel.parse_incoming(payload)
    
    async def reply(self, channel_name: str, message: ChannelMessage, reply: ChannelReply) -> bool:
        """通过指定渠道发送回复"""
        channel = self.channels.get(channel_name)
        if not channel:
            return False
        return await channel.send_reply(message, reply)
    
    def describe(self) -> str:
        lines = ["已加载的消息渠道:"]
        for name, ch in self.channels.items():
            lines.append(f"  • {name}: {ch.describe()}")
        if not self.channels:
            lines.append("  (无)")
        return "\n".join(lines)
