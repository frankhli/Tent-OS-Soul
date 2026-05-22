"""
声纹克隆适配器 — Phase 3 预留接口

设计目标：将用户积累的语音样本转化为可用于 TTS 的 speaker embedding 和韵律模型。

支持的后端模型（未来可选）：
- GPT-SoVITS: 仅需 1 分钟样本，支持跨语言克隆
- F5-TTS: 仅需 3 秒样本，推理速度快
- CosyVoice: 阿里开源，支持情感控制
- Qwen3-TTS: 阿里最新，仅 3 秒样本即可实时高质量克隆

数据流：
  voice_samples/ (Phase 2 已收集)
       ↓
  VoiceCloneAdapter.train(user_id) → speaker_embedding.pt + prosody_model.pt
       ↓
  VoiceCloneAdapter.synthesize(text, emotion) → audio_bytes
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class VoiceCloneResult:
    """声纹克隆结果"""
    audio_bytes: bytes
    sample_rate: int = 24000
    duration_seconds: float = 0.0
    emotion_applied: str = "neutral"
    model_used: str = ""


@dataclass
class SpeakerEmbedding:
    """说话人嵌入向量（模型无关格式）"""
    vector: List[float]
    dimension: int = 256
    sample_count: int = 0
    total_duration_seconds: float = 0.0
    model_type: str = ""


class VoiceCloneAdapter(ABC):
    """
    声纹克隆适配器基类
    
    所有具体克隆模型（GPT-SoVITS / F5-TTS / CosyVoice）需继承此类。
    """
    
    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        self.model_path = model_path
        self.device = device
        self.is_trained = False
    
    @abstractmethod
    def train(self, user_id: str, sample_dir: Path) -> Dict:
        """
        用用户的语音样本训练声纹模型
        
        Args:
            user_id: 用户标识
            sample_dir: 语音样本目录（voice_modeler 已收集）
        
        Returns:
            {"status": "ok", "model_path": str, "speaker_embedding": SpeakerEmbedding}
        """
        pass
    
    @abstractmethod
    def synthesize(self, text: str, speaker_embedding: SpeakerEmbedding,
                   emotion: str = "neutral", speed: float = 1.0) -> VoiceCloneResult:
        """
        用训练好的声纹合成语音
        
        Args:
            text: 要合成的文本
            speaker_embedding: 说话人嵌入向量
            emotion: 情绪标签（happy/sad/calm/angry/neutral）
            speed: 语速倍率（0.5-2.0）
        """
        pass
    
    @abstractmethod
    def get_readiness(self, sample_dir: Path) -> Dict:
        """评估样本是否足够训练"""
        pass
    
    def export_persona_packet(self, user_id: str, output_path: Path) -> Dict:
        """
        将声纹模型打包到人格数据包中（用于跨机器迁移）
        
        输出格式：
        {
            "version": "1.0",
            "user_id": str,
            "speaker_embedding": {vector: [...], dimension: 256},
            "prosody_profile": {"avg_pitch": 120, "avg_speed": 1.0, "pause_pattern": [...]},
            "sample_manifest": [{"path": str, "duration": float, "emotion": str}],
        }
        """
        return {
            "status": "not_implemented",
            "message": "声纹克隆模型尚未训练。请在 Phase 3 部署 GPU 环境后调用 train()。",
        }


class GPTSoVITSAdapter(VoiceCloneAdapter):
    """
    GPT-SoVITS 适配器（预留）
    
    需求：
    - GPU: >= 8GB VRAM
    - 依赖: gpt-sovits, torch, transformers
    - 样本: 1 分钟有效语音
    
    部署命令（参考）：
    ```bash
    pip install gpt-sovits
    python -m gpt_sovits.train --samples_dir ./tent_memory/soul/voice_samples/{user_id}
    ```
    """
    
    def train(self, user_id: str, sample_dir: Path) -> Dict:
        return {
            "status": "not_ready",
            "message": "GPT-SoVITS 未安装。请执行：pip install gpt-sovits && 配置 GPU 环境",
            "user_id": user_id,
            "sample_dir": str(sample_dir),
        }
    
    def synthesize(self, text: str, speaker_embedding: SpeakerEmbedding,
                   emotion: str = "neutral", speed: float = 1.0) -> VoiceCloneResult:
        raise RuntimeError("GPT-SoVITS 未初始化。请先调用 train() 训练模型。")
    
    def get_readiness(self, sample_dir: Path) -> Dict:
        # 检查样本目录
        samples = list(sample_dir.glob("*.wav")) + list(sample_dir.glob("*.mp3")) + list(sample_dir.glob("*.webm"))
        total_duration = 0.0  # 需要 ffprobe 获取真实时长
        return {
            "status": "pending_gpu",
            "sample_count": len(samples),
            "message": f"已收集 {len(samples)} 个样本。GPT-SoVITS 需要 GPU 环境（>=8GB VRAM）",
        }


class F5TTSAdapter(VoiceCloneAdapter):
    """
    F5-TTS 适配器（预留）
    
    需求：
    - GPU: >= 6GB VRAM（也可 CPU，慢）
    - 依赖: f5-tts, torch
    - 样本: 3 秒即可，推荐 10 秒以上
    """
    
    def train(self, user_id: str, sample_dir: Path) -> Dict:
        return {
            "status": "not_ready",
            "message": "F5-TTS 未安装。请执行：pip install f5-tts",
            "user_id": user_id,
            "sample_dir": str(sample_dir),
        }
    
    def synthesize(self, text: str, speaker_embedding: SpeakerEmbedding,
                   emotion: str = "neutral", speed: float = 1.0) -> VoiceCloneResult:
        raise RuntimeError("F5-TTS 未初始化。请先调用 train() 训练模型。")
    
    def get_readiness(self, sample_dir: Path) -> Dict:
        samples = list(sample_dir.glob("*.wav")) + list(sample_dir.glob("*.mp3")) + list(sample_dir.glob("*.webm"))
        return {
            "status": "pending_gpu",
            "sample_count": len(samples),
            "message": f"已收集 {len(samples)} 个样本。F5-TTS 需要 GPU 环境（>=6GB VRAM）",
        }
