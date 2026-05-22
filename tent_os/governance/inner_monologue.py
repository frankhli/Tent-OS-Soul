"""内心独白生成器（Inner Monologue Generator）

在 AI 回应用户之前，生成一段简短的"内心想法"，
通过 NATS 流式推送到前端，让用户看到 AI 的"思考过程"。

与 LLM 原生的 reasoning 不同：
- reasoning 是模型内部的 CoT（Chain of Thought）
- inner_monologue 是独立的轻量生成，更像"日记体"内心独白
"""

import time
import json
from typing import Dict, List, Optional

from tent_os.logging_config import get_logger

logger = get_logger()


class InnerMonologueGenerator:
    """内心独白生成器"""

    def __init__(self, llm, config: Optional[Dict] = None):
        self.llm = llm
        self.config = config or {}
        self.enabled = self.config.get("transparency", {}).get("inner_monologue", {}).get("enabled", True)
        self.max_length = self.config.get("transparency", {}).get("inner_monologue", {}).get("max_length", 120)

    async def generate(self, session_id: str, llm_messages: List[Dict], state: Dict, bus) -> str:
        """生成内心独白，流式输出到 NATS
        
        Args:
            session_id: 会话ID
            llm_messages: 已组装好的 LLM 消息列表
            state: 会话状态
            bus: 消息总线，用于流式推送
            
        Returns:
            完整的内心独白文本
        """
        if not self.enabled or not self.llm:
            return ""

        try:
            # 提取用户最后一条消息和当前情绪
            user_msgs = [m for m in llm_messages if m.get("role") == "user"]
            last_user_msg = user_msgs[-1]["content"][:100] if user_msgs else ""
            
            emotion = state.get("emotion", "listening")
            persona = state.get("persona", "work")
            
            # 轻量 prompt：让 AI 以第一人称写日记式的内心独白
            system_prompt = (
                "你是 Tent OS 的内心世界。用第一人称，简短写下你对当前对话的真实想法。"
                "不超过3句话。语气自然、真诚，像日记一样。"
                f"\n当前情绪: {emotion}"
                f"\n当前人格: {persona}"
                f"\n用户最后说: {last_user_msg}"
                "\n你的内心独白:"
            )

            messages = [{"role": "system", "content": system_prompt}]
            
            full_text = ""
            chunk_buffer = ""
            
            # 调用 LLM（非流式，因为内心独白很短）
            response = await self.llm.chat(messages, temperature=0.8, max_tokens=150)
            if hasattr(response, 'content'):
                full_text = response.content
            elif isinstance(response, str):
                full_text = response
            else:
                full_text = str(response)
            
            # 截断到最大长度
            if len(full_text) > self.max_length:
                full_text = full_text[:self.max_length] + "..."
            
            # 流式模拟：逐字推送（营造"实时思考"的感觉）
            if bus and full_text:
                for i, char in enumerate(full_text):
                    chunk_buffer += char
                    # 每 3-5 个字符推送一次，带随机间隔感
                    if i % 4 == 0 or i == len(full_text) - 1:
                        try:
                            await bus.publish_raw(
                                f"governance.stream.monologue.{session_id}",
                                json.dumps({
                                    "session_id": session_id,
                                    "chunk": chunk_buffer,
                                    "done": i == len(full_text) - 1,
                                }).encode()
                            )
                        except Exception:
                            pass
                        chunk_buffer = ""
            
            logger.debug(f"[MONOLOGUE] 内心独白生成完成 [{session_id}]: {full_text[:50]}...")
            return full_text
            
        except Exception as e:
            logger.debug(f"[MONOLOGUE] 内心独白生成失败 [{session_id}]: {e}")
            return ""
