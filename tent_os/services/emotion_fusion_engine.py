"""
多模态情绪融合引擎 —— 将文本、视觉、语音情绪融合为统一的情绪状态

核心设计：
1. 短期融合：当前消息的 3 模态加权融合
2. 中期融合：本轮对话的情绪趋势曲线
3. 长期融合：用户独特的情绪表达模式
4. 真实性检测：文本 vs 非文本模态的差异度
"""

import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class EmotionSignal:
    """单模态情绪信号"""
    emotion: str
    intensity: float
    valence: float
    arousal: float
    confidence: float
    source: str  # "text" / "vision" / "voice"
    timestamp: float = field(default_factory=time.time)
    raw_features: Dict = field(default_factory=dict)


@dataclass
class MultimodalEmotionState:
    """融合后的多模态情绪状态"""
    primary: str
    intensity: float
    valence: float
    arousal: float
    confidence: float
    mixed: Dict[str, float]  # 混合情绪 {emotion: score}
    trend: str  # "escalating" | "de-escalating" | "stable"
    authenticity: float  # 0-1, 越高越真实
    sources: Dict[str, Dict]  # 各模态原始数据快照
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""


# 情绪 → valence/arousal 映射（Russell 环状模型）
EMOTION_VA = {
    "joy": {"valence": 0.8, "arousal": 0.6},
    "happy": {"valence": 0.7, "arousal": 0.5},
    "excited": {"valence": 0.8, "arousal": 0.9},
    "anger": {"valence": -0.7, "arousal": 0.8},
    "angry": {"valence": -0.7, "arousal": 0.8},
    "sadness": {"valence": -0.7, "arousal": 0.2},
    "sad": {"valence": -0.6, "arousal": 0.2},
    "fear": {"valence": -0.7, "arousal": 0.7},
    "fearful": {"valence": -0.7, "arousal": 0.7},
    "surprise": {"valence": 0.3, "arousal": 0.8},
    "surprised": {"valence": 0.3, "arousal": 0.8},
    "disgust": {"valence": -0.6, "arousal": 0.4},
    "disgusted": {"valence": -0.6, "arousal": 0.4},
    "neutral": {"valence": 0.0, "arousal": 0.3},
    "calm": {"valence": 0.3, "arousal": 0.1},
    "confused": {"valence": -0.2, "arousal": 0.5},
    "frustrated": {"valence": -0.5, "arousal": 0.6},
    "tired": {"valence": -0.3, "arousal": 0.1},
    "sleepy": {"valence": -0.2, "arousal": 0.05},
    "proud": {"valence": 0.7, "arousal": 0.5},
    "thinking": {"valence": 0.0, "arousal": 0.4},
    "listening": {"valence": 0.1, "arousal": 0.2},
}

# 模态权重（可根据用户历史调优）
DEFAULT_WEIGHTS = {
    "text": 0.40,
    "vision": 0.35,
    "voice": 0.25,
}


