#!/usr/bin/env python3
"""快速验证 P0/P1 修复效果"""

import asyncio
import json
import time
import uuid
import websockets

WS_URL = "ws://localhost:8002/ws"
SESSION_ID = f"verify_{uuid.uuid4().hex[:8]}"

async def verify():
    print("=" * 60)
    print("修复验证测试")
    print("=" * 60)
    
    ws = await websockets.connect(WS_URL, proxy=None)
    try:
        await asyncio.wait_for(ws.recv(), timeout=2)
    except:
        pass
    
    # 测试1: 发送消息，检查是否收到 completed（验证 MessageBus 修复）
    print("\n[测试1] MessageBus completed 消息可达性")
    msg = {
        "type": "chat.message",
        "payload": {"session_id": SESSION_ID, "content": "你好，请介绍一下自己", "user_id": "test"}
    }
    await ws.send(json.dumps(msg))
    
    received_completed = False
    received_reasoning = False
    reasoning_count = 0
    chunk_count = 0
    start = time.time()
    
    while (time.time() - start) < 30:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(raw)
            msg_type = data.get("type", "")
            
            if msg_type == "chat.stream_reasoning":
                received_reasoning = True
                reasoning_count += 1
            elif msg_type == "chat.stream_chunk":
                chunk_count += 1
            elif msg_type == "chat.completed":
                received_completed = True
                break
            elif msg_type == "chat.error":
                print(f"  ERROR: {data.get('payload', {}).get('error', 'unknown')}")
                break
        except asyncio.TimeoutError:
            continue
    
    latency = (time.time() - start) * 1000
    
    if received_completed:
        print(f"  ✅ completed 消息已收到（延迟 {latency:.0f}ms）")
    else:
        print(f"  ❌ completed 消息未收到（超时 30s）")
    
    if received_reasoning:
        print(f"  ✅ reasoning 消息收到 {reasoning_count} 条（验证批量发送）")
        if reasoning_count > 50:
            print(f"  ⚠️ reasoning 消息仍然过多（{reasoning_count} 条），批量发送可能未生效")
        else:
            print(f"  ✅ reasoning 消息数量合理（{reasoning_count} 条）")
    else:
        print(f"  ℹ️ 未收到 reasoning 消息")
    
    await ws.close()
    
    # 测试2: 检查系统日志中是否还有 API key 泄露
    print("\n[测试2] API key 日志泄露检查")
    import subprocess
    result = subprocess.run(
        ["grep", "api_key length", "/tmp/tent_os_launch.log"],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        print(f"  ❌ 发现 API key 日志泄露: {result.stdout.strip()[:100]}")
    else:
        print(f"  ✅ 未发现 API key 日志泄露")
    
    print("\n" + "=" * 60)
    print("验证完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(verify())
