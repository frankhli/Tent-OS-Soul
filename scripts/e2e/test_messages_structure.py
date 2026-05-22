"""
A/B 测试：验证 messages 结构对 LLM 工具调用的影响

假设：当前代码用 user 角色放工具结果，导致 LLM confused。
规范做法是用 tool 角色 + assistant tool_calls。
"""
import asyncio
import json
import httpx
import os

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


async def call_llm(messages, label):
    """调用 LLM，返回是否有 tool_calls"""
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
    print(f"  [DEBUG] resp status: {resp.status_code}")
    print(f"  [DEBUG] data keys: {list(data.keys())[:10]}")
    if "error" in data:
        print(f"  [DEBUG] API ERROR: {data['error']}")

    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content", "")
    reasoning = msg.get("reasoning_content", "")
    tool_calls = msg.get("tool_calls", [])
    finish_reason = choice.get("finish_reason", "")

    print(f"\n{'='*60}")
    print(f"测试组: {label}")
    print(f"finish_reason: {finish_reason}")
    print(f"messages 角色序列: {[m['role'] for m in messages]}")
    print(f"reasoning: '{reasoning[:200]}'")
    print(f"content: '{content[:200]}'")
    print(f"tool_calls: {len(tool_calls)} 个")
    print(f"完整 msg keys: {list(msg.keys())}")
    if tool_calls:
        for tc in tool_calls:
            print(f"  → {tc['function']['name']}: {tc['function']['arguments'][:80]}")
    print(f"结果: {'✅ 调用工具' if tool_calls else '❌ 无工具调用'}")
    return bool(tool_calls)


async def test_ab():
    """A/B 测试：user 角色 vs tool 角色"""
    print("=" * 60)
    print("测试 1: messages 结构 A/B 测试")
    print("=" * 60)

    # A 组：当前实现（user 角色放工具结果）
    messages_a = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "在 /tmp/test_ab.txt 写入 hello"},
        # 模拟之前读了两个文件
        {"role": "user", "content": "【工具执行结果 | file_read】\n文件 weather.py 内容...\n\n---\n[请判断下一步操作]"},
        {"role": "user", "content": "【工具执行结果 | file_read】\n文件 api.py 内容...\n\n---\n[请判断下一步操作]"},
    ]

    # B 组：规范实现（tool 角色 + assistant tool_calls）
    messages_b = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "在 /tmp/test_ab.txt 写入 hello"},
        # assistant 消息包含之前的 tool_calls
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "file_read", "arguments": '{"path": "weather.py"}'}},
            {"id": "call_2", "type": "function", "function": {"name": "file_read", "arguments": '{"path": "api.py"}'}},
        ]},
        # tool 角色消息包含结果
        {"role": "tool", "tool_call_id": "call_1", "content": "文件 weather.py 内容..."},
        {"role": "tool", "tool_call_id": "call_2", "content": "文件 api.py 内容..."},
    ]

    results = []
    results.append(await call_llm(messages_a, "A组: user角色放工具结果(当前实现)"))
    results.append(await call_llm(messages_b, "B组: tool角色+assistant tool_calls(规范)"))

    print(f"\n{'='*60}")
    print("测试 1 总结:")
    print(f"  A组 (user角色): {'✅ 调用' if results[0] else '❌ 未调用'}")
    print(f"  B组 (tool角色): {'✅ 调用' if results[1] else '❌ 未调用'}")
    if results[1] and not results[0]:
        print("  🎯 结论: messages 结构是根因！")
    elif results[0] and results[1]:
        print("  ⚠️ 两组都调用或都未调用，需要更多测试")
    else:
        print("  ⚠️ 结果异常，需要排查")


async def test_context_length():
    """测试不同上下文长度对 LLM 行为的影响"""
    print("\n" + "=" * 60)
    print("测试 2: 上下文长度影响")
    print("=" * 60)

    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "在 /tmp/test_len.txt 写入 hello"},
    ]

    # 构造不同长度的 messages，模拟历史工具调用
    for num_history in [0, 5, 10, 15, 20, 30]:
        messages = list(base_messages)
        for i in range(num_history):
            # 模拟一轮 tool_call + 结果
            messages.append({"role": "user", "content": f"【工具执行结果 | file_read】\n历史文件 {i} 的内容..."})

        result = await call_llm(messages, f"历史 {num_history} 轮工具结果 ({len(messages)} 条 messages)")


async def main():
    await test_ab()
    await test_context_length()


if __name__ == "__main__":
    asyncio.run(main())
