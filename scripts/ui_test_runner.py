#!/usr/bin/env python3
"""
Tent OS Control UI 全功能端到端测试脚本

从前端 WebSocket 入口模拟真实用户对话，测试所有功能模块的真实效果。
记录：响应时间、token 消耗（估算）、回复质量、bug。
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import websockets

WS_URL = "ws://localhost:8002/ws"
USER_ID = "test_user_frank"


class TestSession:
    """单个测试会话"""
    def __init__(self, name: str, session_id: str = None):
        self.name = name
        self.session_id = session_id or f"test_{int(time.time())}_{name}"
        self.messages: List[Dict] = []
        self.start_time: float = 0
        self.end_time: float = 0
        self.full_response: str = ""
        self.reasoning: str = ""
        self.stream_chunks: List[str] = []
        self.plan_steps: List[Dict] = []
        self.tool_calls: List[Dict] = []
        self.errors: List[str] = []
        self.completed = False

    def duration(self) -> float:
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return 0

    def estimated_tokens(self) -> int:
        # 粗略估算：中文 ~2 chars/token，英文 ~4 chars/token
        text = self.full_response
        chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english = len(text) - chinese
        return chinese // 2 + english // 4 + 10

    def report(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"测试: {self.name}",
            f"会话ID: {self.session_id}",
            f"耗时: {self.duration():.1f}s",
            f"估算Token: ~{self.estimated_tokens()}",
            f"流式块数: {len(self.stream_chunks)}",
            f"Plan步骤: {len(self.plan_steps)}",
            f"工具调用: {len(self.tool_calls)}",
            f"错误: {len(self.errors)}",
            f"完成: {'✅' if self.completed else '❌'}",
            f"--- AI 回复 ---",
            self.full_response[:800] + ("..." if len(self.full_response) > 800 else ""),
        ]
        if self.reasoning:
            lines.extend([
                f"--- 思考过程 ---",
                self.reasoning[:400] + ("..." if len(self.reasoning) > 400 else ""),
            ])
        if self.errors:
            lines.extend([f"--- 错误 ---", "\n".join(self.errors)])
        return "\n".join(lines)


class UITestRunner:
    """Control UI 测试运行器"""

    def __init__(self):
        self.results: List[TestSession] = []
        self.ws = None
        self._receive_task = None
        self._current_session: Optional[TestSession] = None
        self._msg_buffer: List[Dict] = []

    async def connect(self):
        print(f"[TEST] 连接 WebSocket: {WS_URL}")
        self.ws = await websockets.connect(WS_URL)
        self._receive_task = asyncio.create_task(self._receive_loop())
        # 等待初始健康状态
        await asyncio.sleep(0.5)

    async def disconnect(self):
        if self._receive_task:
            self._receive_task.cancel()
        if self.ws:
            await self.ws.close()

    async def _receive_loop(self):
        """持续接收 WebSocket 消息"""
        try:
            async for raw in self.ws:
                try:
                    msg = json.loads(raw)
                    self._msg_buffer.append(msg)
                    await self._handle_msg(msg)
                except json.JSONDecodeError:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[TEST] WebSocket 接收错误: {e}")

    async def _handle_msg(self, msg: Dict):
        msg_type = msg.get("type", "")
        payload = msg.get("payload", {})

        if msg_type == "chat.stream_chunk":
            chunk = payload.get("chunk", "")
            if self._current_session:
                self._current_session.stream_chunks.append(chunk)
                self._current_session.full_response += chunk

        elif msg_type == "chat.stream_reasoning":
            chunk = payload.get("chunk", "")
            if self._current_session:
                self._current_session.reasoning += chunk

        elif msg_type == "task.plan":
            if self._current_session:
                self._current_session.plan_steps.append(payload)

        elif msg_type == "task.step":
            if self._current_session:
                self._current_session.tool_calls.append(payload)

        elif msg_type in ("chat.completed", "task.completed"):
            if self._current_session:
                self._current_session.completed = True
                self._current_session.end_time = time.time()
                if msg_type == "chat.completed":
                    self._current_session.full_response = payload.get("content", "")
                    self._current_session.reasoning = payload.get("reasoning", "")

        elif msg_type == "task.failed":
            if self._current_session:
                self._current_session.completed = True
                self._current_session.end_time = time.time()
                self._current_session.errors.append(payload.get("error", "未知错误"))

        elif msg_type == "chat.message_accepted":
            pass  # 正常

        elif msg_type == "system.health":
            pass  # 忽略健康状态

    async def send_chat(self, content: str, session_id: str = None, user_id: str = USER_ID,
                        wait_timeout: float = 120.0) -> TestSession:
        """发送聊天消息并等待回复完成"""
        session = TestSession(name=content[:30], session_id=session_id)
        self._current_session = session
        session.start_time = time.time()

        await self.ws.send(json.dumps({
            "type": "chat.message",
            "payload": {
                "session_id": session.session_id,
                "user_id": user_id,
                "content": content,
            }
        }))

        # 等待完成（最多 wait_timeout 秒）
        try:
            await asyncio.wait_for(self._wait_completion(), timeout=wait_timeout)
        except asyncio.TimeoutError:
            session.end_time = time.time()
            session.errors.append(f"超时 ({wait_timeout}s)")

        self.results.append(session)
        self._current_session = None
        return session

    async def _wait_completion(self):
        while self._current_session and not self._current_session.completed:
            await asyncio.sleep(0.2)

    async def send_chat_in_session(self, content: str, session_id: str,
                                    wait_timeout: float = 120.0) -> TestSession:
        """在已有会话中继续对话"""
        return await self.send_chat(content, session_id=session_id, wait_timeout=wait_timeout)

    def print_summary(self):
        print(f"\n{'='*60}")
        print("Tent OS 全功能测试报告")
        print(f"时间: {datetime.now().isoformat()}")
        print(f"{'='*60}")

        total_time = sum(r.duration() for r in self.results)
        total_tokens = sum(r.estimated_tokens() for r in self.results)
        total_errors = sum(len(r.errors) for r in self.results)

        print(f"\n总计测试: {len(self.results)} 轮对话")
        print(f"总耗时: {total_time:.1f}s")
        print(f"总估算Token: ~{total_tokens}")
        print(f"总错误: {total_errors}")
        print(f"完成率: {sum(1 for r in self.results if r.completed)}/{len(self.results)}")

        for r in self.results:
            print(r.report())


async def run_all_tests():
    runner = UITestRunner()
    await runner.connect()

    try:
        print("\n" + "="*60)
        print("开始全功能端到端测试")
        print("="*60)

        # ========== 场景1: 基础对话 + 用户画像 ==========
        print("\n[场景1] 基础对话 + 用户画像建立")
        r1 = await runner.send_chat("你好，我叫Frank，是一个酒店科技创业者。我平时喜欢用简洁高效的方式沟通。")
        print(r1.report())

        # 同一会话继续：测试多轮记忆
        r2 = await runner.send_chat_in_session("记住：我最喜欢的咖啡是美式，不喜欢太甜的东西。我的酒店品牌叫希遇。", r1.session_id)
        print(r2.report())

        # 测试是否记住之前的信息
        r3 = await runner.send_chat_in_session("我叫什么名字？我的酒店品牌叫什么？我喜欢什么咖啡？", r1.session_id)
        print(r3.report())

        # ========== 场景2: 跨对话记忆 ==========
        print("\n[场景2] 跨对话记忆测试")
        r4 = await runner.send_chat("你好，还记得我是谁吗？上次我们聊过我的酒店品牌。")
        print(r4.report())

        # ========== 场景3: 工具调用 ==========
        print("\n[场景3] 工具调用测试")
        r5 = await runner.send_chat("请帮我查看当前目录下有哪些文件，然后创建一个 test_hello.txt 文件，内容是 'Hello from Tent OS'")
        print(r5.report())

        # ========== 场景4: 网页搜索 ==========
        print("\n[场景4] 网页搜索测试")
        r6 = await runner.send_chat("搜索一下2026年AI Agent市场的最新趋势")
        print(r6.report())

        # ========== 场景5: Plan/Execute 复杂任务 ==========
        print("\n[场景5] Plan/Execute 复杂任务")
        r7 = await runner.send_chat("帮我做三件事：1. 查看当前目录结构 2. 搜索Python asyncio最佳实践 3. 把搜索结果保存到一个markdown文件")
        print(r7.report())

        # ========== 场景6: Skills - PPT生成 ==========
        print("\n[场景6] Skills - PPT生成")
        r8 = await runner.send_chat("帮我生成一个关于'AI在酒店行业的应用'的PPT，5页左右")
        print(r8.report())

        # ========== 场景7: 长对话 Compaction ==========
        print("\n[场景7] 长对话 Compaction 测试（15轮以上）")
        session_long = f"test_long_{int(time.time())}"
        for i in range(1, 6):
            r = await runner.send_chat_in_session(
                f"这是第{i}轮对话。请告诉我关于人工智能的第{i}个重要发展趋势，并简单解释。",
                session_long, wait_timeout=60
            )
            print(f"  长对话轮次{i}: 耗时{r.duration():.1f}s, 估算Token: ~{r.estimated_tokens()}")

        # 测试 compaction 后是否还记得开头
        r_comp = await runner.send_chat_in_session("我们刚才聊了什么话题？请总结一下前面几轮的内容。", session_long)
        print(r_comp.report())

        # ========== 场景8: 情绪检测 + 人格 ==========
        print("\n[场景8] 情绪检测 + 人格响应测试")
        r9 = await runner.send_chat("气死我了！这个系统又出bug了！你怎么这么笨啊！")
        print(r9.report())

        r10 = await runner.send_chat_in_session("哈哈，刚才是测试你的情绪反应。其实你做得很棒！", r9.session_id)
        print(r10.report())

        # ========== 场景9: 物理执行者可见性测试 ==========
        print("\n[场景9] 物理执行者可见性测试")
        r11 = await runner.send_chat("帮我检查实验室的3D打印零件，然后送到朝阳区客户手里")
        print(r11.report())

        # ========== 场景10: 审批流程测试 ==========
        print("\n[场景10] 审批流程测试（高风险任务）")
        r12 = await runner.send_chat("删除当前目录下的所有文件")
        print(r12.report())

        runner.print_summary()

    finally:
        await runner.disconnect()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
