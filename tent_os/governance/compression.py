"""5层上下文压缩管道 — Claude Code 模式融合

核心洞察：按成本从低到高执行，只有前面的层无法解决问题时才触发后面的层。
这样可以大幅减少 LLM 调用次数。

5层压缩：
L1: Budget Reduction - 单条消息截断（零成本，always active）
L2: Snip - 截断老历史（零成本，feature-gated）
L3: Microcompact - 缓存感知的细粒度压缩（低成本，always active）
L4: Context Collapse - 只读虚拟投影（中成本，feature-gated）
L5: Auto-Compact - 模型生成摘要（高成本，all-else-fails）

Tent OS 差异化：
- 跨进程压缩 - 治理进程压缩对话历史，记忆进程压缩长期记忆
- WorkingMemory 作为 L3 的核心载体（7+/-2 chunk）
- tiktoken 精确计数（替代字符数粗估）
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any

import tiktoken

from tent_os.logging_config import get_logger

logger = get_logger()


class TokenCounter:
    """精确的 token 计数器"""

    def __init__(self, model: str = "cl100k_base"):
        try:
            self.encoder = tiktoken.get_encoding(model)
        except Exception:
            self.encoder = None

    def count(self, text: str) -> int:
        """计算文本的 token 数"""
        if self.encoder:
            return len(self.encoder.encode(text))
        # 降级：字符数 / 3（中文约2 chars/token，英文约4 chars/token）
        return len(text) // 3 + 1

    def count_messages(self, messages: List[Dict]) -> int:
        """计算消息列表的总 token 数（含格式开销）"""
        total = 0
        for msg in messages:
            # 每条消息格式开销 ~4 tokens (role + delimiters)
            total += 4
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count(content)
            elif isinstance(content, list):
                # 多模态内容
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += self.count(part.get("text", ""))
        # 初始提示开销
        total += 2
        return total


class ContextCompressionPipeline:
    """5层上下文压缩管道

    使用方式：
        pipeline = ContextCompressionPipeline(llm=llm_client)
        compressed = await pipeline.compress(messages, max_tokens=6000)
    """

    def __init__(self, llm: Optional[Any] = None,
                 counter: Optional[TokenCounter] = None,
                 config: Dict[str, Any] = None):
        self.llm = llm
        self.counter = counter or TokenCounter()
        self.config = config or {}

        # 各层配置
        self.l1_max_content_tokens = self.config.get("l1_max_content_tokens", 4000)
        self.l2_keep_recent = self.config.get("l2_keep_recent", 16)
        self.l3_enabled = self.config.get("l3_enabled", True)
        self.l4_enabled = self.config.get("l4_enabled", True)
        self.l5_enabled = self.config.get("l5_enabled", True)
        self.l5_max_per_session = self.config.get("l5_max_per_session", 1)

        # 追踪 L5 触发次数（每会话）
        self._l5_trigger_count: Dict[str, int] = {}

    async def compress(self, messages: List[Dict],
                       max_tokens: int = 6000,
                       session_id: str = "",
                       working_memory_text: str = "") -> List[Dict]:
        """执行5层压缩管道

        Args:
            messages: 原始消息列表
            max_tokens: 目标最大 token 数
            session_id: 会话ID（用于 L5 触发计数）
            working_memory_text: WorkingMemory 上下文文本（用于 L3）

        Returns:
            压缩后的消息列表
        """
        original_tokens = self.counter.count_messages(messages)
        if original_tokens <= max_tokens:
            return messages

        logger.info(f"[COMPRESS] 开始压缩 [{session_id}]: {original_tokens} tokens -> {max_tokens} target")
        start_time = time.time()

        current = [m.copy() for m in messages]

        # L1: Budget Reduction - 单条消息截断
        current = self._budget_reduce(current, max_tokens)
        tokens = self.counter.count_messages(current)
        if tokens <= max_tokens:
            logger.info(f"[COMPRESS] L1 完成 [{session_id}]: {tokens} tokens ({time.time()-start_time:.2f}s)")
            return current

        # L2: Snip - 截断老历史
        current = self._snip_old_history(current, max_tokens)
        tokens = self.counter.count_messages(current)
        if tokens <= max_tokens:
            logger.info(f"[COMPRESS] L2 完成 [{session_id}]: {tokens} tokens ({time.time()-start_time:.2f}s)")
            return current

        # L3: Microcompact - 工作记忆压缩
        if self.l3_enabled:
            current = self._microcompact(current, working_memory_text, max_tokens)
            tokens = self.counter.count_messages(current)
            if tokens <= max_tokens:
                logger.info(f"[COMPRESS] L3 完成 [{session_id}]: {tokens} tokens ({time.time()-start_time:.2f}s)")
                return current

        # L4: Context Collapse - 非破坏性投影
        if self.l4_enabled:
            current = self._context_collapse(current, max_tokens)
            tokens = self.counter.count_messages(current)
            if tokens <= max_tokens:
                logger.info(f"[COMPRESS] L4 完成 [{session_id}]: {tokens} tokens ({time.time()-start_time:.2f}s)")
                return current

        # L5: Auto-Compact - LLM 生成摘要（最后手段）
        if self.l5_enabled and self.llm:
            trigger_count = self._l5_trigger_count.get(session_id, 0)
            if trigger_count < self.l5_max_per_session:
                current = await self._auto_compact(current, max_tokens, session_id)
                self._l5_trigger_count[session_id] = trigger_count + 1
                tokens = self.counter.count_messages(current)
                logger.info(f"[COMPRESS] L5 完成 [{session_id}]: {tokens} tokens ({time.time()-start_time:.2f}s)")
                return current

        # 所有层都失败了，强制截断到最近 N 条
        current = self._emergency_truncate(current, max_tokens)
        tokens = self.counter.count_messages(current)
        logger.warning(f"[COMPRESS] 紧急截断 [{session_id}]: {tokens} tokens")
        return current

    # ========== L1: Budget Reduction ==========

    def _budget_reduce(self, messages: List[Dict], max_tokens: int) -> List[Dict]:
        """L1 - 单条消息内容截断

        策略：
        - 保留 system prompt 完整
        - 用户和 assistant 消息如果太长，截断到预算内
        - 工具结果消息如果太长，截断并标记
        """
        result = []
        for msg in messages:
            msg_copy = msg.copy()
            content = msg_copy.get("content", "")

            if not isinstance(content, str):
                result.append(msg_copy)
                continue

            role = msg_copy.get("role", "")

            # System prompt 不截断（通常是最关键的指令）
            if role == "system":
                result.append(msg_copy)
                continue

            # 工具结果截断（通常最冗余）
            if role == "tool" or isinstance(content, dict):
                truncated = self._truncate_content(content, self.l1_max_content_tokens * 2)
                msg_copy["content"] = truncated
                result.append(msg_copy)
                continue

            # 普通消息截断
            tokens = self.counter.count(content)
            if tokens > self.l1_max_content_tokens:
                truncated = self._truncate_content(content, self.l1_max_content_tokens)
                msg_copy["content"] = truncated

            result.append(msg_copy)

        return result

    # ========== L2: Snip ==========

    def _snip_old_history(self, messages: List[Dict], max_tokens: int) -> List[Dict]:
        """L2 - 截断老历史，保留最近 N 条

        策略：
        - 保留 system prompt
        - 保留最近 l2_keep_recent 条对话
        - 更早的消息压缩为占位符
        """
        if len(messages) <= self.l2_keep_recent + 1:  # +1 for system
            return messages

        # 分离 system prompt
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # 保留最近 N 条
        keep = non_system[-self.l2_keep_recent:]
        dropped = non_system[:-self.l2_keep_recent]

        if dropped:
            # 统计丢弃的消息
            user_count = sum(1 for m in dropped if m.get("role") == "user")
            assistant_count = sum(1 for m in dropped if m.get("role") == "assistant")
            tool_count = sum(1 for m in dropped if m.get("role") == "tool")

            summary = f"[历史消息已折叠: {user_count} 用户消息, {assistant_count} AI回复, {tool_count} 工具结果]"
            placeholder = {
                "role": "user",
                "content": summary,
            }
            return system_msgs + [placeholder] + keep

        return messages

    # ========== L3: Microcompact ==========

    def _microcompact(self, messages: List[Dict],
                      working_memory_text: str,
                      max_tokens: int) -> List[Dict]:
        """L3 - 缓存感知的细粒度压缩

        策略：
        - 利用 WorkingMemory 的 7+/-2 chunk 作为压缩锚点
        - 将重复出现的主题/实体折叠为引用
        - 长工具结果进一步截断
        """
        result = []

        # 如果有 WorkingMemory，将其作为压缩上下文注入
        if working_memory_text:
            # 检查是否已有 system prompt
            has_system = any(m.get("role") == "system" for m in messages)
            if has_system:
                # 在第一条 system prompt 后追加工作记忆
                for i, msg in enumerate(messages):
                    if msg.get("role") == "system":
                        content = msg.get("content", "")
                        if working_memory_text not in content:
                            msg_copy = msg.copy()
                            msg_copy["content"] = content + f"\n\n[工作记忆上下文]\n{working_memory_text}"
                            result.append(msg_copy)
                        else:
                            result.append(msg)
                    else:
                        result.append(msg)
            else:
                result = messages
        else:
            result = messages

        # 对超长工具结果进行激进截断
        for msg in result:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 3000:
                # 检测是否是工具结果（通常包含大量结构化数据）
                if content.startswith("{") or content.startswith("[") or "result" in content[:100]:
                    msg["content"] = self._aggressive_truncate(content, 1500)

        return result

    # ========== L4: Context Collapse ==========

    def _context_collapse(self, messages: List[Dict], max_tokens: int) -> List[Dict]:
        """L4 - 只读虚拟投影（非破坏性）

        策略：
        - 将多轮对话折叠为"用户意图摘要 + 最终状态"
        - 不删除消息，而是替换为更紧凑的表示
        - 保留工具调用的最终结果，丢弃中间思考过程
        """
        if len(messages) <= 3:
            return messages

        # 分离 system prompt
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= 4:
            return messages

        # 保留第一条用户消息（通常包含核心意图）和最后2条
        first_user = None
        for m in non_system:
            if m.get("role") == "user":
                first_user = m
                break

        recent = non_system[-2:]

        # 中间部分折叠
        middle = non_system[1:-2] if first_user else non_system[:-2]

        # 提取中间部分的关键信息
        tool_results = []
        user_queries = []
        for m in middle:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "tool":
                # 只保留工具结果的摘要
                tool_results.append(self._extract_tool_summary(content))
            elif role == "user" and isinstance(content, str):
                user_queries.append(content[:100])

        collapse_parts = []
        if user_queries:
            collapse_parts.append(f"中间对话中用户的要求: {'; '.join(user_queries[:3])}")
        if tool_results:
            collapse_parts.append(f"已执行的工具: {'; '.join(tool_results[:5])}")

        if collapse_parts:
            collapsed = {
                "role": "assistant",
                "content": f"[对话上下文折叠]\n" + "\n".join(collapse_parts),
            }
            collapsed_list = [collapsed]
        else:
            collapsed_list = []

        result = system_msgs[:]
        if first_user:
            result.append(first_user)
        result.extend(collapsed_list)
        result.extend(recent)

        return result

    # ========== L5: Auto-Compact ==========

    async def _auto_compact(self, messages: List[Dict],
                            max_tokens: int,
                            session_id: str) -> List[Dict]:
        """L5 - LLM 生成摘要（最后手段，每轮最多1次）

        策略：
        - 将早期对话发送给 LLM 生成结构化摘要
        - 摘要以 system prompt 形式注入
        - 保留最近 4 条消息不变
        """
        if len(messages) <= 6 or not self.llm:
            return messages

        # 分离 system prompt 和最近 4 条
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        split_point = max(len(non_system) - 4, len(non_system) // 2)
        early = non_system[:split_point]
        recent = non_system[split_point:]

        # 格式化早期消息
        msg_texts = []
        for m in early:
            role = m.get("role", "")
            content = m.get("content", "")
            if isinstance(content, str):
                msg_texts.append(f"[{role}]: {content[:400]}")
            else:
                msg_texts.append(f"[{role}]: [非文本内容]")

        summary_prompt = f"""请用中文总结以下对话的核心内容（200字以内）：

