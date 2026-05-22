"""通用 Webhook 渠道 —— 零配置、零 key

接收任意 JSON POST，直接转发到 Tent OS 处理。
特别适合 n8n 工作流：n8n 的 HTTP Request 节点 → Tent OS webhook → n8n 回复。

用法:
  POST /api/v1/channels/webhook/{channel_id}
  Body: {"user_id": "xxx", "text": "消息内容", ...}

回复通过 HTTP 响应体返回，n8n 可以直接读取。
"""

from typing import Any, Dict, Optional

from tent_os.channels.base import ChannelMessage, ChannelReply, MessageChannel


class WebhookChannel(MessageChannel):
    """通用 Webhook 渠道"""
    
    name = "webhook"
    
    async def initialize(self):
        pass  # 无状态，无需初始化
    
    async def parse_incoming(self, payload: Dict[str, Any]) -> Optional[ChannelMessage]:
        """解析通用 webhook payload"""
        text = payload.get("text", "")
        if not text:
            # 尝试其他常见字段名
            for key in ("message", "content", "body", "msg"):
                if key in payload:
                    text = payload[key]
                    break
        
        if not text:
            return None
        
        return ChannelMessage(
            channel="webhook",
            user_id=str(payload.get("user_id", payload.get("from", "anonymous"))),
            user_name=payload.get("user_name", payload.get("from_name", "User")),
            text=text,
            raw=payload,
            thread_id=payload.get("thread_id", payload.get("conversation_id")),
        )
    
    async def send_reply(self, message: ChannelMessage, reply: ChannelReply) -> bool:
        """Webhook 渠道通过 HTTP 响应返回回复，这里无需实际发送"""
        return True
