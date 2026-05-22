#!/usr/bin/env python3
"""
极端场景三：多任务并发资源争抢
在一个session内连续创建5个并行任务，检验调度隔离
"""
import httpx, time, json, threading, sys
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8002"
USER = "test_user"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/extreme_test_scenario3_concurrent.log", "a") as f:
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
    open("/Users/frank/Desktop/tent_os/extreme_test_scenario3_concurrent.log", "w").close()
    
    log("=" * 60)
    log("=== 极端场景三：多任务并发资源争抢 ===")
    log("=" * 60)
    
    session_id = "concurrent_s03"
    
    # 清理之前的缓存
    log("\n>>> 发送复合任务（包含5个子任务）")
    
    task = """你是一个AI管家。我现在要同时启动5个任务，你需要全部接受，然后分先后告诉我每个任务的进度和完成情况。

任务1：创建一个名为project_alpha的文件夹，在里面生成一个README.md，内容包含"任务1完成"和当前时间戳。
任务2：创建一个名为project_beta的文件夹，在里面生成一个README.md，内容包含"任务2完成"和当前时间戳。
任务3：帮我查询今天的天气（模拟调用天气API），如果气温超过30度，就创建一个alert.txt，内容为"高温预警"。
任务4：模拟发送一封邮件给ceo@company.com，主题是"测试邮件"，内容是"任务4完成"。
任务5：先检查project_alpha文件夹是否存在，如果存在，就在里面追加一个文件叫alpha_status.txt，内容为"已验证"。

注意：
- 任务3和任务5都依赖任务1的结果
- 但你不能等任务1完成再做任务3，你必须同时启动所有任务
- 如果有依赖关系的任务失败，你要汇报哪个任务因为依赖失败而无法完成
- 最后，你要给出一份完整的执行报告，列出每个任务的最终状态"""
    
    text, elapsed, status = send_task(session_id, task, timeout=180)
    log(f"并发任务 ({elapsed:.1f}s): [{status.upper()}] {text[:500]}")
    
    # 评估
    log("\n=== 评估 ===")
    checks = {
        "提到5个任务": all(f"任务{i}" in text for i in range(1, 6)),
        "任务1完成": "任务1" in text and ("完成" in text or "project_alpha" in text),
        "任务2完成": "任务2" in text and ("完成" in text or "project_beta" in text),
        "任务4完成": "任务4" in text or "邮件" in text or "ceo" in text,
        "有执行报告": "报告" in text or "总结" in text or "状态" in text,
    }
    
    for check, passed in checks.items():
        log(f"  {'✅' if passed else '❌'} {check}")
    
    passed = sum(checks.values())
    total = len(checks)
    log(f"\n总分: {passed}/{total}")
    
    if passed >= 3:
        log("🎉 场景三通过")
    else:
        log("⚠️ 场景三未通过")

if __name__ == "__main__":
    main()
