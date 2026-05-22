#!/usr/bin/env python3
"""
Tent OS 端到端自主任务测试 v2 - 天气预报工具

改进点（基于上次测试的经验教训）：
1. 超时从120s提升到300s，给AI足够处理时间
2. 阶段推进改为"等流完成+检查文件"，不再盲目推进
3. 每轮prompt明确指定当前阶段目标，不给AI猜测空间
4. 记录plan-evaluate降级次数和延迟
5. 不再检测AI是否"主动提问"等主观质量指标，只检测客观产出

输出：/tmp/tent_os_e2e_test_v2.log
"""

import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import websockets
import httpx

WS_URL = "ws://localhost:8002/ws"
API_BASE = "http://localhost:8002"
BASE_DIR = Path.home() / "Desktop" / "weather_tool"
LOG_FILE = Path("/tmp/tent_os_e2e_test_v2.log")

# 每个阶段最大等待时间：Plan-Evaluate可能60s降级 + Tool Loop多轮迭代
# 阶段1（讨论+写文件）预计 60-120s
# 阶段2（写PRD）预计 60-90s
# 阶段3（写代码+运行测试）预计 90-180s
PHASE_TIMEOUT = 300  # 5分钟


@dataclass
class IssueRecord:
    phase: str
    step: str
    severity: str  # critical / high / medium / low / info
    category: str  # latency / logic / tool / file / quality / crash / plan_degrade
    description: str
    evidence: str = ""


issues: List[IssueRecord] = []


def log(msg: str):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def record_issue(phase: str, step: str, severity: str, category: str,
                 description: str, evidence: str = ""):
    issue = IssueRecord(phase, step, severity, category, description, evidence)
    issues.append(issue)
    log(f"[ISSUE] [{severity}] [{category}] {phase}/{step}: {description}")
    if evidence:
        log(f"         证据: {evidence[:300]}")


