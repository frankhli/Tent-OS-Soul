"""声音合成引擎 —— edge-tts 主力实现

当前使用 edge-tts（微软 Edge 免费 TTS）作为主力合成引擎。
未来可接入真正的声音克隆模型（GPT-SoVITS、F5-TTS 等），
所有声纹样本已通过 VoiceModeler 采集存储，换模型时零成本迁移。
"""

import hashlib
from pathlib import Path
from typing import Dict, Optional, List
import asyncio

from tent_os.logging_config import get_logger

logger = get_logger()

# edge-tts 支持的中文声音
CHINESE_VOICES = {
    # 女声
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",      # 晓晓 — 年轻女声，通用
    "xiaoyi": "zh-CN-XiaoyiNeural",          # 小艺 — 年轻女声，温柔
    "yunjian": "zh-CN-YunjianNeural",        # 云健 — 男声，新闻播报风格
    "yunxi": "zh-CN-YunxiNeural",            # 云希 — 男声，年轻自然
    "yunxia": "zh-CN-YunxiaNeural",          # 云夏 — 男声，活泼
    "xiaohan": "zh-CN-XiaohanNeural",        # 晓涵 — 女声，成熟稳重
    "xiaomeng": "zh-CN-XiaomengNeural",      # 晓梦 — 女声，甜美
    "xiaorui": "zh-CN-XiaoruiNeural",        # 晓睿 — 女声，知性
}

# 情绪到声音/语速的映射
EMOTION_VOICE_MAP = {
    "happy": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+10%", "pitch": "+10Hz"},
    "joy": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+10%", "pitch": "+10Hz"},
    "excited": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+15%", "pitch": "+15Hz"},
    "sad": {"voice": "zh-CN-XiaohanNeural", "rate": "-10%", "pitch": "-10Hz"},
    "sadness": {"voice": "zh-CN-XiaohanNeural", "rate": "-10%", "pitch": "-10Hz"},
    "melancholy": {"voice": "zh-CN-XiaohanNeural", "rate": "-15%", "pitch": "-15Hz"},
    "angry": {"voice": "zh-CN-YunxiNeural", "rate": "+5%", "pitch": "+5Hz"},
    "rage": {"voice": "zh-CN-YunxiNeural", "rate": "+10%", "pitch": "+10Hz"},
    "calm": {"voice": "zh-CN-XiaoyiNeural", "rate": "-5%", "pitch": "0Hz"},
    "peaceful": {"voice": "zh-CN-XiaoyiNeural", "rate": "-5%", "pitch": "0Hz"},
    "serene": {"voice": "zh-CN-XiaoyiNeural", "rate": "-10%", "pitch": "-5Hz"},
    "thinking": {"voice": "zh-CN-XiaoruiNeural", "rate": "-5%", "pitch": "0Hz"},
    "curious": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+5%", "pitch": "+5Hz"},
    "neutral": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+0%", "pitch": "+0Hz"},
    "listening": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+0%", "pitch": "+0Hz"},
}


# OpenAI TTS 支持的声音
OPENAI_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

# 情绪到 OpenAI voice 的映射（简单映射）
EMOTION_OPENAI_MAP = {
    "happy": "nova",
    "joy": "nova",
    "excited": "nova",
    "sad": "echo",
    "sadness": "echo",
    "melancholy": "echo",
    "angry": "onyx",
    "rage": "onyx",
    "calm": "alloy",
    "peaceful": "alloy",
    "serene": "alloy",
    "thinking": "fable",
    "curious": "nova",
    "neutral": "alloy",
    "listening": "alloy",
}