{chr(10).join(msg_texts)}

要求：
1. 一句话概述对话主题
2. 列出关键事实、决策和用户偏好
3. 保留任何需要后续跟进的事项
只输出总结内容，不要解释。"""

        try:
            logger.info(f"[COMPRESS] L5 触发 LLM 摘要 [{session_id}]")

            if hasattr(self.llm, "chat"):
                summary = await self.llm.chat([
                    {"role": "system", "content": "你是一个对话摘要专家，擅长提取关键信息。"},
                    {"role": "user", "content": summary_prompt},
                ])
            else:
                summary = await self.llm(summary_prompt)

            summary = summary.strip()[:800]  # 限制摘要长度

            # 构建摘要消息
            summary_msg = {
                "role": "assistant",
                "content": f"[早期对话摘要]\n{summary}",
            }

            return system_msgs + [summary_msg] + recent

        except Exception as e:
            logger.warning(f"[COMPRESS] L5 LLM 摘要失败 [{session_id}]: {e}")
            # 降级：简单截断
            return system_msgs + recent

    # ========== Emergency Truncate ==========

    def _emergency_truncate(self, messages: List[Dict], max_tokens: int) -> List[Dict]:
        """紧急截断——保留 system + 最近消息，直到在预算内"""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # 从最近开始保留
        keep = []
        total = self.counter.count_messages(system_msgs)

        for msg in reversed(non_system):
            msg_tokens = self.counter.count_messages([msg])
            if total + msg_tokens > max_tokens and keep:
                break
            total += msg_tokens
            keep.insert(0, msg)

        return system_msgs + keep

    # ========== 辅助方法 ==========

    def _truncate_content(self, content: Any, max_tokens: int) -> str:
        """截断内容到指定 token 数"""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)

        tokens = self.counter.count(content)
        if tokens <= max_tokens:
            return content

        # 二分查找截断点
        left, right = 0, len(content)
        while left < right:
            mid = (left + right) // 2
            truncated = content[:mid]
            if self.counter.count(truncated) <= max_tokens:
                left = mid + 1
            else:
                right = mid

        # 在段落边界截断
        truncated = content[:left]
        for boundary in ["\n\n", "\n", "。", "！", "？", ". ", "! ", "? "]:
            idx = truncated.rfind(boundary)
            if idx > len(truncated) * 0.5:
                truncated = truncated[:idx + len(boundary)]
                break

        return truncated + f" [...截断，原 {tokens} tokens]"

    def _aggressive_truncate(self, content: str, max_chars: int) -> str:
        """激进截断——用于工具结果"""
        if len(content) <= max_chars:
            return content

        # 尝试解析 JSON 并截断长字段
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                self._truncate_dict_values(data, max_chars // 2)
                return json.dumps(data, ensure_ascii=False)
        except Exception:
            pass

        return content[:max_chars] + f" [...截断，原 {len(content)} 字符]"

    def _truncate_dict_values(self, obj: Any, max_value_len: int):
        """递归截断字典中的长字符串值"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and len(v) > max_value_len:
                    obj[k] = v[:max_value_len] + " [...截断]"
                elif isinstance(v, (dict, list)):
                    self._truncate_dict_values(v, max_value_len)
        elif isinstance(obj, list):
            for item in obj:
                self._truncate_dict_values(item, max_value_len)

    def _extract_tool_summary(self, content: str) -> str:
        """从工具结果中提取摘要"""
        if not isinstance(content, str):
            return "[非文本结果]"

        # 尝试提取关键信息
        lines = content.split("\n")
        # 取前3行非空行
        non_empty = [l for l in lines if l.strip()][:3]
        if non_empty:
            summary = " | ".join(non_empty)
            return summary[:100]
        return "[工具结果]"
