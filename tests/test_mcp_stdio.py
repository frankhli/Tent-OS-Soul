#!/usr/bin/env python3
"""MCPClient stdio 模式端到端测试"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tent_os.plugins.mcp_client import MCPClientPlugin


async def test_stdio():
    print("=" * 60)
    print("MCPClient stdio 端到端测试")
    print("=" * 60)

    mcp = MCPClientPlugin()

    # 配置：通过 python3 启动测试 MCP Server
    await mcp.initialize({
        "name": "test_stdio",
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(Path(__file__).parent / "mcp_test_server.py")],
    })

    # 1. 验证工具发现
    actions = mcp.supported_actions()
    print(f"\n📋 发现工具: {actions}")
    assert "echo" in actions, f"echo 不在工具列表中: {actions}"
    assert "add" in actions, f"add 不在工具列表中: {actions}"
    assert "get_time" in actions, f"get_time 不在工具列表中: {actions}"
    print("  ✅ tools/list 工具发现正常")

    # 2. 测试 echo 工具
    result = await mcp.execute("echo", {"message": "Hello Tent OS", "task_id": "t1"})
    print(f"\n🔧 echo 结果: {result}")
    assert result["status"] == "completed"
    assert "Hello Tent OS" in str(result["result"])
    print("  ✅ echo 工具调用正常")

    # 3. 测试 add 工具
    result = await mcp.execute("add", {"a": 3, "b": 5, "task_id": "t2"})
    print(f"\n🔧 add 结果: {result}")
    assert result["status"] == "completed"
    assert "8" in str(result["result"])
    print("  ✅ add 工具调用正常")

    # 4. 测试 get_time 工具
    result = await mcp.execute("get_time", {"task_id": "t3"})
    print(f"\n🔧 get_time 结果: {result}")
    assert result["status"] == "completed"
    assert "202" in str(result["result"])  # 年份
    print("  ✅ get_time 工具调用正常")

    # 5. 关闭连接
    await mcp.shutdown()
    print("\n  ✅ 连接关闭正常")

    print("\n" + "=" * 60)
    print("✅ MCPClient stdio 端到端测试全部通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_stdio())
