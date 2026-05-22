"""情绪检测器 —— 从对话文本中提取情绪强度

简单规则 + LLM 增强的混合方案：
- 快速路径：基于表情符号和关键词的情绪检测（<1ms）
- 深度路径：LLM 分析情绪强度和类型（有成本）

情绪类型：
    joy, anger, sadness, fear, surprise, disgust, neutral
    
强度：0-1 浮点数
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("tent_os.memory.emotion")


@dataclass
class EmotionState:
    """情绪状态"""
    primary: str           # 主要情绪类型
    intensity: float       # 强度 0-1
    valence: float         # 效价（正负面）-1 到 +1
    arousal: float         # 唤醒度（活跃度）0-1
    confidence: float      # 检测置信度


# 情绪表情符号映射
EMOJI_MAP = {
    # 正面
    "😀": ("joy", 0.6), "😃": ("joy", 0.7), "😄": ("joy", 0.7), "😁": ("joy", 0.8),
    "😊": ("joy", 0.6), "🙂": ("joy", 0.4), "😉": ("joy", 0.5), "😌": ("joy", 0.5),
    "😍": ("joy", 0.9), "🥰": ("joy", 0.9), "😘": ("joy", 0.8), "😗": ("joy", 0.6),
    "🤩": ("joy", 0.9), "🥳": ("joy", 0.9), "😎": ("joy", 0.6),
    "👍": ("joy", 0.5), "🎉": ("joy", 0.8), "❤️": ("joy", 0.9), "💖": ("joy", 0.9),
    "😂": ("joy", 0.8), "🤣": ("joy", 0.9), "😅": ("joy", 0.4),
    "🙏": ("joy", 0.4), "✨": ("joy", 0.5), "🔥": ("joy", 0.7),
    "💪": ("joy", 0.6), "🌟": ("joy", 0.7), "⭐": ("joy", 0.5),
    # 负面
    "😢": ("sadness", 0.7), "😭": ("sadness", 0.9), "😞": ("sadness", 0.6),
    "😔": ("sadness", 0.6), "😟": ("sadness", 0.5), "😕": ("sadness", 0.4),
    "☹️": ("sadness", 0.6), "🙁": ("sadness", 0.5),
    "😠": ("anger", 0.7), "😡": ("anger", 0.9), "🤬": ("anger", 1.0),
    "👎": ("anger", 0.5), "💔": ("sadness", 0.8),
    "😨": ("fear", 0.7), "😰": ("fear", 0.8), "😥": ("fear", 0.6),
    "😱": ("fear", 0.9), "😬": ("fear", 0.5), "🤯": ("surprise", 0.9),
    "😳": ("surprise", 0.7), "😲": ("surprise", 0.7), "😮": ("surprise", 0.6),
    "🤢": ("disgust", 0.8), "🤮": ("disgust", 0.9), "🤧": ("disgust", 0.4),
    # 中性
    "😐": ("neutral", 0.5), "😑": ("neutral", 0.4), "🤔": ("neutral", 0.4),
    "🙄": ("neutral", 0.3), "😴": ("neutral", 0.2),
}

# 情绪关键词映射
KEYWORD_MAP = {
    # 正面
    "joy": ["开心", "高兴", "快乐", "兴奋", "棒", "赞", "好", "喜欢", "爱", "感谢", "谢谢",
            "great", "good", "excellent", "awesome", "love", "like", "happy", "glad", "thanks", "perfect"],
    "anger": ["生气", "愤怒", "讨厌", "烦", "差", "烂", "失望", "不满", "垃圾",
              "angry", "mad", "hate", "terrible", "awful", "bad", "worst", "annoying", "frustrated"],
    "sadness": ["难过", "伤心", "失望", "遗憾", "沮丧", "痛苦",
                "sad", "disappointed", "sorry", "upset", "depressed", "regret"],
    "fear": ["害怕", "担心", "焦虑", "紧张", "恐惧",
             "afraid", "worried", "anxious", "nervous", "scared", "concerned"],
    "surprise": ["惊讶", "震惊", "意外", "居然",
                 "surprised", "shocked", "amazed", "unexpected", "wow", "omg"],
    "disgust": ["恶心", "厌恶", "反感", "受不了",
                "disgusting", "gross", "sick", "hate"],
}

# 否定词（翻转情绪）
NEGATION_WORDS = ["不", "没", "无", "别", "not", "no", "never", "don't", "doesn't", "didn't", "wasn't", "weren't"]

# 强度修饰词
INTENSIFIERS = {
    "非常": 1.5, "特别": 1.4, "超级": 1.6, "极其": 1.7, "太": 1.3,
    "very": 1.5, "really": 1.4, "extremely": 1.7, "super": 1.5, "so": 1.3,
    "totally": 1.4, "absolutely": 1.5, "incredibly": 1.6,
}

# 弱化词
DIMINISHERS = {
    "有点": 0.6, "稍微": 0.5, "略微": 0.4, "一般": 0.5,
    "a bit": 0.6, "slightly": 0.5, "somewhat": 0.6, "kind of": 0.5, "little": 0.5,
}


class EmotionDetector:
    """情绪检测器"""
    
    def __init__(self, llm=None):
        self.llm = llm
    
    def detect_fast(self, text: str) -> EmotionState:
        """快速情绪检测（基于规则，<1ms）"""
        text_lower = text.lower()
        
        # 1. 检测表情符号
        emoji_scores: Dict[str, float] = {}
        for emoji, (emotion, intensity) in EMOJI_MAP.items():
            count = text.count(emoji)
            if count > 0:
                emoji_scores[emotion] = max(emoji_scores.get(emotion, 0), intensity * min(count, 3) / 3)
        
        # 2. 检测关键词
        keyword_scores: Dict[str, float] = {}
        for emotion, keywords in KEYWORD_MAP.items():
            for kw in keywords:
                # 检查否定
                for neg in NEGATION_WORDS:
                    if neg + kw in text or neg + " " + kw in text_lower:
                        # 否定情绪 → 翻转
                        keyword_scores[emotion] = max(keyword_scores.get(emotion, 0), -0.3)
                        break
                else:
                    # 非否定，正常计分
                    if kw in text or kw in text_lower:
                        base_score = 0.4
                        # 检查强度修饰
                        for intens, mult in INTENSIFIERS.items():
                            if intens in text or intens in text_lower:
                                base_score *= mult
                                break
                        # 检查弱化
                        for dim, mult in DIMINISHERS.items():
                            if dim in text or dim in text_lower:
                                base_score *= mult
                                break
                        keyword_scores[emotion] = max(keyword_scores.get(emotion, 0), min(base_score, 1.0))
        
        # 3. 合并分数
        combined = {}
        all_emotions = set(emoji_scores.keys()) | set(keyword_scores.keys())
        for emotion in all_emotions:
            e_score = emoji_scores.get(emotion, 0)
            k_score = keyword_scores.get(emotion, 0)
            # 表情符号权重更高（用户主动表达）
            combined[emotion] = e_score * 1.2 + k_score
        
        if not combined:
            return EmotionState(
                primary="neutral", intensity=0.0, valence=0.0,
                arousal=0.3, confidence=0.5
            )
        
        # 找出主要情绪
        primary = max(combined, key=combined.get)
        intensity = min(abs(combined[primary]), 1.0)
        
        # 计算效价（正负面）
        positive = combined.get("joy", 0)
        negative = sum(combined.get(e, 0) for e in ["anger", "sadness", "fear", "disgust"])
        valence = max(-1.0, min(1.0, (positive - negative) / max(positive + negative, 0.1)))
        
        # 计算唤醒度
        arousal = min(1.0, intensity * 0.8 + (0.3 if "surprise" in combined else 0))
        
        # 置信度
        confidence = min(1.0, 0.3 + intensity * 0.5 + (0.2 if emoji_scores else 0))
        
        return EmotionState(
            primary=primary, intensity=intensity, valence=valence,
            arousal=arousal, confidence=confidence
        )
    
    async def detect_deep(self, text: str) -> EmotionState:
        """深度情绪检测（LLM 增强）
        
        如果配置了 LLM，使用 LLM 进行更精确的情绪分析。
        否则回退到快速检测。
        """
        if not self.llm:
            return self.detect_fast(text)
        
        fast_result = self.detect_fast(text)
        
        # 如果快速检测置信度已经很高，跳过 LLM
        if fast_result.confidence >= 0.8:
            return fast_result
        
        try:
            prompt = f"""分析以下文本的情绪状态。请只输出 JSON：

