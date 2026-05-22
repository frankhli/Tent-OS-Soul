"""Slack 渠道 —— 支持 Slack Bot

需要配置:
  • bot_token —— Slack Bot User OAuth Token (xoxb-...)
  • signing_secret —— 可选，请求签名验证

文档: https://api.slack.com/start/overview
"""

from typing import Any, Dict, Optional

import httpx

from tent_os.channels.base import ChannelMessage, ChannelReply, MessageChannel


class SlackChannel(MessageChannel):
    """Slack 消息渠道"""
    
    name = "slack"
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.bot_token = config.get("bot_token", "")
        self.signing_secret = config.get("signing_secret", "")
        self.base_url = "https://slack.com/api"
    
    async def initialize(self):
        if not self.bot_token:
            self.enabled = False
            return
        # 验证 token 有效性
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/auth.test",
                headers={"Authorization": f"Bearer {self.bot_token}"}
            )
            data = resp.json()
            if not data.get("ok"):
                self.enabled = False
    
    async def parse_incoming(self, payload: Dict[str, Any]) -> Optional[ChannelMessage]:
        """解析 Slack Events API payload"""
        # 处理 URL verification
        if payload.get("type") == "url_verification":
            return None  # 由上层处理 challenge
        
        event = payload.get("event", {})
        
        # 忽略 bot 自己的消息
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return None
        
        text = event.get("text", "")
        if not text:
            return None
        
        # 去掉 @bot 的 mention
        bot_id = payload.get("authorizations", [{}])[0].get("user_id", "")
        if bot_id:
            text = text.replace(f"<@{bot_id}>", "").strip()
        
        return ChannelMessage(
            channel="slack",
            user_id=event.get("user", "unknown"),
            user_name=event.get("user", "User"),
            text=text,
            raw=payload,
            thread_id=event.get("channel"),
        )
    
    async def send_reply(self, message: ChannelMessage, reply: ChannelReply) -> bool:
        """发送回复到 Slack"""
        if not self.bot_token:
            return False
        
        channel = message.thread_id or message.raw.get("event", {}).get("channel")
        thread_ts = message.raw.get("event", {}).get("thread_ts") or message.raw.get("event", {}).get("ts")
        
        body = {
            "channel": channel,
            "text": reply.text,
            "thread_ts": thread_ts,
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat.postMessage",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                json=body,
            )
            data = resp.json()
            return data.get("ok", False)
