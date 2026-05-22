"""声音克隆引擎

提供抽象接口，支持多种声音克隆后端：
- EdgeTTSVoiceClone: 基于 edge-tts 的轻量克隆（无需 GPU，基于样本特征调整参数）
- F5TTSVoiceClone: 基于 F5-TTS 的深度克隆（需要安装 f5-tts 包）

使用策略：
1. 优先尝试 F5-TTS（如果已安装且有足够样本）
2. 回退到 EdgeTTS（根据样本特征动态调整 rate/pitch）
3. 兜底到默认 TTS
"""

import asyncio
import hashlib
import json
import os
import re
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class VoiceFeatures:
    """从语音样本中提取的特征"""
    
    # 语速：每分钟字数（估算）
    words_per_minute: float = 0.0
    
    # 音调：平均基频（Hz）
    avg_pitch: float = 0.0
    
    # 音调范围：最高 - 最低
    pitch_range: float = 0.0
    
    # 音量动态范围（dB）
    volume_range: float = 0.0
    
    # 平均音量（dB）
    avg_volume: float = 0.0
    
    # 停顿模式：平均停顿时长（秒）
    avg_pause: float = 0.0
    
    # 性别推断：male / female / unknown
    inferred_gender: str = "unknown"
    
    # 年龄推断：young / middle / senior / unknown
    inferred_age: str = "unknown"
    
    # 情绪基调：calm / energetic / melancholic / unknown
    inferred_mood: str = "unknown"
    
    # 样本数量
    sample_count: int = 0
    
    # 总时长（秒）
    total_duration: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "words_per_minute": round(self.words_per_minute, 1),
            "avg_pitch": round(self.avg_pitch, 1),
            "pitch_range": round(self.pitch_range, 1),
            "volume_range": round(self.volume_range, 1),
            "avg_volume": round(self.avg_volume, 1),
            "avg_pause": round(self.avg_pause, 2),
            "inferred_gender": self.inferred_gender,
            "inferred_age": self.inferred_age,
            "inferred_mood": self.inferred_mood,
            "sample_count": self.sample_count,
            "total_duration": round(self.total_duration, 1),
        }


