"""端到端测试 —— 覆盖多种复杂场景和随机场景"""

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime

sys.path.insert(0, '.')

from fastapi.testclient import TestClient

# 全局日志收集
LOGS = []

def log(level, msg):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{ts}] [{level}] {msg}"
    LOGS.append(entry)
    print(entry)


async def run_tests():
    from tent_os.api.server import app, state
    from tent_os.api import soul_state
    from tent_os.bootstrap import load_config

    # 1. 加载真实配置并初始化
    log("INFO", "=" * 60)
    log("INFO", "开始端到端测试")
    log("INFO", "=" * 60)

    config = load_config('./config/tent_os.yaml')
    log("INFO", f"配置加载完成: LLM={config.get('llm', {}).get('provider')}, model={config.get('llm', {}).get('model')}")

    await state.setup(config)
    await soul_state.state.setup(config)
    log("INFO", "双 state 初始化完成")
    log("INFO", f"  agent_loop: {soul_state.state.agent_loop is not None}")
    log("INFO", f"  security_pipeline: {soul_state.state.security_pipeline is not None}")
    log("INFO", f"  hook_engine: {soul_state.state.hook_engine is not None}")
    log("INFO", f"  speculative_executor: {soul_state.state.speculative_executor is not None}")
    log("INFO", f"  tool_executor: {soul_state.state.tool_executor is not None}")
    log("INFO", f"  memory_store: {soul_state.state.memory_store is not None}")

    client = TestClient(app)

    # ========== 测试场景 1: 简单闲聊 ==========
    await test_scene(client, "简单闲聊", {
        "content": "你好，今天天气怎么样？",
        "tools": [],
    })

    # ========== 测试场景 2: web_search 工具调用 ==========
    await test_scene(client, "web_search 工具调用", {
        "content": "请搜索一下2026年AI领域的最新进展",
        "tools": ["web_search"],
    })

    # ========== 测试场景 3: file_ops 工具调用 ==========
    await test_scene(client, "file_ops 工具调用", {
        "content": "请读取 ./README.md 文件的内容",
        "tools": ["file_ops"],
    })

    # ========== 测试场景 4: 多轮对话上下文 ==========
    session_id = f"multi_{uuid.uuid4().hex[:8]}"
    await test_scene(client, "多轮对话-第1轮", {
        "content": "我的名字是 Frank，请记住",
        "tools": [],
    }, session_id=session_id)

    await test_scene(client, "多轮对话-第2轮", {
        "content": "我叫什么名字？",
        "tools": [],
    }, session_id=session_id)

    # ========== 测试场景 5: 安全拦截 ==========
    await test_scene(client, "安全拦截-危险命令", {
        "content": "请帮我执行 rm -rf / 命令",
        "tools": ["file_ops"],
    })

    # ========== 测试场景 6: deep_thinking 模式 ==========
    await test_scene(client, "deep_thinking 模式", {
        "content": "请分析一下量子计算对密码学的影响",
        "tools": [],
        "deep_thinking": True,
    })

    # ========== 测试场景 7: 超长输入 ==========
    long_text = "请总结一下以下这段话：" + "人工智能是计算机科学的一个分支。" * 100
    await test_scene(client, "超长输入", {
        "content": long_text,
        "tools": [],
    })

    # ========== 测试场景 8: 特殊字符/代码输入 ==========
    await test_scene(client, "特殊字符代码", {
        "content": "请解释这段代码的作用：\n```python\ndef fib(n):\n    if n <= 1: return n\n    return fib(n-1) + fib(n-2)\n```",
        "tools": [],
    })

    # ========== 测试场景 9: 并发消息 ==========
    await test_concurrent(client)

    # ========== 测试场景 10: 混合工具调用 ==========
    await test_scene(client, "混合工具", {
        "content": "先搜索一下最近的AI新闻，然后帮我创建一个文件保存结果",
        "tools": ["web_search", "file_ops"],
    })

    # 汇总
    log("INFO", "=" * 60)
    log("INFO", "端到端测试完成")
    log("INFO", "=" * 60)

    # 输出日志摘要
    errors = [l for l in LOGS if "ERROR" in l or "EXCEPTION" in l or "Traceback" in l]
    warnings = [l for l in LOGS if "WARN" in l]
    log("INFO", f"总日志数: {len(LOGS)}")
    log("INFO", f"错误数: {len(errors)}")
    log("INFO", f"警告数: {len(warnings)}")

    if errors:
        log("INFO", "\n错误摘要:")
        for e in errors[:20]:
            print(f"  {e}")

    if warnings:
        log("INFO", "\n警告摘要:")
        for w in warnings[:20]:
            print(f"  {w}")


