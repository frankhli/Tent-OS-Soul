"""上下文组装管道 —— 参考 Claude Code 的 assemble() 设计

组装顺序（与 Claude Code 一致）：
1. System Prompt（人格 + 规则 + 工作记忆 + 相关记忆）
2. Tool Schemas（通过 tools 参数传入，不在此处组装）
3. Conversation History（经 5 层压缩管道）
4. Current User Message

核心原则：
- Context Engineering > Prompt Engineering
- 精确 tiktoken 计数，不粗估
- 保护 tool_call / tool_result 消息对的完整性
- 不过早压缩（Kimi K2.6 256K 窗口，context rot 在 50K-150K 开始）
"""

import json
import time
from typing import Dict, List, Optional, Any, Tuple

from tent_os.governance.compression import ContextCompressionPipeline, TokenCounter
from tent_os.logging_config import get_logger

logger = get_logger()


# 参考 Claude Code 的上下文策略
DEFAULT_MAX_CONTEXT_TOKENS = 120_000   # Kimi K2.6 256K 窗口，留 136K 给回复
DEFAULT_MAX_OUTPUT_TOKENS = 8_000      # 中文回复需要更多（原 4096 不够）
L2_KEEP_RECENT = 32                    # 保留最近 32 条消息（原 16 太少）
L1_MAX_CONTENT_TOKENS = 8_000          # 单条消息截断阈值（原 4000 对中文不够）
MEMORY_INJECT_MAX_TOKENS = 4_000       # 注入记忆的最大 token 数