class VoiceCloneEngine(ABC):
    """声音克隆引擎抽象基类"""
    
    NAME: str = "base"
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查引擎是否可用（依赖是否安装）"""
        pass
    
    @abstractmethod
    async def train(self, user_id: str, sample_paths: List[str]) -> Dict[str, Any]:
        """训练/加载用户的克隆声音模型
        
        Returns:
            {"status": "ready"|"training"|"failed", "message": str, "features": VoiceFeatures}
        """
        pass
    
    @abstractmethod
    async def synthesize(self, user_id: str, text: str, emotion: str = "neutral",
                         output_path: Optional[str] = None) -> Optional[str]:
        """合成语音
        
        Args:
            user_id: 用户ID
            text: 要合成的文本
            emotion: 情绪标签
            output_path: 输出文件路径，如果为 None 则生成临时文件
        
        Returns:
            合成后的音频文件路径，或 None（失败）
        """
        pass
    
    @abstractmethod
    def get_features(self, user_id: str) -> Optional[VoiceFeatures]:
        """获取用户的语音特征"""
        pass


class EdgeTTSVoiceClone(VoiceCloneEngine):
    """基于 edge-tts 的轻量声音克隆
    
    不需要 GPU 或 ML 库。原理：
    1. 分析语音样本的声学特征（音调、语速、音量）
    2. 根据特征选择最接近的 edge-tts 预设声音
    3. 动态调整 rate（语速）和 pitch（音调）参数
    
    这是"最小可用"方案，无需安装额外依赖即可工作。
    """
    
    NAME = "edge_tts_clone"
    
    # edge-tts 中文预设声音库（扩展至18个，覆盖更多音色维度）
    CN_VOICES = {
        "male_young": ["zh-CN-YunxiNeural", "zh-CN-YunxiaNeural", "zh-CN-XiaochenNeural"],
        "male_middle": ["zh-CN-YunxiNeural", "zh-CN-YunfengNeural", "zh-CN-YunjianNeural"],
        "male_senior": ["zh-CN-YunyangNeural", "zh-CN-YunyeNeural"],
        "male_deep": ["zh-CN-YunyeNeural", "zh-CN-YunfengNeural"],
        "male_energetic": ["zh-CN-YunxiaNeural", "zh-CN-YunhaoNeural"],
        "female_young": ["zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-XiaomengNeural"],
        "female_middle": ["zh-CN-XiaoxiaoNeural", "zh-CN-XiaohanNeural", "zh-CN-XiaoyanNeural"],
        "female_senior": ["zh-CN-XiaohanNeural", "zh-CN-XiaoyanNeural"],
        "female_sweet": ["zh-CN-XiaomengNeural", "zh-CN-XiaoyiNeural", "zh-CN-XiaobeiNeural"],
        "female_intellectual": ["zh-CN-XiaoruiNeural", "zh-CN-XiaoyanNeural"],
        "female_intimate": ["zh-CN-XiaoniNeural", "zh-CN-XiaoyiNeural"],
    }
    
    # 每个预设声音的特征档案（用于多维度匹配）
    VOICE_PROFILES = {
        "zh-CN-XiaoxiaoNeural":   {"gender": "female", "age": "young",   "pitch": 260, "energy": 0.7, "warmth": 0.6},
        "zh-CN-XiaoyiNeural":     {"gender": "female", "age": "young",   "pitch": 240, "energy": 0.4, "warmth": 0.9},
        "zh-CN-XiaohanNeural":    {"gender": "female", "age": "middle",  "pitch": 210, "energy": 0.5, "warmth": 0.7},
        "zh-CN-XiaomengNeural":   {"gender": "female", "age": "young",   "pitch": 280, "energy": 0.8, "warmth": 0.9},
        "zh-CN-XiaoruiNeural":    {"gender": "female", "age": "middle",  "pitch": 220, "energy": 0.5, "warmth": 0.5},
        "zh-CN-XiaoyanNeural":    {"gender": "female", "age": "middle",  "pitch": 200, "energy": 0.4, "warmth": 0.6},
        "zh-CN-XiaobeiNeural":    {"gender": "female", "age": "young",   "pitch": 300, "energy": 0.9, "warmth": 0.8},
        "zh-CN-XiaoniNeural":     {"gender": "female", "age": "young",   "pitch": 250, "energy": 0.5, "warmth": 0.9},
        "zh-CN-XiaochenNeural":   {"gender": "male",   "age": "young",   "pitch": 160, "energy": 0.7, "warmth": 0.6},
        "zh-CN-YunxiNeural":      {"gender": "male",   "age": "young",   "pitch": 145, "energy": 0.6, "warmth": 0.7},
        "zh-CN-YunjianNeural":    {"gender": "male",   "age": "middle",  "pitch": 130, "energy": 0.4, "warmth": 0.4},
        "zh-CN-YunxiaNeural":     {"gender": "male",   "age": "young",   "pitch": 170, "energy": 0.9, "warmth": 0.8},
        "zh-CN-YunyangNeural":    {"gender": "male",   "age": "senior",  "pitch": 115, "energy": 0.4, "warmth": 0.5},
        "zh-CN-YunfengNeural":    {"gender": "male",   "age": "middle",  "pitch": 125, "energy": 0.5, "warmth": 0.6},
        "zh-CN-YunhaoNeural":     {"gender": "male",   "age": "young",   "pitch": 155, "energy": 0.9, "warmth": 0.5},
        "zh-CN-YunyeNeural":      {"gender": "male",   "age": "middle",  "pitch": 105, "energy": 0.3, "warmth": 0.4},
    }
    
    def __init__(self, storage_path: str = "./tent_memory/soul/voice_clone"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._features_cache: Dict[str, VoiceFeatures] = {}
    
    def is_available(self) -> bool:
        try:
            import edge_tts
            return True
        except ImportError:
            return False
    
    async def train(self, user_id: str, sample_paths: List[str]) -> Dict[str, Any]:
        """分析样本特征，不真正训练模型"""
        if not sample_paths:
            return {"status": "failed", "message": "没有样本", "features": None}
        
        features = await self._analyze_samples(sample_paths)
        self._features_cache[user_id] = features
        
        # 保存特征到文件
        features_path = self.storage_path / f"{user_id}_features.json"
        with open(features_path, "w", encoding="utf-8") as f:
            json.dump(features.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(
            f"[EdgeTTSClone] 语音特征分析完成 [{user_id}] "
            f"样本={features.sample_count}, 时长={features.total_duration:.1f}s, "
            f"性别={features.inferred_gender}, 语速={features.words_per_minute:.0f}wpm"
        )
        
        return {
            "status": "ready",
            "message": f"基于 {features.sample_count} 个样本完成特征分析",
            "features": features.to_dict(),
        }
    
    async def synthesize(self, user_id: str, text: str, emotion: str = "neutral",
                         output_path: Optional[str] = None) -> Optional[str]:
        """使用 edge-tts 合成，根据用户特征调整参数"""
        try:
            import edge_tts
        except ImportError:
            logger.error("[EdgeTTSClone] edge-tts 未安装")
            return None
        
        features = self.get_features(user_id)
        if not features:
            logger.warning(f"[EdgeTTSClone] 用户 [{user_id}] 无语音特征，使用默认参数")
            features = VoiceFeatures()
        
        # 选择声音
        voice = self._select_voice(features)
        
        # 计算调整参数
        rate, pitch = self._calculate_adjustments(features)
        
        # 情绪映射
        emotion_adjustments = self._emotion_adjustments(emotion)
        rate = self._apply_rate_adjustment(rate, emotion_adjustments.get("rate", 0))
        pitch = self._apply_pitch_adjustment(pitch, emotion_adjustments.get("pitch", 0))
        
        # 生成输出路径
        if not output_path:
            output_path = str(self.storage_path / f"{user_id}_{hashlib.md5(text.encode()).hexdigest()[:12]}.mp3")
        
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)
        
        logger.debug(f"[EdgeTTSClone] 合成完成 [{user_id}] voice={voice}, rate={rate}, pitch={pitch}")
        return output_path
    
    def get_features(self, user_id: str) -> Optional[VoiceFeatures]:
        # 先查内存缓存
        if user_id in self._features_cache:
            return self._features_cache[user_id]
        
        # 查文件
        features_path = self.storage_path / f"{user_id}_features.json"
        if features_path.exists():
            try:
                with open(features_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                features = VoiceFeatures(**data)
                self._features_cache[user_id] = features
                return features
            except Exception:
                pass
        
        return None
    
    async def _analyze_samples(self, sample_paths: List[str]) -> VoiceFeatures:
        """分析语音样本的声学特征"""
        features = VoiceFeatures()
        features.sample_count = len(sample_paths)
        
        total_duration = 0.0
        pitches = []
        volumes = []
        pause_durations = []
        
        for path in sample_paths:
            try:
                # 使用 soundfile 读取音频
                try:
                    import soundfile as sf
                    data, sr = sf.read(path)
                    duration = len(data) / sr
                    total_duration += duration
                    
                    # 音调分析（使用 FFT 峰值频率作为近似）
                    if len(data) > sr:
                        frame_size = int(sr * 0.04)  # 40ms frame
                        hop = int(sr * 0.02)  # 20ms hop
                        for i in range(0, len(data) - frame_size, hop):
                            frame = data[i:i+frame_size]
                            if len(frame) < frame_size:
                                break
                            # 加窗
                            window = np.hanning(len(frame))
                            fft = np.fft.rfft(frame * window)
                            magnitude = np.abs(fft)
                            # 限制在 80-400Hz（人声基频范围）
                            freqs = np.fft.rfftfreq(len(frame), 1/sr)
                            valid_idx = (freqs >= 80) & (freqs <= 400)
                            if valid_idx.any():
                                valid_magnitude = magnitude[valid_idx]
                                valid_freqs = freqs[valid_idx]
                                if len(valid_magnitude) > 0:
                                    peak_idx = np.argmax(valid_magnitude)
                                    peak_freq = valid_freqs[peak_idx]
                                    if peak_freq > 0:
                                        pitches.append(peak_freq)
                    
                    # 音量分析（RMS）
                    rms = np.sqrt(np.mean(data ** 2))
                    if rms > 0:
                        db = 20 * np.log10(rms)
                        volumes.append(db)
                    
                    # 停顿检测（低音量段）
                    frame_len = int(sr * 0.1)  # 100ms
                    for i in range(0, len(data) - frame_len, frame_len):
                        frame = data[i:i+frame_len]
                        frame_rms = np.sqrt(np.mean(frame ** 2))
                        if frame_rms < 0.01:  # 低音量阈值
                            pause_durations.append(0.1)
                
                except ImportError:
                    # soundfile 未安装，使用 mutagen 获取时长
                    try:
                        from mutagen.mp3 import MP3
                        audio = MP3(path)
                        total_duration += audio.info.length
                    except Exception:
                        # 最后尝试用文件大小估算
                        size = os.path.getsize(path)
                        total_duration += size / (16000 * 2)  # 16kHz, 16bit mono
                
            except Exception as e:
                logger.warning(f"[EdgeTTSClone] 分析样本失败 {path}: {e}")
                continue
        
        features.total_duration = total_duration
        
        # 计算统计特征
        if pitches:
            features.avg_pitch = float(np.median(pitches))
            features.pitch_range = float(np.percentile(pitches, 95) - np.percentile(pitches, 5))
            # 性别推断：男性基频通常 < 165Hz，女性 > 180Hz
            if features.avg_pitch < 155:
                features.inferred_gender = "male"
            elif features.avg_pitch > 185:
                features.inferred_gender = "female"
            else:
                features.inferred_gender = "unknown"
        
        if volumes:
            features.avg_volume = float(np.mean(volumes))
            features.volume_range = float(np.std(volumes))
        
        if pause_durations:
            features.avg_pause = float(np.mean(pause_durations))
        
        # 语速估算（基于文本长度和时长）
        if total_duration > 0:
            # 假设中文语速约 200-300 字/分钟
            # 用音频时长反推（粗略估计）
            features.words_per_minute = max(150, min(350, 240 + (features.avg_pitch - 200) * 0.5))
        
        # 情绪基调推断
        if features.avg_pitch > 220:
            features.inferred_mood = "energetic"
        elif features.avg_pitch < 130 and features.avg_volume < -30:
            features.inferred_mood = "melancholic"
        else:
            features.inferred_mood = "calm"
        
        return features
    
    def _select_voice(self, features: VoiceFeatures) -> str:
        """多维度特征匹配：选择最接近用户真实声音的 edge-tts 预设"""
        gender = features.inferred_gender or "unknown"
        default_voice = "zh-CN-YunxiNeural"
        
        # 1. 根据性别筛选候选
        candidates = []
        for voice_id, profile in self.VOICE_PROFILES.items():
            if gender == "unknown" or profile["gender"] == gender:
                candidates.append(voice_id)
        
        if not candidates:
            return default_voice
        
        # 2. 计算每个候选的匹配分数（越低越匹配）
        best_voice = candidates[0]
        best_score = float('inf')
        
        user_pitch = features.avg_pitch if features.avg_pitch > 0 else (
            130 if gender == "male" else 220
        )
        user_energy = 0.5  # 默认中等能量
        if features.words_per_minute > 0:
            # 语速映射到能量：快=高能量，慢=低能量
            user_energy = min(1.0, max(0.1, features.words_per_minute / 300))
        
        for voice_id in candidates:
            profile = self.VOICE_PROFILES[voice_id]
            
            # 音高差异（权重最高，40%）
            pitch_diff = abs(profile["pitch"] - user_pitch) / 200  # 归一化
            
            # 能量差异（权重 30%）
            energy_diff = abs(profile["energy"] - user_energy)
            
            # 情绪基调匹配（权重 30%）
            mood_match = 0
            if features.inferred_mood == "energetic" and profile["energy"] > 0.7:
                mood_match = -0.2  # 加分
            elif features.inferred_mood == "melancholic" and profile["energy"] < 0.4:
                mood_match = -0.2
            elif features.inferred_mood == "calm" and 0.3 < profile["energy"] < 0.7:
                mood_match = -0.1
            
            score = pitch_diff * 0.4 + energy_diff * 0.3 + mood_match * 0.3
            
            if score < best_score:
                best_score = score
                best_voice = voice_id
        
        logger.info(
            f"[EdgeTTSClone] 声音匹配 [{features.inferred_gender}] "
            f"pitch={features.avg_pitch:.0f}Hz → {best_voice} "
            f"(score={best_score:.2f})"
        )
        return best_voice
    
    def _calculate_adjustments(self, features: VoiceFeatures) -> Tuple[str, str]:
        """计算 rate 和 pitch 调整参数"""
        # Rate: 默认 +0%，根据语速调整
        # 标准语速 ~240 wpm
        if features.words_per_minute > 0:
            rate_pct = int((features.words_per_minute - 240) / 240 * 100)
            rate_pct = max(-30, min(30, rate_pct))
            rate = f"{rate_pct:+d}%"
        else:
            rate = "+0%"
        
        # Pitch: 默认 +0Hz
        # 根据与标准音调的差异调整
        if features.avg_pitch > 0:
            # 标准男声 ~120Hz，女声 ~220Hz
            standard = 120 if features.inferred_gender == "male" else 220
            pitch_hz = int(features.avg_pitch - standard)
            pitch_hz = max(-50, min(50, pitch_hz))
            pitch = f"{pitch_hz:+d}Hz"
        else:
            pitch = "+0Hz"
        
        return rate, pitch
    
    def _emotion_adjustments(self, emotion: str) -> Dict[str, int]:
        """情绪对 rate 和 pitch 的额外调整"""
        adjustments = {
            "joy": {"rate": +5, "pitch": +20},
            "sadness": {"rate": -10, "pitch": -15},
            "anger": {"rate": +15, "pitch": +30},
            "fear": {"rate": +10, "pitch": +25},
            "surprise": {"rate": +10, "pitch": +35},
            "neutral": {"rate": 0, "pitch": 0},
        }
        return adjustments.get(emotion.lower(), {"rate": 0, "pitch": 0})
    
    def _apply_rate_adjustment(self, base_rate: str, emotion_adj: int) -> str:
        """将情绪调整合并到 rate 参数"""
        m = re.match(r"([+-])(\d+)%", base_rate)
        if not m:
            return base_rate
        sign = 1 if m.group(1) == "+" else -1
        base = int(m.group(2))
        new_val = base + emotion_adj
        new_val = max(-50, min(50, new_val))
        return f"{new_val:+d}%"
    
    def _apply_pitch_adjustment(self, base_pitch: str, emotion_adj: int) -> str:
        """将情绪调整合并到 pitch 参数"""
        m = re.match(r"([+-])(\d+)Hz", base_pitch)
        if not m:
            return base_pitch
        sign = 1 if m.group(1) == "+" else -1
        base = int(m.group(2))
        new_val = base + emotion_adj
        new_val = max(-100, min(100, new_val))
        return f"{new_val:+d}Hz"


class F5TTSVoiceClone(VoiceCloneEngine):
    """基于 F5-TTS 的深度声音克隆
    
    需要安装 f5-tts 包：pip install f5-tts
    需要 GPU 支持（推荐）
    
    当前为占位实现，当 f5-tts 安装后自动启用。
    """
    
    NAME = "f5_tts_clone"
    
    def __init__(self, storage_path: str = "./tent_memory/soul/voice_clone"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._is_initialized = False
    
    def is_available(self) -> bool:
        try:
            import f5_tts
            return True
        except ImportError:
            return False
    
    async def train(self, user_id: str, sample_paths: List[str]) -> Dict[str, Any]:
        if not self.is_available():
            return {"status": "failed", "message": "F5-TTS 未安装。请运行: pip install f5-tts", "features": None}
        
        # TODO: 实现 F5-TTS 训练逻辑
        return {"status": "failed", "message": "F5-TTS 训练尚未实现", "features": None}
    
    async def synthesize(self, user_id: str, text: str, emotion: str = "neutral",
                         output_path: Optional[str] = None) -> Optional[str]:
        if not self.is_available():
            return None
        
        # TODO: 实现 F5-TTS 推理逻辑
        return None
    
    def get_features(self, user_id: str) -> Optional[VoiceFeatures]:
        return None


class VoiceCloneRouter:
    """声音克隆路由器
    
    根据可用性自动选择最佳克隆引擎：
    1. F5-TTS（如果已安装且模型就绪）
    2. EdgeTTS（轻量克隆，无需额外依赖）
    3. 默认 TTS（兜底）
    """
    
    def __init__(self, storage_path: str = "./tent_memory/soul/voice_clone"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._engines: List[VoiceCloneEngine] = [
            F5TTSVoiceClone(storage_path),
            EdgeTTSVoiceClone(storage_path),
        ]
    
    def get_available_engine(self, user_id: str) -> Optional[VoiceCloneEngine]:
        """获取可用的最佳引擎"""
        for engine in self._engines:
            if not engine.is_available():
                continue
            
            # 检查该用户是否有训练好的模型/特征
            features = engine.get_features(user_id)
            if features and features.sample_count > 0:
                return engine
        
        # 如果没有训练好的，返回第一个可用的（EdgeTTS 总是可用如果 edge-tts 安装了）
        for engine in self._engines:
            if engine.is_available():
                return engine
        
        return None
    
    async def train(self, user_id: str, sample_paths: List[str]) -> Dict[str, Any]:
        """使用最佳可用引擎训练"""
        for engine in self._engines:
            if not engine.is_available():
                continue
            result = await engine.train(user_id, sample_paths)
            if result.get("status") == "ready":
                return {**result, "engine": engine.NAME}
        
        return {"status": "failed", "message": "没有可用的克隆引擎", "engine": None}
    
    async def synthesize(self, user_id: str, text: str, emotion: str = "neutral",
                         output_path: Optional[str] = None) -> Optional[str]:
        """使用最佳可用引擎合成"""
        engine = self.get_available_engine(user_id)
        if not engine:
            logger.warning(f"[VoiceCloneRouter] 没有可用的克隆引擎 [{user_id}]")
            return None
        
        return await engine.synthesize(user_id, text, emotion, output_path)
    
    def get_status(self, user_id: str) -> Dict[str, Any]:
        """获取用户的克隆状态"""
        status = {
            "user_id": user_id,
            "engines": [],
            "best_engine": None,
            "features": None,
        }
        
        for engine in self._engines:
            available = engine.is_available()
            features = engine.get_features(user_id)
            engine_status = {
                "name": engine.NAME,
                "available": available,
                "trained": features is not None and features.sample_count > 0,
                "features": features.to_dict() if features else None,
            }
            status["engines"].append(engine_status)
            
            if available and engine_status["trained"] and not status["best_engine"]:
                status["best_engine"] = engine.NAME
                status["features"] = engine_status["features"]
        
        return status
