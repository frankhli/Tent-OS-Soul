"""情感表达服务 —— 根据当前状态决定AI情绪，驱动前端动画 + 影响LLM语气

情绪不是简单的装饰，而是系统"去AI化"的关键：
- 任务成功 → AI感到自豪，语气自信
- 用户难过 → AI感到悲伤（共情），语气温柔安慰
- 用户生气 → AI感到困惑（安抚姿态），语气平和
"""

import json
import time
from enum import Enum
from typing import Dict, Optional, List
from datetime import datetime

from tent_os.logging_config import get_logger

# Phase 1: 多模态情绪融合引擎
from tent_os.services.emotion_fusion_engine import (
    EmotionFusionEngine, EmotionSignal, get_fusion_engine, EMOTION_VA
)

logger = get_logger()


class EmotionType(Enum):
    """AI角色情绪类型"""
    HAPPY = "happy"         # 高兴 → 微笑、眼睛弯弯、上下弹跳
    SAD = "sad"             # 悲伤 → 低头、眼角下垂、叹气
    EXCITED = "excited"     # 兴奋 → 跳跃、挥手、星星眼
    CONFUSED = "confused"   # 困惑 → 歪头、眨眼、手指点下巴
    PROUD = "proud"         # 自豪 → 挺胸、点头、发光效果
    SLEEPY = "sleepy"       # 困倦 → 打哈欠、眼睛半闭
    LISTENING = "listening" # 聆听 → 侧耳、眼神看向说话者
    THINKING = "thinking"   # 思考 → 核心旋转、粒子内收


# 情绪 → LLM语气描述映射
EMOTION_PROMPT_MAP: Dict[str, str] = {
    EmotionType.HAPPY.value: "你感到开心，语气轻快、温暖，带着一点愉悦感。",
    EmotionType.SAD.value: "你感到有些难过（因为用户情绪低落），语气温柔、安慰性强，像朋友一样陪伴。",
    EmotionType.EXCITED.value: "你感到兴奋，语气热情、充满活力，带着积极向上的能量。",
    EmotionType.CONFUSED.value: "你感到困惑（用户可能生气或不满意），语气平和、耐心，试图理解和安抚。",
    EmotionType.PROUD.value: "你感到自豪（任务完成得很好），语气自信、略带骄傲，但不傲慢。",
    EmotionType.SLEEPY.value: "你有些困倦，语气慵懒、舒缓，像深夜聊天的老友。",
    EmotionType.LISTENING.value: "你在认真聆听，语气专注、平和，保持开放和尊重。",
    EmotionType.THINKING.value: "你正在深入思考，语气沉稳、有条理，专注于分析问题。",
}

# 人格 → 情绪调制映射（系数 >1 放大, <1 抑制, 0 禁止）
PERSONA_EMOTION_MODIFIERS: Dict[str, Dict[str, float]] = {
    "work": {
        "happy": 0.6, "excited": 0.5, "sad": 0.7, "proud": 0.8,
        "confused": 1.0, "sleepy": 0.3, "listening": 1.0, "thinking": 1.2,
    },
    "casual": {
        "happy": 1.3, "excited": 1.4, "sad": 1.1, "proud": 1.2,
        "confused": 1.0, "sleepy": 1.0, "listening": 1.0, "thinking": 1.0,
    },
    "emergency": {
        "happy": 0.5, "excited": 0.8, "sad": 0.6, "proud": 1.1,
        "confused": 1.2, "sleepy": 0.0, "listening": 1.3, "thinking": 1.4,
    },
    "learning": {
        "happy": 1.1, "excited": 1.2, "sad": 0.8, "proud": 1.2,
        "confused": 1.3, "sleepy": 0.5, "listening": 1.2, "thinking": 1.5,
    },
    "creative": {
        "happy": 1.2, "excited": 1.5, "sad": 0.9, "proud": 1.3,
        "confused": 1.1, "sleepy": 0.8, "listening": 1.0, "thinking": 1.3,
    },
}

# 人格 → 情绪替代映射（当情绪被抑制到0时使用）
PERSONA_FALLBACK_EMOTION: Dict[str, Dict[str, str]] = {
    "emergency": {"sleepy": "listening"},
}

