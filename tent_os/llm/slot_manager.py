"""Output Slot Manager —— 输出槽位预留系统

借鉴 Claude Code 的做法：
- 默认 4K 输出上限
- 模型输出被截断时自动升级到 32K
- 99% 的请求保持在 4K 以内节省上下文

核心设计：
1. 默认槽位 —— 足够大多数任务使用
2. 截断检测 —— 监控 finish_reason
3. 自动升级 —— 无缝升级到扩展槽位
4. 降级恢复 —— 升级后如果连续 N 次用不到，降级回默认

Tent OS 差异化：
- 槽位管理与会话绑定（不同会话可以有不同槽位策略）
- 支持 provider-specific 的槽位大小
- 与 JSONL Logger 集成，记录槽位升级事件

使用方式：
    slot_mgr = OutputSlotManager(config)
    
    async def llm_call(messages, max_tokens):
        return await openai.chat.completions.create(..., max_tokens=max_tokens)
    
    result = await slot_mgr.call_with_slot(
        llm_call, messages, session_id="abc", provider="openai"
    )
"""

import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum

from tent_os.logging_config import get_logger

logger = get_logger()


class SlotTier(Enum):
    """槽位等级"""
    DEFAULT = "default"
    EXTENDED = "extended"
    MAXIMUM = "maximum"


# Provider -> 槽位配置
PROVIDER_SLOT_CONFIG = {
    "openai": {
        SlotTier.DEFAULT: 4096,
        SlotTier.EXTENDED: 16384,
        SlotTier.MAXIMUM: 32768,
    },
    "anthropic": {
        SlotTier.DEFAULT: 4096,
        SlotTier.EXTENDED: 8192,
        SlotTier.MAXIMUM: 64000,
    },
    "kimi": {
        SlotTier.DEFAULT: 4096,
        SlotTier.EXTENDED: 8192,
        SlotTier.MAXIMUM: 16384,
    },
    "ollama": {
        SlotTier.DEFAULT: 4096,
        SlotTier.EXTENDED: 8192,
        SlotTier.MAXIMUM: 8192,
    },
}


@dataclass
class SlotResult:
    """槽位调用结果"""
    content: str
    tier_used: str
    tokens_used: int
    tokens_limit: int
    was_truncated: bool
    upgraded: bool
    latency_ms: float
    calls_made: int


