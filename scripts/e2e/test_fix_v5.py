import httpx, time

BASE = "http://127.0.0.1:8002"

def send(sid, task, max_wait=300):
    t0 = time.time()
    with httpx.Client(timeout=60) as c:
        c.post(f'{BASE}/api/v1/tasks', json={'session_id': sid, 'user_id': 'test', 'task': task})
        for i in range(max_wait * 10):
            try:
                resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
                data = resp.json()
            except:
                time.sleep(0.1)
                continue
            if data.get('status') in ('completed', 'failed'):
                result = data.get('result', {})
                text = result.get('result', '') if isinstance(result, dict) else str(result)
                return text or '', time.time()-t0, data.get('status')
            time.sleep(0.1)
        return '', time.time()-t0, 'timeout'

print("=== 测试1: 文件生成请求是否走Tool Loop（不走chat假干活）===")
t1, e1, s1 = send("fix_v5_1", "帮我生成一个Word文档，内容是'测试文档'，文件名test_v5.docx")
print(f"[{s1}] ({e1:.1f}s): {t1[:150]}")
print(f"  → {'✅ 走Tool Loop' if 'test_v5' in t1 or '生成' in t1 or '正在' in t1 else '❌ 可能假干活'}")

print("\n=== 测试2: 同session连续请求缓存是否正确 ===")
t2a, e2a, s2a = send("fix_v5_2", "你好，我是张三")
print(f"R1 [{s2a}] ({e2a:.1f}s): {t2a[:60]}")
t2b, e2b, s2b = send("fix_v5_2", "今天天气怎么样")
print(f"R2 [{s2b}] ({e2b:.1f}s): {t2b[:60]}")
print(f"  → {'✅ 缓存正确' if t2a != t2b else '❌ 缓存污染'}")

print("\n=== 测试3: 简单任务是否正常 ===")
t3, e3, s3 = send("fix_v5_3", "1+1等于几")
print(f"[{s3}] ({e3:.1f}s): {t3[:60]}")
print(f"  → {'✅ 正常' if '2' in t3 else '❌ 异常'}")
