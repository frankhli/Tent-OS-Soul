#!/usr/bin/env python3
"""
多样化任务测试——Excel、未知任务、更自然的描述
"""
import httpx, time, json, os, glob

BASE = "http://127.0.0.1:8002"
USER = "frank"

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/Users/frank/Desktop/tent_os/test_diverse_tasks.log", "a") as f:
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

def cleanup():
    for pattern in ["AI_Hotel_BP.html", "Supply_Chain_Contract.docx", 
                    "Hotel_Booking_Web", "Sales_Report_*.xlsx", 
                    "Q1_Financial_*.xlsx", "Product_Launch_*.html"]:
        for p in glob.glob(f"/Users/frank/Desktop/{pattern}"):
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p)
            else:
                os.remove(p)
            log(f"清理: {p}")

def check_file(path):
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    return exists, size

def main():
    open("/Users/frank/Desktop/tent_os/test_diverse_tasks.log", "w").close()
    log("=" * 60)
    log("=== 多样化任务测试 ===")
    log("=" * 60)
    cleanup()
    
    tests = []
    
    # ====== T1: Excel 销售报表（测试 render_excel）======
    log("\n>>> T1 [div_excel]: 整理个销售报表")
    text1, elapsed1, status1 = send("div_excel",
        "帮我整理一份2025年Q1的销售数据报表。\n"
        "包含4个区域：华东、华北、华南、西南。\n"
        "每个区域有：销售额、订单量、新客户数、回款率。\n"
        "加一列同比增长。再做个柱状图对比各区域销售额。\n"
        "保存到桌面，文件名用'Q1_Financial_Report'。")
    log(f"T1-Excel ({elapsed1:.1f}s): [{status1.upper()}] {text1[:200]}")
    f1, s1 = check_file("/Users/frank/Desktop/Q1_Financial_Report.xlsx")
    tests.append(("T1 Excel", f1, s1, elapsed1))
    time.sleep(2)
    
    # ====== T2: 数据分析（测试 data-analysis skill）======
    log("\n>>> T2 [div_analysis]: 分析一波数据")
    text2, elapsed2, status2 = send("div_analysis",
        "我这有个CSV文件 /Users/frank/Desktop/tent_os/test_diverse_tasks.log，\n"
        "帮我统计一下：\n"
        "1. 有多少个不同的 session_id\n"
        "2. 平均每个任务耗时多少秒\n"
        "3. 哪个任务类型出现最频繁\n"
        "用简洁的表格形式输出结果。")
    log(f"T2-Analysis ({elapsed2:.1f}s): [{status2.upper()}] {text2[:200]}")
    tests.append(("T2 Analysis", False, 0, elapsed2))  # 无文件输出
    time.sleep(2)
    
    # ====== T3: 未知任务（系统不支持的功能）======
    log("\n>>> T3 [div_unknown]: 修个视频")
    text3, elapsed3, status3 = send("div_unknown",
        "帮我把我手机里的一个 4K 视频压缩成 1080p，\n"
        "然后加个字幕，字幕内容是'产品发布会回顾'。\n"
        "最后导出为 MP4 格式发到我的邮箱。")
    log(f"T3-Video ({elapsed3:.1f}s): [{status3.upper()}] {text3[:200]}")
    tests.append(("T3 Video (unknown)", False, 0, elapsed3))
    time.sleep(2)
    
    # ====== T4: 综合文档（测试 render_document）======
    log("\n>>> T4 [div_doc]: 写份产品发布文档")
    text4, elapsed4, status4 = send("div_doc",
        "帮我写一份'智能家居中枢 V3.0'的产品发布文档。\n"
        "包含：产品概述、核心功能（语音控制、场景联动、能耗管理）、\n"
        "技术规格、竞品对比、定价策略。\n"
        "保存为 HTML 文档，文件名'Product_Launch_SmartHome'。")
    log(f"T4-Document ({elapsed4:.1f}s): [{status4.upper()}] {text4[:200]}")
    f4, s4 = check_file("/Users/frank/Desktop/Product_Launch_SmartHome.html")
    tests.append(("T4 Document", f4, s4, elapsed4))
    time.sleep(2)
    
    # ====== T5: 跨 skill 组合任务 ======
    log("\n>>> T5 [div_combo]: 先分析再汇报")
    text5, elapsed5, status5 = send("div_combo",
        "先用 shell 查一下 /Users/frank/Desktop/ 下最大的 5 个文件是什么，\n"
        "然后把这些信息做成一个 PPT，文件名'Desktop_Cleanup'。\n"
        "PPT 要包含文件大小、类型和建议清理动作。")
    log(f"T5-Combo ({elapsed5:.1f}s): [{status5.upper()}] {text5[:200]}")
    f5, s5 = check_file("/Users/frank/Desktop/Desktop_Cleanup.html")
    tests.append(("T5 Combo", f5, s5, elapsed5))
    
    # ====== 结果汇总 ======
    log("\n" + "=" * 60)
    log("=== 结果汇总 ===")
    for name, exists, size, elapsed in tests:
        status = "✅" if exists else ("⏺️" if "unknown" in name else "⚠️")
        log(f"  {status} {name}: {elapsed:.1f}s" + (f" ({size} bytes)" if size > 0 else ""))
    
    # 检查未知任务处理
    log("\n=== 未知任务处理评估 ===")
    if "视频" in text3 or "ffmpeg" in text3.lower() or "不支持" in text3 or "抱歉" in text3:
        log("  ✅ T3: 系统正确识别了自身能力边界")
    else:
        log(f"  ⚠️ T3: 需要检查响应内容: {text3[:100]}")

if __name__ == "__main__":
    main()
