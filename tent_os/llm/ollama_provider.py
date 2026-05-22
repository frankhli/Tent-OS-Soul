"""Ollama Provider —— 本地模型支持

Ollama 提供 OpenAI 兼容的 API（/api/chat 和 /v1/chat/completions），
这里直接使用 /v1/chat/completions 以保持一致性。
"""

import json
from typing import Dict, List, Optional, Callable

import httpx

from tent_os.llm.provider import LLMProvider


class OllamaProvider(LLMProvider):
    """Ollama 本地模型适配器"""

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        timeout: float = 120.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    @property
    def model_id(self) -> str:
        return f"ollama/{self.model}"

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json"}

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
            }
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]

    async def generate_plan(self, task: str, tools: List[Dict], extra_context: str = "") -> Dict:
        system_prompt = """你是 Tent OS 的规划引擎。请为给定任务制定执行方案，输出严格JSON格式。"""

        context_block = f"\n\n【经验规则】\n{extra_context}\n" if extra_context else ""
        user_prompt = f"""任务：{task}
可用工具：{json.dumps(tools, ensure_ascii=False)}{context_block}
输出：{{"analysis": "...", "steps": [{{"step": 1, "action": "...", "executor": "...", "params": {{}}}}]}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        content = await self.chat(messages)
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
            "stream": True,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
            }
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        full_text = ""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                headers=self._headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        done = chunk.get("done", False)
                        if content:
                            full_text += content
                            on_chunk(content, "content")
                        if done:
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue
        return full_text

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict:
        """Ollama 的 tool calling 支持（通过 /v1/chat/completions）"""
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
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
            "reasoning_content": "",
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
        """流式 tool calling（Ollama /v1/chat/completions OpenAI 兼容格式）"""
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
                f"{self.base_url}/v1/chat/completions",
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

                        content = delta.get("content", "")
                        if content:
                            full_text += content
                            on_chunk(content, "content")

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
