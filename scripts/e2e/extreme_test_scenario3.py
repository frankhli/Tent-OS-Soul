#!/usr/bin/env python3
"""
极端场景三：多任务并发资源争抢（调度维度）
同时创建5个并行任务，检验任务隔离和依赖处理
"""
import httpx, time, os, glob
from datetime import datetime

BASE = "http://localhost:8002"
USER = "extreme_s03"
LOG_FILE = "/Users/frank/Desktop/tent_os/extreme_test_scenario3.log"

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
        f.flush()

def send(user_id, msg):
    t0 = time.time()
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(f'{BASE}/api/v1/tasks', json={'user_id': user_id, 'task': msg})
            sid = r.json().get('session_id')
            if not sid:
                return None, 0
            for i in range(600):
                resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
                data = resp.json()
                if data.get('status') in ('completed', 'failed'):
                    text = str(data.get('result', ''))
                    return text, time.time() - t0
                time.sleep(0.1)
            return None, 60
    except Exception as e:
        return f"ERROR: {e}", 0

with open(LOG_FILE, "w") as f:
    f.write("=== 极端场景三：多任务并发资源争抢 ===\n")
    f.write(f"开始时间: {datetime.now().isoformat()}\n\n")

# 清理之前的可能残留
for d in ['project_alpha', 'project_beta']:
    if os.path.exists(d):
        import shutil
        shutil.rmtree(d)

log("=== 启动5个并行任务 ===")

tasks = [
    ("task1", "创建一个名为project_alpha的文件夹，在里面生成一个README.md，内容包含'任务1完成'和当前时间戳。"),
    ("task2", "创建一个名为project_beta的文件夹，在里面生成一个README.md，内容包含'任务2完成'和当前时间戳。"),
    ("task3", "查询今天的天气（模拟调用天气API），如果气温超过30度，就创建一个alert.txt，内容为'高温预警'。如果无法查询天气，请说明原因。"),
    ("task4", "模拟发送一封邮件给ceo@company.com，主题是'测试邮件'，内容是'任务4完成'。请告诉我你模拟的发送结果。"),
    ("task5", "先检查project_alpha文件夹是否存在，如果存在，就在里面追加一个文件叫alpha_status.txt，内容为'已验证'。如果不存在，请说明。"),
]

results = {}
for name, msg in tasks:
    log(f"\n启动 {name}...")
    text, elapsed = send(USER, msg)
    results[name] = {'text': text, 'elapsed': elapsed}
    has_alert = '⚠️' in str(text) or '任务可能未完成' in str(text)
    log(f"  {name} 完成 ({elapsed:.1f}s): alert={has_alert}")
    log(f"  回复摘要: {str(text)[:300]}")

# 验证文件系统结果
log("\n=== 验证文件系统结果 ===")
for d in ['project_alpha', 'project_beta']:
    exists = os.path.exists(d)
    log(f"  {d}/ 存在: {exists}")
    if exists:
        files = os.listdir(d)
        log(f"    文件: {files}")
        for f in files:
            path = os.path.join(d, f)
            if os.path.isfile(path):
                try:
                    with open(path) as fh:
                        content = fh.read()
                        log(f"    {f}: {content[:100]}")
                except:
                    pass

# 验证任务隔离：task5是否正确地只在project_alpha中创建了文件
log("\n=== 验证任务隔离 ===")
alpha_has_status = os.path.exists('project_alpha/alpha_status.txt')
beta_has_status = os.path.exists('project_beta/alpha_status.txt')
log(f"  project_alpha/alpha_status.txt 存在: {alpha_has_status}")
log(f"  project_beta/alpha_status.txt 存在: {beta_has_status} (应为False)")
isolated = alpha_has_status and not beta_has_status
log(f"  任务隔离正确: {isolated}")

# 汇总
log("\n=== 场景三 结果汇总 ===")
all_ok = all(results[t]['text'] is not None for t in results)
log(f"所有任务完成: {all_ok}")
log(f"任务隔离正确: {isolated}")
avg_time = sum(results[t]['elapsed'] for t in results) / len(results)
log(f"平均响应时间: {avg_time:.1f}s")
