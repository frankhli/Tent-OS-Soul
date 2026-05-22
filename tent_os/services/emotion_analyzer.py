"""
EmotionEngine —— 基于 MediaPipe FaceLandmarker 52 Blendshapes 的情绪分析引擎

核心能力：
1. 实时情绪识别：7 种基础情绪（happy/sad/angry/surprised/fearful/disgusted/neutral）
2. 复合情绪推断：confused（困惑）、excited（兴奋）、sleepy（困倦）
3. 情绪时间线：滑动窗口平滑 + 突变检测
4. 疲劳度评估：眨眼频率 + 打哈欠检测

设计原则：
- 不依赖外部 API，纯本地计算（基于 FACS 编码规则）
- 竞争评分架构：所有情绪同时计算相对匹配度，不是硬阈值 if/else
- 输出连续值（0-1 置信度），不是硬分类
- 支持情绪时间线查询，用于观察用户情绪波动
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
import math


@dataclass
class EmotionResult:
    """单次情绪分析结果"""
    primary: str           # 主导情绪
    primary_score: float   # 主导情绪得分 0-1
    scores: Dict[str, float]  # 所有情绪得分
    confidence: float      # 整体置信度
    fatigue_level: float   # 疲劳度 0-1
    timestamp: float       # 时间戳（毫秒）


@dataclass
class EmotionTimelineEvent:
    """情绪时间线事件"""
    emotion: str
    score: float
    timestamp: float
    duration_ms: float


class EmotionTimeline:
    """情绪时间线：滑动窗口平滑 + 突变检测 + 滞后确认"""

    def __init__(self, window_size: int = 10, max_history: int = 300, required_confirmations: int = 3):
        self.window_size = window_size
        self.max_history = max_history
        self.required_confirmations = required_confirmations  # Layer 4: 新情绪需要连续确认次数
        self._buffer: deque[Tuple[str, float, float]] = deque(maxlen=max_history)
        self._current_emotion = "neutral"
        self._current_start_time: Optional[float] = None
        self._pending_emotion: Optional[str] = None  # 待确认的新情绪
        self._pending_count = 0  # 待确认计数

    def add(self, emotion: str, score: float, timestamp: float) -> Optional[EmotionTimelineEvent]:
        """
        添加一次情绪样本，返回情绪突变事件（如果有）
        Layer 4: 新情绪需要连续 required_confirmations 次确认才切换
        """
        self._buffer.append((emotion, score, timestamp))

        # 滑动窗口：取最近 window_size 个样本投票
        if len(self._buffer) < 3:
            return None

        recent = list(self._buffer)[-self.window_size:]
        votes: Dict[str, List[float]] = {}
        for e, s, _ in recent:
            votes.setdefault(e, []).append(s)

        # 加权投票（得分越高权重越大）
        best_emotion = max(votes.keys(), key=lambda e: sum(votes[e]) / len(votes[e]))
        best_score = sum(votes[best_emotion]) / len(votes[best_emotion])

        # Layer 4: 滞后确认逻辑
        if best_emotion == self._current_emotion:
            # 当前情绪维持 → 重置待确认
            self._pending_emotion = None
            self._pending_count = 0
            return None

        # 新情绪出现
        if best_emotion == self._pending_emotion:
            self._pending_count += 1
        else:
            self._pending_emotion = best_emotion
            self._pending_count = 1

        # 达到确认次数才切换
        if self._pending_count >= self.required_confirmations:
            event = None
            if self._current_start_time is not None:
                event = EmotionTimelineEvent(
                    emotion=self._current_emotion,
                    score=best_score,
                    timestamp=timestamp,
                    duration_ms=timestamp - self._current_start_time,
                )
            self._current_emotion = best_emotion
            self._current_start_time = timestamp
            self._pending_emotion = None
            self._pending_count = 0
            return event

        return None

    def get_dominant_emotion(self, window_seconds: float = 5.0) -> Tuple[str, float]:
        """获取最近 N 秒内的主导情绪"""
        if not self._buffer:
            return ("neutral", 0.5)

        now = self._buffer[-1][2]
        cutoff = now - window_seconds * 1000

        recent = [(e, s) for e, s, t in self._buffer if t >= cutoff]
        if not recent:
            return ("neutral", 0.5)

        votes: Dict[str, List[float]] = {}
        for e, s in recent:
            votes.setdefault(e, []).append(s)

        best = max(votes.keys(), key=lambda e: sum(votes[e]))
        return (best, sum(votes[best]) / len(votes[best]))

    def get_timeline(self, limit: int = 50) -> List[Dict]:
        """获取情绪时间线（用于前端展示）"""
        result = []
        for emotion, score, timestamp in list(self._buffer)[-limit:]:
            result.append({
                "emotion": emotion,
                "score": round(score, 2),
                "timestamp": timestamp,
                "time": datetime.fromtimestamp(timestamp / 1000).strftime("%H:%M:%S"),
            })
        return result


# ============================================================================
# 情绪特征签名（与前端 useVision.ts 保持同步）
# ============================================================================
# 每个情绪是一个特征签名：blendshape -> 权重（可正可负）
# 正权重 = 该 blendshape 激活支持此情绪
# 负权重 = 该 blendshape 激活抑制此情绪
# ============================================================================

EMOTION_SIGNATURES: List[Dict] = [
    {
        "name": "happy",
        "weights": {
            "mouthSmileLeft": 2.0, "mouthSmileRight": 2.0,
            "cheekPuff": 0.8,
            "jawOpen": 0.4,
            "eyeBlinkLeft": 0.2, "eyeBlinkRight": 0.2,
            "mouthFrownLeft": -1.0, "mouthFrownRight": -1.0,
            "browDownLeft": -0.5, "browDownRight": -0.5,
        },
    },
    {
        "name": "sad",
        "weights": {
            "mouthFrownLeft": 2.0, "mouthFrownRight": 2.0,
            "browInnerUp": 1.2,
            "browOuterUpLeft": 0.6, "browOuterUpRight": 0.6,
            "mouthPucker": 0.8,
            "mouthSmileLeft": -1.5, "mouthSmileRight": -1.5,
            "jawOpen": -0.3,
        },
    },
    {
        "name": "angry",
        "weights": {
            "browDownLeft": 2.0, "browDownRight": 2.0,
            "mouthFrownLeft": 1.5, "mouthFrownRight": 1.5,
            "noseSneerLeft": 1.0, "noseSneerRight": 1.0,
            "jawOpen": 0.3,
            "mouthSmileLeft": -1.5, "mouthSmileRight": -1.5,
            "browInnerUp": -0.5,
        },
    },
    {
        "name": "surprised",
        "weights": {
            "eyeWideLeft": 1.8, "eyeWideRight": 1.8,
            "browInnerUp": 1.2,
            "browOuterUpLeft": 0.8, "browOuterUpRight": 0.8,
            "jawOpen": 1.2,
            "mouthSmileLeft": -0.5, "mouthSmileRight": -0.5,
            "browDownLeft": -0.8, "browDownRight": -0.8,
        },
    },
    {
        "name": "fearful",
        "weights": {
            "eyeWideLeft": 1.8, "eyeWideRight": 1.8,
            "browInnerUp": 1.0,
            "browOuterUpLeft": 0.8, "browOuterUpRight": 0.8,
            "mouthStretchLeft": 0.8, "mouthStretchRight": 0.8,
            "jawOpen": -0.5,
            "mouthSmileLeft": -0.5, "mouthSmileRight": -0.5,
        },
    },
    {
        "name": "disgusted",
        "weights": {
            "noseSneerLeft": 2.0, "noseSneerRight": 2.0,
            "mouthFrownLeft": 1.2, "mouthFrownRight": 1.2,
            "browDownLeft": 0.6, "browDownRight": 0.6,
            "mouthSmileLeft": -1.0, "mouthSmileRight": -1.0,
            "jawOpen": -0.3,
        },
    },
]


# 收集所有与情绪签名相关的 blendshape 名称
_RELEVANT_BLENDSHAPES = set()
for sig in EMOTION_SIGNATURES:
    for bs in sig["weights"]:
        _RELEVANT_BLENDSHAPES.add(bs)


class EmotionAnalyzer:
    """
    情绪分析器 —— 基于 MediaPipe 52 Blendshapes 的竞争评分引擎

    核心改进（取代旧版的硬阈值 if/else 和简单加权平均）：
    1. 所有情绪同时计算匹配度（加权点积），不是 if/else 链
    2. 每个签名有正/负权重，支持"抑制"关系（如微笑抑制悲伤）
    3. 归一化使不同签名的得分可比
    4. 基于"区分度"和"信号能量"判断是否 neutral
    5. 自适应阈值：根据用户静止基线自动调整
    6. 时间线滞后确认：新情绪需连续确认才切换
    """

    # 基础情绪定义
    BASE_EMOTIONS = ["happy", "sad", "angry", "surprised", "fearful", "disgusted", "neutral"]

    # 复合情绪推断规则（基于竞争得分的阈值判断）
    COMPOSITE_RULES = [
        {
            "name": "confused",
            # 困惑 = 挑眉 + 皱眉 + 微张嘴（矛盾信号）
            "required_scores": {
                "surprised": 0.15,  # 有惊讶成分（挑眉）
                "angry": 0.10,      # 有愤怒成分（皱眉）
            },
            "modifier": 0.7,
        },
        {
            "name": "excited",
            # 兴奋 = 开心 + 惊讶
            "required_scores": {
                "happy": 0.20,
                "surprised": 0.10,
            },
            "modifier": 0.8,
        },
        {
            "name": "sleepy",
            # 困倦 = 眨眼频繁 + 嘴微张
            "blendshape_conditions": {
                "eyeBlinkLeft": (0.4, 1.0),
                "eyeBlinkRight": (0.4, 1.0),
                "jawOpen": (0.05, 0.4),
            },
            "modifier": 0.6,
        },
    ]

    # Layer 3: 自适应阈值参数
    BASELINE_SAMPLES = 10           # 校准期样本数（约 3 秒 @ 300ms）
    BASELINE_MULTIPLIER = 2.5       # 阈值 = 基线 × 乘数
    FIXED_SIGNAL_ENERGY_TH = 0.008  # 固定保底阈值
    FIXED_BEST_SCORE_TH = 0.05
    FIXED_MARGIN_TH = 0.05

    def __init__(self):
        self.timelines: Dict[str, EmotionTimeline] = {}  # user_id -> timeline
        # Layer 3: 用户基线校准数据
        self._baselines: Dict[str, Dict] = {}  # user_id -> {signal_energy, margin, samples}

    def get_timeline(self, user_id: str = "default") -> EmotionTimeline:
        if user_id not in self.timelines:
            self.timelines[user_id] = EmotionTimeline()
        return self.timelines[user_id]

    def _get_or_init_baseline(self, user_id: str) -> Dict:
        if user_id not in self._baselines:
            self._baselines[user_id] = {
                "signal_energy_samples": [],
                "margin_samples": [],
                "calibrated": False,
            }
        return self._baselines[user_id]

    def _update_baseline(self, user_id: str, signal_energy: float, margin: float):
        """Layer 3: 更新用户噪声基线（校准期）"""
        baseline = self._get_or_init_baseline(user_id)
        if baseline["calibrated"]:
            return

        baseline["signal_energy_samples"].append(signal_energy)
        baseline["margin_samples"].append(margin)

        if len(baseline["signal_energy_samples"]) >= self.BASELINE_SAMPLES:
            # 取前 N 个样本的中位数作为基线（排除离群值）
            se_sorted = sorted(baseline["signal_energy_samples"])
            margin_sorted = sorted(baseline["margin_samples"])
            mid = self.BASELINE_SAMPLES // 2
            baseline["signal_energy_base"] = se_sorted[mid]
            baseline["margin_base"] = margin_sorted[mid]
            baseline["calibrated"] = True

    def _get_adaptive_thresholds(self, user_id: str) -> Tuple[float, float, float]:
        """Layer 3: 获取自适应阈值（保底值 vs 基线值取较大）"""
        baseline = self._get_or_init_baseline(user_id)
        if not baseline.get("calibrated"):
            return (self.FIXED_SIGNAL_ENERGY_TH, self.FIXED_BEST_SCORE_TH, self.FIXED_MARGIN_TH)

        se_th = max(self.FIXED_SIGNAL_ENERGY_TH, baseline["signal_energy_base"] * self.BASELINE_MULTIPLIER)
        margin_th = max(self.FIXED_MARGIN_TH, baseline["margin_base"] * self.BASELINE_MULTIPLIER)
        return (se_th, self.FIXED_BEST_SCORE_TH, margin_th)

    def analyze(self, blendshapes: Dict[str, float], user_id: str = "default") -> EmotionResult:
        """
        分析 blendshapes，返回情绪结果（竞争评分架构）
        """
        s = blendshapes.get

        # 1. 计算每个情绪的匹配得分（加权点积 + 归一化）
        scores: Dict[str, float] = {}
        for sig in EMOTION_SIGNATURES:
            score = 0.0
            total_weight = 0.0
            for bs, w in sig["weights"].items():
                score += s(bs, 0) * w
                total_weight += abs(w)
            scores[sig["name"]] = score / total_weight if total_weight > 0 else 0

        # 2. 计算面部信号能量（Layer 3: 只用相关 blendshapes）
        relevant_values = [v for k, v in blendshapes.items() if k in _RELEVANT_BLENDSHAPES]
        signal_energy = sum(v * v for v in relevant_values) / len(relevant_values) if relevant_values else 0

        # 3. 找出最高分和次高分
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_emotion, best_score = sorted_scores[0] if sorted_scores else ("neutral", 0)
        second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0
        margin = best_score - second_score

        # Layer 3: 更新基线
        self._update_baseline(user_id, signal_energy, margin)
        se_th, best_score_th, margin_th = self._get_adaptive_thresholds(user_id)

        # 4. neutral 判定逻辑（使用自适应阈值）
        primary = best_emotion
        primary_score = best_score

        if signal_energy < se_th:
            # 面部信号能量低于阈值 → 视为无明显表情
            primary = "neutral"
            primary_score = 0.1
        elif best_score < best_score_th:
            # 有面部活动但没有匹配任何情绪签名
            primary = "neutral"
            primary_score = max(0.1, signal_energy * 2)
        elif margin < margin_th:
            # 情绪模糊（两个得分太接近）
            primary = "neutral"
            primary_score = max(0.15, 0.3 + margin * 5)

        scores["neutral"] = primary_score if primary == "neutral" else max(0, 0.1 - best_score)

        # 5. 检测复合情绪
        composites: Dict[str, float] = {}
        for rule in self.COMPOSITE_RULES:
            # 基于已有情绪得分的复合规则
            if "required_scores" in rule:
                match = True
                composite_score = 0.0
                for req_emotion, req_min in rule["required_scores"].items():
                    if scores.get(req_emotion, 0) < req_min:
                        match = False
                        break
                    composite_score += scores[req_emotion]
                if match:
                    composites[rule["name"]] = (composite_score / len(rule["required_scores"])) * rule["modifier"]

            # 基于 blendshape 条件的复合规则
            elif "blendshape_conditions" in rule:
                match_count = 0
                match_score = 0.0
                for bs, (min_val, max_val) in rule["blendshape_conditions"].items():
                    val = s(bs, 0)
                    if min_val <= val <= max_val:
                        match_count += 1
                        match_score += val
                if match_count >= len(rule["blendshape_conditions"]) * 0.6:
                    composites[rule["name"]] = (match_score / match_count) * rule["modifier"]

        scores.update(composites)

        # 6. 重新确认主导情绪（复合情绪可能得分更高）
        primary = max(scores, key=scores.get)
        primary_score = scores[primary]

        # 7. 计算置信度
        confidence = min(0.95, 0.4 + margin * 3 + signal_energy * 4)

        # 8. 疲劳度评估
        fatigue = self._calculate_fatigue(blendshapes)

        # 9. 更新时间线（Layer 4: 滞后确认）
        now = datetime.now().timestamp() * 1000
        timeline = self.get_timeline(user_id)
        event = timeline.add(primary, primary_score, now)

        # Layer 1+4: 返回时间线的平滑结果，而不是瞬时原始值
        smoothed_emotion = timeline._current_emotion

        result = EmotionResult(
            primary=smoothed_emotion,
            primary_score=round(primary_score, 3),
            scores={k: round(v, 3) for k, v in scores.items()},
            confidence=round(confidence, 3),
            fatigue_level=round(fatigue, 3),
            timestamp=now,
        )

        if event:
            result.scores["_event"] = {
                "previous_emotion": event.emotion,
                "duration_ms": round(event.duration_ms, 0),
            }

        return result

    def _calculate_fatigue(self, blendshapes: Dict[str, float]) -> float:
        """
        基于眨眼频率和打哈欠程度计算疲劳度
        """
        blink = (blendshapes.get("eyeBlinkLeft", 0) + blendshapes.get("eyeBlinkRight", 0)) / 2
        yawn = blendshapes.get("jawOpen", 0) * 0.5 + blendshapes.get("mouthStretchLeft", 0) * 0.25 + blendshapes.get("mouthStretchRight", 0) * 0.25

        # 高眨眼 + 打哈欠 = 疲劳
        fatigue = blink * 0.4 + yawn * 0.6
        return min(1.0, fatigue)

    def get_summary(self, user_id: str = "default") -> Dict:
        """获取用户情绪摘要（用于前端展示）"""
        timeline = self.get_timeline(user_id)
        dominant, score = timeline.get_dominant_emotion(window_seconds=10)
        history = timeline.get_timeline(limit=20)

        return {
            "dominant_emotion": dominant,
            "dominant_score": round(score, 2),
            "recent_history": history,
            "sample_count": len(timeline._buffer),
        }


# 全局单例
_analyzer: Optional[EmotionAnalyzer] = None

def get_analyzer() -> EmotionAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = EmotionAnalyzer()
    return _analyzer
