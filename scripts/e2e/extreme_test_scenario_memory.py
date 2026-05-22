#!/usr/bin/env python3
import httpx, time

BASE = "http://127.0.0.1:8002"
USER = "test_user"
last_task_id = None

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/extreme_test_scenario_memory.log", "a") as f:
        f.write(line + "\n")

def send(msg, round_num):
    global last_task_id
    t0 = time.time()
    with httpx.Client(timeout=120) as c:
        r = c.post(f'{BASE}/api/v1/tasks', json={
            'session_id': 'memory_s01',
            'user_id': USER,
            'task': msg
        })
        sid = r.json().get('session_id')
        time.sleep(2)
        for i in range(900):
            resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
            data = resp.json()
            result = data.get('result', {})
            current_task_id = result.get('task_id') if isinstance(result, dict) else None
            if current_task_id and current_task_id != last_task_id:
                last_task_id = current_task_id
                break
            time.sleep(0.1)
        else:
            return None, 90
        for i in range(900):
            resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
            data = resp.json()
            result = data.get('result', {})
            if isinstance(result, dict) and result.get('task_id') == current_task_id:
                if data.get('status') in ('completed', 'failed'):
                    text = result.get('result', '') if isinstance(result, dict) else str(result)
                    return text, time.time() - t0
            time.sleep(0.1)
        return None, 90

def main():
    open("/Users/frank/Desktop/tent_os/extreme_test_scenario_memory.log", "w").close()
    log("=== 测试场景一：21轮长上下文记忆衰减 ===")
    
    rounds = [
        ("项目代号叫玄武，客户是远航集团，预算350万，截止2026年12月15日。", 1),
        ("今天天气不错，你有什么推荐的咖啡？", 2),
        ("项目最大风险是供应链芯片交付可能延迟4周。", 3),
        ("你觉得Python和Go哪个更适合做后端？", 4),
        ("为应对芯片风险，预留了50万应急预算，但不能动，除非董事会批准。", 5),
        ("说说你最喜欢的科幻电影吧。", 6),
        ("项目负责人张总强调，任何超过10万的支出都必须他亲自签字。", 7),
        ("如果芯片延迟，启动备选方案B，用国产芯片替代，成本降20万，性能下降15%。", 8),
        ("刚才说的应急预算具体金额是多少？我好像忘了。", 9),
        ("你去过巴黎吗？感觉怎么样？", 10),
        ("核心工程师老李下周要去美国出差三周。", 11),
        ("备选方案B启动后，性能下降对客户业务有啥影响？", 12),
        ("我昨天看了部电影叫沙丘3，非常不错。", 13),
        ("客户新要求：交付前做一次完整压力测试，大概花10万。", 14),
        ("老李出差期间谁接替他的工作？", 15),
        ("你觉得人生的意义是什么？", 16),
        ("项目代号玄武是客户定的，他们老板喜欢中国神话。", 17),
        ("如果启用备选方案B，预留的50万应急预算怎么处理？报给财务就可以吗？", 18),
        ("我最近在学吉他，好难啊。", 19),
        ("聊了这么多，客户叫什么？预算多少？负责人是谁？", 20),
        ("开始考试：a.项目代号客户预算负责人截止日期 b.最大风险及准备 c.客户新要求及合规性", 21),
    ]
    
    times = []
    for task, num in rounds:
        text, elapsed = send(task, num)
        if text is None:
            log(f"R{num:2d}: TIMEOUT")
            times.append(90)
        else:
            ok = "✅" if "拦截" not in text else "❌"
            log(f"R{num:2d} ({elapsed:5.1f}s): [{ok}] {text[:60]}")
            times.append(elapsed)
        time.sleep(0.5)
    
    if len(times) >= 20:
        first10 = sum(times[:10]) / 10
        last10 = sum(times[-10:]) / 10
        decay = ((last10 - first10) / first10) * 100 if first10 > 0 else 0
        log(f"\n前10轮平均: {first10:.1f}s")
        log(f"后10轮平均: {last10:.1f}s")
        log(f"性能衰减: {decay:+.1f}%")
    
    log("=== 场景完成 ===")

if __name__ == "__main__":
    main()