class TTSSynthesizer:
    """
    TTS 声音合成引擎（edge-tts 主力 + OpenAI TTS 流式）

    设计原则：
    - edge-tts：零成本、8种中文声音、非流式
    - OpenAI TTS：流式输出、低延迟、需 API key
    - 声纹样本通过 VoiceModeler 持续采集
    - 未来接入克隆模型时，直接复用样本数据
    """

    def __init__(self, storage_path: str = "./tent_memory/soul", openai_api_key: str = "",
                 voice_clone_router=None):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.output_dir = self.storage_path.parent / "tts"
        self.output_dir.mkdir(exist_ok=True)
        self._cache: Dict[str, str] = {}  # text_hash -> audio_path
        self.openai_api_key = openai_api_key
        self.openai_base_url = "https://api.openai.com/v1"
        self.voice_clone_router = voice_clone_router
    
    def _get_cache_key(self, text: str, voice: str, rate: str, pitch: str) -> str:
        return hashlib.md5(f"{text}:{voice}:{rate}:{pitch}".encode()).hexdigest()[:16]
    
    async def synthesize(
        self,
        text: str,
        user_id: Optional[str] = None,
        voice_key: Optional[str] = None,
        emotion: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict:
        """
        将文本合成为语音
        
        Args:
            text: 要合成的文本
            user_id: 用户ID（用于未来关联用户声纹）
            voice_key: 声音选择键，如 "xiaoxiao", "yunxi"
            emotion: 情绪标签，如 "happy", "sad", "calm"
            use_cache: 是否使用缓存
        
        Returns:
            {"status": "ok", "audio_path": str, "audio_url": str, "voice": str, "cached": bool}
        """
        if not text or not text.strip():
            return {"status": "error", "message": "文本为空"}
        
        # === 优先尝试声音克隆 ===
        if self.voice_clone_router and user_id:
            try:
                clone_path = await self.voice_clone_router.synthesize(
                    user_id=user_id,
                    text=text,
                    emotion=emotion or "neutral",
                )
                if clone_path:
                    logger.info(f"[TTS] 使用克隆声音 [{user_id}]")
                    return {
                        "status": "ok",
                        "audio_path": clone_path,
                        "audio_url": f"/tts/{Path(clone_path).name}",
                        "voice": "cloned",
                        "cached": False,
                        "source": "voice_clone",
                    }
            except Exception as e:
                logger.warning(f"[TTS] 克隆声音合成失败 [{user_id}]: {e}，回退到默认TTS")
        
        # 确定声音参数
        voice_name = CHINESE_VOICES.get(voice_key, CHINESE_VOICES["xiaoxiao"])
        rate = "+0%"
        pitch = "+0Hz"
        
        if emotion and emotion.lower() in EMOTION_VOICE_MAP:
            emo_cfg = EMOTION_VOICE_MAP[emotion.lower()]
            voice_name = emo_cfg.get("voice", voice_name)
            rate = emo_cfg.get("rate", rate)
            pitch = emo_cfg.get("pitch", pitch)
        
        # 检查缓存
        cache_key = self._get_cache_key(text, voice_name, rate, pitch)
        if use_cache and cache_key in self._cache:
            cached_path = self._cache[cache_key]
            if Path(cached_path).exists():
                logger.info(f"[TTS] 缓存命中 [{user_id or 'unknown'}]")
                return {
                    "status": "ok",
                    "audio_path": cached_path,
                    "audio_url": f"/tts/{Path(cached_path).name}",
                    "voice": voice_name,
                    "cached": True,
                    "source": "edge_tts",
                }
        
        # 生成音频
        try:
            import edge_tts
            
            filename = f"tts_{user_id or 'guest'}_{cache_key}.mp3"
            output_path = self.output_dir / filename
            
            communicate = edge_tts.Communicate(text, voice_name, rate=rate, pitch=pitch)
            await communicate.save(str(output_path))
            
            self._cache[cache_key] = str(output_path)
            
            logger.info(f"[TTS] 合成完成 [{user_id or 'unknown'}]: {voice_name}, {len(text)}字")
            
            return {
                "status": "ok",
                "audio_path": str(output_path),
                "audio_url": f"/tts/{filename}",
                "voice": voice_name,
                "cached": False,
                "source": "edge_tts",
                "emotion": emotion,
            }
        except Exception as e:
            logger.warning(f"[TTS] 合成失败: {e}")
            return {"status": "error", "message": f"语音合成失败: {str(e)[:200]}"}
    
    async def synthesize_for_user(
        self,
        user_id: str,
        text: str,
        emotion: Optional[str] = None,
    ) -> Dict:
        """为用户合成语音（优先使用用户偏好的声音设置）"""
        # 从环境变量或配置读取用户声音偏好
        voice_key = self._get_user_voice_preference(user_id)
        return await self.synthesize(text, user_id=user_id, voice_key=voice_key, emotion=emotion)
    
    def _get_user_voice_preference(self, user_id: str) -> Optional[str]:
        """获取用户的声音偏好（从环境变量）"""
        import os
        env_key = os.environ.get(f"TENT_VOICE_PREF_{user_id}")
        if env_key and env_key in CHINESE_VOICES:
            return env_key
        # 默认
        return os.environ.get("TENT_DEFAULT_VOICE", "xiaoxiao")
    
    def get_available_voices(self) -> List[Dict]:
        """获取所有可用的声音列表"""
        voice_info = {
            "xiaoxiao": {"name": "晓晓", "gender": "女", "style": "通用、自然", "age": "年轻"},
            "xiaoyi": {"name": "小艺", "gender": "女", "style": "温柔、舒缓", "age": "年轻"},
            "xiaohan": {"name": "晓涵", "gender": "女", "style": "成熟、稳重", "age": "成熟"},
            "xiaomeng": {"name": "晓梦", "gender": "女", "style": "甜美、活泼", "age": "年轻"},
            "xiaorui": {"name": "晓睿", "gender": "女", "style": "知性、专业", "age": "成熟"},
            "yunjian": {"name": "云健", "gender": "男", "style": "新闻播报、正式", "age": "成熟"},
            "yunxi": {"name": "云希", "gender": "男", "style": "年轻、自然", "age": "年轻"},
            "yunxia": {"name": "云夏", "gender": "男", "style": "活泼、阳光", "age": "年轻"},
        }
        return [
            {"key": k, "voice_id": v, **voice_info.get(k, {})}
            for k, v in CHINESE_VOICES.items()
        ]
    
    async def synthesize_stream(self, text: str, voice_key: str = "alloy", emotion: Optional[str] = None):
        """流式 TTS 合成（OpenAI TTS-1）

        Yields:
            audio bytes chunks
        """
        if not self.openai_api_key:
            raise RuntimeError("OpenAI API key 未配置，无法使用流式 TTS")

        voice = voice_key if voice_key in OPENAI_VOICES else "alloy"
        if emotion and emotion.lower() in EMOTION_OPENAI_MAP:
            voice = EMOTION_OPENAI_MAP[emotion.lower()]

        import httpx

        payload = {
            "model": "tts-1",
            "input": text[:4096],  # OpenAI TTS 最大输入
            "voice": voice,
            "response_format": "mp3",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.openai_base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    if chunk:
                        yield chunk

    def is_streaming_available(self) -> bool:
        """是否支持流式 TTS"""
        return bool(self.openai_api_key)

    def clear_cache(self):
        """清理缓存"""
        self._cache.clear()
        logger.info("[TTS] 缓存已清理")