文本：{text[:500]}

输出格式：
{{"primary": "joy|anger|sadness|fear|surprise|disgust|neutral", "intensity": 0.0-1.0, "valence": -1.0到1.0, "arousal": 0.0-1.0}}"""
            
            response = await self.llm.complete(prompt)
            
            # 解析 JSON
            import json
            data = json.loads(response.strip())
            
            return EmotionState(
                primary=data.get("primary", fast_result.primary),
                intensity=max(0.0, min(1.0, data.get("intensity", fast_result.intensity))),
                valence=max(-1.0, min(1.0, data.get("valence", fast_result.valence))),
                arousal=max(0.0, min(1.0, data.get("arousal", fast_result.arousal))),
                confidence=0.85
            )
        except Exception as e:
            logger.debug(f"LLM 情绪检测失败，回退到快速检测: {e}")
            return fast_result
    
    def detect_conversation_emotion(self, messages: list) -> EmotionState:
        """检测整个对话的情绪状态（综合最后几条消息）"""
        # 取最后 3 条用户消息
        user_texts = []
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_texts.append(msg.get("content", ""))
            if len(user_texts) >= 3:
                break
        
        if not user_texts:
            return EmotionState("neutral", 0.0, 0.0, 0.3, 0.5)
        
        # 综合检测
        combined_text = " ".join(user_texts)
        return self.detect_fast(combined_text)
