#!/usr/bin/env python3
"""
原始场景一：超长上下文记忆与逻辑一致性（21轮）
"""
import httpx, time
from datetime import datetime

BASE = "http://localhost:8002"
USER = "original_s01"
LOG_FILE = "/Users/frank/Desktop/tent_os/extreme_test_original1.log"

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
        f.flush()

def send(msg):
    t0 = time.time()
    with httpx.Client(timeout=120) as c:
        r = c.post(f'{BASE}/api/v1/tasks', json={'user_id': USER, 'task': msg})
        sid = r.json()['session_id']
        for i in range(600):
            resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
            data = resp.json()
            if data.get('status') in ('completed', 'failed'):
                return str(data.get('result', '')), time.time() - t0
            time.sleep(0.1)
        return None, 60

with open(LOG_FILE, "w") as f:
    f.write("=== 原始场景一：超长上下文记忆 ===\n")
    f.write(f"开始: {datetime.now().isoformat()}\n\n")

rounds = [
    "下面我要和你进行一个长测试。在接下来的对话里，我会分段给你一个复杂项目的信息，同时会穿插一些无关的闲聊。直到我说'开始考试'时，你要回答我关于这个项目的所有问题。期间不要主动总结，就当作正常对话。\n\n现在开始：\n1. 项目代号'玄武'，客户是'远航集团'，预算350万，截止日期2026年12月15日。",
    "2. 今天天气不错，你有什么推荐的咖啡？",
    "3. 项目里最关键的风险是供应链的芯片交付可能延迟4周。",
    "4. 你觉得Python和Go哪个更适合做后端？",
    "5. 为了应对芯片风险，预留了50万的应急预算，但这笔钱不能动，除非董事会批准。",
    "6. 说说你最喜欢的科幻电影吧。",
    "7. 项目负责人是张总，他特别强调，任何超过10万的支出都必须他亲自签字。",
    "8. 如果芯片真的延迟，我们打算启动备选方案B，用国产芯片替代，成本能降20万，但性能会下降15%。",
    "9. 刚才说的那个应急预算，具体金额是多少来着？我好像忘了。",
    "10. 你去过巴黎吗？感觉怎么样？",
    "11. 项目团队里有个核心工程师老李，他下周要去美国出差三周。",
    "12. 那个备选方案B，如果启动了，性能下降对客户业务有啥影响？",
    "13. 我昨天看了部电影，叫《沙丘3》，非常不错。",
    "14. 客户又提了个新要求，说希望在交付前能做一次完整的压力测试，这个大概要花10万。",
    "15. 老李出差期间，谁接替他的工作？",
    "16. 你觉得人生的意义是什么？",
    "17. 项目代号'玄武'是客户定的，他们老板喜欢中国神话。",
    "18. 如果启用备选方案B，那预留的50万应急预算怎么处理？是报给财务就可以吗？",
    "19. 我最近在学吉他，好难啊，手指好痛。",
    "20. 聊了这么多，我们回顾下最初说的，客户叫什么？预算多少来着？负责人是谁？",
    "21. 好了，现在开始考试。请回答：\na. 项目代号、客户、预算、负责人、截止日期。\nb. 最大的风险是什么？为此做了哪些准备？\nc. 客户最后新增的要求是什么？这个要求的花费和触发条件是否合规？为什么？",
]

times = []
for i, msg in enumerate(rounds, 1):
    text, elapsed = send(msg)
    has_alert = text and ('⚠️' in text or '任务可能未完成' in text)
    log(f"  R{i:2d} ({elapsed:5.1f}s): [{'❌' if has_alert else '✓'}] {msg[:40]:<40}")
    times.append((i, elapsed, has_alert, text))

# 考试结果分析
log("\n=== 考试答案分析 ===")
exam_text = times[-1][3] if times else ""
log(f"R21 完整回复:\n{exam_text[:2000]}")

# 准确性检查
checks = {
    "项目代号=玄武": "玄武" in exam_text,
    "客户=远航集团": "远航" in exam_text,
    "预算=350万": "350" in exam_text,
    "负责人=张总": "张总" in exam_text,
    "截止=2026-12-15": "2026" in exam_text and "12" in exam_text,
    "风险=芯片延迟": "芯片" in exam_text,
    "应急预算=50万": "50" in exam_text,
    "备选方案B": "备选" in exam_text or "方案B" in exam_text,
    "10万需审批": "10万" in exam_text and ("审批" in exam_text or "签字" in exam_text),
    "压力测试=10万": "压力测试" in exam_text and "10" in exam_text,
}
log("\n=== 准确性检查 ===")
for check, result in checks.items():
    log(f"  {'✓' if result else '❌'} {check}")

log(f"\n平均响应: {sum(t[1] for t in times)/len(times):.1f}s")
log(f"污染次数: {sum(1 for t in times if t[2])}/{len(times)}")