class OutputSlotManager:
    """输出槽位管理器

    管理每个会话的输出槽位策略：
    - 默认使用 DEFAULT 槽位
    - 如果输出被截断（finish_reason == "length"），自动升级到 EXTENDED
    - 如果 EXTENDED 仍被截断，升级到 MAXIMUM（只升级一次）
    - 如果连续 N 次（默认5次）用不到扩展槽位，降级回 DEFAULT
    """

    def __init__(self,
                 config: Dict[str, Any] = None,
                 jsonl_logger=None):
        self.config = config or {}
        self.jsonl_logger = jsonl_logger

        # 全局默认配置
        self.default_provider = self.config.get("llm", {}).get("provider", "openai")
        self.escalation_threshold = self.config.get("slot", {}).get("escalation_threshold", 0.95)
        self.downgrade_after = self.config.get("slot", {}).get("downgrade_after", 5)

        # 会话级槽位状态
        self._session_tiers: Dict[str, SlotTier] = {}
        self._session_extended_uses: Dict[str, int] = {}  # 扩展槽位使用次数
        self._session_default_uses: Dict[str, int] = {}   # 默认槽位使用次数
        self._session_consecutive_defaults: Dict[str, int] = {}  # 连续使用默认槽位次数

    def get_slot_size(self, session_id: str, provider: str = None) -> int:
        """获取会话当前槽位大小"""
        provider = provider or self.default_provider
        tier = self._session_tiers.get(session_id, SlotTier.DEFAULT)
        config = PROVIDER_SLOT_CONFIG.get(provider, PROVIDER_SLOT_CONFIG["openai"])
        return config.get(tier, 4096)

    async def call_with_slot(self,
                             llm_call: Callable,
                             messages: List[Dict],
                             session_id: str,
                             provider: str = None,
                             **llm_kwargs) -> SlotResult:
        """带槽位管理的 LLM 调用

        Args:
            llm_call: LLM 调用函数，签名: async (messages, max_tokens, **kwargs) -> response
            messages: 消息列表
            session_id: 会话ID
            provider: LLM provider
            **llm_kwargs: 额外 LLM 参数

        Returns:
            SlotResult
        """
        provider = provider or self.default_provider
        start_time = time.time()
        calls_made = 0

        # 获取当前槽位
        current_tier = self._session_tiers.get(session_id, SlotTier.DEFAULT)
        slot_config = PROVIDER_SLOT_CONFIG.get(provider, PROVIDER_SLOT_CONFIG["openai"])

        # 第一次调用：当前槽位
        max_tokens = slot_config.get(current_tier, 4096)
        response = await llm_call(messages, max_tokens=max_tokens, **llm_kwargs)
        calls_made += 1

        # 检测是否被截断
        was_truncated = self._was_truncated(response)
        tokens_used = self._extract_token_usage(response)

        # 如果被截断且还能升级
        if was_truncated and current_tier != SlotTier.MAXIMUM:
            upgraded_tier = self._get_next_tier(current_tier)
            upgraded_size = slot_config.get(upgraded_tier, max_tokens)

            logger.info(
                f"[Slot] 输出被截断，升级槽位 [{session_id}]: "
                f"{current_tier.value}({max_tokens}) -> {upgraded_tier.value}({upgraded_size})"
            )

            # 记录升级事件
            if self.jsonl_logger:
                asyncio = __import__("asyncio")
                asyncio.create_task(self.jsonl_logger.log_event(
                    event="slot.upgrade",
                    session_id=session_id,
                    from_tier=current_tier.value,
                    to_tier=upgraded_tier.value,
                    from_size=max_tokens,
                    to_size=upgraded_size,
                ))

            # 升级后重新调用
            response = await llm_call(messages, max_tokens=upgraded_size, **llm_kwargs)
            calls_made += 1

            # 更新会话状态
            self._session_tiers[session_id] = upgraded_tier
            self._session_extended_uses[session_id] = self._session_extended_uses.get(session_id, 0) + 1
            self._session_consecutive_defaults[session_id] = 0

            was_truncated = self._was_truncated(response)
            tokens_used = self._extract_token_usage(response)

            final_tier = upgraded_tier
            upgraded = True
        else:
            final_tier = current_tier
            upgraded = False

            # 更新使用统计
            if current_tier == SlotTier.DEFAULT:
                self._session_consecutive_defaults[session_id] = self._session_consecutive_defaults.get(session_id, 0) + 1
                # 检查是否需要降级
                self._maybe_downgrade(session_id)
            else:
                self._session_extended_uses[session_id] = self._session_extended_uses.get(session_id, 0) + 1
                self._session_consecutive_defaults[session_id] = 0

        latency_ms = (time.time() - start_time) * 1000

        return SlotResult(
            content=self._extract_content(response),
            tier_used=final_tier.value,
            tokens_used=tokens_used,
            tokens_limit=slot_config.get(final_tier, 4096),
            was_truncated=was_truncated,
            upgraded=upgraded,
            latency_ms=latency_ms,
            calls_made=calls_made,
        )

    def _maybe_downgrade(self, session_id: str):
        """检查是否需要降级到默认槽位"""
        consecutive = self._session_consecutive_defaults.get(session_id, 0)
        current_tier = self._session_tiers.get(session_id, SlotTier.DEFAULT)

        if current_tier != SlotTier.DEFAULT and consecutive >= self.downgrade_after:
            logger.info(f"[Slot] 降级到默认槽位 [{session_id}]: 连续 {consecutive} 次未用完")
            self._session_tiers[session_id] = SlotTier.DEFAULT
            self._session_extended_uses[session_id] = 0

    def _get_next_tier(self, current: SlotTier) -> SlotTier:
        """获取下一个槽位等级"""
        tier_order = [SlotTier.DEFAULT, SlotTier.EXTENDED, SlotTier.MAXIMUM]
        try:
            idx = tier_order.index(current)
            if idx + 1 < len(tier_order):
                return tier_order[idx + 1]
        except ValueError:
            pass
        return current

    def _was_truncated(self, response: Any) -> bool:
        """检测响应是否被截断"""
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "finish_reason"):
                return choice.finish_reason == "length"
        # 字典格式（OpenAI 兼容）
        if isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                return choices[0].get("finish_reason") == "length"
        # 字符串格式
        if isinstance(response, str):
            return False
        return False

    def _extract_token_usage(self, response: Any) -> int:
        """提取 token 使用量"""
        if hasattr(response, "usage") and response.usage:
            return getattr(response.usage, "completion_tokens", 0)
        if isinstance(response, dict):
            usage = response.get("usage", {})
            return usage.get("completion_tokens", 0)
        return 0

    def _extract_content(self, response: Any) -> str:
        """提取响应内容"""
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message"):
                return choice.message.content or ""
        if isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        if isinstance(response, str):
            return response
        return str(response)

    def get_session_stats(self, session_id: str) -> Dict:
        """获取会话的槽位使用统计"""
        return {
            "current_tier": self._session_tiers.get(session_id, SlotTier.DEFAULT).value,
            "extended_uses": self._session_extended_uses.get(session_id, 0),
            "consecutive_defaults": self._session_consecutive_defaults.get(session_id, 0),
        }

    def reset_session(self, session_id: str):
        """重置会话槽位状态"""
        self._session_tiers.pop(session_id, None)
        self._session_extended_uses.pop(session_id, None)
        self._session_default_uses.pop(session_id, None)
        self._session_consecutive_defaults.pop(session_id, None)
