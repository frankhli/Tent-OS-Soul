#!/usr/bin/env python3
"""
快速验证：_handle_chat_reply 路径 reasoning 批量效果
"""

import asyncio
import json
import time
import websockets

WS_URL = "ws://localhost:8002/ws"
USER_ID = "test_user_reasoning"


async def verify():
    print("[VERIFY] 连接 WebSocket...")
    ws = await websockets.connect(WS_URL, proxy=None)
    
    session_id = f"verify_chat_reply_{int(time.time())}"
    reasoning_chunks = []
    content_chunks = []
    completed = False
    
    async def recv_loop():
        nonlocal completed
        async for raw in ws:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                payload = msg.get("payload", {})
                
                if msg_type == "chat.stream_reasoning":
                    reasoning_chunks.append(payload.get("chunk", ""))
                elif msg_type == "chat.stream_chunk":
                    content_chunks.append(payload.get("chunk", ""))
                elif msg_type in ("chat.completed", "task.completed"):
                    completed = True
                    break
                elif msg_type == "task.failed":
                    completed = True
                    break
            except json.JSONDecodeError:
                pass
    
    recv_task = asyncio.create_task(recv_loop())
    
    # 发送一个纯聊天问题（预期走 _handle_chat_reply）
    await ws.send(json.dumps({
        "type": "chat.message",
        "payload": {
            "session_id": session_id,
            "user_id": USER_ID,
            "content": "请详细解释一下量子计算的基本原理，包括叠加态和纠缠态",
        }
    }))
    
    print(f"[VERIFY] 等待回复完成（超时120s）...")
    try:
        await asyncio.wait_for(recv_task, timeout=120)
    except asyncio.TimeoutError:
        print("[VERIFY] ⚠️ 超时")
    
    await ws.close()
    
    total_reasoning_msgs = len(reasoning_chunks)
    total_reasoning_chars = sum(len(c) for c in reasoning_chunks)
    total_content_msgs = len(content_chunks)
    avg_reasoning_chunk = total_reasoning_chars / total_reasoning_msgs if total_reasoning_msgs else 0
    
    print(f"\n{'='*50}")
    print(f"路径: _handle_chat_reply (纯聊天)")
    print(f"会话ID: {session_id}")
    print(f"完成状态: {'✅' if completed else '❌'}")
    print(f"reasoning 消息数: {total_reasoning_msgs}")
    print(f"reasoning 总字符: {total_reasoning_chars}")
    print(f"reasoning 平均块大小: {avg_reasoning_chunk:.1f} 字符")
    print(f"content 消息数: {total_content_msgs}")
    print(f"{'='*50}")
    
    return completed, total_reasoning_msgs, avg_reasoning_chunk


if __name__ == "__main__":
    asyncio.run(verify())
