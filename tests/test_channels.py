"""Tests for Channel Adapters —— 企业微信 & 钉钉"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from tent_os.channels.base import ChannelMessage, ChannelReply
from tent_os.channels.wechat_work_channel import WeChatWorkChannel
from tent_os.channels.dingtalk_channel import DingTalkChannel


@pytest.mark.unit
class TestWeChatWorkChannel:

    @pytest.mark.asyncio
    async def test_parse_text_message(self):
        channel = WeChatWorkChannel({
            "corp_id": "test_corp",
            "agent_id": "100001",
            "secret": "test_secret",
        })

        payload = {
            "MsgType": "text",
            "FromUserName": "zhangsan",
            "Content": "Hello bot",
            "ChatId": "chat_123",
        }

        msg = await channel.parse_incoming(payload)
        assert msg is not None
        assert msg.channel == "wechat_work"
        assert msg.user_id == "zhangsan"
        assert msg.text == "Hello bot"
        assert msg.thread_id == "chat_123"

    @pytest.mark.asyncio
    async def test_parse_voice_message(self):
        channel = WeChatWorkChannel({
            "corp_id": "test_corp",
            "agent_id": "100001",
            "secret": "test_secret",
        })

        payload = {
            "MsgType": "voice",
            "FromUserName": "lisi",
            "Recognition": "语音转文字内容",
            "ChatId": "chat_456",
        }

        msg = await channel.parse_incoming(payload)
        assert msg is not None
        assert msg.text == "语音转文字内容"

    @pytest.mark.asyncio
    async def test_parse_unsupported_message(self):
        channel = WeChatWorkChannel({
            "corp_id": "test_corp",
            "agent_id": "100001",
            "secret": "test_secret",
        })

        payload = {"MsgType": "video", "FromUserName": "wangwu"}
        msg = await channel.parse_incoming(payload)
        assert msg is None

    @pytest.mark.asyncio
    async def test_send_reply(self):
        channel = WeChatWorkChannel({
            "corp_id": "test_corp",
            "agent_id": "100001",
            "secret": "test_secret",
        })
        channel._access_token = "fake_token"
        channel._token_expires_at = 9999999999

        msg = ChannelMessage(
            channel="wechat_work",
            user_id="zhangsan",
            user_name="张三",
            text="Hello",
            raw={},
        )
        reply = ChannelReply(text="Reply text")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json = MagicMock(return_value={"errcode": 0})
            result = await channel.send_reply(msg, reply)
            assert result is True

    @pytest.mark.asyncio
    async def test_send_reply_failure(self):
        channel = WeChatWorkChannel({
            "corp_id": "test_corp",
            "agent_id": "100001",
            "secret": "test_secret",
        })
        channel._access_token = "fake_token"
        channel._token_expires_at = 9999999999

        msg = ChannelMessage(
            channel="wechat_work",
            user_id="zhangsan",
            user_name="张三",
            text="Hello",
            raw={},
        )
        reply = ChannelReply(text="Reply")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json = MagicMock(return_value={"errcode": 40001, "errmsg": "invalid credential"})
            result = await channel.send_reply(msg, reply)
            assert result is False

    def test_initialize_error(self):
        channel = WeChatWorkChannel({"corp_id": "", "agent_id": ""})
        with pytest.raises(ValueError):
            import asyncio
            asyncio.run(channel.initialize())


@pytest.mark.unit
class TestDingTalkChannel:

    @pytest.mark.asyncio
    async def test_parse_text_message(self):
        channel = DingTalkChannel({
            "app_key": "test_key",
            "app_secret": "test_secret",
        })

        payload = {
            "msgtype": "text",
            "text": {"content": "@机器人 Hello"},
            "senderStaffId": "user001",
            "senderNick": "Alice",
            "conversationId": "cid_123",
        }

        msg = await channel.parse_incoming(payload)
        assert msg is not None
        assert msg.channel == "dingtalk"
        assert msg.user_id == "user001"
        assert msg.user_name == "Alice"
        assert msg.text == "Hello"
        assert msg.thread_id == "cid_123"

    @pytest.mark.asyncio
    async def test_parse_markdown_message(self):
        channel = DingTalkChannel({
            "app_key": "test_key",
            "app_secret": "test_secret",
        })

        payload = {
            "msgtype": "markdown",
            "markdown": {"text": "# Title\nContent"},
            "senderStaffId": "user002",
        }

        msg = await channel.parse_incoming(payload)
        assert msg is not None
        assert "# Title" in msg.text

    @pytest.mark.asyncio
    async def test_send_via_webhook(self):
        channel = DingTalkChannel({
            "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
        })

        reply = ChannelReply(text="Webhook reply")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.json = MagicMock(return_value={"errcode": 0})
            result = await channel.send_reply(
                ChannelMessage(channel="dingtalk", user_id="u1", user_name="U", text="hi", raw={}),
                reply,
            )
            assert result is True

    def test_generate_sign(self):
        timestamp = "1234567890"
        secret = "test_secret"
        sign = DingTalkChannel._generate_sign(timestamp, secret)
        assert sign is not None
        assert len(sign) > 0

    def test_initialize_webhook_only(self):
        channel = DingTalkChannel({
            "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
        })
        # 不应抛出异常
        import asyncio
        asyncio.run(channel.initialize())
