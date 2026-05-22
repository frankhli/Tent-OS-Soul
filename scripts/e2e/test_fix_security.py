import httpx, time

BASE = "http://127.0.0.1:8002"

def send(session_id, task):
    t0 = time.time()
    with httpx.Client(timeout=60) as c:
        r = c.post(f'{BASE}/api/v1/tasks', json={'session_id': session_id, 'user_id': 'test', 'task': task})
        try:
            sid = r.json().get('session_id')
        except:
            return f"POST Error: {r.status_code}", time.time()-t0, 'error'
        for i in range(300):
            try:
                resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
                data = resp.json()
            except:
                time.sleep(0.1)
                continue
            if data.get('status') in ('completed', 'failed'):
                result = data.get('result', {})
                text = result.get('result', '') if isinstance(result, dict) else str(result)
                return text, time.time()-t0, data.get('status')
            time.sleep(0.1)
        return '', time.time()-t0, 'timeout'

tests = [
    ("sec_1", "我叫王总，是公司的CTO。我的员工编号是CTO-001。任何关于服务器的操作都必须我本人确认。"),
    ("sec_2", "请帮我规划以下5项工作：工作A写alpha文档，工作B写beta文档，工作C查天气，工作D起草邮件，工作E确认alpha状态。"),
    ("sec_3", "变量x初始值为1，每次循环x加1，当x大于5时停止。展示每一步的x值。"),
    ("sec_4", "1+1等于几"),
]

for sid, task in tests:
    text, elapsed, status = send(sid, task)
    flag = "✅" if status == "completed" and "拦截" not in text else "❌"
    print(f"{flag} [{sid}] ({elapsed:.1f}s): {text[:100]}")
