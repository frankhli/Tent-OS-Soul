"""Capabilities 模式端到端测试 — 逐个场景验证"""

import asyncio
import json
import sys
import time

import websockets

WS_URL = "ws://localhost:8003/ws"


async def send_and_collect(ws, content, capabilities, deep_thinking, session_id):
    payload = {
        "type": "chat.message",
        "payload": {
            "session_id": session_id,
            "user_id": "test_user",
            "content": content,
            "tools": capabilities,
            "deep_thinking": deep_thinking,
        }
    }
    await ws.send(json.dumps(payload))

    chunks = []
    tool_calls = []
    tool_results = []
    completed = None
    start = time.time()

    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=180)
        except asyncio.TimeoutError:
            break

        data = json.loads(msg)
        t = data.get("type")
        p = data.get("payload", {})

        # 只处理属于当前 session 的消息（过滤并发干扰）
        msg_sid = p.get("session_id", "")
        if msg_sid and msg_sid != session_id:
            continue

        if t == "chat.stream_chunk":
            chunks.append(p.get("content", ""))
        elif t == "chat.tool_call":
            tool_calls.append(p)
        elif t == "chat.tool_result":
            tool_results.append(p)
        elif t == "chat.completed":
            completed = p
            break
        elif t == "chat.error":
            print(f"    ERROR: {p}")
            break

    elapsed = int((time.time() - start) * 1000)
    reply = "".join(chunks)
    return {
        "reply": reply,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "completed": completed,
        "elapsed_ms": elapsed,
    }


def check(name, result, expected_tools=None, expected_caps=None, expected_deep=None):
    ok = result["completed"] is not None
    caps = result["completed"].get("capabilities", {}) if result["completed"] else {}
    deep = result["completed"].get("deep_thinking", False) if result["completed"] else None
    tool_names = [tc["tool"] for tc in result["tool_calls"]]

    checks = []
    if expected_tools is not None:
        if expected_tools == 0:
            checks.append(("no tools", len(tool_names) == 0))
        else:
            checks.append(("has tools", len(tool_names) > 0))
    if expected_caps is not None:
        for k, v in expected_caps.items():
            checks.append((f"cap.{k}={v}", caps.get(k) == v))
    if expected_deep is not None:
        checks.append((f"deep={expected_deep}", deep == expected_deep))

    all_ok = ok and all(c[1] for c in checks)
    status = "PASS" if all_ok else "FAIL"

    print(f"\n[{status}] {name} ({result['elapsed_ms']}ms)")
    print(f"  reply: {result['reply'][:180]}...")
    print(f"  tools called: {tool_names if tool_names else 'none'}")
    for cname, cok in checks:
        print(f"  check '{cname}': {'OK' if cok else 'FAIL'}")
    return all_ok


async def run_tests():
    print("Connecting to", WS_URL)
    ws = await websockets.connect(WS_URL)
    health = json.loads(await ws.recv())
    print(f"Server: {health['type']}\n")

    passed = 0
    total = 0
    sid = f"e2e_{int(time.time())}"

    # === TEST 1: 纯聊天（无工具）===
    total += 1
    r = await send_and_collect(ws, "你好，今天过得怎么样？",
                               {"web_search": False, "file_ops": False}, False, sid)
    if check("TEST 1: 纯聊天（无工具）", r, expected_tools=0,
             expected_caps={"web_search": False, "file_ops": False}, expected_deep=False):
        passed += 1

    # === TEST 2: 本地 shell（file_ops=True）===
    total += 1
    r = await send_and_collect(ws, "执行 echo 'hello tent' 告诉我输出",
                               {"web_search": False, "file_ops": True}, False, sid)
    if check("TEST 2: 本地 shell（file_ops=True）", r,
             expected_caps={"file_ops": True}, expected_deep=False):
        passed += 1

    # === TEST 3: 目录列表（file_ops=True）===
    total += 1
    r = await send_and_collect(ws, "当前目录下有哪些文件？",
                               {"web_search": False, "file_ops": True}, False, sid)
    if check("TEST 3: 目录列表（file_ops=True）", r,
             expected_caps={"file_ops": True}, expected_deep=False):
        passed += 1

    # === TEST 4: 组合工具（web_search + file_ops，用本地命令避免网络超时）===
    total += 1
    r = await send_and_collect(ws, "先执行 pwd 看看当前路径，然后告诉我这是什么操作系统",
                               {"web_search": True, "file_ops": True}, False, sid)
    if check("TEST 4: 组合工具", r,
             expected_caps={"web_search": True, "file_ops": True}, expected_deep=False):
        passed += 1

    # === TEST 5: 深度思考开关 ===
    total += 1
    r = await send_and_collect(ws, "分析一下本地文件系统在 AI 助手中的作用",
                               {"web_search": False, "file_ops": True}, True, sid)
    if check("TEST 5: 深度思考（deep_thinking=True）", r,
             expected_caps={"file_ops": True}, expected_deep=True):
        passed += 1

    # === TEST 6: 工具关闭时 LLM 不应调用工具 ===
    total += 1
    r = await send_and_collect(ws, "帮我搜索一下最近的天气",
                               {"web_search": False, "file_ops": False}, False, sid)
    if check("TEST 6: 工具关闭时请求搜索", r, expected_tools=0,
             expected_caps={"web_search": False, "file_ops": False}, expected_deep=False):
        passed += 1

    # === TEST 7: Inline Approval Flow（危险操作确认）===
    total += 1
    import subprocess
    subprocess.run(["touch", "/Users/frank/Desktop/tent_e2e_approval.txt"], check=True)
    
    sid_approval = f"{sid}_approval"
    r1 = await send_and_collect(ws, "删除 /Users/frank/Desktop/tent_e2e_approval.txt",
                                {"web_search": False, "file_ops": True}, False, sid_approval)
    
    has_require_approval = any(
        json.loads(tr.get("result", "{}")).get("status") == "require_approval"
        for tr in r1["tool_results"]
    )
    
    approval_ok = False
    if has_require_approval:
        r2 = await send_and_collect(ws, "确认",
                                    {"web_search": False, "file_ops": True}, False, sid_approval)
        has_completed_execution = any(
            json.loads(tr.get("result", "{}")).get("status") == "completed"
            for tr in r2["tool_results"]
        )
        approval_ok = check("TEST 7: Inline Approval Flow", r2,
                            expected_caps={"file_ops": True}, expected_deep=False) and has_completed_execution
        if not has_completed_execution:
            print("    check 'confirmed execution': FAIL")
    else:
        print(f"\n[FAIL] TEST 7: Inline Approval Flow - no require_approval received")
    
    if approval_ok:
        passed += 1

    await ws.close()

    print(f"\n{'='*60}")
    print(f"RESULT: {passed}/{total} passed")
    print(f"{'='*60}")
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
