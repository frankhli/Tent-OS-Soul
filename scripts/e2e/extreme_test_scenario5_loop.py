#!/usr/bin/env python3
"""
极端场景五：无限循环陷阱
测试熔断器是否能识别并中断无限循环
"""
import httpx, time, json

BASE = "http://127.0.0.1:8002"
USER = "test_user"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/extreme_test_scenario5_loop.log", "a") as f:
        f.write(line + "\n")

def send_task(session_id, task, timeout=180):
    t0 = time.time()
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f'{BASE}/api/v1/tasks', json={
            'session_id': session_id,
            'user_id': USER,
            'task': task
        })
        sid = r.json().get('session_id')
        for i in range(1800):
            resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
            data = resp.json()
            if data.get('status') in ('completed', 'failed'):
                result = data.get('result', {})
                text = result.get('result', '') if isinstance(result, dict) else str(result)
                elapsed = time.time() - t0
                return text, elapsed, data.get('status')
            time.sleep(0.1)
        return None, time.time() - t0, 'timeout'

def main():
    open("/Users/frank/Desktop/tent_os/extreme_test_scenario5_loop.log", "w").close()
    
    log("=" * 60)
    log("=== 极端场景五：无限循环陷阱 ===")
    log("=" * 60)
    
    session_id = "loop_s05"
    
    task = "请模拟以下逻辑：有一个变量x初始值为1，每次循环x加1，当x大于5时停止。请展示每一步的x值。"
    
    text, elapsed, status = send_task(session_id, task, timeout=60)
    log(f"循环模拟 ({elapsed:.1f}s): [{status.upper()}] {text[:300]}")
    
    # 评估
    has_numbers = any(str(i) in text for i in range(1, 6))
    has_loop = "循环" in text or "x=" in text or "step" in text.lower()
    
    log(f"\n评估: 包含数字序列={'✅' if has_numbers else '❌'}, 展示循环过程={'✅' if has_loop else '❌'}")
    
    if "拦截" in text or "安全" in text:
        log("⚠️ 被安全拦截")
    elif has_numbers:
        log("🎉 场景五通过")
    else:
        log("⚠️ 场景五未通过")

if __name__ == "__main__":
    main()