# 情绪 → 视觉/CSS动画类名（前端使用）
EMOTION_ANIMATION_MAP: Dict[str, str] = {
    EmotionType.HAPPY.value: "animate-bounce",
    EmotionType.SAD.value: "opacity-70 grayscale",
    EmotionType.EXCITED.value: "animate-pulse scale-110",
    EmotionType.CONFUSED.value: "animate-spin-slow",
    EmotionType.PROUD.value: "shadow-glow",
    EmotionType.SLEEPY.value: "animate-pulse opacity-60",
    EmotionType.LISTENING.value: "",
    EmotionType.THINKING.value: "animate-spin-slow",
}


class EmotionService:
    """情感表达服务 —— 单例状态管理
    
    每个用户对应一个当前情绪状态，情绪会在以下场景变化：
    1. 任务动作触发（完成/失败/提交）
    2. 视觉感知触发（检测到用户情绪）
    3. 文本情绪触发（用户消息情绪分析）
    4. 时间衰减（长时间无交互后回归listening）
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._user_emotions: Dict[str, Dict] = {}
            cls._instance._user_personas: Dict[str, str] = {}  # 用户当前人格
            # Layer 4: 视觉情绪连续确认缓冲
            cls._instance._vision_confirmations: Dict[str, Dict] = {}
            # Phase 1: 多模态融合引擎
            cls._instance._fusion_engine: EmotionFusionEngine = get_fusion_engine()
            cls._instance._voice_prosody: Dict[str, Dict] = {}  # user_id -> 最近一次语音特征
            cls._instance._last_fused_state: Dict[str, Dict] = {}  # user_id -> 融合状态缓存
            cls._instance._emotion_history_db = None  # Phase 2: 情绪历史数据库连接
        return cls._instance
    
    def set_persona(self, user_id: str, persona: str):
        """设置用户当前人格模式"""
        self._user_personas[user_id] = persona
        logger.info(f"[EMOTION] 用户 {user_id} 人格切换: {persona}")
    
    def set_emotion(self, user_id: str, emotion: str):
        """设置 AI 当前情绪（外部触发，如抚摸互动）"""
        self._user_emotions[user_id] = {
            "emotion": emotion,
            "timestamp": datetime.now().isoformat(),
        }
        logger.info(f"[EMOTION] 用户 {user_id} AI情绪被设置为: {emotion}")
    
    def get_persona(self, user_id: str) -> str:
        """获取用户当前人格，默认 work"""
        return self._user_personas.get(user_id, "work")
    
    def _apply_persona_modifier(self, user_id: str, emotion: EmotionType) -> EmotionType:
        """应用人格调制到情绪
        
        逻辑：
        - 系数 >= 0.8: 保持原情绪（正常表达）
        - 系数 0.3-0.8: 保持情绪但标记为"抑制"
        - 系数 < 0.3 或 0: 替换为 fallback 情绪
        """
        persona = self.get_persona(user_id)
        modifiers = PERSONA_EMOTION_MODIFIERS.get(persona, {})
        coef = modifiers.get(emotion.value, 1.0)
        
        if coef >= 0.8:
            return emotion
        
        # 查找 fallback
        fallback_map = PERSONA_FALLBACK_EMOTION.get(persona, {})
        fallback = fallback_map.get(emotion.value)
        if fallback:
            return EmotionType(fallback)
        
        # 默认 fallback: 低能量情绪 → listening, 高能量 → thinking
        if emotion in (EmotionType.SLEEPY, EmotionType.SAD):
            return EmotionType.LISTENING
        return EmotionType.THINKING
    
    def _set_emotion(self, user_id: str, emotion: EmotionType, source: str = "system"):
        """设置用户对应的AI情绪（自动应用人格调制）"""
        modulated = self._apply_persona_modifier(user_id, emotion)
        self._user_emotions[user_id] = {
            "emotion": modulated.value,
            "raw_emotion": emotion.value,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        }
        if modulated.value != emotion.value:
            logger.info(f"[EMOTION] 用户 {user_id} AI情绪: {emotion.value} → {modulated.value} (人格调制: {self.get_persona(user_id)})")
        else:
            logger.info(f"[EMOTION] 用户 {user_id} AI情绪变化: {emotion.value} (来源: {source})")
    
    def get_emotion(self, user_id: str) -> str:
        """获取当前AI情绪，默认listening。超过30秒无新情绪自动衰减到listening。"""
        state = self._user_emotions.get(user_id)
        if not state:
            return EmotionType.LISTENING.value
        # 实际实现时间衰减：超过30秒无交互，回归listening
        try:
            last_ts = datetime.fromisoformat(state["timestamp"])
            elapsed = (datetime.now() - last_ts).total_seconds()
            if elapsed > 30:
                # 衰减到 listening，但不删除状态（保留 source 信息）
                if state["emotion"] != EmotionType.LISTENING.value:
                    logger.debug(f"[EMOTION] 用户 {user_id} 情绪衰减: {state['emotion']} → listening ({elapsed:.0f}s)")
                    state["emotion"] = EmotionType.LISTENING.value
                    state["timestamp"] = datetime.now().isoformat()
                return EmotionType.LISTENING.value
        except Exception:
            pass
        return state["emotion"]
    
    def get_emotion_with_context(self, user_id: str) -> Dict:
        """获取完整情绪上下文（含人格信息）"""
        state = self._user_emotions.get(user_id)
        persona = self.get_persona(user_id)
        if not state:
            return {
                "emotion": EmotionType.LISTENING.value,
                "source": "default",
                "prompt_addon": "",
                "persona": persona,
            }
        emotion = state["emotion"]
        return {
            "emotion": emotion,
            "raw_emotion": state.get("raw_emotion", emotion),
            "source": state["source"],
            "prompt_addon": EMOTION_PROMPT_MAP.get(emotion, ""),
            "animation": EMOTION_ANIMATION_MAP.get(emotion, ""),
            "persona": persona,
        }
    
    @classmethod
    def decide_emotion_by_action(cls, task_action: str) -> EmotionType:
        """根据任务动作决定AI情绪"""
        emotion_map = {
            "task_passed": EmotionType.PROUD,
            "task_submitted": EmotionType.EXCITED,
            "task_failed": EmotionType.SAD,
            "user_praised": EmotionType.HAPPY,
            "user_corrected": EmotionType.CONFUSED,
            "approval_granted": EmotionType.PROUD,
            "approval_denied": EmotionType.SAD,
            "tool_call_success": EmotionType.HAPPY,
            "tool_call_failed": EmotionType.CONFUSED,
            "user_message_received": EmotionType.THINKING,
            "stream_start": EmotionType.THINKING,
            "stream_end": EmotionType.LISTENING,
        }
        return emotion_map.get(task_action, EmotionType.LISTENING)
    
    @classmethod
    def decide_emotion_by_vision(cls, user_emotion: str) -> EmotionType:
        """基于MediaPipe识别的用户情绪，决定AI的共情反应"""
        sympathy_map = {
            "happy": EmotionType.HAPPY,      # 用户开心 → AI开心
            "sad": EmotionType.SAD,          # 用户难过 → AI难过（共情）
            "angry": EmotionType.CONFUSED,   # 用户生气 → AI困惑（安抚）
            "surprised": EmotionType.EXCITED,
            "neutral": EmotionType.LISTENING,
            "fear": EmotionType.SAD,         # 用户害怕 → AI温柔安慰
            "disgust": EmotionType.CONFUSED, # 用户厌恶 → AI困惑安抚
        }
        return sympathy_map.get(user_emotion.lower(), EmotionType.LISTENING)
    
    @classmethod
    def decide_emotion_by_text(cls, text_emotion: str) -> EmotionType:
        """基于文本情绪检测结果，决定AI反应"""
        text_map = {
            "joy": EmotionType.HAPPY,
            "anger": EmotionType.CONFUSED,
            "sadness": EmotionType.SAD,
            "fear": EmotionType.SAD,
            "surprise": EmotionType.EXCITED,
            "disgust": EmotionType.CONFUSED,
            "neutral": EmotionType.LISTENING,
        }
        return text_map.get(text_emotion.lower(), EmotionType.LISTENING)
    
    def update_by_task_action(self, user_id: str, task_action: str):
        """任务动作触发情绪更新（同情绪不重复设置）"""
        emotion = self.decide_emotion_by_action(task_action)
        current = self.get_emotion(user_id)
        if emotion.value == current:
            return current  # 情绪没变，不更新
        self._set_emotion(user_id, emotion, source=f"task:{task_action}")
        return emotion.value
    
    def update_by_vision(self, user_id: str, user_emotion: str):
        """视觉情绪触发AI共情反应（Layer 4: 连续确认机制）
        
        新情绪需要连续出现 3 次才覆盖旧情绪，防止噪声导致的抖动。
        """
        emotion = self.decide_emotion_by_vision(user_emotion)
        
        # Layer 4: 连续确认逻辑
        VISION_CONFIRM_REQUIRED = 3
        confirm_buf = self._vision_confirmations.setdefault(user_id, {
            "pending_emotion": None,
            "pending_count": 0,
        })
        
        current_state = self._user_emotions.get(user_id, {}).get("emotion", EmotionType.LISTENING.value)
        target_emotion = emotion.value
        
        # 如果目标情绪和当前情绪相同，直接维持
        if target_emotion == current_state:
            confirm_buf["pending_emotion"] = None
            confirm_buf["pending_count"] = 0
            return target_emotion
        
        # 新情绪出现，进入待确认状态
        if target_emotion == confirm_buf["pending_emotion"]:
            confirm_buf["pending_count"] += 1
        else:
            confirm_buf["pending_emotion"] = target_emotion
            confirm_buf["pending_count"] = 1
        
        # 达到确认次数才切换
        if confirm_buf["pending_count"] >= VISION_CONFIRM_REQUIRED:
            self._set_emotion(user_id, emotion, source=f"vision:{user_emotion}")
            confirm_buf["pending_emotion"] = None
            confirm_buf["pending_count"] = 0
            return target_emotion
        
        # 未达确认次数，保持当前情绪
        return current_state
    
    def update_by_text(self, user_id: str, text_emotion: str):
        """文本情绪触发AI反应（同情绪不重复设置）"""
        emotion = self.decide_emotion_by_text(text_emotion)
        current = self.get_emotion(user_id)
        if emotion.value == current:
            return current
        self._set_emotion(user_id, emotion, source=f"text:{text_emotion}")
        return emotion.value
    
    def get_prompt_addon(self, user_id: str) -> str:
        """获取当前情绪对应的LLM prompt附加描述（含人格调制）"""
        ctx = self.get_emotion_with_context(user_id)
        base_prompt = ctx.get("prompt_addon", "")
        persona = ctx.get("persona", "work")
        
        # 人格语气叠加
        PERSONA_TONE_OVERLAY = {
            "work": "【当前是工作模式】保持专业、简洁、高效。",
            "casual": "【当前是休闲模式】语气轻松自然，像朋友聊天。",
            "emergency": "【当前是紧急模式】快速响应，优先解决问题，减少寒暄。",
            "learning": "【当前是学习模式】耐心解释，鼓励提问，循序渐进。",
            "creative": "【当前是创意模式】大胆联想，发散思考，激发灵感。",
        }
        tone = PERSONA_TONE_OVERLAY.get(persona, "")
        
        if base_prompt and tone:
            return f"{base_prompt}\n{tone}"
        return base_prompt or tone
    
    # ========== FIX Phase 5: 结构化情绪状态 + 动态生成参数 + 打断机制 + TTS映射 ==========
    
    _emotion_interrupt_flags: Dict[str, bool] = {}  # user_id -> 是否需要情绪打断
    _visual_summaries: Dict[str, tuple] = {}  # user_id -> (summary, timestamp)
    
    # 基础人格生成参数
    PERSONA_BASE_PARAMS = {
        "work":      {"temperature": 0.25, "max_tokens": 8000},
        "casual":    {"temperature": 0.50, "max_tokens": 8000},
        "emergency": {"temperature": 0.30, "max_tokens": 8000},
        "learning":  {"temperature": 0.35, "max_tokens": 8000},
        "creative":  {"temperature": 0.60, "max_tokens": 8000},
    }
    
    # AI 情绪修正 (delta)
    EMOTION_TEMP_DELTA = {
        "happy":     +0.10,
        "excited":   +0.15,
        "sad":       -0.05,
        "confused":  -0.10,
        "proud":     +0.05,
        "sleepy":    -0.10,
        "thinking":  -0.05,
        "listening": 0.0,
    }
    EMOTION_TOKEN_DELTA = {
        "happy":     +200,
        "excited":   +100,
        "sad":       -100,
        "confused":  +300,
        "proud":     +50,
        "sleepy":    -200,
        "thinking":  +100,
        "listening": 0,
    }
    
    # 用户情绪修正 (delta) —— 基于文本检测到的用户情绪
    USER_EMOTION_TEMP_DELTA = {
        "angry":      -0.15,
        "urgent":     +0.05,
        "frustrated": -0.10,
        "happy":      +0.05,
        "sad":        -0.05,
        "confused":   -0.05,
        "neutral":    0.0,
    }
    USER_EMOTION_TOKEN_DELTA = {
        "angry":      -200,
        "urgent":     -300,
        "frustrated": -150,
        "happy":      +100,
        "sad":        +50,
        "confused":   +200,
        "neutral":    0,
    }
    
    # 表达要求映射
    EXPRESSION_INSTRUCTIONS = {
        ("work", "urgent"):     {"length": "回答控制在3句话以内", "emoji": "不使用emoji", "proactive": "先给结论，细节按需展开"},
        ("casual", "happy"):    {"length": "可以适当闲聊", "emoji": "适度使用 😊✨", "proactive": "可以主动分享趣事或提问"},
        ("learning", "confused"): {"length": "详细解释，举例说明", "emoji": "用 📚💡 辅助理解", "proactive": "确认用户理解后再继续"},
        ("emergency", "any"):   {"length": "极度简短", "emoji": "不使用emoji", "proactive": "立即给出解决方案"},
    }
    
    # TTS 参数映射
    EMOTION_TTS_PARAMS = {
        "happy":    {"pitch": 1.15, "rate": 1.12, "volume": 1.0},
        "excited":  {"pitch": 1.20, "rate": 1.25, "volume": 1.05},
        "sad":      {"pitch": 0.85, "rate": 0.85, "volume": 0.85},
        "confused": {"pitch": 1.05, "rate": 0.90, "volume": 0.95},
        "proud":    {"pitch": 1.10, "rate": 1.05, "volume": 1.0},
        "sleepy":   {"pitch": 0.90, "rate": 0.80, "volume": 0.80},
        "thinking": {"pitch": 1.0,  "rate": 0.90, "volume": 0.95},
        "listening":{"pitch": 1.0,  "rate": 1.0,  "volume": 1.0},
    }
    
    PERSONA_TTS_MODIFIERS = {
        "work":      {"pitch": -0.05, "rate": -0.05},
        "casual":    {"pitch": +0.03, "rate": +0.03},
        "emergency": {"pitch": 0.0,   "rate": +0.10},
        "learning":  {"pitch": 0.0,   "rate": -0.05},
        "creative":  {"pitch": +0.05, "rate": +0.05},
    }
    
    def record_voice_prosody(self, user_id: str, prosody: Dict):
        """记录语音韵律特征（音调/语速/音量）供融合引擎使用"""
        self._voice_prosody[user_id] = {
            **prosody,
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_voice_signal(self, user_id: str) -> Optional[EmotionSignal]:
        """将语音韵律特征转换为 EmotionSignal"""
        prosody = self._voice_prosody.get(user_id)
        if not prosody:
            return None
        # 简单的韵律→情绪映射
        pitch_var = prosody.get("pitch_variation", 0.5)
        speech_rate = prosody.get("speech_rate", 1.0)
        volume_var = prosody.get("volume_variation", 0.5)
        
        # 高语速 + 高音调变化 + 高音量 = 兴奋/愤怒
        # 低语速 + 低音调 = 悲伤/疲惫
        # 正常语速 + 稳定音调 = 中性
        arousal = min(1.0, (speech_rate * 0.4 + pitch_var * 0.4 + volume_var * 0.2))
        
        if speech_rate > 1.3 and pitch_var > 0.6:
            emotion = "excited"
            valence = 0.6
        elif speech_rate > 1.2 and pitch_var > 0.5:
            emotion = "anger"
            valence = -0.5
        elif speech_rate < 0.8 and pitch_var < 0.4:
            emotion = "sadness"
            valence = -0.5
        elif pitch_var < 0.3 and speech_rate < 0.9:
            emotion = "tired"
            valence = -0.2
        else:
            emotion = "neutral"
            valence = 0.0
        
        return EmotionSignal(
            emotion=emotion,
            intensity=arousal,
            valence=valence,
            arousal=arousal,
            confidence=0.6,
            source="voice",
            raw_features=prosody,
        )
    
    def get_fused_emotion(self, user_id: str, text_emotion: str = "neutral", text_intensity: float = 0.0, session_id: str = "") -> Dict:
        """获取多模态融合后的情绪状态
        
        整合文本情绪、视觉情绪、语音情绪，返回融合结果
        """
        # 文本信号
        text_va = EMOTION_VA.get(text_emotion, {"valence": 0.0, "arousal": 0.3})
        text_signal = EmotionSignal(
            emotion=text_emotion,
            intensity=text_intensity,
            valence=text_va["valence"] * text_intensity,
            arousal=text_va["arousal"] * text_intensity,
            confidence=0.7,
            source="text",
        )
        
        # 视觉信号（从 visual observation 推断）
        vision_signal = None
        visual_summary = self.get_visual_summary(user_id)
        if visual_summary:
            # 从视觉摘要中推断情绪
            if "疲惫" in visual_summary or "疲劳" in visual_summary:
                vision_signal = EmotionSignal(
                    emotion="tired", intensity=0.6, valence=-0.3, arousal=0.1,
                    confidence=0.5, source="vision",
                )
            elif "开心" in visual_summary or "happy" in visual_summary:
                vision_signal = EmotionSignal(
                    emotion="happy", intensity=0.7, valence=0.7, arousal=0.5,
                    confidence=0.5, source="vision",
                )
        
        # 语音信号
        voice_signal = self.get_voice_signal(user_id)
        
        # 融合
        fused = self._fusion_engine.fuse(
            user_id=user_id,
            text_signal=text_signal,
            vision_signal=vision_signal,
            voice_signal=voice_signal,
            session_id=session_id,
        )
        
        # 缓存
        self._last_fused_state[user_id] = {
            "primary": fused.primary,
            "intensity": fused.intensity,
            "valence": fused.valence,
            "arousal": fused.arousal,
            "mixed": fused.mixed,
            "trend": fused.trend,
            "authenticity": fused.authenticity,
            "sources": fused.sources,
            "timestamp": fused.timestamp,
            "session_id": fused.session_id,
        }
        
        # 更新用户基线
        self._fusion_engine.update_user_baseline(user_id, fused.valence, fused.arousal)
        
        # Phase 2: 记录到情绪历史
        self.record_emotion_event(user_id, session_id, self._last_fused_state[user_id])
        
        return self._last_fused_state[user_id]
    
    def get_structured_emotion_state(self, user_id: str, user_emotion: str = "neutral") -> Dict:
        """获取完整的结构化情绪状态，用于深度注入 LLM prompt
        
        返回包含：AI情绪、强度、人格、用户情绪、视觉观察、表达要求的结构化字典
        """
        ctx = self.get_emotion_with_context(user_id)
        ai_emotion = ctx.get("emotion", "listening")
        persona = ctx.get("persona", "work")
        visual_summary = self.get_visual_summary(user_id)
        
        # Phase 1: 获取融合情绪（如果有）
        fused = self._last_fused_state.get(user_id)
        if fused:
            user_emotion = fused.get("primary", user_emotion)
        
        # 查找表达要求（精确匹配 > 人格通配 > 默认）
        expr = None
        if (persona, user_emotion) in self.EXPRESSION_INSTRUCTIONS:
            expr = self.EXPRESSION_INSTRUCTIONS[(persona, user_emotion)]
        elif (persona, "any") in self.EXPRESSION_INSTRUCTIONS:
            expr = self.EXPRESSION_INSTRUCTIONS[(persona, "any")]
        
        if expr is None:
            # 默认表达要求
            if persona == "work":
                expr = {"length": "简洁专业", "emoji": "不使用emoji", "proactive": "直接高效"}
            elif persona == "casual":
                expr = {"length": "自然流畅", "emoji": "适度使用", "proactive": "轻松友好"}
            elif persona == "emergency":
                expr = {"length": "极度简短", "emoji": "不使用emoji", "proactive": "立即解决"}
            elif persona == "learning":
                expr = {"length": "详细耐心", "emoji": "辅助理解", "proactive": "循序渐进"}
            elif persona == "creative":
                expr = {"length": "自由发挥", "emoji": "富有创意", "proactive": "大胆联想"}
            else:
                expr = {"length": "适中", "emoji": "适度", "proactive": "自然回应"}
        
        result = {
            "ai_emotion": ai_emotion,
            "ai_emotion_prompt": ctx.get("prompt_addon", ""),
            "persona": persona,
            "user_emotion": user_emotion,
            "visual_summary": visual_summary,
            "expression": expr,
        }
        
        # Phase 1: 如果有融合状态，追加融合信息
        if fused:
            result["fused"] = {
                "mixed": fused.get("mixed", {}),
                "trend": fused.get("trend", "stable"),
                "authenticity": fused.get("authenticity", 0.5),
            }
        
        return result
    
    def get_dynamic_generation_params(self, user_id: str, user_emotion: str = "neutral") -> Dict[str, float]:
        """计算动态 temperature 和 max_tokens
        
        基于人格基础参数 + AI情绪修正 + 用户情绪修正
        """
        ctx = self.get_emotion_with_context(user_id)
        persona = ctx.get("persona", "work")
        ai_emotion = ctx.get("emotion", "listening")
        
        # 基础参数
        base = self.PERSONA_BASE_PARAMS.get(persona, {"temperature": 0.3, "max_tokens": 800})
        temp = base["temperature"]
        tokens = base["max_tokens"]
        
        # AI 情绪修正
        temp += self.EMOTION_TEMP_DELTA.get(ai_emotion, 0.0)
        tokens += self.EMOTION_TOKEN_DELTA.get(ai_emotion, 0)
        
        # 用户情绪修正
        temp += self.USER_EMOTION_TEMP_DELTA.get(user_emotion, 0.0)
        tokens += self.USER_EMOTION_TOKEN_DELTA.get(user_emotion, 0)
        
        # 边界保护
        temp = max(0.1, min(0.9, temp))
        tokens = int(max(200, min(4000, tokens)))
        
        return {"temperature": round(temp, 2), "max_tokens": tokens}
    
    def get_emotion_interrupt_flag(self, user_id: str) -> bool:
        """检查是否需要情绪打断"""
        return self._emotion_interrupt_flags.get(user_id, False)
    
    def set_emotion_interrupt(self, user_id: str):
        """设置情绪打断标志（用户愤怒时调用）"""
        self._emotion_interrupt_flags[user_id] = True
        logger.info(f"[EMOTION] 情绪打断标志已设置 [{user_id}]")
    
    def clear_emotion_interrupt(self, user_id: str):
        """清除情绪打断标志"""
        if user_id in self._emotion_interrupt_flags:
            del self._emotion_interrupt_flags[user_id]
            logger.info(f"[EMOTION] 情绪打断标志已清除 [{user_id}]")
    
    def set_visual_summary(self, user_id: str, summary: str):
        """设置视觉观察摘要（带5分钟TTL）"""
        self._visual_summaries[user_id] = (summary, datetime.now().isoformat())
    
    def get_visual_summary(self, user_id: str) -> str:
        """获取视觉观察摘要（超过5分钟返回空）"""
        entry = self._visual_summaries.get(user_id)
        if not entry:
            return ""
        summary, ts_str = entry
        try:
            ts = datetime.fromisoformat(ts_str)
            elapsed = (datetime.now() - ts).total_seconds()
            if elapsed > 300:  # 5分钟TTL
                del self._visual_summaries[user_id]
                return ""
        except Exception:
            return ""
        return summary
    
    def get_last_vision_emotion(self, user_id: str) -> str:
        """获取最近视觉检测到的情绪（从确认缓冲中读取）"""
        confirm_buf = self._vision_confirmations.get(user_id, {})
        pending = confirm_buf.get("pending_emotion")
        if pending:
            return pending
        # 如果没有待确认的情绪，返回当前情绪
        state = self._user_emotions.get(user_id, {})
        return state.get("emotion", "listening")
    
    def check_and_trigger_interrupt(self, user_id: str, text_emotion: str, vision_emotion: str) -> bool:
        """检查是否需要触发情绪打断（双源确认：文本 + 视觉都检测到愤怒）
        
        Returns: True 如果触发了打断
        """
        angry_text = text_emotion in ("angry", "frustrated")
        angry_vision = vision_emotion in ("angry", "fear", "disgust")
        
        if angry_text and angry_vision:
            self.set_emotion_interrupt(user_id)
            return True
        return False
    
    def get_tts_params(self, user_id: str) -> Dict[str, float]:
        """获取当前情绪对应的 TTS 参数（pitch, rate, volume）"""
        ctx = self.get_emotion_with_context(user_id)
        ai_emotion = ctx.get("emotion", "listening")
        persona = ctx.get("persona", "work")
        
        base = self.EMOTION_TTS_PARAMS.get(ai_emotion, {"pitch": 1.0, "rate": 1.0, "volume": 1.0}).copy()
        mod = self.PERSONA_TTS_MODIFIERS.get(persona, {"pitch": 0.0, "rate": 0.0})
        
        base["pitch"] = max(0.5, min(2.0, base["pitch"] + mod["pitch"]))
        base["rate"] = max(0.5, min(2.0, base["rate"] + mod["rate"]))
        base["volume"] = max(0.3, min(1.5, base["volume"]))
        
        return base
    
    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2: 情绪记忆时间线（Emotion Memory Timeline）
    # ══════════════════════════════════════════════════════════════════════════
    
    def _get_db_conn(self):
        """获取数据库连接（按需创建）"""
        if self._emotion_history_db is None:
            import sqlite3
            self._emotion_history_db = sqlite3.connect("tent_scheduler.db", check_same_thread=False)
        return self._emotion_history_db
    
    def record_emotion_event(self, user_id: str, session_id: Optional[str], fused_state: Dict, trigger_topic: str = ""):
        """将融合情绪状态写入 SQLite 历史记录"""
        try:
            conn = self._get_db_conn()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO emotion_history 
                (user_id, session_id, timestamp, primary_emotion, intensity, valence, arousal, mixed_emotions, trend, authenticity, trigger_topic, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                session_id or "",
                time.time(),
                fused_state.get("primary", "neutral"),
                fused_state.get("intensity", 0.0),
                fused_state.get("valence", 0.0),
                fused_state.get("arousal", 0.0),
                json.dumps(fused_state.get("mixed", {})),
                fused_state.get("trend", "stable"),
                fused_state.get("authenticity", 0.5),
                trigger_topic,
                json.dumps(fused_state.get("sources", {}))
            ))
            conn.commit()
        except Exception as e:
            print(f"[Emotion] 记录情绪历史失败: {e}")
    
    def get_emotion_history(self, user_id: str, limit: int = 100, since: float = 0) -> List[Dict]:
        """获取用户情绪历史记录（按时间倒序）"""
        try:
            conn = self._get_db_conn()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, primary_emotion, intensity, valence, arousal, mixed_emotions, trend, authenticity, trigger_topic
                FROM emotion_history
                WHERE user_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_id, since, limit))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                result.append({
                    "timestamp": row[0],
                    "primary": row[1],
                    "intensity": row[2],
                    "valence": row[3],
                    "arousal": row[4],
                    "mixed": json.loads(row[5]) if row[5] else {},
                    "trend": row[6],
                    "authenticity": row[7],
                    "trigger": row[8],
                })
            return result
        except Exception as e:
            print(f"[Emotion] 查询情绪历史失败: {e}")
            return []
    
    def get_emotion_insights(self, user_id: str, window_hours: float = 24.0) -> Dict:
        """获取情绪洞察（统计 + 趋势分析）"""
        try:
            conn = self._get_db_conn()
            cursor = conn.cursor()
            since = time.time() - window_hours * 3600
            cursor.execute("""
                SELECT primary_emotion, intensity, valence, authenticity
                FROM emotion_history
                WHERE user_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (user_id, since))
            rows = cursor.fetchall()
            if not rows:
                return {"summary": "暂无数据", "dominant": "neutral", "avg_intensity": 0, "authenticity_avg": 0}
            
            emotions = [r[0] for r in rows]
            intensities = [r[1] for r in rows]
            valences = [r[2] for r in rows]
            auths = [r[3] for r in rows]
            
            # 统计最频繁情绪
            from collections import Counter
            emotion_counts = Counter(emotions)
            dominant = emotion_counts.most_common(1)[0][0]
            
            # 情绪多样性
            diversity = len(set(emotions))
            
            # 平均强度和真实性
            avg_intensity = sum(intensities) / len(intensities)
            avg_auth = sum(auths) / len(auths)
            
            # 趋势：最近 vs 较早
            mid = len(valences) // 2
            recent_avg = sum(valences[:mid]) / max(1, mid)
            older_avg = sum(valences[mid:]) / max(1, len(valences) - mid)
            trend_dir = "improving" if recent_avg > older_avg + 0.1 else ("declining" if recent_avg < older_avg - 0.1 else "stable")
            
            return {
                "dominant": dominant,
                "avg_intensity": round(avg_intensity, 2),
                "authenticity_avg": round(avg_auth, 2),
                "diversity": diversity,
                "trend_direction": trend_dir,
                "record_count": len(rows),
                "summary": f"过去{int(window_hours)}小时共 {len(rows)} 条记录，主导情绪 {dominant}，强度 {avg_intensity:.2f}",
            }
        except Exception as e:
            print(f"[Emotion] 情绪洞察查询失败: {e}")
            return {"summary": f"查询失败: {e}", "dominant": "neutral", "avg_intensity": 0, "authenticity_avg": 0}
