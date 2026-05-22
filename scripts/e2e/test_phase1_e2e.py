#!/usr/bin/env python3
"""Phase 1 E2E 测试 —— 跨会话真实 LLM 测试"""

import asyncio
import json
import time
import sys
sys.path.insert(0, '.')

import websockets


async def chat_session(session_id: str, user_id: str, messages: list, results: dict):
    """单个会话的 WebSocket 聊天测试"""
    uri = "ws://localhost:8002/ws"
    results[session_id] = []
    
    async with websockets.connect(uri, proxy=None) as ws:
        for msg_text in messages:
            start = time.time()
            
            payload = {
                "type": "chat.message",
                "payload": {
                    "session_id": session_id,
                    "content": msg_text,
                }
            }
            await ws.send(json.dumps(payload))
            
            chunks = []
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=120)
                    data = json.loads(raw)
                    msg_type = data.get("type", "")
                    
                    if msg_type == "chat.stream_chunk":
                        chunk = data.get("payload", {}).get("chunk", "")
                        chunks.append(chunk)
                    elif msg_type == "chat.stream_reasoning":
                        pass  # 忽略 reasoning
                    elif msg_type == "chat.completed":
                        break
                    elif msg_type == "task.completed":
                        break
                    elif msg_type == "task.failed":
                        chunks.append("[FAILED]")
                        break
                    elif msg_type == "chat.message_accepted":
                        pass  # 消息已接收，继续等待
                    elif msg_type == "error":
                        chunks.append(f"[ERROR: {data.get('payload', {})}]")
                        break
                        
                except asyncio.TimeoutError:
                    chunks.append("[TIMEOUT]")
                    break
            
            elapsed = time.time() - start
            full_response = "".join(chunks)
            
            results[session_id].append({
                "msg": msg_text,
                "elapsed": elapsed,
                "response": full_response[:300],
                "timestamp": start,
            })
            
            print(f"  [{session_id}] '{msg_text}' -> {elapsed:.1f}s | {full_response[:100]}...")


async def main():
    print("=" * 60)
    print("Phase 1 E2E 测试 —— 跨会话真实 LLM")
    print("=" * 60)
    
    results = {}
    
    # Test 1: 两个 session 同时发问候语
    print("\n[Test 1] 两个 Session 同时发问候语")
    print("-" * 40)
    
    t0 = time.time()
    await asyncio.gather(
        chat_session("phase1_test_a", "user_a", ["你好"], results),
        chat_session("phase1_test_b", "user_b", ["你好"], results),
    )
    total = time.time() - t0
    
    print(f"\n  并发总耗时: {total:.1f}s")
    print(f"  Session A: {results['phase1_test_a'][0]['elapsed']:.1f}s")
    print(f"  Session B: {results['phase1_test_b'][0]['elapsed']:.1f}s")
    
    if total < results['phase1_test_a'][0]['elapsed'] + results['phase1_test_b'][0]['elapsed'] - 1:
        print("  ✅ 并发验证通过: 两 session 非串行执行")
    else:
        print("  ⚠️ 并发可能串行")
    
    # Test 2: Session A 发复杂任务
    print("\n[Test 2] Session A 发复杂任务，Session B 发问候语")
    print("-" * 40)
    
    results2 = {}
    t0 = time.time()
    await asyncio.gather(
        chat_session("phase1_test_a2", "user_a", ["帮我写一首关于春天的诗"], results2),
        chat_session("phase1_test_b2", "user_b", ["在吗"], results2),
    )
    total = time.time() - t0
    
    print(f"\n  并发总耗时: {total:.1f}s")
    for sid in ["phase1_test_a2", "phase1_test_b2"]:
        r = results2[sid][0]
        print(f"  {sid}: '{r['msg']}' -> {r['elapsed']:.1f}s")
    
    # 检查日志中 Phase 1 的关键信号
    print("\n[Test 3] 检查日志中 Phase 1 关键信号")
    print("-" * 40)
    
    import subprocess
    log = subprocess.run(
        ["tail", "-n", "150", "/tmp/tent_os_test.log"],
        capture_output=True, text=True
    ).stdout
    
    signals = {
        "安全评估跳过(直觉)": "安全评估跳过" in log,
        "安全评估直觉": "安全评估(直觉)" in log,
        "自验证跳过": "自验证跳过" in log,
        "经验提取跳过": "经验提取跳过" in log,
        "背景认知(事件驱动)": "背景认知循环启动（事件驱动）" in log,
    }
    
    for name, found in signals.items():
        status = "✅" if found else "❌"
        print(f"  {status} {name}")
    
    print("\n" + "=" * 60)
    print("Phase 1 E2E 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
