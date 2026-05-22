"""
验证：工具结果提示是不是根因

场景：已写了一个文件，继续写第二个
A组：当前复杂提示（两个选项）
B组：简化提示（强制继续，不给选择）
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


def build_messages_a():
    """A组：当前复杂提示"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "把 weather.py 和 formatter.py 都写完"},
        {"role": "user", "content": (
            "【工具执行结果 | file_write】\nweather.py 已成功写入。\n\n"
            "---\n"
            "[基于以上结果，你的下一步只有两个选项："
            "1) 如果还需要操作（读取更多文件、修改文件、执行命令等），直接调用对应工具，不要输出任何计划或步骤描述；"
            "2) 如果任务确实已完成，给出一句简要总结。"
            "严禁输出'先读...然后...'、'接下来...'、'让我...'等中间计划——直接调用工具或给出总结。]"
        )},
    ]


def build_messages_b():
    """B组：简化提示，不给选择"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "把 weather.py 和 formatter.py 都写完"},
        {"role": "user", "content": (
            "【工具执行结果 | file_write】\nweather.py 已成功写入。\n\n"
            "---\n"
            "[以上是你之前调用的工具的结果。请继续完成任务。"
            "如果需要操作，直接调用对应工具。不要输出计划或步骤描述。]"
        )},
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
    choice = data.get("choices", [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning_content", "") or ""
    tool_calls = msg.get("tool_calls", [])

    print(f"\n{'='*60}")
    print(f"测试组: {label}")
    print(f"reasoning: {reasoning[:100]}...")
    print(f"content: {content[:100]}...")
    print(f"tool_calls: {len(tool_calls)}")
    print(f"结果: {'✅ 调用' if tool_calls else '❌ 未调用'}")
    return bool(tool_calls)


async def main():
    print("=" * 60)
    print("验证：工具结果提示是不是根因")
    print("=" * 60)

    result_a = await call_llm(build_messages_a(), "A组: 复杂提示(两个选项)")
    result_b = await call_llm(build_messages_b(), "B组: 简化提示(强制继续)")

    print(f"\n{'='*60}")
    print("结论:")
    print(f"  A组 (复杂提示): {'✅ 调用' if result_a else '❌ 未调用'}")
    print(f"  B组 (简化提示): {'✅ 调用' if result_b else '❌ 未调用'}")
    if result_b and not result_a:
        print("  🎯 工具结果提示是根因！")
    elif result_a and result_b:
        print("  ⚠️ 两组都调用——提示不是根因")
    elif not result_a and not result_b:
        print("  ⚠️ 两组都不调用——可能是模型/任务问题")


if __name__ == "__main__":
    asyncio.run(main())
