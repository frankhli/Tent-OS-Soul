"""Agent Loop —— 真流式对话引擎

核心设计（参考 Claude Code + LangGraph）：
```
while not done:
    context = assemble()           # ContextAssemblyPipeline
    action = model(context, tools) # chat_stream_with_tools（真流式）
    if action.is_text_only():
        done = True
        continue
    if not permitted(action):      # Security Pipeline
        continue
    result = execute(action)       # ToolExecutor + MCP Gateway
    history.append(action, result)
```

与旧 _handle_fast_chat 的关键差异：
1. 真流式：chunk 从 LLM API 直接流到前端，不等待完整回复
2. 高安全上限：max_rounds=50（LLM 自终止 via stop_reason="end_turn"）
3. 认知预算：3600秒，耗尽时转入后台续跑
4. 工具结果缓存：避免 LLM 绕圈子重复执行
5. 进度心跳：每 30 秒通知用户系统仍在工作
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Callable, Set

from fastapi import WebSocket

from tent_os.agent.context_assembly import (
    ContextAssemblyPipeline,
    DEFAULT_MAX_CONTEXT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
)
from tent_os.logging_config import get_logger

logger = get_logger()

# 安全上限（参考 Claude Code 不设硬上限，但服务端需要兜底）
MAX_TOOL_ROUNDS = 50
# 认知预算（秒）—— 长任务支持
DEFAULT_COGNITIVE_BUDGET_SECONDS = 3600.0
# 进度心跳间隔（秒）
PROGRESS_HEARTBEAT_SECONDS = 30
# 流式 chunk 批量缓冲（减少 WS 发送次数）
STREAM_BUFFER_SIZE = 50
STREAM_BUFFER_TIMEOUT = 0.5


class AgentLoop:
    """Agent 对话循环"""

    def __init__(
        self,
        llm: Any,
        context_assembler: ContextAssemblyPipeline,
        tool_executor: Any,
        mcp_gateway: Optional[Any] = None,
        state_store: Optional[Any] = None,
        security_pipeline: Optional[Any] = None,
        hook_engine: Optional[Any] = None,
        speculative_executor: Optional[Any] = None,
        config: Optional[Dict] = None,
    ):
        self.llm = llm
        self.context_assembler = context_assembler
        self.tool_executor = tool_executor
        self.mcp_gateway = mcp_gateway
        self.state_store = state_store
        self.security = security_pipeline
        self.hooks = hook_engine
        self.speculative = speculative_executor
        self.config = config or {}

        # 工具结果缓存：避免 LLM 重复执行相同操作（绕圈子）
        self._tool_result_cache: Dict[str, Dict] = {}
        # 每轮迭代的工具执行历史
        self._tool_execution_history: List[str] = []

        # 认知预算（支持热更新）
        self._cognitive_budget = self.config.get(
            "cognitive_budget_seconds", DEFAULT_COGNITIVE_BUDGET_SECONDS
        )

    async def run(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        websocket: Any,  # WebSocket or ws_manager wrapper
        capabilities: Optional[Dict] = None,
        deep_thinking: bool = False,
        system_prompt_base: str = "",
        persona_hint: str = "",
        mode_fragment: str = "",
        working_memory_text: str = "",
        relevant_memories: Optional[List[Dict]] = None,
        conversation_history: Optional[List[Dict]] = None,
        on_chunk: Optional[Callable[[str, str], None]] = None,
        on_tool_call: Optional[Callable[[Dict], None]] = None,
        on_tool_result: Optional[Callable[[Dict], None]] = None,
        on_complete: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """执行一轮完整的 Agent 对话

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            user_message: 当前用户消息
            websocket: WebSocket 连接（用于发送流式 chunk）
            capabilities: 用户启用的工具能力
            deep_thinking: 是否启用深度思考（影响 temperature）
            system_prompt_base: 基础 system prompt
            persona_hint: 人格画像片段
            mode_fragment: 模式路由器片段
            working_memory_text: WorkingMemory 上下文
            relevant_memories: 向量搜索召回的记忆
            conversation_history: 已有对话历史
            on_chunk: 流式 chunk 回调 (text, chunk_type)
            on_tool_call: 工具调用回调
            on_tool_result: 工具结果回调
            on_complete: 完成回调

        Returns:
            {"content": str, "reasoning": str, "tool_calls": List, "elapsed_ms": int}
        """
        start_time = time.time()
        capabilities = capabilities or {}
        loop_start_time = time.time()
        _background_notified = False

        # ========== 0. 安全评估（System 1 + System 2）==========
        if self.security:
            try:
                assessment = await self.security.assess(session_id, user_message)
                if assessment.safety_level in ("dangerous", "critical") and assessment.confidence > 0.95:
                    refusal_msg = (
                        f"🛡️ 安全拦截\n\n"
                        f"原因：{assessment.reasoning}\n\n"
                        f"该请求已被自动拦截。如涉及误判，请联系系统管理员。"
                    )
                    if on_chunk:
                        on_chunk(refusal_msg, "content")
                    return {
                        "content": refusal_msg,
                        "reasoning": "",
                        "tool_calls": [],
                        "elapsed_ms": int((time.time() - start_time) * 1000),
                        "tool_rounds": 0,
                    }
            except Exception as e:
                logger.warning(f"[AGENT] 安全评估异常 [{session_id}]: {e}")

        # ========== 1. 组装上下文 ==========
        history = conversation_history or []
        messages = await self.context_assembler.assemble(
            session_id=session_id,
            user_id=user_id,
            user_message=user_message,
            conversation_history=history,
            system_prompt_base=system_prompt_base,
            persona_hint=persona_hint,
            mode_fragment=mode_fragment,
            working_memory_text=working_memory_text,
            relevant_memories=relevant_memories,
            max_context_tokens=DEFAULT_MAX_CONTEXT_TOKENS,
        )

        # ========== 2. 获取工具列表 ==========
        tools = await self._get_tools(capabilities, session_id)
        has_tools = bool(tools)

        # ========== 2.1 Hook: tool.assemble ==========
        if self.hooks:
            try:
                hook_result = await self.hooks.trigger(
                    "tool.assemble",
                    session_id=session_id,
                    data={"tools": tools, "count": len(tools)},
                )
                if hook_result.modified and hook_result.data.get("tools"):
                    tools = hook_result.data["tools"]
                    has_tools = bool(tools)
            except Exception as e:
                logger.debug(f"[AGENT] Hook tool.assemble 失败: {e}")

        # ========== 3. 推测执行（只读工具预执行）==========
        if self.speculative:
            try:
                # 跳过闲聊和问候
                task_lower = user_message.lower().strip()
                is_greeting = len(user_message) < 20 and any(
                    g in task_lower for g in ['你好', 'hi', 'hello', '在吗', '谢谢', '再见']
                )
                is_short_chat = len(user_message) < 30 and not any(
                    a in task_lower for a in ['查', '找', '搜索', '读', '看', '获取']
                )
                if not is_greeting and not is_short_chat:
                    intent = self.speculative.detect_intent(user_message)
                    if intent:
                        task = await self.speculative.execute_if_safe(intent, session_id)
                        if task:
                            # 短超时等待结果
                            try:
                                result = await asyncio.wait_for(task, timeout=3.0)
                                # tool_executor.execute() 返回 JSON 字符串
                                if isinstance(result, str):
                                    try:
                                        result = json.loads(result)
                                    except json.JSONDecodeError:
                                        result = None
                                if result and isinstance(result, dict):
                                    status = result.get("status")
                                    content = result.get("result") or result.get("content") or result.get("stdout") or result.get("output", "")
                                    if status == "completed" and content:
                                        tool_name_map = {
                                            "file_read": "📄 文件内容",
                                            "directory_list": "📂 目录列表",
                                            "web_search": "🔍 搜索结果",
                                            "web_fetch": "🌐 网页内容",
                                            "memory_search": "🧠 相关记忆",
                                            "memory_get": "🧠 记忆详情",
                                        }
                                        label = tool_name_map.get(intent.tool, intent.tool)
                                        if len(str(content)) > 2000:
                                            content = str(content)[:2000] + f"\n... (共 {len(str(content))} 字符，已截断)"
                                        injection = {
                                            "role": "system",
                                            "content": f"【预执行结果 — {label}】\n\n{content}\n\n---\n上述内容已自动获取，你可以在回复中直接引用。"
                                        }
                                        messages.append(injection)
                                        logger.info(f"[AGENT] 推测执行命中 [{session_id}]: {intent.tool}")
                            except asyncio.TimeoutError:
                                logger.debug(f"[AGENT] 推测执行超时 [{session_id}]: {intent.tool}")
            except Exception as e:
                logger.debug(f"[AGENT] 推测执行失败 [{session_id}]: {e}")

        # ========== 4. Agent Loop ==========
        full_response = ""
        reasoning_text = ""
        all_tool_calls: List[Dict] = []
        current_messages = list(messages)
        tool_round = 0
        consecutive_failures = 0
        last_failed_tool = None

        # 重置会话工具计数和推测执行状态
        if self.tool_executor:
            self.tool_executor.reset_session(session_id)
        if self.speculative:
            self.speculative.reset_session(session_id)

        # 流式缓冲区
        stream_buffer = {"content": "", "reasoning": "", "last_flush": time.time()}

        def _flush_stream(force: bool = False):
            """批量发送流式 chunk 到前端，减少 WS 开销"""
            now = time.time()
            should_flush = force or (now - stream_buffer["last_flush"] > STREAM_BUFFER_TIMEOUT)

            if should_flush:
                if stream_buffer["reasoning"] and on_chunk:
                    on_chunk(stream_buffer["reasoning"], "reasoning")
                    stream_buffer["reasoning"] = ""
                if stream_buffer["content"] and on_chunk:
                    on_chunk(stream_buffer["content"], "content")
                    stream_buffer["content"] = ""
                stream_buffer["last_flush"] = now

        try:
            while True:
                tool_round += 1

                # --- 4.1 认知预算检查 ---
                elapsed = time.time() - loop_start_time
                if elapsed > self._cognitive_budget:
                    if not _background_notified:
                        _background_notified = True
                        bg_msg = (
                            "\n\n---\n⏳ 任务已处理较长时间，系统已转入后台继续执行，"
                            "完成后会通知您。"
                        )
                        if on_chunk:
                            on_chunk(bg_msg, "content")
                        logger.info(
                            f"[AGENT] 转入后台 [{session_id}]: {elapsed:.1f}s"
                        )
                    # 重置计时器，允许继续执行（后台续跑）
                    loop_start_time = time.time()
                    _background_notified = False

                # --- 4.2 任务中止检查 ---
                if await self._is_aborted(session_id):
                    logger.info(f"[AGENT] 任务中止 [{session_id}]")
                    if on_chunk:
                        on_chunk("\n\n[任务已中止]", "content")
                    break

                # --- 4.3 进度心跳 ---
                if tool_round > 1 and elapsed > PROGRESS_HEARTBEAT_SECONDS:
                    progress_msg = (
                        f"⏳ 正在处理中... 已执行 {int(elapsed)} 秒，"
                        f"当前第 {tool_round} 步"
                    )
                    if on_chunk:
                        on_chunk(progress_msg, "content")

                # --- 4.4 安全上限检查 ---
                if tool_round > MAX_TOOL_ROUNDS:
                    logger.warning(
                        f"[AGENT] 达到安全上限 [{session_id}]: {MAX_TOOL_ROUNDS} 轮"
                    )
                    if on_chunk:
                        on_chunk(
                            "\n\n（已达到工具调用安全上限，请简化任务或分步执行。）",
                            "content",
                        )
                    break

                logger.info(
                    f"[AGENT] 迭代 {tool_round}/{MAX_TOOL_ROUNDS} "
                    f"[{session_id}] elapsed={elapsed:.1f}s tools={len(tools)}"
                )

                # --- 4.5 LLM 调用（真流式）---
                if has_tools and hasattr(self.llm, "chat_stream_with_tools"):
                    round_tool_calls: List[Dict] = []
                    round_content = ""
                    round_reasoning = ""

                    def _on_chunk(chunk: str, chunk_type: str = "content"):
                        nonlocal round_content, round_reasoning
                        if chunk_type == "reasoning":
                            round_reasoning += chunk
                            stream_buffer["reasoning"] += chunk
                        else:
                            round_content += chunk
                            stream_buffer["content"] += chunk
                        _flush_stream()

                    def _on_tool_calls(tcs: List[Dict]):
                        nonlocal round_tool_calls
                        round_tool_calls = tcs

                    # 调用真流式 tool calling
                    await self.llm.chat_stream_with_tools(
                        messages=current_messages,
                        tools=tools,
                        on_chunk=_on_chunk,
                        on_tool_calls=_on_tool_calls,
                        temperature=0.7 if not deep_thinking else 0.5,
                        max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
                    )

                    # 强制刷新缓冲区
                    _flush_stream(force=True)

                    # 累积 reasoning
                    if round_reasoning:
                        reasoning_text += round_reasoning + "\n"

                    # --- 4.6 没有工具调用 → 对话完成 ---
                    if not round_tool_calls:
                        full_response = round_content
                        break

                    # --- 4.7 有工具调用 → 执行工具 ---
                    all_tool_calls.extend(round_tool_calls)

                    # 将 assistant 的 tool_call 消息追加到对话
                    assistant_msg = {
                        "role": "assistant",
                        "content": round_content or "",
                        "tool_calls": [
                            {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": tc.get("function", {}),
                            }
                            for tc in round_tool_calls
                        ],
                    }
                    if round_reasoning:
                        assistant_msg["reasoning_content"] = round_reasoning
                    current_messages.append(assistant_msg)

                    # 执行每个工具调用
                    for tc in round_tool_calls:
                        tool_name = tc["function"]["name"]
                        try:
                            args = json.loads(tc["function"].get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}

                        # 通知前端
                        if on_tool_call:
                            on_tool_call({
                                "tool": tool_name,
                                "arguments": args,
                                "session_id": session_id,
                            })

                        # --- Hook: pre_tool_use ---
                        if self.hooks:
                            try:
                                hook_result = await self.hooks.trigger(
                                    "pre_tool_use",
                                    session_id=session_id,
                                    data={
                                        "tool_name": tool_name,
                                        "arguments": args,
                                        "round": tool_round,
                                    },
                                )
                                if hook_result.modified:
                                    args = hook_result.data.get("arguments", args)
                            except Exception as e:
                                logger.debug(f"[AGENT] Hook pre_tool_use 失败: {e}")

                        # --- 安全拦截：工具执行前权限检查 ---
                        if self.security:
                            try:
                                permit = self.security.permit_tool(
                                    session_id=session_id,
                                    tool_name=tool_name,
                                    arguments=args,
                                )
                                if not permit.get("allowed"):
                                    tool_result = {
                                        "status": "error",
                                        "error": f"权限拒绝：{permit.get('reason', '未知原因')}",
                                        "allowed": False,
                                    }
                                    result_str = json.dumps(tool_result, ensure_ascii=False)
                                    current_messages.append({
                                        "role": "tool",
                                        "tool_call_id": tc.get("id", ""),
                                        "content": result_str,
                                    })
                                    if on_tool_result:
                                        on_tool_result({
                                            "tool": tool_name,
                                            "result": result_str,
                                            "session_id": session_id,
                                            "blocked": True,
                                        })
                                    continue
                            except Exception as e:
                                logger.warning(f"[AGENT] 工具权限检查异常 [{session_id}]: {e}")

                        # 工具结果缓存 key
                        cache_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                        if cache_key in self._tool_result_cache:
                            tool_result = self._tool_result_cache[cache_key]
                            logger.info(
                                f"[AGENT] 工具缓存命中 [{session_id}]: {tool_name}"
                            )
                        else:
                            # 执行工具
                            tool_result = await self._execute_tool(
                                session_id, tool_name, args
                            )
                            self._tool_result_cache[cache_key] = tool_result

                        # 追踪连续失败
                        if tool_result.get("status") == "error":
                            if last_failed_tool == tool_name:
                                consecutive_failures += 1
                            else:
                                consecutive_failures = 1
                                last_failed_tool = tool_name
                        else:
                            consecutive_failures = 0
                            last_failed_tool = None

                        # 工具结果截断（防止上下文爆炸）
                        result_str = json.dumps(tool_result, ensure_ascii=False)
                        if len(result_str) > 12000:
                            result_str = self._truncate_tool_result(result_str, 12000)

                        # 将 tool_result 追加到对话
                        current_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": result_str,
                        })

                        # --- Hook: post_tool_use ---
                        if self.hooks:
                            try:
                                await self.hooks.trigger(
                                    "post_tool_use",
                                    session_id=session_id,
                                    data={
                                        "tool_name": tool_name,
                                        "arguments": args,
                                        "result": tool_result,
                                        "round": tool_round,
                                    },
                                )
                            except Exception as e:
                                logger.debug(f"[AGENT] Hook post_tool_use 失败: {e}")

                        # 通知前端
                        if on_tool_result:
                            on_tool_result({
                                "tool": tool_name,
                                "result": result_str[:800] if len(result_str) > 800 else result_str,
                                "session_id": session_id,
                            })

                        # 连续失败 3 次同一工具，提示 LLM 换策略
                        if consecutive_failures >= 3:
                            current_messages.append({
                                "role": "system",
                                "content": (
                                    f"注意：工具 {tool_name} 已连续失败 3 次，"
                                    f"请尝试其他方法或向用户说明情况。"
                                ),
                            })

                else:
                    # 没有工具或 LLM 不支持流式 tool calling：纯流式对话
                    round_content = ""
                    round_reasoning = ""

                    if hasattr(self.llm, "chat_stream"):
                        def _on_plain_chunk(chunk: str, chunk_type: str = "content"):
                            nonlocal round_content, round_reasoning
                            if chunk_type == "reasoning":
                                round_reasoning += chunk
                                stream_buffer["reasoning"] += chunk
                            else:
                                round_content += chunk
                                stream_buffer["content"] += chunk
                            _flush_stream()

                        await self.llm.chat_stream(
                            messages=current_messages,
                            on_chunk=_on_plain_chunk,
                            temperature=0.7,
                            max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
                        )
                        _flush_stream(force=True)
                    else:
                        # 降级：非流式
                        result = await self.llm.chat(
                            messages=current_messages,
                            temperature=0.7,
                            max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
                        )
                        round_content = result or ""
                        if on_chunk:
                            on_chunk(round_content, "content")

                    if round_reasoning:
                        reasoning_text += round_reasoning + "\n"
                    full_response = round_content
                    break

        except Exception as e:
            logger.error(f"[AGENT] Loop 异常 [{session_id}]: {e}", exc_info=True)
            if not full_response:
                full_response = "抱歉，处理过程中出现了一些问题，请稍后再试。"
            if on_chunk:
                on_chunk(full_response, "content")

        elapsed_ms = int((time.time() - start_time) * 1000)

        result = {
            "content": full_response,
            "reasoning": reasoning_text.strip(),
            "tool_calls": all_tool_calls,
            "elapsed_ms": elapsed_ms,
            "tool_rounds": tool_round,
        }

        # 统计推测执行浪费率
        if self.speculative:
            self.speculative.mark_wasted(session_id)
            stats = self.speculative.get_stats()
            if stats["intents_detected"] > 0:
                logger.info(
                    f"[AGENT] 推测执行统计 [{session_id}]: "
                    f"detected={stats['intents_detected']} "
                    f"hit_rate={stats['hit_rate']} "
                    f"waste_rate={stats['waste_rate']}"
                )

        if on_complete:
            on_complete(result)

        return result

    async def _get_tools(self, capabilities: Dict, session_id: str = "") -> List[Dict]:
        """获取可用工具列表（MCP Gateway + 本地工具）"""
        tools: List[Dict] = []

        # 本地工具（根据 capabilities 过滤）
        local_tools = self._get_local_tools(capabilities)
        tools.extend(local_tools)

        # MCP 工具（动态发现）
        mcp_tools = self._get_mcp_tools()
        tools.extend(mcp_tools)

        # Hook: tool.prefilter — 根据 session 状态动态过滤
        if self.hooks:
            try:
                hook_result = await self.hooks.trigger(
                    "tool.prefilter",
                    session_id=session_id,
                    data={"tools": tools, "count": len(tools)},
                )
                if hook_result.modified and hook_result.data.get("tools"):
                    tools = hook_result.data["tools"]
            except Exception as e:
                logger.debug(f"[AGENT] Hook tool.prefilter 失败: {e}")

        return tools

    def _get_local_tools(self, capabilities: Dict) -> List[Dict]:
        """获取本地工具（替代硬编码 get_tools_by_mode）"""
        from tent_os.tools.definitions import get_tools_by_mode

        all_tools = get_tools_by_mode("deep")
        allowed_names = {"memory_search", "memory_get"}  # 记忆工具始终可用

        if capabilities.get("web_search"):
            allowed_names.update({
                "web_search", "web_fetch",
                "browser_navigate", "browser_click", "browser_type",
                "browser_read", "browser_screenshot", "http_request",
            })
        if capabilities.get("file_ops"):
            allowed_names.update({
                "shell", "file_read", "file_write", "directory_list",
                "render_ppt", "render_document", "render_contract",
                "render_excel", "render_word",
            })

        tools = [t for t in all_tools if t.get("function", {}).get("name") in allowed_names]

        # 添加自定义工具（skill 注册的工具）
        if self.tool_executor and hasattr(self.tool_executor, "get_custom_tool_schemas"):
            try:
                custom = self.tool_executor.get_custom_tool_schemas()
                tools.extend(custom)
            except Exception as e:
                logger.debug(f"[AGENT] 自定义工具获取失败: {e}")

        return tools

    def _get_mcp_tools(self) -> List[Dict]:
        """从 MCP ServerManager 获取工具并转换为 OpenAI function calling 格式"""
        tools = []
        if not self.mcp_gateway:
            return tools

        try:
            # 支持两种 MCP 管理器：MCPServerManager 和 MCPGatewayRegistry
            raw_tools = []
            if hasattr(self.mcp_gateway, "get_all_tools"):
                raw_tools = self.mcp_gateway.get_all_tools()
            elif hasattr(self.mcp_gateway, "list_all_tools"):
                raw_tools = self.mcp_gateway.list_all_tools()

            for t in raw_tools:
                # MCPTool 对象 -> OpenAI format
                if hasattr(t, "name") and hasattr(t, "description"):
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": getattr(t, "name", "unknown"),
                            "description": getattr(t, "description", ""),
                            "parameters": getattr(t, "input_schema", {}),
                        },
                    })
                # 已经是 OpenAI format 的 dict
                elif isinstance(t, dict) and "function" in t:
                    tools.append(t)
                elif isinstance(t, dict) and "name" in t:
                    tools.append({
                        "type": "function",
                        "function": t,
                    })
        except Exception as e:
            logger.warning(f"[AGENT] MCP 工具获取失败: {e}")

        return tools

    async def _execute_tool(
        self, session_id: str, tool_name: str, arguments: Dict
    ) -> Dict:
        """执行工具调用"""
        if not self.tool_executor:
            return {"status": "error", "error": "工具执行器未初始化"}

        try:
            result_str = await self.tool_executor.execute(
                tool_name, arguments, session_id=session_id, max_calls=100
            )
            return json.loads(result_str)
        except Exception as e:
            logger.error(f"[AGENT] 工具执行失败 [{session_id}] {tool_name}: {e}")
            return {"status": "error", "error": str(e)}

    async def _is_aborted(self, session_id: str) -> bool:
        """检查用户是否请求中止"""
        if not self.state_store:
            return False
        try:
            state = await self.state_store.load(session_id)
            return bool(state.get("abort_requested"))
        except Exception:
            return False

    def _truncate_tool_result(self, result_str: str, max_chars: int) -> str:
        """截断工具结果字符串

        参考 worker.py 的 _truncate_tool_result_object，但这里是字符串版本。
        Phase 2 会移植完整的递归 JSON 截断。
        """
        if len(result_str) <= max_chars:
            return result_str

        # 尝试解析 JSON 并截断
        try:
            data = json.loads(result_str)
            if isinstance(data, dict):
                self._truncate_dict(data, max_chars // 2)
                return json.dumps(data, ensure_ascii=False)
        except Exception:
            pass

        # 简单截断
        return result_str[:max_chars] + f"\n... [截断，原 {len(result_str)} 字符]"

    def _truncate_dict(self, obj: Any, max_value_len: int):
        """递归截断字典/列表中的长字符串"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and len(v) > max_value_len:
                    obj[k] = v[:max_value_len] + " [...截断]"
                elif isinstance(v, (dict, list)):
                    self._truncate_dict(v, max_value_len)
        elif isinstance(obj, list):
            for item in obj:
                self._truncate_dict(item, max_value_len)
