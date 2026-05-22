"""主动行为引擎（Proactive Care Engine）

检测用户情绪状态、空闲时间和任务卡壳情况，主动发起关怀或建议。
所有检查都是轻量的，不涉及 LLM 调用（除非触发后生成消息）。
"""

import time
import json
from typing import Dict, Optional, List
from dataclasses import dataclass, field

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class ProactiveAction:
    action_type: str  # "emotion_care", "idle_checkin", "task_stall"
    session_id: str
    user_id: str
    message: str
    priority: int  # 1-10, 越高越紧急


class ProactiveCareEngine:
    """主动关怀引擎 —— 检测用户状态，适时主动介入"""

    def __init__(self, bus, llm, state_store, config: Optional[Dict] = None):
        self.bus = bus
        self.llm = llm
        self.state_store = state_store
        self.config = config or {}
        self.enabled = self.config.get("proactive_care", {}).get("enabled", True)
        self.idle_timeout = self.config.get("proactive_care", {}).get("idle_timeout_seconds", 300)
        self.distress_threshold = self.config.get("proactive_care", {}).get("distress_threshold", 2)
        self.max_daily = self.config.get("proactive_care", {}).get("max_daily_proactive", 10)

        # 每用户/session 的状态跟踪
        self._session_emotion_history: Dict[str, List[Dict]] = {}  # session_id -> [{emotion, timestamp}]
        self._session_last_user_msg_time: Dict[str, float] = {}
        self._session_proactive_count: Dict[str, int] = {}  # 今日 proactive 计数
        self._session_tool_retry_count: Dict[str, int] = {}
        self._last_check_time: float = 0

    def record_user_emotion(self, session_id: str, user_id: str, fused_emotion: Dict):
        """记录用户融合情绪，用于情绪趋势检测"""
        if not self.enabled:
            return
        if session_id not in self._session_emotion_history:
            self._session_emotion_history[session_id] = []
        self._session_emotion_history[session_id].append({
            "emotion": fused_emotion.get("primary", "neutral"),
            "valence": fused_emotion.get("valence", 0),
            "timestamp": time.time(),
        })
        # 只保留最近 20 条
        self._session_emotion_history[session_id] = self._session_emotion_history[session_id][-20:]
        self._session_last_user_msg_time[session_id] = time.time()

    def record_tool_retry(self, session_id: str):
        """记录工具重试，用于检测任务卡壳"""
        if not self.enabled:
            return
        self._session_tool_retry_count[session_id] = self._session_tool_retry_count.get(session_id, 0) + 1

    def reset_tool_retry(self, session_id: str):
        """重置工具重试计数（任务完成或进入新阶段时调用）"""
        self._session_tool_retry_count.pop(session_id, None)

    def check(self, session_id: str, user_id: str = "web_user") -> Optional[ProactiveAction]:
        """检查是否需要触发主动行为。返回 ProactiveAction 或 None"""
        if not self.enabled:
            return None

        now = time.time()
        # 节流：每 session 每 60 秒最多检查一次
        last_check = getattr(self, '_last_check_per_session', {}).get(session_id, 0)
        if now - last_check < 60:
            return None
        if not hasattr(self, '_last_check_per_session'):
            self._last_check_per_session = {}
        self._last_check_per_session[session_id] = now

        # 每日计数限制
        day_key = f"{session_id}_{time.strftime('%Y%m%d')}"
        if self._session_proactive_count.get(day_key, 0) >= self.max_daily:
            return None

        # 1. 情绪低落关怀检测
        care_action = self._check_emotion_distress(session_id, user_id)
        if care_action:
            self._session_proactive_count[day_key] = self._session_proactive_count.get(day_key, 0) + 1
            return care_action

        # 2. 长时间沉默检测
        idle_action = self._check_idle(session_id, user_id)
        if idle_action:
            self._session_proactive_count[day_key] = self._session_proactive_count.get(day_key, 0) + 1
            return idle_action

        # 3. 任务卡壳检测
        stall_action = self._check_task_stall(session_id, user_id)
        if stall_action:
            self._session_proactive_count[day_key] = self._session_proactive_count.get(day_key, 0) + 1
            return stall_action

        return None

    def _check_emotion_distress(self, session_id: str, user_id: str) -> Optional[ProactiveAction]:
        """检测用户是否连续情绪低落"""
        history = self._session_emotion_history.get(session_id, [])
        if len(history) < self.distress_threshold:
            return None

        # 看最近 N 条是否有连续 negative
        recent = history[-self.distress_threshold:]
        negative_emotions = {"sad", "angry", "tired", "frustrated", "fear", "anxious", "sleepy"}
        negative_count = sum(1 for h in recent if h["emotion"] in negative_emotions)

        if negative_count >= self.distress_threshold:
            # 避免重复触发：如果最近 5 分钟内已经触发过情绪关怀，跳过
            last_care = getattr(self, '_last_emotion_care', {}).get(session_id, 0)
            if time.time() - last_care < 300:
                return None
            if not hasattr(self, '_last_emotion_care'):
                self._last_emotion_care = {}
            self._last_emotion_care[session_id] = time.time()

            messages = [
                "我注意到你似乎有些疲惫/不开心。需要我帮你做点什么吗？",
                "你还好吗？我在这里，如果需要倾诉或帮助，随时告诉我。",
                "看起来你现在状态不太好。要不要先休息一下？我可以帮你整理待办事项。",
            ]
            import random
            msg = random.choice(messages)
            logger.info(f"[PROACTIVE] 情绪关怀触发 [{session_id}]: {recent[-1]['emotion']}")
            return ProactiveAction(
                action_type="emotion_care",
                session_id=session_id,
                user_id=user_id,
                message=msg,
                priority=8,
            )
        return None

    def _check_idle(self, session_id: str, user_id: str) -> Optional[ProactiveAction]:
        """检测用户是否长时间未发消息"""
        last_msg_time = self._session_last_user_msg_time.get(session_id)
        if not last_msg_time:
            return None

        elapsed = time.time() - last_msg_time
        if elapsed < self.idle_timeout:
            return None

        # 避免重复触发
        last_idle = getattr(self, '_last_idle_checkin', {}).get(session_id, 0)
        if time.time() - last_idle < self.idle_timeout:
            return None
        if not hasattr(self, '_last_idle_checkin'):
            self._last_idle_checkin = {}
        self._last_idle_checkin[session_id] = time.time()

        messages = [
            "还在吗？如果需要帮助，随时叫我。",
            "你似乎已经离开了一会儿。我刚才整理了一些信息，回来的时候可以继续聊。",
            "哈喽？我还在这里等着呢。",
        ]
        import random
        msg = random.choice(messages)
        logger.info(f"[PROACTIVE] 空闲检测触发 [{session_id}]: idle={elapsed:.0f}s")
        return ProactiveAction(
            action_type="idle_checkin",
            session_id=session_id,
            user_id=user_id,
            message=msg,
            priority=4,
        )

    def _check_task_stall(self, session_id: str, user_id: str) -> Optional[ProactiveAction]:
        """检测任务是否卡壳（工具重试过多）"""
        retry_count = self._session_tool_retry_count.get(session_id, 0)
        if retry_count < 3:
            return None

        # 避免重复触发
        last_stall = getattr(self, '_last_task_stall', {}).get(session_id, 0)
        if time.time() - last_stall < 120:
            return None
        if not hasattr(self, '_last_task_stall'):
            self._last_task_stall = {}
        self._last_task_stall[session_id] = time.time()

        msg = "这个任务似乎有点棘手，我已经尝试了好几次。要不我们换个思路，或者你告诉我更具体的需求？"
        logger.info(f"[PROACTIVE] 任务卡壳触发 [{session_id}]: retries={retry_count}")
        return ProactiveAction(
            action_type="task_stall",
            session_id=session_id,
            user_id=user_id,
            message=msg,
            priority=7,
        )

    async def execute(self, action: ProactiveAction):
        """执行主动行为：发布 governance.request 消息"""
        try:
            await self.bus.publish("governance.request", json.dumps({
                "session_id": action.session_id,
                "user_id": action.user_id,
                "content": action.message,
                "source": "proactive",
                "proactive_type": action.action_type,
            }).encode())
            logger.info(f"[PROACTIVE] 已发送主动消息 [{action.session_id}]: {action.action_type}")
        except Exception as e:
            logger.warning(f"[PROACTIVE] 发送主动消息失败 [{action.session_id}]: {e}")