class ContextAssemblyPipeline:
    """上下文组装管道

    将分散的上下文来源整合为 LLM 可用的 messages 列表。
    与 Claude Code 的 assemble() 对应。
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        compression_pipeline: Optional[ContextCompressionPipeline] = None,
        token_counter: Optional[TokenCounter] = None,
        config: Optional[Dict] = None,
    ):
        self.llm = llm
        self.config = config or {}
        self.counter = token_counter or TokenCounter()
        # 复用已有的 5 层压缩管道，但调整参数以匹配主流实践
        compression_cfg = {
            "l1_max_content_tokens": self.config.get(
                "l1_max_content_tokens", L1_MAX_CONTENT_TOKENS
            ),
            "l2_keep_recent": self.config.get(
                "l2_keep_recent", L2_KEEP_RECENT
            ),
            "l3_enabled": self.config.get("l3_enabled", True),
            "l4_enabled": self.config.get("l4_enabled", True),
            "l5_enabled": self.config.get("l5_enabled", True),
            "l5_max_per_session": self.config.get("l5_max_per_session", 1),
        }
        self.compression = compression_pipeline or ContextCompressionPipeline(
            llm=llm,
            counter=self.counter,
            config=compression_cfg,
        )

    async def assemble(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        conversation_history: List[Dict],
        system_prompt_base: str = "",
        persona_hint: str = "",
        mode_fragment: str = "",
        working_memory_text: str = "",
        relevant_memories: Optional[List[Dict]] = None,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> List[Dict]:
        """组装完整的 LLM 上下文

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            user_message: 当前用户消息
            conversation_history: 完整对话历史（含 tool_call/tool_result）
            system_prompt_base: 基础 system prompt
            persona_hint: 人格画像片段
            mode_fragment: 模式路由器片段
            working_memory_text: WorkingMemory 上下文文本
            relevant_memories: 向量搜索召回的相关记忆
            max_context_tokens: 上下文 token 上限（默认 120K）

        Returns:
            组装好的 messages 列表，可直接传给 LLM
        """
        start_time = time.time()

        # ========== 1. 构建 System Prompt ==========
        system_prompt = self._build_system_prompt(
            base=system_prompt_base,
            persona_hint=persona_hint,
            mode_fragment=mode_fragment,
            working_memory_text=working_memory_text,
            relevant_memories=relevant_memories,
        )

        # ========== 2. 准备对话历史 ==========
        # 过滤掉空消息，保护 tool_call/tool_result 对
        history = self._sanitize_history(conversation_history)

        # ========== 3. 组装完整消息列表（尚未压缩）==========
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # ========== 4. 精确计数 ==========
        original_tokens = self.counter.count_messages(messages)
        logger.info(
            f"[ASSEMBLE] [{session_id}] 原始上下文: {original_tokens} tokens, "
            f"历史 {len(history)} 条, 记忆 {len(relevant_memories or [])} 条"
        )

        # ========== 5. 5 层压缩（仅在超过阈值时）==========
        if original_tokens > max_context_tokens:
            logger.warning(
                f"[ASSEMBLE] [{session_id}] 上下文超限: {original_tokens} > {max_context_tokens}, "
                f"触发 5 层压缩"
            )
            messages = await self.compression.compress(
                messages=messages,
                max_tokens=max_context_tokens,
                session_id=session_id,
                working_memory_text=working_memory_text,
            )
            compressed_tokens = self.counter.count_messages(messages)
            logger.info(
                f"[ASSEMBLE] [{session_id}] 压缩后: {compressed_tokens} tokens "
                f"({time.time() - start_time:.2f}s)"
            )
        else:
            logger.info(
                f"[ASSEMBLE] [{session_id}] 无需压缩 ({time.time() - start_time:.2f}s)"
            )

        return messages

    def _build_system_prompt(
        self,
        base: str,
        persona_hint: str = "",
        mode_fragment: str = "",
        working_memory_text: str = "",
        relevant_memories: Optional[List[Dict]] = None,
    ) -> str:
        """构建 System Prompt

        组装顺序（重要性从高到低）：
        1. 基础指令（base）
        2. 模式片段（mode_fragment）
        3. 人格画像（persona_hint）
        4. 工作记忆（working_memory_text）
        5. 相关记忆（relevant_memories）
        """
        parts = []

        if base and base.strip():
            parts.append(base.strip())

        if mode_fragment and mode_fragment.strip():
            parts.append(mode_fragment.strip())

        if persona_hint and persona_hint.strip():
            parts.append(persona_hint.strip())

        if working_memory_text and working_memory_text.strip():
            parts.append(working_memory_text.strip())

        # 相关记忆：格式化召回的记忆，限制 token 数
        if relevant_memories:
            memory_text = self._format_memories(relevant_memories)
            if memory_text:
                parts.append(memory_text)

        return "\n\n".join(parts)

    def _format_memories(self, memories: List[Dict]) -> str:
        """将记忆格式化为 prompt 文本，限制 token 数"""
        if not memories:
            return ""

        lines = ["## 相关记忆（自动召回）"]
        total_tokens = 0

        for mem in memories:
            abstract = mem.get("abstract", "")
            overview = mem.get("overview", "")
            uri = mem.get("uri", "")
            score = mem.get("score", 0)

            # 优先使用 L1 概览， fallback 到 L0 摘要
            content = overview if overview else abstract
            if not content:
                continue

            # 限制单条记忆长度
            content = content[:500]
            line = f"- [{score:.2f}] {content}"
            line_tokens = self.counter.count(line)

            if total_tokens + line_tokens > MEMORY_INJECT_MAX_TOKENS:
                lines.append("...（更多记忆已省略）")
                break

            lines.append(line)
            total_tokens += line_tokens

        if len(lines) == 1:
            # 只有标题，没有实际内容
            return ""

        return "\n".join(lines)

    def _sanitize_history(self, history: List[Dict]) -> List[Dict]:
        """清理对话历史，保护 tool_call/tool_result 对的完整性

        策略：
        - 移除空内容消息（保留结构）
        - 确保每条 tool_result 都有对应的 tool_call
        - 不修改消息内容（压缩由 ContextCompressionPipeline 处理）
        """
        if not history:
            return []

        # 收集所有有效的 tool_call_id
        valid_tool_call_ids = set()
        for msg in history:
            if msg.get("role") == "assistant":
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    tc_id = tc.get("id") or tc.get("tool_call_id")
                    if tc_id:
                        valid_tool_call_ids.add(tc_id)

        sanitized = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # 跳过完全空的消息（但保留 tool_call 消息，即使 content 为空）
            if role == "assistant" and msg.get("tool_calls"):
                sanitized.append(dict(msg))
                continue

            if role == "tool":
                # 检查 tool_call_id 是否有效
                tc_id = msg.get("tool_call_id", "")
                if tc_id and tc_id not in valid_tool_call_ids:
                    logger.debug(f"[ASSEMBLE] 丢弃孤立的 tool_result: {tc_id}")
                    continue
                sanitized.append(dict(msg))
                continue

            # 普通消息：保留非空的
            if content or msg.get("tool_calls"):
                sanitized.append(dict(msg))

        return sanitized

    def estimate_tokens(self, messages: List[Dict]) -> int:
        """估算 messages 的总 token 数"""
        return self.counter.count_messages(messages)

    def get_context_budget(self, messages: List[Dict], max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS) -> Dict:
        """获取上下文预算使用情况"""
        used = self.counter.count_messages(messages)
        return {
            "used": used,
            "max": max_tokens,
            "remaining": max(0, max_tokens - used),
            "percent": round(used / max_tokens * 100, 1),
            "needs_compression": used > max_tokens,
        }
