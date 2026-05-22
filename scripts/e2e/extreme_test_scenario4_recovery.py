#!/usr/bin/env python3
"""
极端场景四：进程崩溃与状态恢复
测试治理进程重启后能否从Redis恢复状态
"""
import httpx, time, json, subprocess, os, signal

BASE = "http://127.0.0.1:8002"
USER = "test_user"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/extreme_test_scenario4_recovery.log", "a") as f:
        f.write(line + "\n")

def send_task(session_id, task, timeout=60):
    t0 = time.time()
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f'{BASE}/api/v1/tasks', json={
            'session_id': session_id,
            'user_id': USER,
            'task': task
        })
        sid = r.json().get('session_id')
        for i in range(300):
            resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
            data = resp.json()
            if data.get('status') in ('completed', 'failed'):
                result = data.get('result', {})
                text = result.get('result', '') if isinstance(result, dict) else str(result)
                return text, time.time()-t0, data.get('status')
            time.sleep(0.1)
        return None, time.time()-t0, 'timeout'

def get_pid(name):
    try:
        result = subprocess.run(['pgrep', '-f', name], capture_output=True, text=True)
        pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
        return pids
    except:
        return []

def main():
    open("/Users/frank/Desktop/tent_os/extreme_test_scenario4_recovery.log", "w").close()
    
    log("=" * 60)
    log("=== 极端场景四：进程崩溃与状态恢复 ===")
    log("=" * 60)
    
    session_id = "recovery_s04"
    
    # Phase 1: 创建session并发送一条消息
    log("\n>>> Phase 1: 创建session并发送消息")
    text, elapsed, status = send_task(session_id, "记住这个数字：42")
    log(f"Phase 1 ({elapsed:.1f}s): [{status.upper()}] {text[:100]}")
    
    # Phase 2: 检查治理进程PID
    gov_pids = get_pid("python.*governance")
    log(f"\n>>> Phase 2: 治理进程PID: {gov_pids}")
    
    # Phase 3: 模拟崩溃重启（kill -9）
    if gov_pids:
        log(f">>> Phase 3: kill -9 治理进程")
        for pid in gov_pids:
            try:
                os.kill(int(pid), signal.SIGKILL)
                log(f"  已kill PID {pid}")
            except:
                log(f"  无法kill PID {pid}")
        time.sleep(3)
        
        # 检查进程是否已重启
        new_pids = get_pid("python.*governance")
        log(f"  新治理进程PID: {new_pids}")
        
        # Phase 4: 验证session是否恢复
        log(f"\n>>> Phase 4: 验证session恢复")
        time.sleep(5)  # 等进程重启
        
        # 检查健康状态
        try:
            r = httpx.get(f'{BASE}/api/v1/health', timeout=10)
            health = r.json()
            log(f"  健康状态: {health.get('status')}, workers: {health.get('workers')}")
        except Exception as e:
            log(f"  健康检查失败: {e}")
        
        # Phase 5: 再次查询session
        log(f"\n>>> Phase 5: 再次查询session状态")
        with httpx.Client(timeout=30) as c:
            resp = c.get(f'{BASE}/api/v1/tasks/{session_id}')
            data = resp.json()
            log(f"  Session状态: {data.get('status')}")
            result = data.get('result', {})
            if isinstance(result, dict):
                log(f"  Result: {result.get('result', '')[:100]}")
    else:
        log("  未找到治理进程，跳过kill测试")
    
    # Phase 6: 发送新消息验证记忆
    log(f"\n>>> Phase 6: 发送新消息验证记忆")
    text, elapsed, status = send_task(session_id, "我刚才让你记住的数字是多少？")
    log(f"Phase 6 ({elapsed:.1f}s): [{status.upper()}] {text[:100]}")
    
    has_memory = "42" in text if text else False
    log(f"\n评估: 记忆恢复={'✅' if has_memory else '❌'}")

if __name__ == "__main__":
    main()
