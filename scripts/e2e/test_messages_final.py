"""
最终验证：messages 结构是不是假干活的根因

场景模拟：LLM 已经调用过一次 file_write，现在需要继续调用第二次。
A组：当前实现（无 assistant tool_calls，工具结果是 user 消息）
B组：规范实现（有 assistant tool_calls，工具结果是 tool 消息）
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
铁律：当用户要求修改或写入文件时，必须调用 file_write 工具直接写入磁盘，严禁在回复中输出代码块。
如果已经写了一个文件，继续写下一个文件，直到所有文件都写完。不要停下来汇报计划。"""

USER_TASK = "把 weather.py 和 formatter.py 都写完"


def build_messages_a():
    """A组：当前实现"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TASK},
        # 模拟上一轮 LLM 调用了 file_write，工具结果作为 user 消息
        {"role": "user", "content": "【工具执行结果 | file_write】\nweather.py 已成功写入。\n\n---\n[基于以上结果，你的下一步只有两个选项...]"},
    ]


def build_messages_b():
    """B组：规范实现"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TASK},
        # assistant 消息包含 tool_calls
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "用户要求写两个文件。我先写 weather.py。",
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {"name": "file_write", "arguments": '{"path": "/tmp/weather.py", "content": "# weather"}'}
                }
            ]
        },
        # tool 消息包含结果
        {"role": "tool", "tool_call_id": "call_abc123", "content": "weather.py 已成功写入。"},
    ]


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
    
    if "error" in data:
        print(f"\n{'='*60}")
        print(f"测试组: {label}")
        print(f"API 错误: {data['error']}")
        return None
    
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning_content", "") or ""
    tool_calls = msg.get("tool_calls", [])

    print(f"\n{'='*60}")
    print(f"测试组: {label}")
    print(f"messages 角色序列: {[m['role'] for m in messages]}")
    print(f"reasoning: {reasoning[:120]}...")
    print(f"content: {content[:120]}...")
    print(f"tool_calls: {len(tool_calls)}")
    if tool_calls:
        for tc in tool_calls:
            print(f"  → {tc['function']['name']}: {tc['function']['arguments'][:60]}")
    print(f"结果: {'✅ 调用工具' if tool_calls else '❌ 无工具调用'}")
    return bool(tool_calls)


async def main():
    print("=" * 60)
    print("最终验证：messages 结构 A/B 测试")
    print("场景：已写 weather.py，继续写 formatter.py")
    print("=" * 60)

    result_a = await call_llm(build_messages_a(), "A组: 当前实现(user角色)")
    result_b = await call_llm(build_messages_b(), "B组: 规范实现(assistant+tool角色)")

    print(f"\n{'='*60}")
    print("结论:")
    print(f"  A组 (user角色): {'✅ 调用' if result_a else '❌ 未调用'}")
    print(f"  B组 (tool角色): {'✅ 调用' if result_b else '❌ 未调用'}")
    if result_b and not result_a:
        print("  🎯 messages 结构是根因！必须改代码！")
    elif result_a and result_b:
        print("  ⚠️ 两组都调用——messages 结构不是根因，问题在别处")
    elif not result_a and not result_b:
        print("  ⚠️ 两组都不调用——可能是任务/模型问题")
    else:
        print("  ⚠️ 结果异常——需要进一步分析")


if __name__ == "__main__":
    asyncio.run(main())
