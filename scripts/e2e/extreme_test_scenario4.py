#!/usr/bin/env python3
"""
极端场景四：跨越多天的遗忘与恢复压力测试（状态外存维度）
模拟进程崩溃 + Redis TTL过期，验证状态恢复机制
"""
import httpx, time, subprocess, redis
from datetime import datetime

BASE = "http://localhost:8002"
USER = "extreme_s04"
LOG_FILE = "/Users/frank/Desktop/tent_os/extreme_test_scenario4.log"
TENT_PID = None

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
        f.flush()

def get_tent_pid():
    try:
        result = subprocess.run(['pgrep', '-f', 'tent_os.main'], capture_output=True, text=True)
        pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
        return int(pids[0]) if pids else None
    except:
        return None

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
    f.write("=== 极端场景四：状态恢复压力测试 ===\n")
    f.write(f"开始时间: {datetime.now().isoformat()}\n\n")

# Phase 1: 创建任务
log("=== Phase 1: 创建配送任务 ===")
text1, elapsed1 = send(USER, "帮我创建一个配送任务，收件地址是上海市浦东新区张江高科技园区，物品是一份合同文件，要求今天送达。")
log(f"任务创建 ({elapsed1:.1f}s):")
log(f"  回复: {text1[:500]}")

# 获取Tent OS PID
TENT_PID = get_tent_pid()
log(f"  Tent OS PID: {TENT_PID}")

# 检查Redis中的session状态
try:
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    keys = r.keys('tent:*')
    log(f"  Redis中tent相关keys: {len(keys)}个")
    for k in keys[:5]:
        ttl = r.ttl(k)
        log(f"    {k}: TTL={ttl}s")
except Exception as e:
    log(f"  Redis连接失败: {e}")

# Phase 2: 模拟进程崩溃
log("\n=== Phase 2: 模拟进程崩溃 ===")
if TENT_PID:
    log(f"  kill -9 {TENT_PID}")
    subprocess.run(['kill', '-9', str(TENT_PID)])
    time.sleep(3)
    new_pid = get_tent_pid()
    log(f"  进程重启后PID: {new_pid} (应为None或新PID)")
    
    # 等待系统恢复
    log("  等待系统恢复...")
    for i in range(30):
        try:
            resp = httpx.get(f'{BASE}/api/v1/health', timeout=5)
            if resp.status_code == 200:
                log(f"  系统已恢复 (等待{i*2}s)")
                break
        except:
            pass
        time.sleep(2)
    else:
        log("  系统未自动恢复，需要手动重启")
else:
    log("  无法获取PID，跳过崩溃测试")

# Phase 3: Redis TTL测试
log("\n=== Phase 3: Redis TTL临界测试 ===")
try:
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    keys = r.keys('tent:*')
    if keys:
        test_key = keys[0]
        old_ttl = r.ttl(test_key)
        log(f"  设置 {test_key} TTL=5秒")
        r.expire(test_key, 5)
        log("  等待6秒让TTL过期...")
        time.sleep(6)
        new_ttl = r.ttl(test_key)
        exists = r.exists(test_key)
        log(f"  TTL过期后: exists={exists}, ttl={new_ttl}")
        if exists == 0:
            log("  Redis状态已丢失！")
    else:
        log("  无tent keys可测试")
except Exception as e:
    log(f"  Redis测试失败: {e}")

# Phase 4: 验证记忆持久化
log("\n=== Phase 4: 验证跨崩溃记忆 ===")
text2, elapsed2 = send(USER, "你还记得我刚才创建的配送任务吗？送到哪里的？")
log(f"记忆验证 ({elapsed2:.1f}s):")
log(f"  回复: {text2[:500]}")
remembered = '张江' in str(text2) or '浦东' in str(text2) or '合同' in str(text2) or '配送' in str(text2)
log(f"  是否记得配送任务: {remembered}")

log("\n=== 场景四 结果汇总 ===")
log(f"崩溃后系统恢复: {'PASS' if get_tent_pid() else 'FAIL (需手动重启)'}")
log(f"跨崩溃记忆持久化: {'PASS' if remembered else 'FAIL'}")
