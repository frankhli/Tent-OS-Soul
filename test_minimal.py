import asyncio
import json
import websockets

async def test():
    print("Connecting...")
    ws = await websockets.connect("ws://localhost:8003/ws")
    msg = await ws.recv()
    print(f"Health: {json.loads(msg)['type']}")

    payload = {
        "type": "chat.message",
        "payload": {
            "session_id": "test_minimal_1",
            "user_id": "test_user",
            "content": "你好",
            "tools": {"web_search": False, "file_ops": False},
            "deep_thinking": False,
        }
    }
    print("Sending...")
    await ws.send(json.dumps(payload))

    for i in range(20):
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=15)
            data = json.loads(msg)
            print(f"  [{data['type']}] {str(data.get('payload',''))[:150]}")
            if data['type'] == 'chat.completed':
                break
        except asyncio.TimeoutError:
            print("  [TIMEOUT]")
            break

    await ws.close()
    print("Done")

asyncio.run(test())
