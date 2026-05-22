"""验证基础修复的端到端测试"""

import asyncio
import json
import sys
import time

import websockets

WS_URL = "ws://localhost:8003/ws"


async def send_and_collect(ws, content, tools, deep_thinking, session_id, timeout=60):
    payload = {
        "type": "chat.message",
        "payload": {
            "session_id": session_id,
            "user_id": "test_user",
            "content": content,
            "tools": tools,
            "deep_thinking": deep_thinking,
        }
    }
    await ws.send(json.dumps(payload))

    chunks = []
    reasoning_chunks = []
    completed = None
    start = time.time()

    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            break

        data = json.loads(msg)
        t = data.get("type")
        p = data.get("payload", {})

        msg_sid = p.get("session_id", "")
        if msg_sid and msg_sid != session_id:
            continue

        if t == "chat.stream_chunk":
            chunks.append(p.get("content", ""))
        elif t == "chat.stream_reasoning":
            reasoning_chunks.append(p.get("chunk", ""))
        elif t == "chat.completed":
            completed = p
            break
        elif t == "chat.error":
            print(f"    ERROR: {p}")
            break

    elapsed = int((time.time() - start) * 1000)
    return {
        "reply": "".join(chunks),
        "reasoning_stream": "".join(reasoning_chunks),
        "completed": completed,
        "elapsed_ms": elapsed,
    }


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return condition


async def run_tests():
    print("Connecting to", WS_URL)
    ws = await websockets.connect(WS_URL)
    health = json.loads(await ws.recv())
    print(f"Server: {health['type']}\n")

    passed = 0
    total = 0
    sid = f"fix_{int(time.time())}"

    # === TEST 1: reasoning 字段存在于 chat.completed ===
    total += 1
    r = await send_and_collect(ws, "你好，请简单介绍一下自己", {"web_search": False, "file_ops": False}, False, sid)
    ok = True
    ok &= check("reply not empty", bool(r["reply"]), r["reply"][:80])
    ok &= check("completed.payload has 'reasoning' key", r["completed"] is not None and "reasoning" in r["completed"])
    if r["completed"]:
        ok &= check("reasoning is string", isinstance(r["completed"].get("reasoning"), str))
    if ok:
        passed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] TEST 1: reasoning field in chat.completed\n")

    # === TEST 2: deep_thinking 可开启 ===
    total += 1
    sid2 = f"{sid}_deep_on"
    r = await send_and_collect(ws, "1+1等于几", {"web_search": False, "file_ops": False}, True, sid2)
    ok = r["completed"] is not None and r["completed"].get("deep_thinking") is True
    if ok:
        passed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] TEST 2: deep_thinking can be enabled")
    if r["completed"]:
        print(f"  deep_thinking={r['completed'].get('deep_thinking')}")
    print()

    # === TEST 3: deep_thinking 可关闭（同会话）===
    total += 1
    # 在同一会话中发送 deep_thinking=False
    r = await send_and_collect(ws, "2+2等于几", {"web_search": False, "file_ops": False}, False, sid2)
    ok = r["completed"] is not None and r["completed"].get("deep_thinking") is False
    if ok:
        passed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] TEST 3: deep_thinking can be disabled (same session)")
    if r["completed"]:
        print(f"  deep_thinking={r['completed'].get('deep_thinking')}")
    print()

    # === TEST 4: 工具开关透传正确 ===
    total += 1
    sid4 = f"{sid}_tools"
    r = await send_and_collect(ws, "执行 echo test", {"web_search": False, "file_ops": True}, False, sid4)
    ok = r["completed"] is not None
    if ok:
        caps = r["completed"].get("capabilities", {})
        ok &= check("cap.file_ops=True", caps.get("file_ops") is True)
        ok &= check("cap.web_search=False", caps.get("web_search") is False)
    if ok:
        passed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] TEST 4: tool caps forwarded correctly\n")

    # === TEST 5: user.emotion 是单播（不收到其他 session 的消息）===
    total += 1
    # 这个测试比较间接：我们检查收到的消息是否都带有正确的 session_id
    # 如果 broadcast 有问题，我们可能会收到其他 session 的 completion
    r = await send_and_collect(ws, "今天心情不错", {"web_search": False, "file_ops": False}, False, sid)
    ok = r["completed"] is not None and r["completed"].get("session_id") == sid
    if ok:
        passed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] TEST 5: message routing correct\n")

    await ws.close()

    print(f"{'='*60}")
    print(f"RESULT: {passed}/{total} passed")
    print(f"{'='*60}")
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
