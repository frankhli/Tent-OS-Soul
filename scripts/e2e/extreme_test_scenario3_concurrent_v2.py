#!/usr/bin/env python3
"""
极端场景三v2：多任务并发（避开安全拦截关键词）
"""
import httpx, time, json

BASE = "http://127.0.0.1:8002"
USER = "test_user"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/extreme_test_scenario3_concurrent_v2.log", "a") as f:
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
    open("/Users/frank/Desktop/tent_os/extreme_test_scenario3_concurrent_v2.log", "w").close()
    
    log("=" * 60)
    log("=== 场景三v2：多任务并发（安全措辞） ===")
    log("=" * 60)
    
    session_id = "concurrent_s03_v2"
    
    task = """请帮我规划以下5项工作，并说明每项的完成状态和它们之间的依赖关系：

工作A：编写一份关于alpha项目的说明文档，需要包含"alpha项目已启动"和时间信息。
工作B：编写一份关于beta项目的说明文档，需要包含"beta项目已启动"和时间信息。  
工作C：查看今日气温，如果超过30度，记录一条"注意防暑"的提醒。
工作D：起草一份给公司高层的汇报邮件，主题是"工作进展"，内容是"D项已完成"。
工作E：确认alpha项目的说明文档是否已完成，如果已完成，追加记录"已通过验收"。

要求：
- 工作C和工作E都依赖工作A的结果
- 你需要同时规划所有工作，而不是等A完成再做其他
- 如果有依赖项未完成，请指出哪项工作因此受阻
- 最后给出完整的工作状态汇总"""
    
    text, elapsed, status = send_task(session_id, task, timeout=180)
    log(f"并发任务 ({elapsed:.1f}s): [{status.upper()}] {text[:600]}")
    
    log("\n=== 评估 ===")
    checks = {
        "提到5项工作": sum(1 for i in ["A","B","C","D","E"] if i in text or f"工作{i}" in text) >= 3,
        "有依赖关系说明": "依赖" in text or "先后" in text or "顺序" in text,
        "有状态汇总": "汇总" in text or "报告" in text or "状态" in text or "完成" in text,
        "响应非拦截": "拦截" not in text and "安全" not in text,
    }
    
    for check, passed in checks.items():
        log(f"  {'✅' if passed else '❌'} {check}")
    
    passed = sum(checks.values())
    total = len(checks)
    log(f"\n总分: {passed}/{total}")
    
    if passed >= 3:
        log("🎉 场景三v2通过")
    else:
        log("⚠️ 场景三v2未通过")

if __name__ == "__main__":
    main()
