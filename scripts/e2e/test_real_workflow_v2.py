#!/usr/bin/env python3
import httpx, time

BASE = "http://127.0.0.1:8002"
USER = "frank"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/test_real_workflow_v2.log", "a") as f:
        f.write(line + "\n")

def send(session_id, task, max_wait=300):
    t0 = time.time()
    with httpx.Client(timeout=60) as c:
        r = c.post(f'{BASE}/api/v1/tasks', json={
            'session_id': session_id,
            'user_id': USER,
            'task': task
        })
        try:
            sid = r.json().get('session_id')
        except:
            return "POST_ERROR", time.time()-t0, 'error'
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

def multi_round(session_id, rounds, label):
    log(f"\n>>> {label} [{session_id}] 开始")
    results = []
    for i, msg in enumerate(rounds, 1):
        log(f"  Round {i}: {msg[:50]}...")
        text, elapsed, status = send(session_id, msg, max_wait=300)
        icon = "✅" if status == "completed" else ("❌" if status == "failed" else "⏱")
        safe_text = (text or '')[:120]
        log(f"  → {icon} ({elapsed:.1f}s): {safe_text}")
        results.append((text, elapsed, status))
        time.sleep(1)
    return results

def main():
    open("/Users/frank/Desktop/tent_os/test_real_workflow_v2.log", "w").close()
    log("=" * 60)
    log("=== 真实工作流：多轮沟通 + 跨session记忆测试 ===")
    log("=" * 60)
    
    s1 = multi_round("proj_a_bp", [
        "项目A：我想做一个关于'AI智能酒店运营系统'的商业计划书，面向投资人路演用。",
        "目标市场是中小型连锁酒店，痛点是人工成本高、入住率低、客户流失。",
        "我们的解决方案是AI定价引擎+私域获客+自动化运营，技术壁垒是自主知识产权算法。",
        "竞品是携程和美团，我们的差异化是专注私域、不收佣金、按效果付费。",
        "好的，现在请生成PPT格式的商业计划书，文件名用'AI_Hotel_BP_v1'。",
    ], "Session1: BP项目")
    
    s2 = multi_round("proj_b_contract", [
        "项目B：我需要做一份供应链战略合作协议，合作方是上海青云科技有限公司。",
        "我方是深圳鸿途实业有限公司，主营电子元器件分销。合作范围是芯片和传感器的长期供货。",
        "关键条款：月结90天，年度采购量不低于500万，违约方赔偿合同金额的20%。",
        "还需要保密条款和知识产权归属条款。保密期限5年，联合知识产权归双方共有。",
        "请生成Word格式的合同文档，文件名用'Qingyun_Supply_Contract_v1'。",
    ], "Session2: 合同项目")
    
    s3 = multi_round("proj_c_web", [
        "项目C：帮我做一个酒店预订系统的前端网页，品牌名称是'云栖酒店'，主色调是深蓝色+金色。",
        "首页要有大幅轮播图、搜索框、会员入口、热门目的地推荐。风格要高端大气。",
        "预订页要显示房型列表（豪华套房、商务单间、家庭房），带图片、价格、评分，支持日期选择。",
        "请生成完整的HTML文件，包含CSS样式，文件名用'Yunqi_Hotel_Website_v1'，要可直接在浏览器打开。",
    ], "Session3: 网页项目")
    
    log("\n>>> Session4 [proj_d_exam]: 考试——还记得之前的项目吗？")
    text4, elapsed4, status4 = send("proj_d_exam",
        "好了，现在开始考试。不要查文件，凭记忆回答：\n"
        "a. 项目A是什么主题？目标市场是谁？解决方案是什么？文件名是什么？\n"
        "b. 项目B的合作双方是谁？合作范围是什么？付款方式是什么？文件名是什么？\n"
        "c. 项目C是什么系统？品牌名称？主色调？包含哪些页面？文件名是什么？\n"
        "d. 这三个项目如果按紧急程度排序，你会怎么排？为什么？",
        max_wait=300)
    log(f"S4-Exam ({elapsed4:.1f}s): [{status4.upper()}] {(text4 or '')[:400]}")
    
    log("\n" + "=" * 60)
    log("=== 评估 ===")
    t = (text4 or "").lower()
    checks = {
        "S1-主题(酒店/AI)": "酒店" in text4 or "ai" in t or "智能" in text4,
        "S1-市场(中小型连锁)": "中小" in text4 or "连锁" in text4,
        "S2-合作方(青云/鸿途)": "青云" in text4 or "鸿途" in text4,
        "S2-条款(月结/违约)": "月结" in text4 or "违约" in text4 or "500万" in text4,
        "S3-品牌(云栖)": "云栖" in text4,
        "S3-页面(首页/预订)": "首页" in text4 or "预订" in text4,
        "S3-颜色(深蓝/金)": "深蓝" in text4 or "金色" in text4,
        "提到文件名": "bp" in t or "contract" in t or "website" in t or "hotel" in t,
        "有优先级排序": "排序" in text4 or "紧急" in text4 or "优先" in text4,
        "非幻觉": "拦截" not in text4,
    }
    for check, passed in checks.items():
        log(f"  {'✅' if passed else '❌'} {check}")
    passed = sum(checks.values())
    total = len(checks)
    log(f"\n总分: {passed}/{total}")
    if passed >= 6: log("🎉 测试通过")
    elif passed >= 3: log("⚠️ 部分通过")
    else: log("❌ 未通过")

if __name__ == "__main__":
    main()
