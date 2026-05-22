import httpx, time
BASE = "http://127.0.0.1:8002"

def send(session_id, task):
    t0 = time.time()
    with httpx.Client(timeout=60) as c:
        r = c.post(f'{BASE}/api/v1/tasks', json={'session_id': session_id, 'user_id': 'test', 'task': task})
        sid = r.json().get('session_id')
        for i in range(300):
            resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
            data = resp.json()
            if data.get('status') in ('completed', 'failed'):
                result = data.get('result', {})
                text = result.get('result', '') if isinstance(result, dict) else str(result)
                return text or '', time.time()-t0, data.get('status')
            time.sleep(0.1)
        return '', time.time()-t0, 'timeout'

tests = [
    ("minimal_hello", "你好"),
    ("minimal_name", "你叫什么名字"),
    ("minimal_weather", "今天天气怎么样"),
    ("minimal_math", "1+1等于几"),
    ("minimal_story", "讲个短笑话"),
]

for sid, task in tests:
    text, elapsed, status = send(sid, task)
    flag = "✅" if status == "completed" and "拦截" not in text else "❌"
    print(f"{flag} [{sid}] ({elapsed:.1f}s): {text[:80]}")