class EmotionFusionEngine:
    """多模态情绪融合引擎"""

    def __init__(self):
        # 每用户的中期情绪缓冲区（本轮对话）
        self._session_buffers: Dict[str, deque] = {}  # user_id -> deque of (valence, arousal, timestamp)
        # 每用户的长期情绪画像
        self._user_baselines: Dict[str, Dict] = {}  # user_id -> {"typical_valence", "typical_arousal", "expression_patterns"}
        # 每用户的模态权重（可学习）
        self._user_weights: Dict[str, Dict] = {}

    def fuse(
        self,
        user_id: str,
        text_signal: Optional[EmotionSignal] = None,
        vision_signal: Optional[EmotionSignal] = None,
        voice_signal: Optional[EmotionSignal] = None,
        session_id: str = "",
    ) -> MultimodalEmotionState:
        """
        融合多模态情绪信号

        Returns:
            MultimodalEmotionState: 融合后的情绪状态
        """
        signals = []
        if text_signal:
            signals.append(text_signal)
        if vision_signal:
            signals.append(vision_signal)
        if voice_signal:
            signals.append(voice_signal)

        if not signals:
            return MultimodalEmotionState(
                primary="neutral",
                intensity=0.0,
                valence=0.0,
                arousal=0.3,
                confidence=0.0,
                mixed={},
                trend="stable",
                authenticity=0.5,
                sources={},
                session_id=session_id,
            )

        # 1. 短期融合：加权平均
        weights = self._get_weights(user_id)
        fused_va = self._fuse_valence_arousal(signals, weights)
        fused_intensity = self._fuse_intensity(signals, weights)
        fused_confidence = self._fuse_confidence(signals, weights)

        # 2. 识别混合情绪
        mixed = self._detect_mixed_emotions(signals)

        # 3. 检测真实性（authenticity）
        authenticity = self._detect_authenticity(signals, weights)

        # 4. 从 VA 空间映射回主要情绪标签
        primary = self._va_to_emotion(fused_va["valence"], fused_va["arousal"])

        # 5. 中期融合：情绪趋势
        trend = self._detect_trend(user_id, fused_va["valence"])

        # 6. 长期融合：用户基线调整
        adjusted = self._apply_user_baseline(user_id, fused_va)

        # 记录到会话缓冲区
        self._record_session(user_id, adjusted["valence"], adjusted["arousal"])

        sources = {}
        for sig in signals:
            sources[sig.source] = {
                "emotion": sig.emotion,
                "intensity": sig.intensity,
                "confidence": sig.confidence,
            }

        return MultimodalEmotionState(
            primary=primary,
            intensity=fused_intensity,
            valence=adjusted["valence"],
            arousal=adjusted["arousal"],
            confidence=fused_confidence,
            mixed=mixed,
            trend=trend,
            authenticity=authenticity,
            sources=sources,
            session_id=session_id,
        )

    def _get_weights(self, user_id: str) -> Dict[str, float]:
        """获取用户个性化的模态权重"""
        return self._user_weights.get(user_id, DEFAULT_WEIGHTS.copy())

    def _fuse_valence_arousal(self, signals: List[EmotionSignal], weights: Dict[str, float]) -> Dict[str, float]:
        """融合 valence 和 arousal（加权平均）"""
        total_weight = 0.0
        valence_sum = 0.0
        arousal_sum = 0.0

        for sig in signals:
            w = weights.get(sig.source, 0.33) * sig.confidence
            va = EMOTION_VA.get(sig.emotion, {"valence": 0.0, "arousal": 0.3})
            valence_sum += va["valence"] * sig.intensity * w
            arousal_sum += va["arousal"] * sig.intensity * w
            total_weight += w

        if total_weight == 0:
            return {"valence": 0.0, "arousal": 0.3}

        return {
            "valence": max(-1.0, min(1.0, valence_sum / total_weight)),
            "arousal": max(0.0, min(1.0, arousal_sum / total_weight)),
        }

    def _fuse_intensity(self, signals: List[EmotionSignal], weights: Dict[str, float]) -> float:
        """融合情绪强度"""
        total_weight = 0.0
        intensity_sum = 0.0
        for sig in signals:
            w = weights.get(sig.source, 0.33) * sig.confidence
            intensity_sum += sig.intensity * w
            total_weight += w
        return intensity_sum / total_weight if total_weight > 0 else 0.0

    def _fuse_confidence(self, signals: List[EmotionSignal], weights: Dict[str, float]) -> float:
        """融合置信度（加权平均）"""
        total_weight = 0.0
        conf_sum = 0.0
        for sig in signals:
            w = weights.get(sig.source, 0.33)
            conf_sum += sig.confidence * w
            total_weight += w
        return conf_sum / total_weight if total_weight > 0 else 0.0

    def _detect_mixed_emotions(self, signals: List[EmotionSignal]) -> Dict[str, float]:
        """
        识别混合情绪：保留所有模态中置信度 > 0.3 的情绪
        如果不同模态检测到不同情绪，说明用户有复杂/矛盾情绪
        """
        mixed = {}
        for sig in signals:
            if sig.confidence > 0.3 and sig.intensity > 0.3:
                # 统一情绪名称（如 happy/joy 映射到 joy）
                normalized = self._normalize_emotion_name(sig.emotion)
                existing = mixed.get(normalized, 0.0)
                mixed[normalized] = max(existing, sig.confidence * sig.intensity)
        return mixed

    def _normalize_emotion_name(self, emotion: str) -> str:
        """统一情绪名称"""
        mapping = {
            "happy": "joy",
            "angry": "anger",
            "sad": "sadness",
            "fearful": "fear",
            "surprised": "surprise",
            "disgusted": "disgust",
        }
        return mapping.get(emotion, emotion)

    def _detect_authenticity(self, signals: List[EmotionSignal], weights: Dict[str, float]) -> float:
        """
        检测情绪表达的真实性（authenticity）
        
        原理：文本情绪（可被意识控制）与非文本情绪（更难伪装）的差异
        - 差异大 → 可能在强撑（authenticity 低）
        - 差异小 → 真实表达（authenticity 高）
        
        Returns: 0-1，1=完全真实
        """
        text_sig = next((s for s in signals if s.source == "text"), None)
        non_text = [s for s in signals if s.source != "text"]

        if not text_sig or not non_text:
            # 只有单一模态，无法判断真实性，返回中等值
            return 0.7

        # 计算文本与非文本在 valence 上的差异
        text_va = EMOTION_VA.get(text_sig.emotion, {"valence": 0.0})
        text_valence = text_va["valence"] * text_sig.intensity

        non_text_valences = []
        for sig in non_text:
            va = EMOTION_VA.get(sig.emotion, {"valence": 0.0})
            non_text_valences.append(va["valence"] * sig.intensity)

        avg_non_text_valence = sum(non_text_valences) / len(non_text_valences)
        valence_diff = abs(text_valence - avg_non_text_valence)

        # 差异越大，authenticity 越低
        # diff=0 → authenticity=1.0, diff=2.0 → authenticity=0.0
        authenticity = max(0.0, 1.0 - valence_diff * 0.8)

        # 额外调整：如果文本是 positive 但非文本是 negative，authenticity 更低
        if text_valence > 0.2 and avg_non_text_valence < -0.2:
            authenticity *= 0.6

        return round(authenticity, 2)

    def _va_to_emotion(self, valence: float, arousal: float) -> str:
        """从 VA 空间映射回情绪标签"""
        best_match = "neutral"
        best_score = -float("inf")

        for emotion, va in EMOTION_VA.items():
            # 计算欧氏距离（在 VA 空间中）
            dv = valence - va["valence"]
            da = arousal - va["arousal"]
            score = -(dv * dv + da * da)
            if score > best_score:
                best_score = score
                best_match = emotion

        return best_match

    def _detect_trend(self, user_id: str, current_valence: float) -> str:
        """检测情绪趋势（基于最近 10 个数据点）"""
        buf = self._session_buffers.get(user_id)
        if not buf or len(buf) < 5:
            return "stable"

        recent = list(buf)[-10:]
        # 线性回归计算 valence 变化斜率
        n = len(recent)
        sum_x = sum(i for i in range(n))
        sum_y = sum(v for v, _, _ in recent)
        sum_xy = sum(i * v for i, (v, _, _) in enumerate(recent))
        sum_x2 = sum(i * i for i in range(n))

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return "stable"

        slope = (n * sum_xy - sum_x * sum_y) / denominator

        # 斜率阈值
        if slope > 0.08:
            return "escalating"
        elif slope < -0.08:
            return "de-escalating"
        return "stable"

    def _apply_user_baseline(self, user_id: str, fused_va: Dict[str, float]) -> Dict[str, float]:
        """应用用户长期基线调整"""
        baseline = self._user_baselines.get(user_id)
        if not baseline:
            return fused_va

        # 如果用户通常比较 positive，小的 negative 会被放大感知
        typical_valence = baseline.get("typical_valence", 0.0)
        delta = fused_va["valence"] - typical_valence

        # 偏离基线时，偏离方向的情绪会被强化
        adjusted_valence = fused_va["valence"] + delta * 0.1
        return {
            "valence": max(-1.0, min(1.0, adjusted_valence)),
            "arousal": fused_va["arousal"],
        }

    def _record_session(self, user_id: str, valence: float, arousal: float):
        """记录到会话缓冲区"""
        if user_id not in self._session_buffers:
            self._session_buffers[user_id] = deque(maxlen=100)
        self._session_buffers[user_id].append((valence, arousal, time.time()))

    def update_user_baseline(self, user_id: str, valence: float, arousal: float):
        """更新用户长期基线（每次融合后调用）"""
        if user_id not in self._user_baselines:
            self._user_baselines[user_id] = {
                "typical_valence": valence,
                "typical_arousal": arousal,
                "sample_count": 1,
            }
        else:
            b = self._user_baselines[user_id]
            n = b["sample_count"]
            b["typical_valence"] = (b["typical_valence"] * n + valence) / (n + 1)
            b["typical_arousal"] = (b["typical_arousal"] * n + arousal) / (n + 1)
            b["sample_count"] = n + 1

    def get_session_trend_data(self, user_id: str) -> List[Dict]:
        """获取会话情绪趋势数据（用于前端心电图）"""
        buf = self._session_buffers.get(user_id)
        if not buf:
            return []
        return [
            {"valence": v, "arousal": a, "timestamp": t}
            for v, a, t in buf
        ]

    def reset_session(self, user_id: str):
        """重置用户会话缓冲区（新对话开始时调用）"""
        self._session_buffers.pop(user_id, None)


# 全局单例
_fusion_engine: Optional[EmotionFusionEngine] = None


def get_fusion_engine() -> EmotionFusionEngine:
    global _fusion_engine
    if _fusion_engine is None:
        _fusion_engine = EmotionFusionEngine()
    return _fusion_engine
