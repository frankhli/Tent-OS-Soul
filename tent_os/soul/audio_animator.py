"""音频动画驱动 —— 分析音频特征，生成面部动画参数

轻量级实现，不依赖 librosa（避免编译问题）。
使用 soundfile + numpy FFT 提取音频特征。

核心特征：
- 音量 (RMS) → 嘴巴张开度
- 音高 (基频) → 眉毛高度
- 语速 (零穿越率) → 头部摆动频率
- 能量起伏 → 呼吸深度
"""

import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import tempfile

from tent_os.logging_config import get_logger

logger = get_logger()


class AudioAnimator:
    """
    音频动画驱动器
    
    将音频文件分析为面部动画关键帧，
    用于驱动 CanvasAvatar 的口型同步和微表情。
    """

    def __init__(self):
        self.sample_rate = 16000
        self.frame_length = 512
        self.hop_length = 256

    def analyze(self, audio_path: str) -> Dict:
        """
        分析音频文件，返回动画参数序列
        
        Returns:
            {
                "duration": float,
                "fps": int,
                "frames": [
                    {
                        "time": float,
                        "volume": float,      # 0~1, 音量
                        "pitch": float,       # 0~1, 归一化音高
                        "speech_rate": float, # 0~1, 语速
                        "energy": float,      # 0~1, 能量
                    }
                ]
            }
        """
        try:
            import soundfile as sf

            data, sr = sf.read(audio_path)
            if data.ndim > 1:
                data = data.mean(axis=1)

            # 重采样到 16kHz（简单线性插值）
            if sr != self.sample_rate:
                from fractions import Fraction
                ratio = Fraction(self.sample_rate, sr)
                n_samples = int(len(data) * ratio)
                data = np.interp(
                    np.linspace(0, len(data) - 1, n_samples),
                    np.arange(len(data)),
                    data,
                )

            # 分帧
            frames = self._extract_frames(data)
            
            duration = len(data) / self.sample_rate
            fps = self.sample_rate / self.hop_length

            return {
                "status": "ok",
                "duration": duration,
                "fps": round(fps),
                "frame_count": len(frames),
                "frames": frames,
            }

        except Exception as e:
            logger.warning(f"[AudioAnimator] 分析失败: {e}")
            return {"status": "error", "message": str(e)}

    def _extract_frames(self, data: np.ndarray) -> List[Dict]:
        """提取每一帧的特征"""
        frames = []
        n_frames = (len(data) - self.frame_length) // self.hop_length + 1

        # 全局统计用于归一化
        all_volumes = []
        all_pitches = []
        all_zcrs = []

        raw_frames = []
        for i in range(n_frames):
            start = i * self.hop_length
            end = start + self.frame_length
            frame = data[start:end]
            
            # 音量 (RMS)
            volume = np.sqrt(np.mean(frame ** 2))
            
            # 零穿越率 (ZCR) → 语速指标
            zcr = np.mean(np.abs(np.diff(np.sign(frame)))) / 2
            
            # 音高 (简化：用 FFT 峰值)
            fft = np.fft.rfft(frame * np.hanning(len(frame)))
            magnitude = np.abs(fft)
            # 只考虑 80~400Hz 语音频段
            freqs = np.fft.rfftfreq(len(frame), 1 / self.sample_rate)
            voice_idx = (freqs >= 80) & (freqs <= 400)
            if np.any(voice_idx):
                pitch_idx = np.argmax(magnitude[voice_idx])
                pitch = freqs[voice_idx][pitch_idx]
            else:
                pitch = 150

            raw_frames.append({
                "volume": volume,
                "pitch": pitch,
                "zcr": zcr,
                "energy": volume * (1 + zcr * 2),
            })
            all_volumes.append(volume)
            all_pitches.append(pitch)
            all_zcrs.append(zcr)

        # 归一化参数
        vol_max = np.percentile(all_volumes, 95) or 1e-6
        vol_min = np.percentile(all_volumes, 5) or 0
        pitch_max = max(all_pitches) if all_pitches else 300
        pitch_min = min(all_pitches) if all_pitches else 80
        pitch_range = max(pitch_max - pitch_min, 1)
        zcr_max = np.percentile(all_zcrs, 95) or 1e-6

        for i, raw in enumerate(raw_frames):
            time = i * self.hop_length / self.sample_rate
            
            # 归一化到 0~1
            norm_vol = min(1.0, max(0, (raw["volume"] - vol_min) / (vol_max - vol_min)))
            norm_pitch = min(1.0, max(0, (raw["pitch"] - pitch_min) / pitch_range))
            norm_zcr = min(1.0, raw["zcr"] / zcr_max) if zcr_max > 0 else 0
            norm_energy = min(1.0, raw["energy"] / (vol_max * 3)) if vol_max > 0 else 0

            frames.append({
                "time": round(time, 3),
                "volume": round(norm_vol, 3),
                "pitch": round(norm_pitch, 3),
                "speech_rate": round(norm_zcr, 3),
                "energy": round(norm_energy, 3),
            })

        return frames

    def get_mouth_open_for_frame(self, frame: Dict) -> float:
        """根据音频帧计算嘴巴张开度"""
        # 音量主导，语速辅助
        base = frame["volume"] * 0.8 + frame["speech_rate"] * 0.2
        # 音高影响嘴巴形状：高音→嘴更扁，低音→嘴更圆
        return min(1.0, base * 1.2)

    def get_brow_height_for_frame(self, frame: Dict) -> float:
        """根据音高计算眉毛高度"""
        # 高音 → 眉毛扬起（惊讶/兴奋感）
        return (frame["pitch"] - 0.5) * 0.4

    def get_head_tilt_for_frame(self, frame: Dict) -> float:
        """根据能量起伏计算头部倾斜"""
        return (frame["energy"] - 0.5) * 0.1


# 全局实例
_audio_animator = None

def get_audio_animator() -> AudioAnimator:
    global _audio_animator
    if _audio_animator is None:
        _audio_animator = AudioAnimator()
    return _audio_animator
