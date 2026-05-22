"""飞书渠道 —— 支持群聊和私聊

需要配置:
  • app_id     —— 飞书应用 ID
  • app_secret —— 飞书应用 Secret
  • encrypt_key —— 可选，消息加密密钥
  • verification_token —— 可选，验证 Token

文档: https://open.feishu.cn/document/home
"""

import hashlib
import json
from typing import Any, Dict, Optional

import httpx

from tent_os.channels.base import ChannelMessage, ChannelReply, MessageChannel


class FeishuChannel(MessageChannel):
    """飞书消息渠道"""
    
    name = "feishu"
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.app_id = config.get("app_id", "")
        self.app_secret = config.get("app_secret", "")
        self.base_url = "https://open.feishu.cn/open-apis"
        self._access_token: Optional[str] = None
    
    async def initialize(self):
        if not self.app_id or not self.app_secret:
            self.enabled = False
            return
        await self._refresh_token()
    
    async def _refresh_token(self):
        """获取飞书 tenant_access_token"""
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            })
            data = resp.json()
            self._access_token = data.get("tenant_access_token")
    
    async def parse_incoming(self, payload: Dict[str, Any]) -> Optional[ChannelMessage]:
        """解析飞书事件回调"""
        header = payload.get("header", {})
        event_type = header.get("event_type", "")
        
        # 处理 challenge（配置 webhook 时飞书会发送验证请求）
        if "challenge" in payload:
            return None  # 由上层处理
        
        event = payload.get("event", {})
        
        # 仅处理用户消息事件
        if event_type not in ("im.message.receive_v1",):
            return None
        
        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})
        
        text = ""
        content = json.loads(message.get("content", "{}"))
        msg_type = message.get("message_type", "")
        
        if msg_type == "text":
            text = content.get("text", "")
        else:
            text = f"[非文本消息: {msg_type}]"
        
        # 去掉 @机器人的部分
        mentions = content.get("mentions", [])
        for m in mentions:
            text = text.replace(m.get("key", ""), "").strip()
        
        if not text:
            return None
        
        return ChannelMessage(
            channel="feishu",
            user_id=sender.get("open_id", "unknown"),
            user_name=sender.get("union_id", "User"),
            text=text,
            raw=payload,
            thread_id=message.get("chat_id"),
        )
    
    async def send_reply(self, message: ChannelMessage, reply: ChannelReply) -> bool:
        """发送回复到飞书"""
        if not self._access_token:
            return False
        
        url = f"{self.base_url}/im/v1/messages"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        
        # 回复到原会话
        chat_id = message.thread_id or message.raw.get("event", {}).get("message", {}).get("chat_id")
        msg_id = message.raw.get("event", {}).get("message", {}).get("message_id")
        
        if not chat_id:
            return False
        
        body = {
            "receive_id": chat_id,
            "content": json.dumps({"text": reply.text}),
            "msg_type": "text",
        }
        
        # 如果是群聊，使用 reply 模式
        if msg_id:
            url = f"{self.base_url}/im/v1/messages/{msg_id}/reply"
            body = {
                "content": json.dumps({"text": reply.text}),
                "msg_type": "text",
            }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=body)
            return resp.status_code == 200
