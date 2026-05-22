"""OpenAI Compatible Provider —— 通用 OpenAI API 兼容适配器

支持几乎所有 OpenAI API 兼容的服务：
- OpenAI (gpt-4o, gpt-3.5-turbo, etc.)
- DeepSeek (deepseek-chat, deepseek-coder)
- Moonshot (kimi 系列)
- Groq (llama3, mixtral 等高速推理)
- Together AI (各种开源模型)
- Fireworks AI
- Mistral AI
- xAI (Grok)
- Perplexity
- OpenRouter
- 以及任何其他 OpenAI 兼容 API

使用方法：
    provider: openai_compatible
    api_key: YOUR_KEY
    model: MODEL_NAME
    base_url: https://api.xxx.com/v1
"""

import json
from typing import Dict, List, Optional, Callable

import httpx

from tent_os.llm.provider import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """通用 OpenAI API 兼容 Provider"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.3,
        timeout: float = 60.0,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

    @property
    def model_id(self) -> str:
        return f"openai_compatible/{self.model}"

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        return headers

    async def chat(
        self,
        messages: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def generate_plan(self, task: str, tools: List[Dict], extra_context: str = "") -> Dict:
        system_prompt = """你是 Tent OS 的规划引擎。请为给定任务制定执行方案。
规则：
1. 分析任务并判断需要哪些步骤
2. 每个步骤必须指定 action、executor、params
3. 输出严格JSON格式"""

        context_block = f"\n\n【经验规则】\n{extra_context}\n" if extra_context else ""
        user_prompt = f"""任务：{task}
可用工具：{json.dumps(tools, ensure_ascii=False)}{context_block}
输出严格JSON：{{"analysis": "...", "steps": [{{"step": 1, "action": "...", "executor": "...", "params": {{}}}}]}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        content = await self.chat(messages, response_format={"type": "json_object"})
        try:
            plan = json.loads(content)
            if "steps" not in plan or not isinstance(plan["steps"], list):
                raise ValueError("Plan 缺少 steps")
            return plan
        except Exception as e:
            return {
                "analysis": f"解析失败({e})，使用 Fallback",
                "steps": [{"step": 1, "action": "chat", "executor": "default", "params": {}}]
            }

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        on_chunk: Callable[[str], None],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        full_text = ""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
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
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        reasoning = delta.get("reasoning_content", "")
                        content = delta.get("content", "")
                        if reasoning:
                            full_text += reasoning
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
        """非流式 tool calling"""
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        message = data.get("choices", [{}])[0].get("message", {})
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
    ) -> str:
        """流式 tool calling（OpenAI 兼容格式 SSE）"""
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

        full_text = ""
        tool_calls_buffer: List[Dict] = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
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

                        reasoning = delta.get("reasoning_content", "")
                        if reasoning:
                            full_text += reasoning
                            on_chunk(reasoning, "reasoning")

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

                        if finish_reason == "tool_calls" and tool_calls_buffer:
                            on_tool_calls(tool_calls_buffer)
                            break

                    except (json.JSONDecodeError, IndexError):
                        continue

        return full_text
