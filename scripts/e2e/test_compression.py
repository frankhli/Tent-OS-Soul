"""
测试：上下文压缩是否移除了用户原始任务

实际日志显示：
- 迭代1 (35→20): LLM 调用工具 ✅
- 迭代2 (26→20): LLM 调用工具 ✅
- 迭代3 (22→20): LLM 只输出文本 ❌

假设：压缩移除了用户原始任务，LLM 不知道要干什么
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

USER_TASK = "汇报一下进度"


def compress(messages, max_msgs=20):
    """模拟当前压缩逻辑"""
    if len(messages) <= max_msgs:
        return messages
    compressed = [messages[0]]  # system
    compressed.extend(messages[-(max_msgs - 1):])
    return compressed


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
    content = msg.get("content", "")
    reasoning = msg.get("reasoning_content", "")
    tool_calls = msg.get("tool_calls", [])

    print(f"\n{'='*60}")
    print(f"测试: {label}")
    print(f"messages 数: {len(messages)}")
    print(f"角色序列: {[m['role'] for m in messages]}")
    print(f"reasoning: {reasoning[:150]}...")
    print(f"content: {content[:150]}...")
    print(f"tool_calls: {len(tool_calls)}")
    print(f"结果: {'✅ 调用工具' if tool_calls else '❌ 无工具调用'}")
    return bool(tool_calls)


async def main():
    print("=" * 60)
    print("测试: 上下文压缩是否移除用户原始任务")
    print("=" * 60)

    # 构造模拟真实场景的 messages
    # 结构: system + user(任务) + 多轮 user(工具结果)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TASK},  # 原始任务在索引1
    ]
    # 添加 20 轮工具结果（模拟之前读了很多文件）
    for i in range(20):
        messages.append({
            "role": "user",
            "content": f"【工具执行结果 | file_read】\n历史文件 {i} 的内容...\n\n---\n[请判断下一步操作]"
        })

    print(f"\n原始 messages: {len(messages)} 条")
    print(f"角色序列: {[m['role'] for m in messages]}")

    # 测试 1: 不压缩
    await call_llm(messages, "不压缩 (22条)")

    # 测试 2: 压缩到 20 条（当前逻辑）
    compressed = compress(messages, 20)
    print(f"\n压缩后 messages: {len(compressed)} 条")
    print(f"移除了: {[m['role'] + ':' + str(m['content'])[:30] for m in messages if m not in compressed]}")
    await call_llm(compressed, "压缩到20条 (当前逻辑)")

    # 测试 3: 更好的压缩——保留用户原始任务
    def compress_keep_task(msgs, max_msgs=20):
        if len(msgs) <= max_msgs:
            return msgs
        # 保留 system + 原始任务 + 最近的消息
        keep = [msgs[0], msgs[1]]  # system + 原始任务
        remaining = max_msgs - 2
        keep.extend(msgs[-remaining:])
        return keep

    compressed2 = compress_keep_task(messages, 20)
    print(f"\n改进压缩后 messages: {len(compressed2)} 条")
    print(f"保留的任务: {compressed2[1]['content'][:30]}")
    await call_llm(compressed2, "压缩到20条 (保留原始任务)")


if __name__ == "__main__":
    asyncio.run(main())
