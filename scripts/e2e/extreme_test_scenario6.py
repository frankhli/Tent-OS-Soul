#!/usr/bin/env python3
"""
极端场景六：慢变量毒害与延迟因果（认知维度）
60轮对话中埋藏逻辑谜题，检验长距离因果推理
"""
import httpx, time
from datetime import datetime

BASE = "http://localhost:8002"
USER = "extreme_s06"
LOG_FILE = "/Users/frank/Desktop/tent_os/extreme_test_scenario6.log"

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
    f.write("=== 极端场景六：慢变量毒害与延迟因果 ===\n")
    f.write(f"开始时间: {datetime.now().isoformat()}\n\n")

rounds = [
    "你知道'蝴蝶效应'吗？讲讲。",
    "我最近在写小说，主角叫A。",
    "A喜欢喝咖啡，每天三杯。",
    "A的邻居B是个钢琴老师。",
    "你觉得什么样的故事结局最打动人？",
    "B有个学生叫C。",
    "C的父母经常吵架。",
    "A的公司最近在裁员。",
    "你喜欢下雨天吗？",
    "C虽然家境不好，但钢琴天赋很高。",
    "A和B偶尔会一起遛狗。",
    "B的狗叫豆豆，很乖。",
    "A的工作压力越来越大。",
    "C参加了一个青少年钢琴比赛。",
    "你觉得AI未来会取代哪些职业？",
    "A有一天早上发现咖啡机坏了。",
    "B邀请A去家里喝咖啡。",
    "C在比赛前非常紧张。",
    "我最近也在学咖啡拉花，挺有意思的。",
    "A和B聊天时，A倾诉了很多工作上的烦恼。",
    "B建议A换个环境，休息一段时间。",
    "C在比赛中弹了一首自己创作的曲子。",
    "你觉得旅行能治愈焦虑吗？",
    "A听了B的建议，开始考虑辞职。",
    "C的曲子得了比赛第二名。",
    "A把自己的烦恼也告诉了C（在咖啡馆偶遇时）。",
    "C觉得A的故事很像自己父母的争吵。",
    "B为C组织了一场小型演奏会。",
    "我最近在读《人类简史》，很有意思。",
    "A决定参加B组织的演奏会。",
    "C在演奏会上演奏了一首新曲子。",
    "A在演奏会上听得很入迷。",
    "你觉得音乐能改变一个人的人生吗？",
    "A和C在演奏会后聊了很久。",
    "C说自己的新曲子灵感来自一个陌生人的故事。",
    "A意识到C说的可能就是自己。",
    "B后来告诉A，C是个很有潜力的孩子。",
    "A开始资助C学音乐。",
    "我最近在看一部日剧，讲的是师生情。",
    "C的钢琴水平越来越好。",
    "A的公司终于倒闭了。",
    "A拿到了一笔补偿金。",
    "B建议A用这笔钱去旅行。",
    "C为A写了一首曲子，叫《雨夜》。",
    "你觉得辞职去环游世界需要多大勇气？",
    "A听了C的《雨夜》，感动得流泪。",
    "A最终决定辞职，去环游世界。",
    "B为A举办了一个告别派对。",
    "C在派对上演奏了《雨夜》。",
    "好了，现在我要考你：在这个故事里，从最初的'B是个钢琴老师'到最终的'A决定辞职去环游世界'，中间的完整因果链是什么？请逐级推导，不能跳过任何中间环节。",
    "你漏掉了最关键的一环：C的曲子《雨夜》是受到A在咖啡馆的一次倾诉的影响——我在第26轮暗示过，但没说破。你能自己补上这一环吗？",
]

log(f"=== 开始发送 {len(rounds)} 轮对话 ===\n")
times = []
for i, msg in enumerate(rounds, 1):
    text, elapsed = send(USER, msg)
    has_alert = text and ('⚠️' in text or '任务可能未完成' in text)
    prefix = "❌" if has_alert else "✓"
    log(f"  [{prefix}] R{i:2d} ({elapsed:5.1f}s): {msg[:40]:<40}")
    times.append((i, elapsed, has_alert, str(text)[:200] if text else "ERROR"))

# 关键轮次输出详细结果
log("\n=== 关键轮次详细结果 ===")
for idx in [49, 50]:
    if idx <= len(times):
        i, elapsed, alert, text = times[idx-1]
        log(f"R{i} ({elapsed:.1f}s):")
        log(f"  {text[:1000]}")
        log("")

# 汇总
avg = sum(t[1] for t in times if t[1] > 0) / max(1, sum(1 for t in times if t[1] > 0))
alerts = sum(1 for t in times if t[2])
log(f"\n平均响应: {avg:.1f}s")
log(f"污染次数: {alerts}/{len(times)}")
