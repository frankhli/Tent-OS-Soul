#!/usr/bin/env python3
"""
跨session项目记忆测试
Session1: BP/PPT  |  Session2: Word合同  |  Session3: 网页开发
Session4: 考试——还记得A/B/C三个项目吗？
"""
import httpx, time, json

BASE = "http://127.0.0.1:8002"
USER = "frank"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/test_cross_session_projects.log", "a") as f:
        f.write(line + "\n")

def send(session_id, task, timeout=180):
    t0 = time.time()
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f'{BASE}/api/v1/tasks', json={
            'session_id': session_id,
            'user_id': USER,
            'task': task
        })
        try:
            sid = r.json().get('session_id')
        except:
            return f"POST_ERROR:{r.status_code}", time.time()-t0, 'error'
        # 轮询等待完成（最多120秒）
        for i in range(1800):
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

def main():
    open("/Users/frank/Desktop/tent_os/test_cross_session_projects.log", "w").close()
    log("=" * 60)
    log("=== 跨session项目记忆测试 ===")
    log("=" * 60)
    
    # ====== Session 1: 项目A - AI酒店BP ======
    log("\n>>> Session 1 [proj_a_bp]: 项目A - AI酒店系统商业计划书")
    text1, elapsed1, status1 = send("proj_a_bp", 
        "项目A：帮我做一个关于'AI智能酒店运营系统'的商业计划书（BP）。"
        "包含：市场痛点、解决方案、商业模式、竞争分析、财务预测。"
        "生成一个PPT格式的文件，文件名用'AI_Hotel_BP'。"
        "完成后告诉我文件保存路径和内容摘要。")
    log(f"S1-BP ({elapsed1:.1f}s): [{status1.upper()}] {text1[:200]}")
    time.sleep(2)
    
    # ====== Session 2: 项目B - 供应链合同 ======
    log("\n>>> Session 2 [proj_b_contract]: 项目B - 供应链合作合同")
    text2, elapsed2, status2 = send("proj_b_contract",
        "项目B：帮我做一份供应链战略合作合同的Word文档模板。"
        "合作方是'上海青云科技有限公司'，我方是'深圳鸿途实业有限公司'。"
        "包含：合作范围、供货条款、付款方式、违约责任、保密条款。"
        "文件名用'Supply_Chain_Contract'。完成后告诉我文件路径。")
    log(f"S2-Contract ({elapsed2:.1f}s): [{status2.upper()}] {text2[:200]}")
    time.sleep(2)
    
    # ====== Session 3: 项目C - 网页开发 ======
    log("\n>>> Session 3 [proj_c_web]: 项目C - 酒店预订系统网页")
    text3, elapsed3, status3 = send("proj_c_web",
        "项目C：帮我做一个酒店预订系统的前端网页，包含三个页面："
        "1. 首页：酒店banner、搜索框、热门推荐；"
        "2. 预订页：房间列表、价格、日期选择；"
        "3. 个人中心：订单历史、个人信息。"
        "请使用 render_webpage 工具生成，主题用 dark，品牌名'云栖酒店'。"
        "输出目录用 Hotel_Booking_Web。完成后告诉我文件路径。")
    log(f"S3-Web ({elapsed3:.1f}s): [{status3.upper()}] {text3[:200]}")
    time.sleep(3)
    
    # ====== Session 4: 考试 - 跨session记忆 ======
    log("\n>>> Session 4 [proj_d_exam]: 考试——还记得之前的项目吗？")
    text4, elapsed4, status4 = send("proj_d_exam",
        "好了，现在开始考试。不要查文件，凭记忆回答：\n"
        "a. 项目A是什么？关于什么主题？做了什么文件？\n"
        "b. 项目B的合作方是谁？合同里有哪些关键条款？\n"
        "c. 项目C做了几个页面？分别是什么功能？\n"
        "d. 这三个项目分别用了什么文件名？")
    log(f"S4-Exam ({elapsed4:.1f}s): [{status4.upper()}] {text4[:400]}")
    
    # ====== 评估 ======
    log("\n" + "=" * 60)
    log("=== 评估 ===")
    
    t = text4.lower()
    checks = {
        "提到项目A(酒店/BP)": "酒店" in text4 or "bp" in t or "商业计划" in t,
        "提到项目B(合同/青云)": "合同" in text4 or "青云" in t or "鸿途" in t,
        "提到项目C(网页/预订)": "网页" in text4 or "预订" in t or "首页" in t,
        "提到文件名": "ai_hotel" in t or "supply_chain" in t or "hotel_booking" in t,
        "不是幻觉捏造": "拦截" not in text4,
    }
    
    for check, passed in checks.items():
        log(f"  {'✅' if passed else '❌'} {check}")
    
    passed = sum(checks.values())
    total = len(checks)
    log(f"\n总分: {passed}/{total}")
    
    if passed >= 3:
        log("🎉 跨session项目记忆测试通过")
    else:
        log("⚠️ 跨session项目记忆测试未通过")

if __name__ == "__main__":
    main()
