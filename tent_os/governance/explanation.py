"""解释生成器（Explanation Generator）

为每条 AI 回复生成一句简短解释："为什么这样回应？"
让用户理解 AI 的决策逻辑，增强双向透明。
"""

import time
import json
from typing import Dict, List, Optional

from tent_os.logging_config import get_logger

logger = get_logger()


class ExplanationGenerator:
    """解释生成器 —— 用一句话解释 AI 为什么这样回应"""

    def __init__(self, llm, config: Optional[Dict] = None):
        self.llm = llm
        self.config = config or {}
        self.enabled = self.config.get("transparency", {}).get("explanation", {}).get("enabled", True)
        self.max_length = self.config.get("transparency", {}).get("explanation", {}).get("max_length", 100)
        # 缓存：避免重复生成
        self._cache: Dict[str, str] = {}

    def _cache_key(self, session_id: str, response: str) -> str:
        return f"{session_id}:{hash(response) & 0xFFFFFF}"

    async def explain(
        self,
        session_id: str,
        user_message: str,
        response: str,
        tools_used: List[str],
        reasoning: str,
    ) -> str:
        """生成解释。返回空字符串如果禁用或失败。"""
        if not self.enabled or not self.llm:
            return ""

        cache_key = self._cache_key(session_id, response)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            # 构建轻量 prompt
            tools_hint = ""
            if tools_used:
                tools_hint = f"使用了工具: {', '.join(tools_used[:3])}。"
            
            system_prompt = (
                "你是 Tent OS 的透明化模块。用一句话（不超过30字）诚实地解释："
                "为什么刚才这样回应用户？要具体，不要套话。"
                f"\n用户问题: {user_message[:80]}"
                f"\n你的回应: {response[:120]}"
                f"\n{tools_hint}"
                "\n解释:"
            )

            messages = [{"role": "system", "content": system_prompt}]
            
            resp = await self.llm.chat(messages, temperature=0.5, max_tokens=80)
            if hasattr(resp, 'content'):
                explanation = resp.content.strip()
            elif isinstance(resp, str):
                explanation = resp.strip()
            else:
                explanation = str(resp).strip()
            
            # 清理引号
            explanation = explanation.strip('"\'')
            
            if len(explanation) > self.max_length:
                explanation = explanation[:self.max_length] + "..."
            
            self._cache[cache_key] = explanation
            logger.debug(f"[EXPLAIN] 解释生成 [{session_id}]: {explanation}")
            return explanation
            
        except Exception as e:
            logger.debug(f"[EXPLAIN] 解释生成失败 [{session_id}]: {e}")
            return ""

    def clear_cache(self, session_id: str):
        """清除指定 session 的缓存"""
        keys = [k for k in self._cache if k.startswith(session_id + ":")]
        for k in keys:
            self._cache.pop(k, None)
