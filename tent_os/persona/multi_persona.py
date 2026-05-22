"""多人格管理 —— 根据场景自动切换人格模式

模式：
    work      —— 工作模式：professional, concise, proactive
    casual    —— 休闲模式：casual, humorous, reactive
    emergency —— 紧急模式：direct, urgent, commanding
    learning  —— 学习模式：patient, thorough, encouraging
    creative  —— 创意模式：creative, open, exploratory

自动切换信号：
    - 时间：工作时间 → work，晚上 → casual
    - 内容：包含"紧急""马上"→ emergency
    - 渠道：工作 IM → work，个人聊天 → casual
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from tent_os.persona.soul_evolution import SoulDimensions

logger = logging.getLogger("tent_os.persona.multi")


@dataclass
class PersonaMode:
    """人格模式定义"""
    name: str
    description: str
    dimensions: SoulDimensions
    trigger_keywords: list
    trigger_hours: Optional[tuple] = None  # (start, end)，None 表示全天


# 预定义人格模式
PERSONA_MODES = {
    "work": PersonaMode(
        name="work",
        description="工作模式：专业、高效、主动",
        dimensions=SoulDimensions(
            formality=0.8, humor=0.1, verbosity=0.4,
            proactivity=0.7, empathy=0.5, directness=0.7,
            creativity=0.3, precision=0.8
        ),
        trigger_keywords=["工作", "项目", "会议", "deadline", "报告", "work", "project", "meeting"],
        trigger_hours=(9, 18),
    ),
    "casual": PersonaMode(
        name="casual",
        description="休闲模式：轻松、幽默、亲和",
        dimensions=SoulDimensions(
            formality=0.2, humor=0.8, verbosity=0.6,
            proactivity=0.3, empathy=0.7, directness=0.4,
            creativity=0.6, precision=0.4
        ),
        trigger_keywords=["聊天", "轻松", "玩", "电影", "音乐", "chat", "fun", "movie", "music"],
        trigger_hours=(18, 23),
    ),
    "emergency": PersonaMode(
        name="emergency",
        description="紧急模式：直接、果断、高效",
        dimensions=SoulDimensions(
            formality=0.5, humor=0.0, verbosity=0.2,
            proactivity=0.9, empathy=0.3, directness=0.9,
            creativity=0.2, precision=0.9
        ),
        trigger_keywords=["紧急", "马上", "立刻", "urgent", "emergency", "asap", "critical", "马上"],
        trigger_hours=None,
    ),
    "learning": PersonaMode(
        name="learning",
        description="学习模式：耐心、详尽、鼓励",
        dimensions=SoulDimensions(
            formality=0.5, humor=0.3, verbosity=0.9,
            proactivity=0.6, empathy=0.8, directness=0.5,
            creativity=0.5, precision=0.7
        ),
        trigger_keywords=["学习", "教程", "解释", "怎么", "为什么", "learn", "tutorial", "explain", "how", "why"],
        trigger_hours=None,
    ),
    "creative": PersonaMode(
        name="creative",
        description="创意模式：发散、开放、探索",
        dimensions=SoulDimensions(
            formality=0.3, humor=0.5, verbosity=0.6,
            proactivity=0.7, empathy=0.6, directness=0.3,
            creativity=0.9, precision=0.4
        ),
        trigger_keywords=["创意", "想法", "设计", "brainstorm", "creative", "idea", "design", "innovate"],
        trigger_hours=None,
    ),
}


class MultiPersonaManager:
    """多人格管理器"""
    
    def __init__(self, default_mode: str = "work"):
        self.modes = PERSONA_MODES
        self.current_mode = default_mode
        self._mode_history: list = []
    
    def detect_mode(self, user_input: str = "", 
                    current_hour: int = None,
                    channel: str = "default") -> str:
        """根据上下文检测最适合的人格模式
        
        优先级：
        1. 关键词匹配（紧急关键词最高优先级）
        2. 时间窗口
        3. 渠道默认
        """
        user_lower = user_input.lower()
        current_hour = current_hour or datetime.now().hour
        
        # 1. 关键词匹配（紧急模式优先）
        for mode_name in ["emergency", "learning", "creative", "work", "casual"]:
            mode = self.modes[mode_name]
            for kw in mode.trigger_keywords:
                if kw.lower() in user_lower:
                    if mode_name != self.current_mode:
                        self._switch_mode(mode_name, f"关键词触发: {kw}")
                    return mode_name
        
        # 2. 时间窗口
        for mode_name, mode in self.modes.items():
            if mode.trigger_hours:
                start, end = mode.trigger_hours
                if start <= current_hour < end:
                    if mode_name != self.current_mode:
                        self._switch_mode(mode_name, f"时间触发: {current_hour}:00")
                    return mode_name
        
        # 3. 保持当前模式
        return self.current_mode
    
    def _switch_mode(self, new_mode: str, reason: str):
        """切换人格模式"""
        old_mode = self.current_mode
        self.current_mode = new_mode
        self._mode_history.append({
            "timestamp": datetime.now().isoformat(),
            "from": old_mode,
            "to": new_mode,
            "reason": reason,
        })
        logger.info(f"人格切换: {old_mode} → {new_mode} ({reason})")
    
    def get_current_dimensions(self) -> SoulDimensions:
        """获取当前模式的维度"""
        mode = self.modes.get(self.current_mode)
        if mode:
            return mode.dimensions
        return SoulDimensions()
    
    def get_mode_description(self) -> str:
        """获取当前模式描述"""
        mode = self.modes.get(self.current_mode)
        if mode:
            return mode.description
        return "默认模式"
    
    def force_mode(self, mode_name: str):
        """强制切换到指定模式"""
        if mode_name in self.modes:
            self._switch_mode(mode_name, "用户强制切换")
        else:
            logger.warning(f"未知人格模式: {mode_name}")
    
    def get_mode_history(self, limit: int = 20) -> list:
        """获取模式切换历史"""
        return self._mode_history[-limit:]
