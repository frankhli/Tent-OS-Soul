import asyncio
import json
from typing import Dict, List, Optional, Callable

import httpx

from tent_os.llm.provider import LLMProvider


class KimiCodingLLM(LLMProvider):
    """Kimi Coding API 适配器

    注意：Kimi Coding API 需要特定的 User-Agent 才能访问。
    支持的 UA 包括: claude-code/0.1, Kilo-Code/1.0 等

    性能优化：
    - 复用 httpx.AsyncClient（连接池）
    - 指数退避重试
    - keep-alive 连接
    """

    def __init__(
        self,
        api_key: str,
        model: str = "kimi-k2.6",
        base_url: str = "https://api.kimi.com/coding/v1",
        user_agent: str = "claude-code/0.1",
        temperature: float = 0.3,
        timeout: float = 180.0,
        max_concurrent: int = 8,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.temperature = temperature
        self.timeout = timeout
        # FIX v3.2: LLM调用级并发限制（替代SessionScheduler的请求级限制）
        self._request_sem = asyncio.Semaphore(max_concurrent)
        # 复用 client：连接池 + keep-alive
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        self._client = httpx.AsyncClient(timeout=timeout, limits=limits)

    @property
    def model_id(self) -> str:
        return f"kimi_coding/{self.model}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
        }

    async def _post_with_retry(
        self,
        endpoint: str,
        payload: Dict,
        max_retries: int = 2,
        skip_sem: bool = False,
    ) -> Dict:
        """带指数退避重试的 POST 请求（受LLM级并发限制）"""
        import asyncio
        url = f"{self.base_url}{endpoint}"
        last_error = None

        # FIX v3.2: 只在实际调用LLM API时获取Semaphore
        # 这样记忆检索、工具执行等非LLM步骤不占用并发槽位
        # skip_sem=True 用于安全预判断等快速路径，避免被正常LLM调用阻塞
        async def _do_request():
            for attempt in range(max_retries + 1):
                try:
                    resp = await self._client.post(
                        url,
                        headers=self._headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp.json()
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    last_error = e
                    if attempt < max_retries:
                        wait = 2 ** attempt  # 1s, 2s
                        await asyncio.sleep(wait)
                    else:
                        raise last_error
                except httpx.HTTPStatusError as e:
                    # 服务端错误 (5xx) 可重试，客户端错误 (4xx) 不重试
                    if e.response.status_code >= 500 and attempt < max_retries:
                        last_error = e
                        wait = 2 ** attempt
                        await asyncio.sleep(wait)
                    else:
                        raise
            raise last_error or Exception("请求失败")

        if skip_sem:
            return await _do_request()
        else:
            async with self._request_sem:
                return await _do_request()

    async def chat(
        self,
        messages: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        skip_sem: bool = False,
        thinking: Optional[Dict] = None,
    ) -> str:
        """调用 Kimi Coding Chat Completions API（复用连接）
        
        Args:
            skip_sem: 是否跳过全局Semaphore（用于安全预判断等快速路径）
            thinking: 控制 reasoning 模式，如 {"type": "disabled"} 关闭 thinking
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format
        if thinking is not None:
            payload["thinking"] = thinking

        data = await self._post_with_retry("/chat/completions", payload, skip_sem=skip_sem)
        # Debug: log raw response structure
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"[KimiCoding] raw response keys: {list(data.keys())}")
        if "choices" in data and data["choices"]:
            msg = data["choices"][0].get("message", {})
            content = msg.get("content", "")
            # FIX: Kimi K2.6 reasoning model 可能返回空 content 但包含 reasoning_content
            # 当 content 为空时，尝试从 reasoning_content 提取（作为 fallback）
            if not content or not content.strip():
                reasoning = msg.get("reasoning_content", "")
                if reasoning and reasoning.strip():
                    _logger.info(f"[KimiCoding] content empty, using reasoning_content ({len(reasoning)} chars)")
                    # reasoning_content 是模型的思考过程，需要清理后使用
                    # 提取关键结论部分（通常以"因此"、"所以"、"总结"等开头）
                    content = self._extract_reply_from_reasoning(reasoning)
            _logger.info(f"[KimiCoding] message keys: {list(msg.keys())}, content len: {len(content or '')}")
            return content or ""
        _logger.warning(f"[KimiCoding] unexpected response structure: {data}")
        return ""
    
    def _extract_reply_from_reasoning(self, reasoning: str) -> str:
        """从 reasoning_content 中提取可用回复（兜底）
        
        Kimi K2.6 的 reasoning_content 包含模型的思考过程。
        当 thinking 模式禁用时，此方法基本不会触发。
        保留作为极端 fallback。
        """
        if not reasoning:
            return ""
        # 取最后一段自然语言文本（通常包含结论）
        paragraphs = [p.strip() for p in reasoning.split("\n\n") if p.strip()]
        if paragraphs:
            last = paragraphs[-1]
            if len(last) > 10 and not last.startswith(("检查", "验证", "确认", "Check", "Verify")):
                return last[:400]
            if len(paragraphs) >= 2:
                second = paragraphs[-2]
                if len(second) > 10:
                    return second[:400]
        return reasoning[:400].strip()

    async def generate_plan(self, task: str, tools: List[Dict], extra_context: str = "",
                            executors_info: List[Dict] = None) -> Dict:
        """生成任务执行方案（返回JSON格式Plan）"""
        system_prompt = """你是 Tent OS 智能体的规划引擎。请为给定任务制定执行方案。

规则：
1. 分析任务并判断需要哪些步骤
2. 每个步骤必须指定 action（短动词，如 move/pick/fetch/process/chat）、executor（必须是可用执行者之一）、params
3. action 必须是简洁的英文动词，不要写长句描述
4. 输出严格JSON格式

可用 executor 必须来自以下列表中的 id 字段。物理执行者（如机械臂、配送平台）有特殊的 capabilities，请根据任务需求合理选择。"""

        context_block = f"\n\n【从过往经验中学到的规则】\n{extra_context}\n" if extra_context else ""
        
        # 物理执行者信息注入
        executors_block = ""
        if executors_info:
            executors_block = "\n\n【可用执行者（含物理执行者）】\n"
            for ex in executors_info:
                caps = ", ".join(ex.get("capabilities", []))
                ex_type = ex.get("type", "unknown")
                desc = ex.get("description", "")
                executors_block += f"- {ex['id']} (类型: {ex_type}, 能力: {caps})"
                if desc:
                    executors_block += f" — {desc}"
                executors_block += "\n"
        
        user_prompt = f"""任务：{task}
可用工具：{json.dumps(tools, ensure_ascii=False)}{context_block}{executors_block}

输出严格JSON格式：
{{"analysis": "...", "steps": [{{"step": 1, "action": "短动词", "executor": "执行者ID", "params": {{}}}}]}}

示例：
{{"analysis": "需要获取数据并处理", "steps": [{{"step": 1, "action": "fetch", "executor": "http_api", "params": {{"url": "..."}}}}, {{"step": 2, "action": "process", "executor": "data_processor", "params": {{}}}}]}}

物理任务示例（检查零件并配送）：
{{"analysis": "先检查3D打印零件质量，再安排配送到客户地址", "steps": [{{"step": 1, "action": "inspect", "executor": "realman", "params": {{"target": "3d_print_parts"}}}}, {{"step": 2, "action": "deliver", "executor": "flashex", "params": {{"pickup_address": "实验室", "delivery_address": "朝阳区客户"}}}}]}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        content = await self.chat(
            messages=messages,
            response_format={"type": "json_object"},
        )

        try:
            plan = json.loads(content)
            # 简单校验
            if "steps" not in plan or not isinstance(plan["steps"], list):
                raise ValueError("Plan 缺少 steps 字段")
            return plan
        except Exception as e:
            # Fallback
            return {
                "analysis": f"LLM解析失败({e})，使用Fallback",
                "steps": [
                    {
                        "step": 1,
                        "action": "chat",
                        "executor": "default",
                        "params": {"task": task},
                    }
                ],
            }

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        on_chunk: callable,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking: Optional[Dict] = None,
    ) -> str:
        """流式调用 Kimi Coding Chat Completions API
        
        Kimi Coding K2.6 特性：
        - SSE 格式为 data:{...}（data: 后无空格）
        - delta 中是 reasoning_content（思考过程）+ content（最终输出）
        
        Args:
            messages: 对话历史
            on_chunk: 回调函数，每收到一个 chunk 调用一次 on_chunk(text_delta, chunk_type)
                chunk_type: "reasoning" | "content"
            temperature: 温度
            max_tokens: 最大生成 token 数
            thinking: 控制 reasoning 模式，默认启用 {"type": "enabled"}
        
        Returns:
            完整响应文本（仅 content 部分，不含 reasoning）
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if thinking is None:
            payload["thinking"] = {"type": "disabled"}
        elif thinking is not None:
            payload["thinking"] = thinking

        full_text = ""
        reasoning_text = ""
        async with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                # Kimi Coding: data:{...}（无空格）或 data: {...}（有空格）
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    # Kimi K2.6: reasoning_content 是思考过程，content 是最终输出
                    reasoning = delta.get("reasoning_content", "")
                    content = delta.get("content", "")
                    if reasoning:
                        reasoning_text += reasoning
                        on_chunk(reasoning, "reasoning")
                    if content:
                        full_text += content
                        on_chunk(content, "content")
                except (json.JSONDecodeError, IndexError):
                    continue
        return full_text

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """非流式调用，支持 tool calling（ReAct Loop 用）
        
        返回结构：
        {
            "content": str,          # assistant 的文本回复（可能为空）
            "tool_calls": [{         # 工具调用列表（可能为空）
                "id": str,
                "type": "function",
                "function": {
                    "name": str,
                    "arguments": str,  # JSON 字符串
                }
            }]
        }
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        data = await self._post_with_retry("/chat/completions", payload)
        
        message = data.get("choices", [{}])[0].get("message", {})
        
        # 解析 tool_calls
        raw_tool_calls = message.get("tool_calls", [])
        tool_calls = []
        for tc in raw_tool_calls:
            if tc.get("type") == "function":
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc["function"].get("name", ""),
                        "arguments": tc["function"].get("arguments", ""),
                    }
                })
        
        return {
            "content": message.get("content", "") or "",
            "tool_calls": tool_calls,
            "reasoning_content": message.get("reasoning_content", ""),
        }
    
    async def chat_stream_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        on_chunk: Callable[[str, str], None],
        on_tool_calls: Callable[[List[Dict]], None],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        thinking: Optional[Dict] = None,
    ) -> str:
        """流式调用，支持 tool calling（ReAct Loop 真流式）
        
        FIX: 这是 chat_with_tools 的流式版本。正常内容实时推送到前端，
        当 LLM 决定调用工具时，收集 tool_calls 并通过回调通知。
        
        Args:
            messages: 对话历史
            tools: 可用工具列表
            on_chunk: 回调函数，每收到一个 chunk 调用一次 on_chunk(text, chunk_type)
                chunk_type: "reasoning" | "content"
            on_tool_calls: 回调函数，当检测到 tool_calls 时调用
            temperature: 温度
            max_tokens: 最大生成 token 数
            thinking: 控制 reasoning 模式，默认启用 {"type": "enabled"}
        
        Returns:
            完整响应文本（仅 content 部分，不含 reasoning）
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "stream": True,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if thinking is not None:
            payload["thinking"] = thinking
        
        full_text = ""
        reasoning_text = ""
        tool_calls_buffer: List[Dict] = []
        
        async with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason", "")
                    
                    # reasoning_content
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        reasoning_text += reasoning
                        on_chunk(reasoning, "reasoning")
                    
                    # content
                    content = delta.get("content", "")
                    if content:
                        full_text += content
                        on_chunk(content, "content")
                    
                    # tool_calls —— 增量收集
                    delta_tool_calls = delta.get("tool_calls", [])
                    for tc in delta_tool_calls:
                        index = tc.get("index", 0)
                        while len(tool_calls_buffer) <= index:
                            tool_calls_buffer.append({
                                "id": "", "type": "function",
                                "function": {"name": "", "arguments": ""}
                            })
                        if tc.get("id"):
                            tool_calls_buffer[index]["id"] = tc["id"]
                        func_delta = tc.get("function", {})
                        if func_delta.get("name"):
                            tool_calls_buffer[index]["function"]["name"] = func_delta["name"]
                        if func_delta.get("arguments"):
                            tool_calls_buffer[index]["function"]["arguments"] += func_delta["arguments"]
                    
                    # 当 finish_reason 为 tool_calls 时，通知回调
                    if finish_reason == "tool_calls" and tool_calls_buffer:
                        on_tool_calls(tool_calls_buffer)
                        break
                        
                except (json.JSONDecodeError, IndexError):
                    continue
        
        return full_text
