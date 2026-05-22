"""
测试：大量历史工具结果是否导致 LLM 不调用工具

模拟实际场景：messages 中有 20+ 条历史工具结果
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
        "description": "【文件写入专用】将完整内容写入本地文件。直接调用此工具，不要输出代码块。",
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

SYSTEM_PROMPT = """你是 Tent OS，一个操作系统。
铁律：当用户要求修改或写入文件时，必须调用 file_write 工具直接写入磁盘，严禁在回复中输出代码块。"""


def build_messages_with_history(num_history):
    """构造包含大量历史工具结果的 messages"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "把 weather.py 和 formatter.py 都写完"},
    ]
    for i in range(num_history):
        messages.append({
            "role": "user",
            "content": f"【工具执行结果 | file_read】\n历史文件 {i} 的内容...\n\n---\n[请判断下一步操作。如果用户要求修改文件，继续调用 file_write 完成修改，不要只给出建议。]"
        })
    return messages


async def call_llm(messages, label):
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
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
    reasoning = msg.get("reasoning_content", "") or ""
    tool_calls = msg.get("tool_calls", [])

    print(f"\n{'='*60}")
    print(f"测试: {label}")
    print(f"messages: {len(messages)} 条")
    print(f"reasoning: {reasoning[:100]}...")
    print(f"content: {content[:100]}...")
    print(f"tool_calls: {len(tool_calls)}")
    print(f"结果: {'✅ 调用' if tool_calls else '❌ 未调用'}")
    return bool(tool_calls)


async def main():
    print("=" * 60)
    print("测试：历史工具结果数量对 LLM 行为的影响")
    print("=" * 60)

    for num in [0, 5, 10, 15, 20, 30]:
        msgs = build_messages_with_history(num)
        await call_llm(msgs, f"{num} 轮历史工具结果 ({len(msgs)} 条 messages)")


if __name__ == "__main__":
    asyncio.run(main())