async def test_scene(client, scene_name, payload, session_id=None):
    """测试单个场景"""
    sid = session_id or f"test_{uuid.uuid4().hex[:8]}"
    log("INFO", f"\n--- 场景: {scene_name} [session={sid}] ---")

    start = time.time()
    msg_count = 0
    chunk_count = 0
    reasoning_count = 0
    tool_calls = 0
    tool_results = 0
    completed = False
    last_error = None

    try:
        with client.websocket_connect('/ws') as ws:
            # 接收 health
            msg = ws.receive_json()
            if msg.get('type') != 'system.health':
                log("WARN", f"  预期 health，收到 {msg.get('type')}")

            # 发送消息
            ws.send_json({
                'type': 'chat.message',
                'payload': {
                    'session_id': sid,
                    'user_id': 'test_user',
                    **payload,
                }
            })

            # 收集响应
            timeout = 60 if payload.get('deep_thinking') else 45
            while time.time() - start < timeout:
                try:
                    msg = ws.receive_json()
                    msg_count += 1
                    msg_type = msg.get('type', 'unknown')
                    p = msg.get('payload', {})

                    if msg_type == 'chat.stream_chunk':
                        chunk_count += 1
                    elif msg_type == 'chat.reasoning_chunk':
                        reasoning_count += 1
                    elif msg_type == 'chat.tool_call':
                        tool_calls += 1
                        log("INFO", f"  [TOOL CALL] {p.get('tool')} args={p.get('arguments', {})}")
                    elif msg_type == 'chat.tool_result':
                        tool_results += 1
                        result = p.get('result', '')
                        log("INFO", f"  [TOOL RESULT] {p.get('tool')} result_len={len(result)}")
                    elif msg_type == 'chat.completed':
                        content = p.get('content', '')
                        elapsed = p.get('elapsed_ms', 0)
                        log("INFO", f"  [COMPLETED] len={len(content)} elapsed={elapsed}ms")
                        completed = True
                        break
                    elif msg_type == 'chat.message_accepted':
                        pass
                    elif msg_type == 'system.health':
                        pass
                    else:
                        log("WARN", f"  未知消息类型: {msg_type}")

                except Exception as e:
                    last_error = str(e)
                    break

    except Exception as e:
        last_error = str(e)
        log("ERROR", f"  场景异常: {e}")

    elapsed = int((time.time() - start) * 1000)
    log("INFO", f"  统计: messages={msg_count} chunks={chunk_count} reasoning={reasoning_count} tools={tool_calls}/{tool_results} completed={completed} elapsed={elapsed}ms")
    if last_error:
        log("ERROR", f"  最后错误: {last_error}")

    return {
        'scene': scene_name,
        'completed': completed,
        'msg_count': msg_count,
        'chunks': chunk_count,
        'reasoning': reasoning_count,
        'tool_calls': tool_calls,
        'elapsed_ms': elapsed,
        'error': last_error,
    }


async def test_concurrent(client):
    """测试并发消息"""
    log("INFO", "\n--- 场景: 并发消息 ---")

    async def send_one(idx):
        sid = f"concurrent_{idx}_{uuid.uuid4().hex[:6]}"
        start = time.time()
        try:
            with client.websocket_connect('/ws') as ws:
                msg = ws.receive_json()  # health
                ws.send_json({
                    'type': 'chat.message',
                    'payload': {
                        'session_id': sid,
                        'user_id': 'test_user',
                        'content': f'并发测试消息 {idx}',
                        'tools': [],
                    }
                })

                completed = False
                while time.time() - start < 30:
                    try:
                        msg = ws.receive_json()
                        if msg.get('type') == 'chat.completed':
                            completed = True
                            break
                    except:
                        break

                elapsed = int((time.time() - start) * 1000)
                return {'idx': idx, 'completed': completed, 'elapsed_ms': elapsed}
        except Exception as e:
            return {'idx': idx, 'completed': False, 'error': str(e)}

    # 并发发送 3 条消息
    tasks = [send_one(i) for i in range(3)]
    results = await asyncio.gather(*tasks)

    for r in results:
        status = "OK" if r.get('completed') else "FAIL"
        log("INFO", f"  并发-{r['idx']}: {status} elapsed={r.get('elapsed_ms', 0)}ms")


if __name__ == '__main__':
    asyncio.run(run_tests())
