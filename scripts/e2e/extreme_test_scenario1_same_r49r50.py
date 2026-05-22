#!/usr/bin/env python3
"""场景一考试轮：R49 + R50（同session复用已有上下文）"""
import httpx, time, json
from datetime import datetime

BASE = "http://localhost:8002"
USER = "extreme_s01"
LOG_FILE = "/Users/frank/Desktop/tent_os/extreme_test_scenario1_same.log"
last_task_id = None

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
        f.flush()

def send(msg, round_num):
    global last_task_id
    t0 = time.time()
    try:
        with httpx.Client(timeout=180) as c:
            r = c.post(f'{BASE}/api/v1/tasks', json={'session_id': 'extreme_s01_fresh', 'user_id': USER, 'task': msg})
            sid = r.json().get('session_id')
            if not sid:
                log(f"R{round_num:2d}: ERROR no session_id")
                return None, 0
            
            current_task_id = None
            for i in range(1200):  # 最多等120秒
                resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
                data = resp.json()
                result = data.get('result', {})
                if isinstance(result, dict):
                    current_task_id = result.get('task_id')
                if current_task_id and current_task_id != last_task_id:
                    last_task_id = current_task_id
                    break
                time.sleep(0.1)
            else:
                log(f"R{round_num:2d}: TIMEOUT waiting for new task")
                return None, 120
            
            for i in range(1200):
                resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
                data = resp.json()
                result = data.get('result', {})
                if isinstance(result, dict) and result.get('task_id') == current_task_id:
                    if data.get('status') in ('completed', 'failed'):
                        text = str(result)
                        elapsed = time.time() - t0
                        return text, elapsed
                time.sleep(0.1)
            log(f"R{round_num:2d}: TIMEOUT after 120s")
            return None, 120
    except Exception as e:
        log(f"R{round_num:2d}: EXCEPTION {e}")
        return None, 0

# 先发送考试轮R49
log("=== 考试轮 R49 ===")
text49, elapsed49 = send(
    "好了，现在开始考试。请你完整、准确地告诉我：\n"
    "a. 公司全名、CEO全名、CTO全名、COO全名。\n"
    "b. 公司所在城市、具体区域。\n"
    "c. 去年营收、今年目标营收。\n"
    "d. 最大客户是谁，第二大客户是谁。\n"
    "e. 核心产品叫什么，技术优势是什么，用了什么底层框架。\n"
    "f. 融资历史（A/B/C轮的投资方和C轮金额）。\n"
    "注意：你要在明显矛盾的信息中选择你认为最正确的，并解释你的判断依据。",
    49
)
if text49:
    log(f"R49 ({elapsed49:5.1f}s): [OK]")
    log(f"R49 RESULT: {text49[:500]}")
else:
    log("R49: FAILED")

# 再发送修正轮R50
log("=== 修正轮 R50 ===")
text50, elapsed50 = send(
    "补充一个信息——刚才第10轮我搞错了，王磊确实是CTO，陈静是CFO。请根据这个修正重新回答a题。",
    50
)
if text50:
    log(f"R50 ({elapsed50:5.1f}s): [OK]")
    log(f"R50 RESULT: {text50[:500]}")
else:
    log("R50: FAILED")

log("\n=== 场景一测试完成 ===")
