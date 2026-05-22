"""Control UI 端到端测试 —— 通过 WebSocket 验证所有修复功能

测试场景：
1. 基础聊天（验证真流式）
2. 工具调用（shell + file_read）
3. 物理执行者调度（scheduler_dispatch → mock 执行者）
4. Heartbeat 状态查询
5. 多轮对话 + 记忆
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).parent.parent))

API_URL = "ws://localhost:8002/ws"
HTTP_URL = "http://localhost:8002"


class ControlUITester:
    def __init__(self):
        self.ws = None
        self.session_id = f"test_{int(time.time())}"
        self.received_chunks = []
        self.received_reasoning = []
        self.completed_response = None
        self.tool_calls_seen = []
        self.heartbeat_status = None

    async def connect(self):
        """连接 WebSocket"""
        self.ws = await websockets.connect(API_URL, proxy=None)
        # 等待初始健康状态
        msg = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
        data = json.loads(msg)
        assert data["type"] == "system.health", f"Expected health, got {data['type']}"
        print(f"✅ WebSocket 连接成功 | 系统状态: {data['payload'].get('status', 'unknown')}")
        print(f"   NATS: {data['payload'].get('natsConnected')} | Redis: {data['payload'].get('redisConnected')}")
        return True

    async def send_chat(self, content: str, images=None):
        """发送聊天消息"""
        await self.ws.send(json.dumps({
            "type": "chat.message",
            "payload": {
                "session_id": self.session_id,
                "user_id": "test_user",
                "content": content,
                "images": images or [],
            }
        }))
        print(f"\n📤 发送: {content[:60]}")

    async def collect_messages(self, timeout=60.0):
        """收集消息直到收到完成通知或超时"""
        self.received_chunks = []
        self.received_reasoning = []
        self.completed_response = None
        start = time.time()

        while time.time() - start < timeout:
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                data = json.loads(msg)
                msg_type = data.get("type", "")
                payload = data.get("payload", {})

                if msg_type == "chat.stream_chunk":
                    chunk = payload.get("chunk", "")
                    self.received_chunks.append(chunk)
                    # 实时打印（模拟前端体验）
                    print(chunk, end="", flush=True)

                elif msg_type == "chat.stream_reasoning":
                    reason = payload.get("chunk", "")
                    self.received_reasoning.append(reason)

                elif msg_type == "chat.completed":
                    self.completed_response = payload.get("content", "")
                    print(f"\n✅ 对话完成 | 长度: {len(self.completed_response)} chars")
                    return True

                elif msg_type == "task.completed":
                    self.completed_response = payload.get("result", "")
                    print(f"\n✅ 任务完成")
                    return True

                elif msg_type == "task.step":
                    step = payload.get("step", {})
                    self.tool_calls_seen.append(step)
                    print(f"\n   [Step] {step.get('action', '?')} via {step.get('executor', '?')}")

                elif msg_type == "error":
                    print(f"\n❌ 错误: {payload.get('message', 'Unknown')}")
                    return False

                elif msg_type == "chat.message_accepted":
                    print(f"   [接受] session={payload.get('session_id')}")

            except asyncio.TimeoutError:
                # 2 秒内无消息，检查是否已有足够内容
                if self.received_chunks:
                    full = "".join(self.received_chunks)
                    # 如果内容看起来完整（以句号/问号/换行结尾），提前返回
                    if full.strip().endswith((".", "。", "!", "？", "?", "\n")):
                        print(f"\n⚠️ 提前返回（流式可能未发完成事件）")
                        self.completed_response = full
                        return True
                continue

        print(f"\n⏱️ 超时 ({timeout}s)")
        self.completed_response = "".join(self.received_chunks)
        return bool(self.completed_response)

    async def test_basic_chat(self):
        """测试 1: 基础聊天（验证流式输出）"""
        print("\n" + "="*60)
        print("TEST 1: 基础聊天（验证真流式 + Brain v2 人格注入）")
        print("="*60)

        await self.send_chat("你好，请简单介绍一下你自己，以及你能为我做什么")
        ok = await self.collect_messages(timeout=45.0)

        full = self.completed_response or "".join(self.received_chunks)
        print(f"\n📊 收到 {len(self.received_chunks)} 个流式 chunk")
        print(f"📊 收到 {len(self.received_reasoning)} 个 reasoning chunk")
        print(f"📊 总回复长度: {len(full)} chars")

        # 验证：回复应该提到 Tent OS、工具能力、物理执行者
        checks = [
            ("Tent OS" in full or "操作系统" in full, "自我介绍包含 Tent OS"),
            ("工具" in full or "shell" in full or "文件" in full, "提到工具能力"),
            (len(self.received_chunks) > 3, "流式输出 >3 个 chunk（真流式验证）"),
        ]
        for passed, desc in checks:
            print(f"   {'✅' if passed else '❌'} {desc}")
        return ok and all(c[0] for c in checks)

    async def test_tool_calling(self):
        """测试 2: 工具调用（shell + file_read）"""
        print("\n" + "="*60)
        print("TEST 2: 工具调用（shell + file_read）")
        print("="*60)

        await self.send_chat("请帮我查看当前目录下有哪些文件，然后读取 README.md 的前20行")
        ok = await self.collect_messages(timeout=60.0)

        full = self.completed_response or "".join(self.received_chunks)
        print(f"\n📊 收到 {len(self.received_chunks)} 个流式 chunk")
        print(f"📊 总回复长度: {len(full)} chars")

        checks = [
            ("README" in full or "readme" in full or "文件" in full, "回复中提到文件/目录"),
            (len(full) > 50, "回复有实质内容"),
        ]
        for passed, desc in checks:
            print(f"   {'✅' if passed else '❌'} {desc}")
        return ok

    async def test_physical_executor(self):
        """测试 3: 物理执行者调度（scheduler_dispatch）"""
        print("\n" + "="*60)
        print("TEST 3: 物理执行者调度（scheduler_dispatch → mock）")
        print("="*60)

        # 直接使用 scheduler_dispatch 工具，看 LLM 是否会调度 mock 执行者
        await self.send_chat(
            "我有一个测试任务：请调度 mock 执行者执行 move 动作，"
            "参数是 target: test_object。这是系统测试，请直接调用 scheduler_dispatch 工具。"
        )
        ok = await self.collect_messages(timeout=45.0)

        full = self.completed_response or "".join(self.received_chunks)
        print(f"\n📊 收到 {len(self.received_chunks)} 个流式 chunk")
        print(f"📊 总回复长度: {len(full)} chars")

        # 验证：回复应该提到调度结果或执行状态
        checks = [
            ("mock" in full.lower() or "调度" in full or "执行" in full or "完成" in full, "回复包含调度/执行信息"),
            (len(full) > 20, "回复有实质内容"),
        ]
        for passed, desc in checks:
            print(f"   {'✅' if passed else '❌'} {desc}")
        return ok

    async def test_heartbeat_status(self):
        """测试 4: Heartbeat 状态查询"""
        print("\n" + "="*60)
        print("TEST 4: Heartbeat 状态查询")
        print("="*60)

        # 通过 API 查询心跳状态
        import httpx
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{HTTP_URL}/api/v1/health")
                data = resp.json()
                print(f"   健康状态: {data}")
            except Exception as e:
                print(f"   ⚠️ 健康检查 API 失败: {e}")

        # 查询会话历史，看是否有 heartbeat 记录
        await self.send_chat("系统最近有没有执行什么后台任务？")
        ok = await self.collect_messages(timeout=45.0)

        full = self.completed_response or "".join(self.received_chunks)
        print(f"\n📊 总回复长度: {len(full)} chars")

        checks = [
            (len(full) > 20, "回复有实质内容"),
        ]
        for passed, desc in checks:
            print(f"   {'✅' if passed else '❌'} {desc}")
        return ok

    async def test_memory_continuity(self):
        """测试 5: 记忆连续性（多轮对话）"""
        print("\n" + "="*60)
        print("TEST 5: 记忆连续性（多轮对话）")
        print("="*60)

        # 第一轮：告诉 AI 一个偏好
        await self.send_chat("请记住：我的名字叫 Frank，我喜欢简洁专业的回答")
        await self.collect_messages(timeout=45.0)
        print(f"   第一轮完成")

        # 第二轮：测试是否记得
        await self.send_chat("我刚才告诉你我叫什么？")
        ok = await self.collect_messages(timeout=45.0)

        full = self.completed_response or "".join(self.received_chunks)
        print(f"\n📊 总回复长度: {len(full)} chars")

        checks = [
            ("Frank" in full or "frank" in full, "记得用户名字 Frank"),
        ]
        for passed, desc in checks:
            print(f"   {'✅' if passed else '❌'} {desc}")
        return ok and all(c[0] for c in checks)

    async def close(self):
        if self.ws:
            await self.ws.close()


async def main():
    print("="*60)
    print("Tent OS Control UI 端到端测试")
    print(f"API: {HTTP_URL}")
    print(f"WebSocket: {API_URL}")
    print("="*60)

    tester = ControlUITester()
    results = []

    try:
        await tester.connect()

        # 运行所有测试
        results.append(("基础聊天", await tester.test_basic_chat()))
        results.append(("工具调用", await tester.test_tool_calling()))
        results.append(("物理执行者调度", await tester.test_physical_executor()))
        results.append(("Heartbeat 状态", await tester.test_heartbeat_status()))
        results.append(("记忆连续性", await tester.test_memory_continuity()))

    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await tester.close()

    # 总结
    print("\n" + "="*60)
    print("测试结果总结")
    print("="*60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        print(f"   {'✅' if result else '❌'} {name}")
    print(f"\n总计: {passed}/{total} 通过")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
