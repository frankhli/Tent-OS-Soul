import httpx, time

BASE = "http://127.0.0.1:8002"

def send(sid, task):
    t0 = time.time()
    with httpx.Client(timeout=60) as c:
        c.post(f'{BASE}/api/v1/tasks', json={'session_id': sid, 'user_id': 'test', 'task': task})
        for i in range(200):
            resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
            data = resp.json()
            if data.get('status') in ('completed', 'failed'):
                result = data.get('result', {})
                text = result.get('result', '') if isinstance(result, dict) else str(result)
                return text[:80], time.time()-t0
            time.sleep(0.1)
        return 'TIMEOUT', time.time()-t0

# 同session连续发送3条不同消息
t1, e1 = send("cache_test", "你好，我是Frank")
print(f"R1 ({e1:.1f}s): {t1}")

t2, e2 = send("cache_test", "今天天气怎么样")
print(f"R2 ({e2:.1f}s): {t2}")

t3, e3 = send("cache_test", "1+1等于几")
print(f"R3 ({e3:.1f}s): {t3}")

# 验证：三条返回内容不同
if t1 != t2 and t2 != t3 and "TIMEOUT" not in [t1,t2,t3]:
    print("\n✅ 缓存修复生效：同session连续请求返回不同结果")
else:
    print(f"\n❌ 缓存可能仍有问题")
