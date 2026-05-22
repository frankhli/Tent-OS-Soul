#!/usr/bin/env python3
"""测试 Tent OS 聊天 v2：System Prompt + Reasoning + Redis 持久化"""
import asyncio
import json
import websockets
import time


async def test():
    uri = "ws://localhost:8002/ws"
    session_id = f"test_{int(time.time())}"
    
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri) as ws:
        # 等待 health 消息
        msg = json.loads(await ws.recv())
        print(f"Health: {msg.get('type')}")
        
        # 发送第一条消息（应该触发第一次对话欢迎）
        print(f"\nSending first message...")
        await ws.send(json.dumps({
            "type": "chat.message",
            "payload": {
                "session_id": session_id,
                "content": "你好",
                "user_id": "test_user"
            }
        }))
        
        # 等待 message_accepted
        msg = json.loads(await ws.recv())
        print(f"  → {msg['type']}")
        
        # 收集所有响应
        reasoning_chunks = 0
        content_chunks = 0
        final_content = ""
        
        start = time.time()
        while time.time() - start < 60:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                msg_type = msg.get("type")
                payload = msg.get("payload", {})
                
                if msg_type == "chat.stream_reasoning":
                    reasoning_chunks += 1
                    chunk = payload.get("chunk", "")
                    if reasoning_chunks <= 3:
                        print(f"  [R] {chunk[:60]}...")
                    elif reasoning_chunks == 4:
                        print(f"  [R] ... ({reasoning_chunks} reasoning chunks)")
                
                elif msg_type == "chat.stream_chunk":
                    content_chunks += 1
                    chunk = payload.get("chunk", "")
                    if content_chunks <= 3:
                        print(f"  [C] {chunk[:60]}...")
                    elif content_chunks == 4:
                        print(f"  [C] ... ({content_chunks} content chunks)")
                
                elif msg_type == "chat.completed":
                    final_content = payload.get("content", "")
                    reasoning_summary = payload.get("reasoning", "")[:100]
                    print(f"\n✅ Completed!")
                    print(f"   Reasoning chunks: {reasoning_chunks}")
                    print(f"   Content chunks: {content_chunks}")
                    print(f"   Final content ({len(final_content)} chars): {final_content[:200]}...")
                    print(f"   Reasoning summary: {reasoning_summary}...")
                    break
                
                elif msg_type == "error":
                    print(f"\n❌ Error: {payload}")
                    break
                    
            except asyncio.TimeoutError:
                print("\n⏱ Timeout waiting for response")
                break
        
        # 验证 Redis 持久化：请求历史消息
        print(f"\nRequesting history from Redis...")
        await ws.send(json.dumps({
            "type": "chat.history",
            "payload": {"session_id": session_id}
        }))
        
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if msg.get("type") == "chat.history":
            messages = msg["payload"].get("messages", [])
            print(f"✅ Redis history: {len(messages)} messages")
            for m in messages:
                print(f"   [{m['role']}] {m['content'][:80]}...")
        
        # 验证会话列表
        await ws.send(json.dumps({
            "type": "chat.session.list",
            "payload": {"user_id": "test_user"}
        }))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if msg.get("type") == "chat.session.list":
            sessions = msg["payload"].get("sessions", [])
            print(f"✅ Session list: {len(sessions)} sessions")
            for s in sessions:
                print(f"   {s['session_id']}: {s['title']} ({s['message_count']} msgs)")


if __name__ == "__main__":
    asyncio.run(test())
