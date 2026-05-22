#!/usr/bin/env python3
"""MCPClient SSE 模式端到端测试"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from tent_os.plugins.mcp_client import MCPClientPlugin


async def wait_for_server(url: str, timeout: float = 10.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                # SSE 是流式响应，用 stream 只读状态码就关闭
                async with client.stream("GET", url, timeout=2) as response:
                    if response.status_code == 200:
                        return True
        except Exception:
            pass
        await asyncio.sleep(0.3)
    return False


async def test_sse():
    print("=" * 60)
    print("MCPClient SSE 端到端测试")
    print("=" * 60)

    # 清理残留进程
    subprocess.run("lsof -ti:8765 | xargs kill -9 2>/dev/null", shell=True)
    time.sleep(1)

    # 启动 SSE Server（后台子进程）
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "mcp_test_server_sse.py")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(Path(__file__).parent.parent),
    )

    # 等待 Server 就绪
    ready = await wait_for_server("http://127.0.0.1:8765/sse", timeout=10)
    if not ready:
        proc.terminate()
        proc.wait()
        raise RuntimeError("SSE Server 启动失败")

    try:
        mcp = MCPClientPlugin()
        await mcp.initialize({
            "name": "test_sse",
            "transport": "sse",
            "url": "http://127.0.0.1:8765/sse",
        })

        # 1. 验证工具发现
        actions = mcp.supported_actions()
        print(f"\n📋 发现工具: {actions}")
        assert "multiply" in actions, f"multiply 不在工具列表中: {actions}"
        assert "uppercase" in actions, f"uppercase 不在工具列表中: {actions}"
        print("  ✅ tools/list 工具发现正常")

        # 2. 测试 multiply
        result = await mcp.execute("multiply", {"x": 6, "y": 7, "task_id": "t1"})
        print(f"\n🔧 multiply 结果: {result}")
        assert result["status"] == "completed"
        assert "42" in str(result["result"])
        print("  ✅ multiply 工具调用正常")

        # 3. 测试 uppercase
        result = await mcp.execute("uppercase", {"text": "tent os", "task_id": "t2"})
        print(f"\n🔧 uppercase 结果: {result}")
        assert result["status"] == "completed"
        assert "TENT OS" in str(result["result"])
        print("  ✅ uppercase 工具调用正常")

        await mcp.shutdown()
        print("\n  ✅ 连接关闭正常")

        print("\n" + "=" * 60)
        print("✅ MCPClient SSE 端到端测试全部通过")
        print("=" * 60)

    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    asyncio.run(test_sse())
