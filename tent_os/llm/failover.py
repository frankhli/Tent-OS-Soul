"""LLM 故障转移包装器 —— OpenClaw 风格

支持：
1. 主 provider 异常时自动 fallback 到备用 provider
2. 错误分类：auth / billing / rate_limit / timeout / context_overflow / unknown
3. 失败 provider 冷却（避免连续重试同一失败 provider）

配置示例：
    llm:
      provider: kimi_coding
      api_key: sk-xxx
      model: kimi-k2.6
      fallbacks:
        - provider: openai_compatible
          api_key: sk-openai
          model: gpt-4o-mini
          base_url: https://api.openai.com/v1
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta

from tent_os.llm.provider import LLMProvider

logger = logging.getLogger("tent_os.llm.failover")


class FailoverLLM(LLMProvider):
    """带故障转移的 LLM 包装器"""
    
    # 冷却时间（秒）
    COOLDOWN_SECONDS = 60
    
    def __init__(self, primary: LLMProvider, fallbacks: List[LLMProvider], config: Dict = None):
        self.primary = primary
        self.fallbacks = fallbacks
        self.config = config or {}
        self._cooldowns: Dict[int, datetime] = {}  # provider index -> 冷却到期时间
        self._failure_counts: Dict[int, int] = {}
    
    @property
    def model_id(self) -> str:
        return self.primary.model_id
    
    def _classify_error(self, error: Exception) -> str:
        """分类错误类型"""
        msg = str(error).lower()
        if any(k in msg for k in ["authentication", "unauthorized", "invalid api key", "api key"]):
            return "auth"
        if any(k in msg for k in ["rate limit", "too many requests", "429"]):
            return "rate_limit"
        if any(k in msg for k in ["timeout", "timed out", "connecttimeout"]):
            return "timeout"
        if any(k in msg for k in ["billing", "quota", "insufficient_quota", "credit"]):
            return "billing"
        if any(k in msg for k in ["context length", "too long", "maximum context", "token"]):
            return "context_overflow"
        return "unknown"
    
    def _is_in_cooldown(self, idx: int) -> bool:
        if idx not in self._cooldowns:
            return False
        return datetime.now() < self._cooldowns[idx]
    
    def _mark_cooldown(self, idx: int, error_type: str):
        """根据错误类型设置冷却时间"""
        cooldown_map = {
            "auth": 300,      # 认证错误冷却 5 分钟
            "billing": 600,   # 额度错误冷却 10 分钟
            "rate_limit": 30, # 限流冷却 30 秒
            "timeout": 10,    # 超时冷却 10 秒
            "context_overflow": 0,  # 上下文溢出不冷却（换模型可能更好）
            "unknown": 30,
        }
        seconds = cooldown_map.get(error_type, 30)
        if seconds > 0:
            self._cooldowns[idx] = datetime.now() + timedelta(seconds=seconds)
            logger.warning(f"LLM provider #{idx} 进入冷却: {error_type} ({seconds}s)")
    
    async def _try_provider(self, idx: int, provider: LLMProvider, method: str, *args, **kwargs):
        """尝试调用单个 provider"""
        try:
            result = await getattr(provider, method)(*args, **kwargs)
            # 成功：重置失败计数
            self._failure_counts.pop(idx, None)
            return result
        except Exception as e:
            error_type = self._classify_error(e)
            self._failure_counts[idx] = self._failure_counts.get(idx, 0) + 1
            self._mark_cooldown(idx, error_type)
            logger.warning(f"LLM provider #{idx} ({provider.model_id}) 失败: {error_type} - {e}")
            raise
    
    async def _execute_with_failover(self, method: str, *args, **kwargs):
        """带故障转移的执行"""
        providers = [(0, self.primary)] + [(i + 1, p) for i, p in enumerate(self.fallbacks)]
        last_error = None
        
        for idx, provider in providers:
            if self._is_in_cooldown(idx):
                logger.debug(f"LLM provider #{idx} 冷却中，跳过")
                continue
            
            try:
                return await self._try_provider(idx, provider, method, *args, **kwargs)
            except Exception as e:
                last_error = e
                continue
        
        # 所有 provider 都失败
        raise last_error or RuntimeError("所有 LLM provider 均不可用")
    
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        return await self._execute_with_failover("chat", messages, **kwargs)
    
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        on_chunk: Callable,
        **kwargs
    ) -> str:
        return await self._execute_with_failover("chat_stream", messages, on_chunk, **kwargs)
    
    async def chat_stream_with_tools(self, messages, tools, on_chunk, on_tool_calls, **kwargs):
        return await self._execute_with_failover("chat_stream_with_tools", messages, tools, on_chunk, on_tool_calls, **kwargs)
    
    async def generate_plan(self, task: str, tools: List[Dict], extra_context: str = "") -> Dict:
        return await self._execute_with_failover("generate_plan", task, tools, extra_context=extra_context)
    
    async def chat_with_tools(self, messages: List[Dict], tools: List[Dict], **kwargs) -> Dict:
        """Tool Loop 用的 chat_with_tools（非 LLMProvider 标准接口，但所有实现都有）"""
        providers = [(0, self.primary)] + [(i + 1, p) for i, p in enumerate(self.fallbacks)]
        last_error = None
        
        for idx, provider in providers:
            if self._is_in_cooldown(idx):
                continue
            if not hasattr(provider, "chat_with_tools"):
                continue
            try:
                result = await provider.chat_with_tools(messages, tools, **kwargs)
                self._failure_counts.pop(idx, None)
                return result
            except Exception as e:
                last_error = e
                self._failure_counts[idx] = self._failure_counts.get(idx, 0) + 1
                self._mark_cooldown(idx, self._classify_error(e))
                continue
        
        raise last_error or RuntimeError("所有 LLM provider 均不支持 chat_with_tools 或已失败")
    
    def get_status(self) -> Dict:
        """获取故障转移状态"""
        providers = [self.primary] + self.fallbacks
        return {
            "primary": self.primary.model_id,
            "fallbacks": [p.model_id for p in self.fallbacks],
            "cooldowns": {
                i: self._cooldowns[i].isoformat() if i in self._cooldowns else None
                for i in range(len(providers))
            },
            "failure_counts": self._failure_counts.copy(),
        }
