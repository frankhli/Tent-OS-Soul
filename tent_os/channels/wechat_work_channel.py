"""WeChat Work (企业微信) 渠道适配器

支持：
- 接收企业微信消息推送（通过自建应用）
- 发送文本/富文本/Markdown 消息
- 被动回复（15秒内）和主动推送（异步）

配置需求：
- corp_id: 企业 ID
- agent_id: 应用 ID
- secret: 应用 Secret
- token / encoding_aes_key: 消息加解密（可选）
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional

import httpx

from tent_os.channels.base import MessageChannel, ChannelMessage, ChannelReply
from tent_os.logging_config import get_logger

logger = get_logger()

WECHAT_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


class WeChatWorkChannel(MessageChannel):
    """企业微信渠道"""

    name = "wechat_work"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.corp_id = config.get("corp_id", "")
        self.agent_id = config.get("agent_id", "")
        self.secret = config.get("secret", "")
        self.token = config.get("token", "")
        self.encoding_aes_key = config.get("encoding_aes_key", "")

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    async def initialize(self):
        if not all([self.corp_id, self.agent_id, self.secret]):
            raise ValueError("企业微信配置不完整: 需要 corp_id, agent_id, secret")
        await self._refresh_access_token()
        logger.info("[WeChatWork] 渠道初始化完成")

    async def parse_incoming(self, payload: Dict[str, Any]) -> Optional[ChannelMessage]:
        """解析企业微信推送的消息"""
        # 企业微信推送格式（解密后）
        msg_type = payload.get("MsgType", "").lower()
        if msg_type not in ("text", "markdown", "voice", "image"):
            return None

        user_id = payload.get("FromUserName", "")
        text = payload.get("Content", "")
        if msg_type == "voice":
            text = payload.get("Recognition", "")  # 语音转文字结果

        return ChannelMessage(
            channel=self.name,
            user_id=user_id,
            user_name=user_id,  # 企业微信中 user_id 通常是人名拼音
            text=text,
            raw=payload,
            thread_id=payload.get("ChatId") or payload.get("FromUserName"),
        )

    async def send_reply(self, message: ChannelMessage, reply: ChannelReply) -> bool:
        """发送回复到企业微信"""
        await self._ensure_token()

        url = f"{WECHAT_API_BASE}/message/send"
        payload = {
            "touser": message.user_id,
            "msgtype": "markdown" if reply.markdown else "text",
            "agentid": int(self.agent_id),
            "text": {"content": reply.text},
        }
        if reply.markdown:
            payload["markdown"] = {"content": reply.markdown}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    params={"access_token": self._access_token},
                    json=payload,
                )
                data = resp.json()
                if data.get("errcode") == 0:
                    return True
                logger.warning(f"[WeChatWork] 发送失败: {data}")
                return False
        except Exception as e:
            logger.error(f"[WeChatWork] 发送异常: {e}")
            return False

    async def send_to_user(self, user_id: str, text: str, markdown: bool = False) -> bool:
        """主动发送消息给用户"""
        await self._ensure_token()

        url = f"{WECHAT_API_BASE}/message/send"
        payload = {
            "touser": user_id,
            "msgtype": "markdown" if markdown else "text",
            "agentid": int(self.agent_id),
            "text": {"content": text},
        }
        if markdown:
            payload["markdown"] = {"content": text}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    params={"access_token": self._access_token},
                    json=payload,
                )
                data = resp.json()
                return data.get("errcode") == 0
        except Exception as e:
            logger.error(f"[WeChatWork] 主动发送异常: {e}")
            return False

    async def upload_media(self, media_type: str, file_path: str) -> Optional[str]:
        """上传临时素材，返回 media_id"""
        await self._ensure_token()

        url = f"{WECHAT_API_BASE}/media/upload"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with open(file_path, "rb") as f:
                    resp = await client.post(
                        url,
                        params={"access_token": self._access_token, "type": media_type},
                        files={"media": f},
                    )
                data = resp.json()
                if data.get("errcode") == 0:
                    return data.get("media_id")
                logger.warning(f"[WeChatWork] 上传失败: {data}")
        except Exception as e:
            logger.error(f"[WeChatWork] 上传异常: {e}")
        return None

    # ========== 内部 ==========

    async def _ensure_token(self):
        if time.time() >= self._token_expires_at - 60:
            await self._refresh_access_token()

    async def _refresh_access_token(self):
        """刷新 access_token"""
        url = f"{WECHAT_API_BASE}/gettoken"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, params={
                    "corpid": self.corp_id,
                    "corpsecret": self.secret,
                })
                data = resp.json()
                if data.get("errcode") == 0:
                    self._access_token = data["access_token"]
                    self._token_expires_at = time.time() + data.get("expires_in", 7200)
                    logger.info("[WeChatWork] AccessToken 刷新成功")
                else:
                    raise RuntimeError(f"获取 access_token 失败: {data}")
        except Exception as e:
            logger.error(f"[WeChatWork] 刷新 Token 失败: {e}")
            raise