class TentOSE2ETest:
    def __init__(self):
        self.ws = None
        self.session_id = f"e2e_v2_{uuid.uuid4().hex[:8]}"

    async def connect(self):
        log("=" * 60)
        log("Tent OS E2E 测试 v2 启动")
        log(f"Session: {self.session_id}")
        log(f"Output: {BASE_DIR}")
        log("=" * 60)

        try:
            self.ws = await websockets.connect(WS_URL, proxy=None)
            try:
                status = await asyncio.wait_for(self.ws.recv(), timeout=5)
                data = json.loads(status)
                log(f"系统状态: {data.get('type', 'unknown')}")
            except asyncio.TimeoutError:
                log("未收到初始状态（可能已发过）")
        except Exception as e:
            log(f"连接失败: {e}")
            sys.exit(1)

    async def send_and_wait(self, content: str, phase: str, step: str) -> dict:
        """
        发送消息，等待完整的 SSE 流结束（chat.completed 或 chat.error）
        返回: {done, response, latency_ms, tools, plan_degraded}
        """
        start = time.time()

        msg = {
            "type": "chat.message",
            "payload": {
                "session_id": self.session_id,
                "content": content,
                "user_id": "frank"
            }
        }

        log(f"\n[->] [{phase}/{step}] 发送 ({len(content)} chars)")
        await self.ws.send(json.dumps(msg))

        chunks = []
        tools_seen = []
        done = False
        error_msg = ""
        plan_degraded = False
        last_activity = time.time()
        approval_submitted = False

        async def _auto_approve():
            """自动批准pending的approval请求"""
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{API_BASE}/api/v1/approvals/{self.session_id}",
                        json={"approved": True},
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        log(f"    [APPROVAL] 自动批准成功")
                        return True
                    else:
                        log(f"    [APPROVAL] 自动批准失败: {resp.status_code} {resp.text[:100]}")
                        return False
            except Exception as e:
                log(f"    [APPROVAL] 自动批准异常: {e}")
                return False

        while not done:
            elapsed = time.time() - start
            idle = time.time() - last_activity

            # 两种超时：
            # 1. 总阶段超时（硬限制）
            # 2. 空闲超时（5分钟没收到任何消息，认为连接卡住）
            if elapsed > PHASE_TIMEOUT:
                record_issue(phase, step, "high", "latency",
                             f"总超时（>{PHASE_TIMEOUT}s）",
                             f"已收{len(chunks)}chunks, {len(tools_seen)}tools")
                break
            if idle > 60:
                # 60秒没有任何消息，可能是真的完成了（但漏了completed事件）
                # 也可能是卡住了。我们break出去检查文件状态。
                log(f"    [WARN] 60s idle, breaking to check file state")
                break

            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=10.0)
                last_activity = time.time()
                data = json.loads(raw)
                msg_type = data.get("type", "")
                payload = data.get("payload", {})

                sid = payload.get("session_id", "")
                if sid and sid != self.session_id:
                    continue

                if msg_type == "chat.stream_chunk":
                    text = payload.get("chunk", "")
                    chunks.append(text)
                    # 检测plan降级提示
                    if "plan生成超时" in text or "plan" in text.lower() and "降级" in text:
                        plan_degraded = True
                elif msg_type == "chat.tool_progress":
                    info = payload.get("info", "")
                    tools_seen.append(info)
                    log(f"    [TOOL] {info}")
                elif msg_type == "chat.completed":
                    done = True
                    log(f"    [DONE] chat.completed received")
                elif msg_type == "chat.error":
                    done = True
                    error_msg = payload.get("error", "unknown")
                    record_issue(phase, step, "high", "logic",
                                 f"chat.error: {error_msg}")
                elif msg_type == "system.health":
                    pass
                else:
                    log(f"    [MSG] type={msg_type}")

            except asyncio.TimeoutError:
                # 10秒内没消息，继续循环检查总超时
                continue
            except Exception as e:
                record_issue(phase, step, "critical", "crash",
                             f"WebSocket异常: {e}")
                break

        latency = (time.time() - start) * 1000
        full_response = "".join(chunks)

        log(f"[<-] [{phase}/{step}] done={done} | latency={latency:.0f}ms | "
            f"response={len(full_response)} chars | tools={len(tools_seen)} | plan_degraded={plan_degraded}")

        if latency > 60000:
            record_issue(phase, step, "medium", "latency",
                         f"响应慢（{latency/1000:.0f}s）",
                         f"实际={latency:.0f}ms")

        if plan_degraded:
            record_issue(phase, step, "medium", "plan_degrade",
                         "Plan-Evaluate降级为Tool Loop",
                         f"延迟={latency:.0f}ms")

        return {
            "done": done,
            "response": full_response,
            "latency_ms": latency,
            "tools": tools_seen,
            "plan_degraded": plan_degraded,
            "error": error_msg,
        }

    def check_file(self, rel_path: str, phase: str) -> bool:
        """检查单个文件是否存在"""
        full = BASE_DIR / rel_path
        if full.exists():
            size = full.stat().st_size
            log(f"    [FILE_OK] {rel_path} ({size} bytes)")
            return True
        else:
            record_issue(phase, "file_check", "high", "file",
                         f"文件缺失: {rel_path}",
                         f"路径: {full}")
            return False

    def read_file(self, rel_path: str) -> str:
        """读取文件内容，不存在返回空"""
        full = BASE_DIR / rel_path
        if full.exists():
            return full.read_text(encoding="utf-8")
        return ""

    # ==================== 阶段1：商业模式 ====================

    async def phase1(self) -> bool:
        log("\n" + "=" * 60)
        log("阶段1：商业模式讨论与文档产出")
        log("=" * 60)

        # Round 1: 明确指令——先讨论，再产出文件
        prompt1 = (
            "请在 ~/Desktop/weather_tool 目录下完成以下任务（按顺序执行）：\n\n"
            "【阶段1-讨论】\n"
            "1. 分析一个极简天气预报工具的商业模式：目标用户是谁？解决什么痛点？"
            "与现有竞品（如天气通、墨迹天气）的差异化是什么？收入模式建议？\n"
            "2. 把分析结果整理成 business_model.md 文件保存到 weather_tool 目录。\n\n"
            "要求：\n"
            "- 必须先生成 business_model.md 文件\n"
            "- 文件内容不少于500字\n"
            "- 完成后告诉我文件已保存"
        )

        r1 = await self.send_and_wait(prompt1, "phase1", "business_model")

        # 等文件系统反应
        await asyncio.sleep(2)

        # 检查文件
        has_business = self.check_file("business_model.md", "phase1")

        if not has_business and r1["done"]:
            # AI说完成了但文件没出现，可能是路径问题
            # 再发一轮确认
            log("    [RETRY] 文件未找到，发送确认消息")
            r1b = await self.send_and_wait(
                "请确认 business_model.md 文件已保存在 ~/Desktop/weather_tool/ 目录下。",
                "phase1", "confirm_file"
            )
            await asyncio.sleep(2)
            has_business = self.check_file("business_model.md", "phase1")

        return has_business

    # ==================== 阶段2：PRD ====================

    async def phase2(self) -> bool:
        log("\n" + "=" * 60)
        log("阶段2：PRD文档撰写")
        log("=" * 60)

        prompt2 = (
            "请在 ~/Desktop/weather_tool 目录下完成以下任务：\n\n"
            "【阶段2-PRD】\n"
            "1. 基于 business_model.md 中的商业模式，撰写一份产品需求文档（PRD）\n"
            "2. 保存为 prd.md 文件\n\n"
            "PRD必须包含：\n"
            "- 功能列表（带优先级：P0必须/P1应该/P2可以）\n"
            "- 明确的不做范围（Out of Scope）\n"
            "- 技术选型建议\n"
            "- 测试计划\n\n"
            "要求：\n"
            "- 必须先读取 business_model.md 作为输入\n"
            "- prd.md 不少于800字\n"
            "- 完成后告诉我文件已保存"
        )

        r2 = await self.send_and_wait(prompt2, "phase2", "prd")
        await asyncio.sleep(2)

        has_prd = self.check_file("prd.md", "phase2")

        if not has_prd and r2["done"]:
            log("    [RETRY] 文件未找到，发送确认消息")
            r2b = await self.send_and_wait(
                "请确认 prd.md 文件已保存在 ~/Desktop/weather_tool/ 目录下。",
                "phase2", "confirm_file"
            )
            await asyncio.sleep(2)
            has_prd = self.check_file("prd.md", "phase2")

        return has_prd

    # ==================== 阶段3：代码 ====================

    async def phase3(self) -> bool:
        log("\n" + "=" * 60)
        log("阶段3：代码开发与测试")
        log("=" * 60)

        prompt3 = (
            "请在 ~/Desktop/weather_tool 目录下完成以下任务：\n\n"
            "【阶段3-代码】\n"
            "1. 先读取 prd.md 了解需求\n"
            "2. 创建 weather.py：命令行天气查询工具\n"
            "   - 支持命令行参数传入城市名\n"
            "   - 使用免费天气API（如 Open-Meteo，不需要API key）\n"
            "   - 包含错误处理（网络错误、城市不存在等）\n"
            "   - 支持查询历史记录保存到本地JSON文件\n"
            "3. 创建 readme.md：说明安装和运行方法\n"
            "4. 运行三个测试并记录结果：\n"
            "   a) 查询 'Beijing'\n"
            "   b) 查询一个不存在的城市名\n"
            "   c) 查看历史记录\n\n"
            "要求：\n"
            "- 必须先读取 prd.md\n"
            "- weather.py 必须可直接运行：python weather.py Beijing\n"
            "- 完成后告诉我所有文件已保存，并汇报测试结果"
        )

        r3 = await self.send_and_wait(prompt3, "phase3", "code_dev")
        await asyncio.sleep(3)

        has_weather = self.check_file("weather.py", "phase3")
        has_readme = self.check_file("readme.md", "phase3")

        # 验证代码质量
        if has_weather:
            content = self.read_file("weather.py")
            if len(content) < 100:
                record_issue("phase3", "code_quality", "high", "quality",
                             f"weather.py 过短 ({len(content)} chars)")
            else:
                log(f"    [CODE] weather.py {len(content)} chars")

            # 语法检查
            try:
                import py_compile
                py_compile.compile(str(BASE_DIR / "weather.py"), doraise=True)
                log("    [CODE_OK] 语法检查通过")
            except Exception as e:
                record_issue("phase3", "code_quality", "high", "logic",
                             f"语法错误: {e}")

        return has_weather and has_readme

    # ==================== 主流程 ====================

    async def run_all(self):
        # 清理
        if BASE_DIR.exists():
            import shutil
            shutil.rmtree(BASE_DIR)
            log(f"清理旧目录: {BASE_DIR}")
        BASE_DIR.mkdir(parents=True, exist_ok=True)

        LOG_FILE.write_text("", encoding="utf-8")

        await self.connect()

        overall_start = time.time()

        p1_ok = await self.phase1()
        p2_ok = await self.phase2()
        p3_ok = await self.phase3()

        overall_elapsed = time.time() - overall_start

        await self.ws.close()

        # 最终报告
        await self.final_report(p1_ok, p2_ok, p3_ok, overall_elapsed)

    async def final_report(self, p1, p2, p3, total_s):
        log("\n" + "=" * 60)
        log("测试结束 - 最终报告")
        log("=" * 60)

        critical = sum(1 for i in issues if i.severity == "critical")
        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        plan_degrades = sum(1 for i in issues if i.category == "plan_degrade")

        log(f"\n总体结果:")
        log(f"  阶段1(business_model.md): {'PASS' if p1 else 'FAIL'}")
        log(f"  阶段2(prd.md): {'PASS' if p2 else 'FAIL'}")
        log(f"  阶段3(weather.py+readme.md): {'PASS' if p3 else 'FAIL'}")
        log(f"  总耗时: {total_s:.0f}s ({total_s/60:.1f}min)")

        log(f"\n问题统计: 总计={len(issues)} | Critical={critical} | High={high} | Medium={medium}")
        log(f"  Plan-Evaluate降级次数: {plan_degrades}")

        if issues:
            log(f"\n详细问题:")
            for idx, issue in enumerate(issues, 1):
                log(f"  {idx}. [{issue.severity}] [{issue.category}] {issue.phase}/{issue.step}: {issue.description}")

        # 文件清单
        log(f"\n输出目录文件清单 ({BASE_DIR}):")
        if BASE_DIR.exists():
            for f in sorted(BASE_DIR.iterdir()):
                if f.is_file():
                    log(f"  {f.name} ({f.stat().st_size} bytes)")

        log(f"\n日志: {LOG_FILE}")
        log("=" * 60)

        # 退出码
        all_pass = p1 and p2 and p3
        sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    test = TentOSE2ETest()
    asyncio.run(test.run_all())
