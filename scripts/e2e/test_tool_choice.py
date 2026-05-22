"""
验证：强制 tool_choice="required" 是否能解决假干活

测试两种 tool_choice：
- auto: LLM 自己决定（当前实现）
- required: 强制调用至少一个工具
"""
import asyncio
import httpx
import json

API_KEY = "sk-kimi-qoFIKrnCfYDkZrfBhhNpxFl5P9N2hvW9frp2K2aEcAhqlnaL8pQFCy4crJ4Rb7nu"
BASE_URL = "https://api.kimi.com/coding/v1"
MODEL = "kimi-k2.6"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "file_write",
        "description": "【文件写入专用】将完整内容写入本地文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    }
}]

MESSAGES = [
    {"role": "system", "content": "你是 Tent OS。铁律：必须调用 file_write 写入磁盘，严禁输出代码块。"},
    {"role": "user", "content": "把 weather.py 和 formatter.py 都写完"},
    {"role": "user", "content": "【工具执行结果 | file_write】\nweather.py 已成功写入。\n\n---\n[继续完成任务。]"},
]


async def call_llm(tool_choice, label):
    payload = {
        "model": MODEL,
        "messages": MESSAGES,
        "tools": TOOLS,
        "tool_choice": tool_choice,
        "stream": False,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "claude-code/0.1",
            },
            json=payload,
            timeout=60,
        )
    data = resp.json()
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content", "") or ""
    tool_calls = msg.get("tool_calls", [])
    finish = choice.get("finish_reason", "")

    print(f"\n{'='*60}")
    print(f"测试: {label}")
    print(f"tool_choice: {tool_choice}")
    print(f"finish_reason: {finish}")
    print(f"content: {content[:80]}...")
    print(f"tool_calls: {len(tool_calls)}")
    print(f"结果: {'✅ 调用' if tool_calls else '❌ 未调用'}")
    return bool(tool_calls)


async def main():
    print("=" * 60)
    print("验证：tool_choice 对 LLM 行为的影响")
    print("=" * 60)

    await call_llm("auto", "auto: LLM 自己决定")
    await call_llm("required", "required: 强制调用工具")


if __name__ == "__main__":
    asyncio.run(main())
