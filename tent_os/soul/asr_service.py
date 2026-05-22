"""ASR 服务 —— 自动语音识别

支持多种 Provider：
- openai_whisper: OpenAI Whisper API（推荐，质量最高）
- kimi: Kimi 语音识别 API（如果支持）
- browser_fallback: 回退到前端 Web Speech API（零配置）

使用方式：
    asr = ASRService(config)
    result = await asr.transcribe(audio_bytes, filename="recording.webm")
    # result = {"text": "识别出的文字", "provider": "openai_whisper"}
"""

import io
import os
import tempfile
from typing import Dict, Optional
from pathlib import Path

import httpx

from tent_os.logging_config import get_logger

logger = get_logger()


class ASRService:
    """自动语音识别服务"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.provider = self.config.get("provider", "browser_fallback")
        self.api_key = self.config.get("api_key", "")
        self.base_url = self.config.get("base_url", "https://api.openai.com/v1")
        self.model = self.config.get("model", "whisper-1")
        self.language = self.config.get("language", "zh")

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm",
                         mime_type: str = "audio/webm") -> Dict:
        """将音频转换为文字

        Args:
            audio_bytes: 音频文件二进制数据
            filename: 文件名（用于推断格式）
            mime_type: MIME 类型

        Returns:
            {"text": str, "provider": str, "confidence": float | None}
        """
        if self.provider == "openai_whisper" and self.api_key:
            return await self._transcribe_openai(audio_bytes, filename)

        if self.provider == "kimi" and self.api_key:
            return await self._transcribe_kimi(audio_bytes, filename)

        # Fallback: 告知前端使用浏览器 ASR
        return {
            "text": "",
            "provider": "browser_fallback",
            "confidence": None,
            "fallback": True,
            "message": "后端 ASR 未配置，请使用浏览器语音识别",
        }

    async def _transcribe_openai(self, audio_bytes: bytes, filename: str) -> Dict:
        """使用 OpenAI Whisper API"""
        try:
            # 确保文件格式被支持（webm 可能需要转换）
            suffix = Path(filename).suffix.lower()
            if suffix not in (".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"):
                # 默认回退到 webm，Whisper 支持 webm
                filename = "audio.webm"

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (filename, io.BytesIO(audio_bytes))},
                    data={
                        "model": self.model,
                        "language": self.language,
                        "response_format": "json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data.get("text", "").strip()
                return {
                    "text": text,
                    "provider": "openai_whisper",
                    "confidence": None,  # Whisper API 不返回 confidence
                }
        except Exception as e:
            logger.warning(f"[ASR] OpenAI Whisper 失败: {e}")
            return {
                "text": "",
                "provider": "openai_whisper",
                "confidence": None,
                "error": str(e),
            }

    async def _transcribe_kimi(self, audio_bytes: bytes, filename: str) -> Dict:
        """使用 Kimi 语音识别 API（如果未来支持）"""
        # Kimi 当前未公开语音 API，占位
        logger.warning("[ASR] Kimi 语音识别尚未支持")
        return {
            "text": "",
            "provider": "kimi",
            "confidence": None,
            "error": "Kimi ASR not supported yet",
        }

    def is_available(self) -> bool:
        """检查 ASR 是否可用（有配置且有 API key）"""
        if self.provider in ("openai_whisper", "kimi"):
            return bool(self.api_key)
        return False

    @property
    def status(self) -> Dict:
        return {
            "provider": self.provider,
            "available": self.is_available(),
            "model": self.model,
            "language": self.language,
        }
