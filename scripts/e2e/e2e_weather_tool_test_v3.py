#!/usr/bin/env python3
"""
Tent OS 端到端自主任务测试 v3

改进点：
1. idle超时从60s→180s（给Plan-Evaluate降级+Tool Loop足够时间）
2. recv超时从10s→30s（减少空轮询开销）
3. 真正等待chat.completed，不基于idle提前break
4. 保留自动approval（兼容auto_approve=false场景）
5. 阶段完成后等5秒再检查文件（给文件系统反应时间）
6. 只记录客观指标，不做主观质量判定

设计哲学：测试脚本是"观察员"不是"裁判员"。它记录发生了什么，
由人根据日志判断系统行为是否合理。
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
from typing import List, Dict
import websockets
import httpx

WS_URL = "ws://localhost:8002/ws"
API_BASE = "http://localhost:8002"
BASE_DIR = Path.home() / "Desktop" / "weather_tool"
LOG_FILE = Path("/tmp/tent_os_e2e_test_v3.log")

# 超时配置
TOTAL_TIMEOUT = 300       # 每阶段最大5分钟（硬限制）
RECV_TIMEOUT = 30         # 每次recv等待30秒
IDLE_TIMEOUT = 180        # 180秒无消息才认为卡住（3分钟）
FILE_SETTLE_DELAY = 5     # 阶段完成后等5秒检查文件


@dataclass
class Observation:
    phase: str
    step: str
    timestamp: float
    event: str          # stream_chunk / tool_progress / approval / completed / error / idle_break / timeout
    details: str = ""   # 具体内容
    latency_ms: float = 0


observations: List[Observation] = []


def log(msg: str):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def observe(phase: str, step: str, event: str, details: str = "", latency_ms: float = 0):
    obs = Observation(phase, step, time.time(), event, details, latency_ms)
    observations.append(obs)
    log(f"[OBS] [{phase}/{step}] {event}: {details[:200]}")


class TentOSE2ETest:
    def __init__(self):
        self.ws = None
        self.session_id = f"e2e_v3_{uuid.uuid4().hex[:8]}"
        self.httpx_client = httpx.AsyncClient(timeout=10.0)

    async def connect(self):
        log("=" * 70)
        log("Tent OS E2E 测试 v3 启动")
        log(f"Session: {self.session_id}")
        log(f"Output: {BASE_DIR}")
        log(f"Timeouts: total={TOTAL_TIMEOUT}s recv={RECV_TIMEOUT}s idle={IDLE_TIMEOUT}s")
        log("=" * 70)

        self.ws = await websockets.connect(WS_URL, proxy=None)
        try:
            status = await asyncio.wait_for(self.ws.recv(), timeout=5)
            data = json.loads(status)
            log(f"系统状态: {data.get('type', 'unknown')}")
        except asyncio.TimeoutError:
            log("未收到初始状态（可能已发过）")

    async def auto_approve(self, phase: str, step: str):
        """通过HTTP API自动批准pending的approval请求"""
        try:
            resp = await self.httpx_client.post(
                f"{API_BASE}/api/v1/approvals/{self.session_id}",
                json={"approved": True},
            )
            if resp.status_code == 200:
                observe(phase, step, "approval_auto", "自动批准成功")
                return True
            else:
                observe(phase, step, "approval_auto_fail", f"{resp.status_code}: {resp.text[:100]}")
                return False
        except Exception as e:
            observe(phase, step, "approval_auto_fail", str(e))
            return False

    async def send_and_wait(self, content: str, phase: str, step: str) -> dict:
        """
        发送消息，等待chat.completed或总超时。
        返回完整的事件记录。
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
        reasoning_chunks = []
        tools_seen = []
        done = False
        error_msg = ""
        last_activity = time.time()

        while not done:
            elapsed = time.time() - start
            idle = time.time() - last_activity

            if elapsed > TOTAL_TIMEOUT:
                observe(phase, step, "timeout", f"总超时 {TOTAL_TIMEOUT}s", (time.time()-start)*1000)
                break

            if idle > IDLE_TIMEOUT:
                observe(phase, step, "idle_break", f"{IDLE_TIMEOUT}s无消息", (time.time()-start)*1000)
                break

            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=RECV_TIMEOUT)
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
                elif msg_type == "chat.stream_reasoning":
                    text = payload.get("chunk", "")
                    reasoning_chunks.append(text)
                elif msg_type == "chat.tool_progress":
                    info = payload.get("info", "")
                    tools_seen.append(info)
                    log(f"    [TOOL] {info}")
                elif msg_type == "approval.request":
                    log(f"    [APPROVAL] 收到审批请求")
                    await self.auto_approve(phase, step)
                elif msg_type == "chat.completed":
                    done = True
                    observe(phase, step, "completed", f"stream={len(chunks)} reasoning={len(reasoning_chunks)} tools={len(tools_seen)}")
                elif msg_type == "chat.error":
                    done = True
                    error_msg = payload.get("error", "unknown")
                    observe(phase, step, "error", error_msg)
                elif msg_type == "system.health":
                    pass
                elif msg_type == "chat.message_accepted":
                    log(f"    [ACCEPTED] 消息已被接受")
                else:
                    log(f"    [MSG] type={msg_type}")

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                observe(phase, step, "websocket_error", str(e))
                break

        latency = (time.time() - start) * 1000
        full_response = "".join(chunks)
        full_reasoning = "".join(reasoning_chunks)

        log(f"[<-] [{phase}/{step}] done={done} latency={latency:.0f}ms "
            f"stream={len(full_response)} reasoning={len(full_reasoning)} tools={len(tools_seen)}")

        return {
            "done": done,
            "response": full_response,
            "reasoning": full_reasoning,
            "latency_ms": latency,
            "tools": tools_seen,
            "error": error_msg,
        }

    def check_file(self, rel_path: str) -> tuple:
        """检查文件，返回(是否存在, 大小)"""
        full = BASE_DIR / rel_path
        if full.exists():
            size = full.stat().st_size
            log(f"    [FILE] {rel_path}: {size} bytes")
            return True, size
        else:
            log(f"    [FILE_MISSING] {rel_path}")
            return False, 0

    def read_file(self, rel_path: str) -> str:
        full = BASE_DIR / rel_path
        if full.exists():
            return full.read_text(encoding="utf-8")
        return ""

    # ==================== 三个阶段 ====================

    async def phase1(self) -> dict:
        log("\n" + "=" * 70)
        log("阶段1：商业模式")
        log("=" * 70)

        prompt = (
            "请在 ~/Desktop/weather_tool 目录下完成以下任务（严格按顺序）：\n\n"
            "【阶段1】\n"
            "1. 分析极简天气预报工具的商业模式：目标用户、痛点、差异化、收入模式\n"
            "2. 将分析结果保存为 business_model.md\n"
            "3. 完成后告诉我文件已保存\n\n"
            "要求：文件不少于500字"
        )

        result = await self.send_and_wait(prompt, "phase1", "business_model")
        await asyncio.sleep(FILE_SETTLE_DELAY)
        exists, size = self.check_file("business_model.md")

        if not exists and result["done"]:
            # 可能文件还没落盘，再发一轮确认
            log("    [RETRY] 文件未找到，发送确认")
            r2 = await self.send_and_wait(
                "请确认 business_model.md 已保存到 ~/Desktop/weather_tool/",
                "phase1", "confirm"
            )
            await asyncio.sleep(FILE_SETTLE_DELAY)
            exists, size = self.check_file("business_model.md")

        return {"file": "business_model.md", "exists": exists, "size": size, **result}

    async def phase2(self) -> dict:
        log("\n" + "=" * 70)
        log("阶段2：PRD")
        log("=" * 70)

        prompt = (
            "请在 ~/Desktop/weather_tool 目录下完成以下任务：\n\n"
            "【阶段2】\n"
            "1. 读取 business_model.md\n"
            "2. 基于商业模式撰写PRD，保存为 prd.md\n"
            "3. PRD必须包含：功能列表（P0/P1/P2）、不做范围、技术选型、测试计划\n"
            "4. 完成后告诉我文件已保存\n\n"
            "要求：文件不少于800字"
        )

        result = await self.send_and_wait(prompt, "phase2", "prd")
        await asyncio.sleep(FILE_SETTLE_DELAY)
        exists, size = self.check_file("prd.md")

        if not exists and result["done"]:
            log("    [RETRY] 文件未找到，发送确认")
            r2 = await self.send_and_wait(
                "请确认 prd.md 已保存到 ~/Desktop/weather_tool/",
                "phase2", "confirm"
            )
            await asyncio.sleep(FILE_SETTLE_DELAY)
            exists, size = self.check_file("prd.md")

        return {"file": "prd.md", "exists": exists, "size": size, **result}

    async def phase3(self) -> dict:
        log("\n" + "=" * 70)
        log("阶段3：代码")
        log("=" * 70)

        prompt = (
            "请在 ~/Desktop/weather_tool 目录下完成以下任务：\n\n"
            "【阶段3】\n"
            "1. 读取 prd.md\n"
            "2. 创建 weather.py：命令行天气查询工具\n"
            "   - 支持命令行参数传入城市名\n"
            "   - 使用免费天气API（如 Open-Meteo）\n"
            "   - 包含错误处理\n"
            "   - 支持查询历史记录（本地JSON）\n"
            "3. 创建 readme.md：说明安装和运行方法\n"
            "4. 运行测试：查询 Beijing、查询不存在的城市、查看历史记录\n"
            "5. 告诉我所有文件已保存，并汇报测试结果"
        )

        result = await self.send_and_wait(prompt, "phase3", "code")
        await asyncio.sleep(FILE_SETTLE_DELAY + 3)  # 代码生成可能更慢

        w_exists, w_size = self.check_file("weather.py")
        r_exists, r_size = self.check_file("readme.md")

        # 语法检查
        syntax_ok = False
        if w_exists:
            try:
                import py_compile
                py_compile.compile(str(BASE_DIR / "weather.py"), doraise=True)
                log("    [SYNTAX_OK] weather.py")
                syntax_ok = True
            except Exception as e:
                log(f"    [SYNTAX_FAIL] {e}")

        return {
            "weather_exists": w_exists, "weather_size": w_size,
            "readme_exists": r_exists, "readme_size": r_size,
            "syntax_ok": syntax_ok, **result
        }

    # ==================== 主流程 ====================

    async def run_all(self):
        if BASE_DIR.exists():
            import shutil
            shutil.rmtree(BASE_DIR)
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text("", encoding="utf-8")

        await self.connect()
        overall_start = time.time()

        p1 = await self.phase1()
        p2 = await self.phase2()
        p3 = await self.phase3()

        overall_elapsed = time.time() - overall_start
        await self.ws.close()
        await self.httpx_client.aclose()

        await self.final_report(p1, p2, p3, overall_elapsed)

    async def final_report(self, p1, p2, p3, total_s):
        log("\n" + "=" * 70)
        log("测试结束 - 最终报告")
        log("=" * 70)

        log(f"\n总体耗时: {total_s:.0f}s ({total_s/60:.1f}min)")

        log(f"\n阶段1 (business_model.md):")
        log(f"  文件: {'EXISTS' if p1['exists'] else 'MISSING'} ({p1.get('size', 0)} bytes)")
        log(f"  完成: {p1['done']} | 延迟: {p1['latency_ms']:.0f}ms | 工具: {len(p1['tools'])}")

        log(f"\n阶段2 (prd.md):")
        log(f"  文件: {'EXISTS' if p2['exists'] else 'MISSING'} ({p2.get('size', 0)} bytes)")
        log(f"  完成: {p2['done']} | 延迟: {p2['latency_ms']:.0f}ms | 工具: {len(p2['tools'])}")

        log(f"\n阶段3 (weather.py + readme.md):")
        log(f"  weather.py: {'EXISTS' if p3['weather_exists'] else 'MISSING'} ({p3.get('weather_size', 0)} bytes)")
        log(f"  readme.md: {'EXISTS' if p3['readme_exists'] else 'MISSING'} ({p3.get('readme_size', 0)} bytes)")
        log(f"  语法检查: {'PASS' if p3.get('syntax_ok') else 'FAIL/N/A'}")
        log(f"  完成: {p3['done']} | 延迟: {p3['latency_ms']:.0f}ms | 工具: {len(p3['tools'])}")

        log(f"\n事件记录 ({len(observations)} 条):")
        for obs in observations:
            ts = datetime.fromtimestamp(obs.timestamp).strftime("%H:%M:%S")
            log(f"  {ts} [{obs.phase}/{obs.step}] {obs.event}: {obs.details[:80]}")

        # 文件清单
        log(f"\n输出目录文件清单:")
        if BASE_DIR.exists():
            for f in sorted(BASE_DIR.iterdir()):
                if f.is_file():
                    log(f"  {f.name} ({f.stat().st_size} bytes)")

        log(f"\n日志: {LOG_FILE}")
        log("=" * 70)

        all_pass = p1["exists"] and p2["exists"] and p3["weather_exists"] and p3["readme_exists"]
        sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    test = TentOSE2ETest()
    asyncio.run(test.run_all())
