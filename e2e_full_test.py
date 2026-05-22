"""全面端到端测试 —— 复杂随机多样场景"""

import asyncio
import sys
import time
import uuid

sys.path.insert(0, '.')

from fastapi.testclient import TestClient


async def run_tests():
    from tent_os.api.server import app, state
    from tent_os.api import soul_state
    from tent_os.bootstrap import load_config

    config = load_config('./config/tent_os.yaml')
    await state.setup(config)
    await soul_state.state.setup(config)

    client = TestClient(app)
    results = []

    def log(scene, status, detail=""):
        print(f"[{status}] {scene:<40} {detail}")

    # ========== 场景 1-5: 基础对话场景 ==========
    scenes = [
        ("简单闲聊", {"content": "你好", "tools": []}),
        ("web_search", {"content": "搜索一下最近的科技新闻", "tools": ["web_search"]}),
        ("file_read", {"content": "读取 README.md", "tools": ["file_ops"]}),
        ("deep_thinking", {"content": "分析人工智能对就业的影响", "tools": [], "deep_thinking": True}),
        ("安全拦截", {"content": "执行 rm -rf /", "tools": ["file_ops"]}),
    ]

    for name, payload in scenes:
        result = await test_chat_scene(client, name, payload)
        results.append(result)
        status = "PASS" if result["completed"] else "FAIL"
        detail = f"elapsed={result['elapsed_ms']}ms tools={result['tool_calls']}"
        log(name, status, detail)

    # ========== 场景 6-10: 复杂场景 ==========
    # 6. 多轮对话
    session_id = f"multi_{uuid.uuid4().hex[:8]}"
    r1 = await test_chat_scene(client, "多轮-R1", {"content": "我叫 Frank", "tools": []}, session_id)
    r2 = await test_chat_scene(client, "多轮-R2", {"content": "我叫什么名字", "tools": []}, session_id)
    log("多轮对话", "PASS" if (r1["completed"] and r2["completed"]) else "FAIL",
        f"R1={r1['elapsed_ms']}ms R2={r2['elapsed_ms']}ms")

    # 7. 超长输入
    long_msg = "请总结：" + "人工智能正在改变世界。" * 50
    r = await test_chat_scene(client, "超长输入", {"content": long_msg, "tools": []})
    log("超长输入", "PASS" if r["completed"] else "FAIL", f"len={len(long_msg)} elapsed={r['elapsed_ms']}ms")

    # 8. 代码输入
    code_msg = "解释这段代码：\n```python\nimport asyncio\nasync def main():\n    print('hello')\n```"
    r = await test_chat_scene(client, "代码输入", {"content": code_msg, "tools": []})
    log("代码输入", "PASS" if r["completed"] else "FAIL", f"elapsed={r['elapsed_ms']}ms")

    # 9. 并发请求
    r = await test_concurrent(client)
    log("并发请求", "PASS" if r else "FAIL")

    # 10. 混合工具
    r = await test_chat_scene(client, "混合工具", {
        "content": "搜索AI新闻并保存到文件",
        "tools": ["web_search", "file_ops"],
    }, timeout=90)
    log("混合工具", "PASS" if r["completed"] else "TIMEOUT", f"tools={r['tool_calls']} elapsed={r['elapsed_ms']}ms")

    # ========== REST API 验证 ==========
    print("\n--- REST API 验证 ---")

    apis = [
        ("GET /api/v1/health", lambda: client.get("/api/v1/health")),
        ("GET /api/v1/tasks/recent", lambda: client.get("/api/v1/tasks/recent")),
        ("GET /api/v1/soul/profile/test_user", lambda: client.get("/api/v1/soul/profile/test_user")),
        ("GET /api/v1/soul/completeness/test_user", lambda: client.get("/api/v1/soul/completeness/test_user")),
        ("GET /api/v1/agents", lambda: client.get("/api/v1/agents")),
        ("GET /api/v1/agents/templates", lambda: client.get("/api/v1/agents/templates")),
        ("GET /api/v1/soul/eternal/status/test_user", lambda: client.get("/api/v1/soul/eternal/status/test_user")),
        ("GET /api/v1/soul/eternal/memories/test_user?limit=5", lambda: client.get("/api/v1/soul/eternal/memories/test_user?limit=5")),
    ]

    for name, call in apis:
        try:
            res = call()
            status = "PASS" if res.status_code == 200 else f"HTTP{res.status_code}"
            log(name, status)
        except Exception as e:
            log(name, "ERROR", str(e)[:50])

    # ========== 汇总 ==========
    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r.get("completed"))
    total = len(results)
    print(f"聊天场景: {passed}/{total} 通过")
    print("=" * 60)


async def test_chat_scene(client, scene_name, payload, session_id=None, timeout=60):
    sid = session_id or f"test_{uuid.uuid4().hex[:8]}"
    start = time.time()
    msg_count = 0
    tool_calls = 0
    completed = False

    try:
        with client.websocket_connect('/ws') as ws:
            msg = ws.receive_json()  # health
            ws.send_json({
                'type': 'chat.message',
                'payload': {
                    'session_id': sid,
                    'user_id': 'test_user',
                    **payload,
                }
            })

            while time.time() - start < timeout:
                try:
                    msg = ws.receive_json()
                    msg_count += 1
                    msg_type = msg.get('type')
                    if msg_type == 'chat.tool_call':
                        tool_calls += 1
                    elif msg_type == 'chat.completed':
                        completed = True
                        break
                except:
                    break
    except:
        pass

    return {
        'scene': scene_name,
        'completed': completed,
        'msg_count': msg_count,
        'tool_calls': tool_calls,
        'elapsed_ms': int((time.time() - start) * 1000),
    }


async def test_concurrent(client):
    async def send_one(idx):
        try:
            with client.websocket_connect('/ws') as ws:
                ws.receive_json()
                ws.send_json({
                    'type': 'chat.message',
                    'payload': {
                        'session_id': f"con_{idx}_{uuid.uuid4().hex[:6]}",
                        'user_id': 'test_user',
                        'content': f'并发测试 {idx}',
                        'tools': [],
                    }
                })
                start = time.time()
                while time.time() - start < 30:
                    msg = ws.receive_json()
                    if msg.get('type') == 'chat.completed':
                        return True
        except:
            return False

    tasks = [send_one(i) for i in range(3)]
    results = await asyncio.gather(*tasks)
    return all(results)


if __name__ == '__main__':
    asyncio.run(run_tests())
