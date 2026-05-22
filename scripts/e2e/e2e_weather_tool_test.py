#!/usr/bin/env python3
"""
Tent OS 端到端自主任务测试 - 开发天气预报工具

原则：
1. 完整执行用户设计的三个阶段（商业模式 -> PRD -> 代码）
2. 记录所有问题：延迟、逻辑错误、工具失败、文件缺失、响应质量
3. 不简化、不跳过，测试不过就记录问题
4. 测试完成后统一分析

输出：/tmp/tent_os_e2e_test.log（详细记录）
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

WS_URL = "ws://localhost:8002/ws"
BASE_DIR = Path.home() / "Desktop" / "weather_tool"
LOG_FILE = Path("/tmp/tent_os_e2e_test.log")
TEST_TIMEOUT = 120  # 每个阶段最长等待时间

# ========== 问题记录器 ==========

@dataclass
class IssueRecord:
    phase: str           # 哪个阶段
    step: str            # 哪个步骤
    severity: str        # critical / high / medium / low / info
    category: str        # latency / logic / tool / file / quality / crash
    description: str     # 问题描述
    evidence: str = ""   # 证据（日志/截图/响应内容）
    expected: str = ""   # 预期行为
    actual: str = ""     # 实际行为

issues: List[IssueRecord] = []

@dataclass
class PhaseResult:
    phase: str
    start_time: float
    end_time: float = 0
    latency_ms: float = 0
    response_length: int = 0
    tools_called: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_expected: List[str] = field(default_factory=list)
    completed: bool = False
    raw_response: str = ""

phase_results: List[PhaseResult] = []

# ========== 日志 ==========

def log(msg: str):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def record_issue(phase: str, step: str, severity: str, category: str,
                 description: str, evidence: str = "", expected: str = "", actual: str = ""):
    issue = IssueRecord(phase, step, severity, category, description, evidence, expected, actual)
    issues.append(issue)
    log(f"[ISSUE] [{severity}] [{category}] {phase}/{step}: {description}")
    if evidence:
        log(f"         证据: {evidence[:200]}")
    if expected and actual:
        log(f"         预期: {expected[:100]}")
        log(f"         实际: {actual[:100]}")

# ========== 核心测试引擎 ==========

class TentOSE2ETest:
    def __init__(self):
        self.ws = None
        self.session_id = f"e2e_weather_{uuid.uuid4().hex[:8]}"
        self.current_phase = "init"
        
    async def connect(self):
        log("=" * 60)
        log("Tent OS 端到端自主任务测试启动")
        log(f"Session ID: {self.session_id}")
        log(f"WebSocket: {WS_URL}")
        log(f"预期输出目录: {BASE_DIR}")
        log("=" * 60)
        
        try:
            self.ws = await websockets.connect(WS_URL, proxy=None)
            # 跳过初始健康消息
            try:
                status = await asyncio.wait_for(self.ws.recv(), timeout=3)
                data = json.loads(status)
                log(f"系统初始状态: {data.get('type', 'unknown')}")
            except:
                log("未收到初始状态消息")
        except Exception as e:
            log(f"ERROR WebSocket 连接失败: {e}")
            sys.exit(1)
    
    async def send_message(self, content: str, phase: str, step: str) -> tuple:
        """发送消息，等待完整响应，记录所有指标
        
        返回: (completed: bool, response: str, latency_ms: float, tools: list)
        """
        self.current_phase = phase
        start = time.time()
        
        msg = {
            "type": "chat.message",
            "payload": {
                "session_id": self.session_id,
                "content": content,
                "user_id": "frank"
            }
        }
        
        log(f"\n[->] [{phase}] 发送: {content[:80]}...")
        await self.ws.send(json.dumps(msg))
        
        chunks = []
        tools_seen = []
        done = False
        error = ""
        
        while not done and (time.time() - start) < TEST_TIMEOUT:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                data = json.loads(raw)
                msg_type = data.get("type", "")
                payload = data.get("payload", {})
                
                # 过滤其他 session 的消息
                sid = payload.get("session_id", "")
                if sid and sid != self.session_id:
                    continue
                
                if msg_type == "chat.stream_chunk":
                    text = payload.get("chunk", "")
                    chunks.append(text)
                elif msg_type == "chat.tool_progress":
                    info = payload.get("info", "")
                    tools_seen.append(info)
                    log(f"    [TOOL] {info}")
                elif msg_type == "chat.completed":
                    done = True
                elif msg_type == "chat.error":
                    done = True
                    error = payload.get("error", "unknown error")
                    record_issue(phase, step, "high", "logic",
                                 "收到 chat.error", evidence=error)
                elif msg_type == "system.health":
                    pass  # 忽略健康消息
                else:
                    # 记录未知消息类型
                    log(f"    [UNKNOWN_MSG] type={msg_type} payload={str(payload)[:100]}")
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                record_issue(phase, step, "critical", "crash",
                             f"WebSocket 接收异常: {e}")
                break
        
        latency = (time.time() - start) * 1000
        full_response = "".join(chunks)
        
        log(f"[<-] [{phase}] 完成={done} | 延迟={latency:.0f}ms | 长度={len(full_response)} | 工具={len(tools_seen)}")
        
        if not done:
            record_issue(phase, step, "high", "latency",
                         f"响应超时（>{TEST_TIMEOUT}s），未完成",
                         evidence=f"已收长度={len(full_response)}",
                         expected=f"{TEST_TIMEOUT}s内完成",
                         actual=f"未完成，延迟={latency:.0f}ms")
        
        if latency > 30000:
            record_issue(phase, step, "medium", "latency",
                         f"响应过慢（>{latency/1000:.0f}s）",
                         evidence=f"实际延迟={latency:.0f}ms",
                         expected="<30s",
                         actual=f"{latency/1000:.0f}s")
        
        return done, full_response, latency, tools_seen
    
    def check_files(self, expected_files: List[str], phase: str) -> List[str]:
        """检查预期文件是否存在，记录缺失"""
        found = []
        for rel_path in expected_files:
            full_path = BASE_DIR / rel_path
            if full_path.exists():
                found.append(rel_path)
                size = full_path.stat().st_size
                log(f"    [FILE_OK] {rel_path} ({size} bytes)")
            else:
                record_issue(phase, "file_check", "high", "file",
                             f"预期文件缺失: {rel_path}",
                             expected=f"存在: {BASE_DIR / rel_path}",
                             actual="不存在")
        return found
    
    def check_file_content(self, rel_path: str, phase: str,
                           min_length: int = 100, expected_keywords: List[str] = None):
        """检查文件内容质量"""
        full_path = BASE_DIR / rel_path
        if not full_path.exists():
            return
        
        content = full_path.read_text(encoding="utf-8")
        
        if len(content) < min_length:
            record_issue(phase, "file_quality", "medium", "quality",
                         f"{rel_path} 内容过短（{len(content)}字符）",
                         expected=f">={min_length}字符",
                         actual=f"{len(content)}字符")
        
        if expected_keywords:
            missing = [kw for kw in expected_keywords if kw.lower() not in content.lower()]
            if missing:
                record_issue(phase, "file_quality", "medium", "quality",
                             f"{rel_path} 缺少关键内容: {missing}")
    
    # ========== 阶段1：商业模式讨论 ==========
    
    async def phase1_business_model(self):
        log("\n" + "=" * 60)
        log("阶段1：商业模式讨论")
        log("=" * 60)
        
        result = PhaseResult("phase1_business", time.time())
        result.files_expected = ["business_model.md"]
        
        # Round 1: 发送初始请求
        prompt = (
            "帮我开发一个极简版的天气预报查询工具。"
            "要求：在桌面新建一个文件夹叫'weather_tool'，所有项目文件都放在里面。"
            "你先和我讨论清楚商业模式，然后再写PRD，最后再写代码。"
            "每完成一个阶段都要停下来让我review。"
        )
        
        done, resp, lat, tools = await self.send_message(prompt, "phase1", "round1_initial")
        result.latency_ms = lat
        result.response_length = len(resp)
        result.tools_called = tools
        result.raw_response = resp
        
        # 检查：系统是否主动提问？
        has_questions = "?" in resp or "？" in resp or "确认" in resp or "问题" in resp
        if not has_questions:
            record_issue("phase1", "round1", "high", "quality",
                         "系统未主动提问或确认需求",
                         evidence=resp[:300],
                         expected="AI主动提问（目标用户、差异化、收入模式等）",
                         actual="未检测到主动提问")
        
        # 检查：系统是否在讨论商业模式？
        business_keywords = ["商业模式", "用户", "赚钱", "收入", "差异化", "竞品", "价值"]
        has_business = any(kw in resp for kw in business_keywords)
        if not has_business:
            record_issue("phase1", "round1", "high", "quality",
                         "系统未讨论商业模式",
                         evidence=resp[:300],
                         expected="讨论商业模式要素",
                         actual="未涉及商业模式")
        
        # Round 2: 模拟用户回复，继续讨论
        user_reply = (
            "目标用户是普通消费者，特别是需要简单快速查天气的人。"
            "差异化是极简、无广告、命令行操作。"
            "收入模式先免费，后期考虑付费API。"
        )
        
        done, resp, lat2, tools2 = await self.send_message(user_reply, "phase1", "round2_discussion")
        result.latency_ms += lat2
        result.response_length += len(resp)
        result.tools_called.extend(tools2)
        
        # 检查：系统是否做了总结？
        has_summary = "总结" in resp or "梳理" in resp or "提炼" in resp or "核心" in resp
        if not has_summary:
            record_issue("phase1", "round2", "medium", "quality",
                         "系统未对用户回答做总结提炼",
                         evidence=resp[:300])
        
        # Round 3: 模拟用户说继续，进入文件产出阶段
        user_continue = "可以，我认可这个方向。请把商业模式整理成文档保存到 weather_tool 文件夹。"
        
        done, resp, lat3, tools3 = await self.send_message(user_continue, "phase1", "round3_output")
        result.latency_ms += lat3
        result.response_length += len(resp)
        result.tools_called.extend(tools3)
        
        # 等待文件系统反应（工具调用可能有延迟）
        await asyncio.sleep(3)
        
        # 检查文件产出
        result.files_created = self.check_files(result.files_expected, "phase1")
        
        if "business_model.md" in result.files_created:
            self.check_file_content("business_model.md", "phase1",
                                    min_length=200,
                                    expected_keywords=["用户", "价值", "收入", "竞品"])
        
        result.end_time = time.time()
        result.completed = done and len(result.files_created) > 0
        phase_results.append(result)
        
        log(f"\n[阶段1总结] 完成={result.completed} | 文件={result.files_created} | 总延迟={result.latency_ms:.0f}ms")
        return result.completed
    
    # ========== 阶段2：PRD撰写 ==========
    
    async def phase2_prd(self):
        log("\n" + "=" * 60)
        log("阶段2：PRD撰写")
        log("=" * 60)
        
        result = PhaseResult("phase2_prd", time.time())
        result.files_expected = ["prd.md"]
        
        prompt = (
            "商业模式已经确认。现在请基于我们讨论的商业模式，"
            "撰写一份PRD文档，保存到 weather_tool/prd.md。"
            "PRD必须包含：功能列表（带优先级）、明确的不做范围、技术选型建议、测试计划。"
            "写完后告诉我PRD已完成，让我review。"
        )
        
        done, resp, lat, tools = await self.send_message(prompt, "phase2", "prd_draft")
        result.latency_ms = lat
        result.response_length = len(resp)
        result.tools_called = tools
        result.raw_response = resp
        
        # 检查：PRD 是否有做什么和不做什么？
        has_scope_in = "做" in resp and "功能" in resp
        has_scope_out = "不做" in resp or "不做什么" in resp or "范围外" in resp or "out of scope" in resp.lower()
        
        if not has_scope_in:
            record_issue("phase2", "prd_draft", "medium", "quality",
                         "PRD响应中未明确功能范围（做什么）",
                         evidence=resp[:300])
        if not has_scope_out:
            record_issue("phase2", "prd_draft", "medium", "quality",
                         "PRD响应中未明确边界（不做什么）",
                         evidence=resp[:300])
        
        # 等待文件系统反应
        await asyncio.sleep(3)
        
        result.files_created = self.check_files(result.files_expected, "phase2")
        
        if "prd.md" in result.files_created:
            self.check_file_content("prd.md", "phase2",
                                    min_length=300,
                                    expected_keywords=["功能", "优先级", "测试", "技术"])
        
        result.end_time = time.time()
        result.completed = done and len(result.files_created) > 0
        phase_results.append(result)
        
        log(f"\n[阶段2总结] 完成={result.completed} | 文件={result.files_created} | 总延迟={result.latency_ms:.0f}ms")
        return result.completed
    
    # ========== 阶段3：代码开发与验证 ==========
    
    async def phase3_code(self):
        log("\n" + "=" * 60)
        log("阶段3：代码开发与验证")
        log("=" * 60)
        
        result = PhaseResult("phase3_code", time.time())
        result.files_expected = ["weather.py", "readme.md"]
        
        prompt = (
            "PRD已确认。现在请按照PRD开发代码。"
            "要求：1) 创建 weather.py 主程序；"
            "2) 支持命令行输入城市查询天气；"
            "3) 包含错误处理；4) 创建 readme.md 说明使用方法。"
            "开发完成后，在本地运行测试：查询北京、查询不存在的城市、查看历史记录。"
            "把测试结果告诉我。"
        )
        
        done, resp, lat, tools = await self.send_message(prompt, "phase3", "code_dev")
        result.latency_ms = lat
        result.response_length = len(resp)
        result.tools_called = tools
        result.raw_response = resp
        
        # 检查：是否有代码文件产出？
        await asyncio.sleep(5)  # 代码生成可能较长
        result.files_created = self.check_files(result.files_expected, "phase3")
        
        # 检查：是否运行了测试？
        has_test = any(kw in resp for kw in ["测试", "运行", "结果", "通过", "北京", "查询"])
        if not has_test:
            record_issue("phase3", "code_dev", "high", "quality",
                         "系统未报告测试结果",
                         evidence=resp[:300],
                         expected="报告三个测试场景的运行结果",
                         actual="未检测到测试结果描述")
        
        # 验证代码可运行性（如果文件存在）
        weather_py = BASE_DIR / "weather.py"
        if weather_py.exists():
            # 尝试语法检查
            try:
                import py_compile
                py_compile.compile(str(weather_py), doraise=True)
                log("    [CODE_OK] weather.py 语法检查通过")
            except Exception as e:
                record_issue("phase3", "code_quality", "high", "logic",
                             f"weather.py 语法错误: {e}",
                             evidence=str(e))
            
            # 尝试运行
            try:
                import subprocess
                result_run = subprocess.run(
                    [sys.executable, str(weather_py), "--help"],
                    capture_output=True, text=True, timeout=10
                )
                if result_run.returncode == 0 or "usage" in result_run.stdout.lower():
                    log("    [CODE_OK] weather.py 可运行")
                else:
                    record_issue("phase3", "code_run", "medium", "logic",
                                 f"weather.py 运行异常: rc={result_run.returncode}",
                                 evidence=result_run.stderr[:200])
            except Exception as e:
                record_issue("phase3", "code_run", "medium", "logic",
                             f"weather.py 运行失败: {e}")
        
        result.end_time = time.time()
        result.completed = done and len(result.files_created) >= 2
        phase_results.append(result)
        
        log(f"\n[阶段3总结] 完成={result.completed} | 文件={result.files_created} | 总延迟={result.latency_ms:.0f}ms")
        return result.completed
    
    async def run_all(self):
        # 清理之前的测试目录
        if BASE_DIR.exists():
            import shutil
            shutil.rmtree(BASE_DIR)
            log(f"清理旧目录: {BASE_DIR}")
        
        LOG_FILE.write_text("", encoding="utf-8")  # 清空日志
        
        await self.connect()
        
        # 执行三个阶段
        p1_ok = await self.phase1_business_model()
        p2_ok = await self.phase2_prd()
        p3_ok = await self.phase3_code()
        
        await self.ws.close()
        
        # 最终报告
        await self.final_report(p1_ok, p2_ok, p3_ok)
    
    async def final_report(self, p1_ok, p2_ok, p3_ok):
        log("\n" + "=" * 60)
        log("测试结束 - 最终报告")
        log("=" * 60)
        
        total_issues = len(issues)
        critical = sum(1 for i in issues if i.severity == "critical")
        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")
        
        log(f"\n总体结果:")
        log(f"  阶段1(商业模式): {'PASS' if p1_ok else 'FAIL'}")
        log(f"  阶段2(PRD): {'PASS' if p2_ok else 'FAIL'}")
        log(f"  阶段3(代码): {'PASS' if p3_ok else 'FAIL'}")
        log(f"\n问题统计: 总计={total_issues} | Critical={critical} | High={high} | Medium={medium} | Low={low}")
        
        log(f"\n详细问题列表:")
        for idx, issue in enumerate(issues, 1):
            log(f"  {idx}. [{issue.severity}] [{issue.category}] {issue.phase}/{issue.step}: {issue.description}")
        
        log(f"\n各阶段指标:")
        for pr in phase_results:
            log(f"  {pr.phase}: 延迟={pr.latency_ms:.0f}ms | 响应长度={pr.response_length} | 工具调用={len(pr.tools_called)} | 文件={pr.files_created}")
        
        log(f"\n日志文件: {LOG_FILE}")
        log("=" * 60)


if __name__ == "__main__":
    test = TentOSE2ETest()
    asyncio.run(test.run_all())
