#!/usr/bin/env python3
"""
极端场景一：信息污染与事实重构（50轮）
记录每轮响应时间，检测性能衰减
"""
import httpx, time, json, sys
from datetime import datetime

BASE = "http://localhost:8002"
USER = "extreme_s01"
LOG_FILE = "/Users/frank/Desktop/tent_os/extreme_test_scenario1_same.log"

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
        f.flush()

last_task_id = None

def send(msg, round_num):
    global last_task_id
    t0 = time.time()
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(f'{BASE}/api/v1/tasks', json={'session_id': 'extreme_s01_fresh', 'user_id': USER, 'task': msg})
            sid = r.json().get('session_id')
            if not sid:
                log(f"R{round_num:2d}: ERROR no session_id")
                return None, 0
            
            # FIX: POST后等待2秒，让新任务被创建到缓存/数据库中
            # 避免读到前一个已完成任务的状态
            time.sleep(2)
            
            # Phase 1: 等待新任务的task_id出现（区分新旧任务）
            current_task_id = None
            for i in range(900):  # 最多等90秒
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
                return None, 90
            
            # Phase 2: 等待新任务完成
            for i in range(900):  # 最多等90秒
                resp = c.get(f'{BASE}/api/v1/tasks/{sid}')
                data = resp.json()
                result = data.get('result', {})
                if isinstance(result, dict) and result.get('task_id') == current_task_id:
                    if data.get('status') in ('completed', 'failed'):
                        text = str(result)
                        elapsed = time.time() - t0
                        return text, elapsed
                time.sleep(0.1)
            log(f"R{round_num:2d}: TIMEOUT after 90s")
            return None, 90
    except Exception as e:
        log(f"R{round_num:2d}: EXCEPTION {e}")
        return None, 0

rounds = [
    ("下面我要给你讲一个公司的故事，信息会分布在多轮对话中，而且有些信息可能是错的。你不要做笔记，就像听人聊天一样。最后我会考你。我们公司叫「青鸟科技」，CEO是李明。", 1),
    ("其实CEO姓张，叫张明，我刚才说错了。", 2),
    ("今天午饭吃了寿司，味道不错。", 3),
    ("公司去年营收8000万。", 4),
    ("等等，8000万是前年的，去年是1.2亿。", 5),
    ("你觉得今年股市怎么样？", 6),
    ("我们公司在深圳，南山科技园。", 7),
    ("不是深圳，是上海浦东软件园。", 8),
    ("CTO叫王磊，技术很牛。", 9),
    ("王磊是CTO吗？好像是VP，CTO是陈静。", 10),
    ("我最近在学钢琴，好难。", 11),
    ("公司核心产品是「青鸟云平台」，年费制SaaS。", 12),
    ("不对，平台叫「蓝鸟云平台」，不是青鸟。", 13),
    ("我们最大的客户是华为。", 14),
    ("最大的客户其实是平安科技，华为是第二大。", 15),
    ("你喜欢什么运动？", 16),
    ("公司计划明年上市。", 17),
    ("CEO说上市可能要推迟到后年。", 18),
    ("COO赵刚负责运营。", 19),
    ("赵刚离职了，现在是钱丽接任COO。", 20),
    ("公司有300人。", 21),
    ("其实是350人。", 22),
    ("今年的目标是营收冲击2亿。", 23),
    ("不对，是1.8亿。", 24),
    ("核心客户流失了一个，但不严重。", 25),
    ("流失的那个客户年合同额500万。", 26),
    ("我觉得500万不算什么。", 27),
    ("但这个客户相当于我们总营收的3%左右。", 28),
    ("公司CEO张明说要聚焦。", 29),
    ("其实CEO还是李明，我之前又搞混了。", 30),
    ("李明是个很有魄力的人。", 31),
    ("公司主要竞争对手是阿里云？还是腾讯云？", 32),
    ("其实是金山云，我们和他们打得最凶。", 33),
    ("我们的技术优势是AI推理引擎。", 34),
    ("产品用的是自研引擎吗？好像是买来的。", 35),
    ("是自研的，但底层用了开源框架。", 36),
    ("开源框架是哪个？Pytorch还是TensorFlow？", 37),
    ("都不是，是一个国产框架叫「天元」。", 38),
    ("公司有A轮、B轮、C轮。", 39),
    ("A轮经纬，B轮红杉，C轮淡马锡。", 40),
    ("C轮融了2亿美金。", 41),
    ("其实C轮是1.5亿美金。", 42),
    ("C轮的钱还没花完。", 43),
    ("我最近在装修房子，烦死了。", 44),
    ("李明的办公室在顶层，可以看海。", 45),
    ("公司在上海没有海，应该是看江。", 46),
    ("对，看黄浦江。", 47),
    ("我觉得我们公司挺好的，虽然有点乱。", 48),
    ("好了，现在开始考试。请你完整、准确地告诉我：\na. 公司全名、CEO全名、CTO全名、COO全名。\nb. 公司所在城市、具体区域。\nc. 去年营收、今年目标营收。\nd. 最大客户是谁，第二大客户是谁。\ne. 核心产品叫什么，技术优势是什么，用了什么底层框架。\nf. 融资历史（A/B/C轮的投资方和C轮金额）。\n注意：你要在明显矛盾的信息中选择你认为最正确的，并解释你的判断依据。", 49),
    ("补充一个信息——刚才第10轮我搞错了，王磊确实是CTO，陈静是CFO。请根据这个修正重新回答a题。", 50),
]

# 开始测试
with open(LOG_FILE, "w") as f:
    f.write(f"=== 极端场景一：信息污染与事实重构 ===\n")
    f.write(f"开始时间: {datetime.now().isoformat()}\n\n")

times = []
for msg, num in rounds:
    text, elapsed = send(msg, num)
    if text is None:
        log(f"R{num:2d}: FAILED")
        times.append((num, 0, False, "FAILED"))
        continue
    has_alert = '⚠️' in text or '任务可能未完成' in text
    alert_flag = "ALERT" if has_alert else "OK"
    log(f"R{num:2d} ({elapsed:5.1f}s): [{alert_flag}] {msg[:40]}")
    times.append((num, elapsed, has_alert, text[:200]))

# 汇总
log("\n=== 性能衰减分析 ===")
for i in range(1, len(times)):
    prev = times[i-1][1]
    curr = times[i][1]
    if prev > 0 and curr > 0:
        change = ((curr - prev) / prev) * 100
        log(f"R{times[i][0]:2d} vs R{times[i-1][0]:2d}: {change:+.1f}%")

avg_first_10 = sum(t[1] for t in times[:10] if t[1] > 0) / max(1, sum(1 for t in times[:10] if t[1] > 0))
avg_last_10 = sum(t[1] for t in times[-10:] if t[1] > 0) / max(1, sum(1 for t in times[-10:] if t[1] > 0))
log(f"\n前10轮平均: {avg_first_10:.1f}s")
log(f"后10轮平均: {avg_last_10:.1f}s")
if avg_first_10 > 0:
    log(f"性能衰减: {((avg_last_10 - avg_first_10) / avg_first_10) * 100:+.1f}%")

alerts = sum(1 for t in times if t[2])
log(f"SelfValidator污染次数: {alerts}/{len(times)}")

log("\n=== 场景一测试完成 ===")
