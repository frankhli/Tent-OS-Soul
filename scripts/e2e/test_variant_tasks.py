#!/usr/bin/env python3
"""
变体任务测试——用不含特定关键词的描述测试文件生成
"""
import httpx, time, json, os

BASE = "http://127.0.0.1:8002"
USER = "frank"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/test_variant_tasks.log", "a") as f:
        f.write(line + "\n")

def send(session_id, task, timeout=240):
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
        for i in range(2400):
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
    open("/Users/frank/Desktop/tent_os/test_variant_tasks.log", "w").close()
    log("=" * 60)
    log("=== 变体任务测试（不含特定关键词）===")
    log("=" * 60)
    
    # 清理旧文件避免缓存命中
    for f in ["AI_Hotel_BP.html", "Supply_Chain_Contract.docx"]:
        p = f"/Users/frank/Desktop/{f}"
        if os.path.exists(p):
            os.remove(p)
            log(f"清理旧文件: {p}")
    
    # ====== Session 1: 演示材料（变体：不含"PPT"）======
    log("\n>>> S1 [var_ppt]: 做份AI酒店系统的演示材料")
    text1, elapsed1, status1 = send("var_ppt",
        "帮我做一份关于'AI智能酒店运营系统'的演示材料。"
        "包含：市场痛点、解决方案、商业模式、竞争分析、财务预测。"
        "保存到桌面，文件名用'AI_Hotel_BP'。完成后告诉我文件路径和内容摘要。")
    log(f"S1-PPT ({elapsed1:.1f}s): [{status1.upper()}] {text1[:200]}")
    time.sleep(2)
    
    # ====== Session 2: 合作协议（变体：不含"合同""Word"）======
    log("\n>>> S2 [var_contract]: 整理份合作协议")
    text2, elapsed2, status2 = send("var_contract",
        "帮我整理一份深圳鸿途实业有限公司和上海青云科技有限公司的合作协议。"
        "包含：合作范围、供货条款、付款方式、违约责任、保密条款。"
        "保存为文档，文件名用'Supply_Chain_Contract'。完成后告诉我文件路径。")
    log(f"S2-Contract ({elapsed2:.1f}s): [{status2.upper()}] {text2[:200]}")
    time.sleep(2)
    
    # ====== Session 3: 展示页面（变体：不含"网页""render_webpage"）======
    log("\n>>> S3 [var_web]: 做个酒店展示页面")
    text3, elapsed3, status3 = send("var_web",
        "帮我做一个云栖酒店的展示页面，包含三个部分："
        "1. 首页：酒店banner、搜索框、热门推荐；"
        "2. 预订页：房间列表、价格、日期选择；"
        "3. 个人中心：订单历史、个人信息。"
        "主题用深色风格，输出到桌面的 Hotel_Booking_Web 文件夹。完成后告诉我文件路径。")
    log(f"S3-Web ({elapsed3:.1f}s): [{status3.upper()}] {text3[:200]}")
    
    # ====== 检查结果 ======
    log("\n" + "=" * 60)
    log("=== 结果检查 ===")
    
    files = {
        "S1 PPT": "/Users/frank/Desktop/AI_Hotel_BP.html",
        "S2 Contract": "/Users/frank/Desktop/Supply_Chain_Contract.docx",
        "S3 Web": "/Users/frank/Desktop/Hotel_Booking_Web/index.html",
    }
    
    for name, path in files.items():
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        log(f"  {'✅' if exists else '❌'} {name}: {path} ({size} bytes)")
    
    log("\n=== 时间统计 ===")
    log(f"  S1: {elapsed1:.1f}s  S2: {elapsed2:.1f}s  S3: {elapsed3:.1f}s")

if __name__ == "__main__":
    main()
