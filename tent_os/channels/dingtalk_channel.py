"""DingTalk (钉钉) 渠道适配器

支持：
- 接收钉钉机器人/自建应用消息推送
- 发送文本/Markdown/ActionCard 消息
- 群机器人 Webhook 和内部应用两种模式

配置需求：
- app_key / app_secret: 内部应用凭证
- robot_code / robot_token: 群机器人凭证
- webhook_url: 群机器人 Webhook（简化模式）
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Dict, Any, Optional

import httpx

from tent_os.channels.base import MessageChannel, ChannelMessage, ChannelReply
from tent_os.logging_config import get_logger

logger = get_logger()

DINGTALK_API_BASE = "https://oapi.dingtalk.com"


class DingTalkChannel(MessageChannel):
    """钉钉渠道"""

    name = "dingtalk"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.app_key = config.get("app_key", "")
        self.app_secret = config.get("app_secret", "")
        self.robot_code = config.get("robot_code", "")
        self.robot_token = config.get("robot_token", "")
        self.webhook_url = config.get("webhook_url", "")

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    async def initialize(self):
        if self.app_key and self.app_secret:
            await self._refresh_access_token()
        elif not self.webhook_url:
            raise ValueError("钉钉配置不完整: 需要 app_key+app_secret 或 webhook_url")
        logger.info("[DingTalk] 渠道初始化完成")

    async def parse_incoming(self, payload: Dict[str, Any]) -> Optional[ChannelMessage]:
        """解析钉钉推送的消息"""
        # 机器人回调格式
        text_content = ""
        msg_type = payload.get("msgtype", "").lower()

        if msg_type == "text":
            text_content = payload.get("text", {}).get("content", "")
        elif msg_type == "markdown":
            text_content = payload.get("markdown", {}).get("text", "")

        # 获取发送者信息
        sender = payload.get("senderStaffId", "")
        sender_nick = payload.get("senderNick", sender)
        conversation_id = payload.get("conversationId", "")

        # 清理 @机器人 前缀
        if text_content.startswith("@"):
            parts = text_content.split(None, 1)
            text_content = parts[1] if len(parts) > 1 else ""

        return ChannelMessage(
            channel=self.name,
            user_id=sender,
            user_name=sender_nick,
            text=text_content.strip(),
            raw=payload,
            thread_id=conversation_id or sender,
        )

    async def send_reply(self, message: ChannelMessage, reply: ChannelReply) -> bool:
        """发送回复到钉钉"""
        if self.webhook_url:
            return await self._send_via_webhook(reply)
        return await self._send_via_api(message, reply)

    async def send_to_conversation(self, conversation_id: str, text: str,
                                    markdown: bool = False) -> bool:
        """主动发送消息到会话"""
        if not self._access_token:
            logger.warning("[DingTalk] 未初始化 AccessToken")
            return False

        await self._ensure_token()
        url = f"{DINGTALK_API_BASE}/topapi/message/corpconversation/asyncsend_v2"

        payload = {
            "agent_id": int(self.app_key),
            "msg": {
                "msgtype": "markdown" if markdown else "text",
                "text": {"content": text},
            },
        }
        if conversation_id.startswith("cid"):
            payload["conversation_id"] = conversation_id
        else:
            payload["userid_list"] = conversation_id

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, params={"access_token": self._access_token}, json=payload)
                data = resp.json()
                return data.get("errcode") == 0
        except Exception as e:
            logger.error(f"[DingTalk] 发送异常: {e}")
            return False

    async def send_group_message(self, open_conversation_id: str, text: str) -> bool:
        """通过群机器人发送消息"""
        await self._ensure_token()
        url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"

        payload = {
            "robotCode": self.robot_code,
            "openConversationId": open_conversation_id,
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": text}),
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    headers={"x-acs-dingtalk-access-token": self._access_token},
                    json=payload,
                )
                data = resp.json()
                return data.get("success", False)
        except Exception as e:
            logger.error(f"[DingTalk] 群消息发送异常: {e}")
            return False

    # ========== 内部 ==========

    async def _send_via_webhook(self, reply: ChannelReply) -> bool:
        """通过 Webhook 发送（群机器人模式）"""
        timestamp = str(round(time.time() * 1000))
        secret = self.config.get("webhook_secret", "")

        if secret:
            sign = self._generate_sign(timestamp, secret)
            url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
        else:
            url = self.webhook_url

        payload = {
            "msgtype": "markdown" if reply.markdown else "text",
            "text": {"content": reply.text},
        }
        if reply.markdown:
            payload["markdown"] = {"title": "Tent OS 回复", "text": reply.markdown}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if data.get("errcode") == 0:
                    return True
                logger.warning(f"[DingTalk] Webhook 发送失败: {data}")
                return False
        except Exception as e:
            logger.error(f"[DingTalk] Webhook 异常: {e}")
            return False

    async def _send_via_api(self, message: ChannelMessage, reply: ChannelReply) -> bool:
        """通过内部应用 API 发送"""
        await self._ensure_token()
        return await self.send_to_conversation(
            message.thread_id or message.user_id,
            reply.markdown or reply.text,
            markdown=bool(reply.markdown),
        )

    async def _ensure_token(self):
        if time.time() >= self._token_expires_at - 60:
            await self._refresh_access_token()

    async def _refresh_access_token(self):
        """刷新 AccessToken"""
        url = f"{DINGTALK_API_BASE}/gettoken"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, params={
                    "appkey": self.app_key,
                    "appsecret": self.app_secret,
                })
                data = resp.json()
                if data.get("errcode") == 0:
                    self._access_token = data["access_token"]
                    self._token_expires_at = time.time() + data.get("expires_in", 7200)
                    logger.info("[DingTalk] AccessToken 刷新成功")
                else:
                    raise RuntimeError(f"获取 access_token 失败: {data}")
        except Exception as e:
            logger.error(f"[DingTalk] 刷新 Token 失败: {e}")
            raise

    @staticmethod
    def _generate_sign(timestamp: str, secret: str) -> str:
        """生成 Webhook 签名"""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
