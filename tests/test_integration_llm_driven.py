"""Integration Test Suite —— 真实 LLM 驱动端到端测试

验证 Tent OS 核心链路在真实 LLM（Kimi K2.6）驱动下的行为：
1. WebSocket 对话入口 → _on_memory_injected
2. Tool Loop（ReAct 循环）
3. LayeredSecurity 各层触发
4. Memory 召回与注入
5. Speculative Execution 推测执行

设计原则：
- 使用真实 LLM，不做 mock（除 bus/state_store 外）
- 断言策略：验证链路完整性 + 响应合理性，不硬匹配 LLM 输出内容
- 每个测试独立 session，互不干扰
"""

import asyncio
import json
import time

import pytest


# ========== Test Helpers ==========

async def _setup_session(worker, session_id: str, task: str, user_id: str = "test_user"):
    """快速创建 session 并追加用户消息"""
    await worker.state_store.create(
        session_id=session_id,
        task=task,
        user_id=user_id,
        title=task[:30] + "..." if len(task) > 30 else task,
    )
    await worker.state_store.append_message(session_id, "user", task)


async def _run_conversation(worker, session_id: str, task: str, injected_context: str = ""):
    """执行一次完整对话调用，返回后等待背景任务完成"""
    await _setup_session(worker, session_id, task)
    data = {"injected_context": injected_context, "type": "memory_injected"}
    await worker._on_memory_injected(session_id, data)
    # _simulate_stream 内部是同步 await publish 的，但 chat_stream 的 on_chunk 用 create_task
    # 额外等待 1.5s 确保所有 background publish 完成
    await asyncio.sleep(1.5)


def _find_completed_message(bus, session_id: str):
    """从 bus 消息中找到 chat.completed 消息"""
    for msg in bus.get_messages(f"governance.response.{session_id}"):
        payload = msg["payload"]
        if isinstance(payload, dict) and payload.get("type") == "chat.completed":
            return payload
    return None


def _find_stream_chunks(bus, session_id: str):
    """获取所有流式输出 chunk"""
    chunks = []
    for msg in bus.get_messages(f"governance.stream.{session_id}"):
        payload = msg["payload"]
        if isinstance(payload, dict) and payload.get("type") == "content":
            chunks.append(payload.get("chunk", ""))
    return chunks


# ========== Test Cases ==========

@pytest.mark.timeout(120)
@pytest.mark.integration
class TestLLMDrivenChat:
    """简单对话链路测试"""

    @pytest.mark.asyncio
    async def test_simple_chat_greeting(self, real_governance_worker):
        """测试简单问候 —— 流式输出链路完整"""
        worker = real_governance_worker
        session_id = f"test_chat_{int(time.time() * 1000)}"
        task = "你好，请用一句话介绍自己"

        await _run_conversation(worker, session_id, task)

        # 验证 1: bus 中有 chat.completed 消息
        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None, "未收到 chat.completed 消息"
        assert completed.get("content"), "响应内容为空"

        # 验证 2: 有流式 chunk 输出
        chunks = _find_stream_chunks(worker.bus, session_id)
        assert len(chunks) > 0, "没有流式 chunk 输出"

        # 验证 3: state_store 中保存了 assistant 消息
        messages = await worker.state_store.get_messages(session_id)
        assert len(messages) >= 2, "消息历史中应包含 user + assistant"
        assert messages[-1]["role"] == "assistant", "最后一条消息应为 assistant"
        assert messages[-1]["content"], "assistant 消息内容为空"

    @pytest.mark.asyncio
    async def test_chat_with_context_persistence(self, real_governance_worker):
        """测试多轮对话上下文保持"""
        worker = real_governance_worker
        session_id = f"test_ctx_{int(time.time() * 1000)}"

        # 第一轮
        await _run_conversation(worker, session_id, "我的名字是 Frank")
        completed1 = _find_completed_message(worker.bus, session_id)
        assert completed1 is not None

        # 第二轮（依赖第一轮的上下文）
        # FIX: 不能调用 _setup_session（会覆盖 session），直接追加消息
        worker.bus.published.clear()
        await worker.state_store.update(session_id, {"task": "请问我刚才说了什么？"})
        await worker.state_store.append_message(session_id, "user", "请问我刚才说了什么？")
        await worker._on_memory_injected(session_id, {"injected_context": ""})
        await asyncio.sleep(1.5)

        completed2 = _find_completed_message(worker.bus, session_id)
        assert completed2 is not None
        response2 = completed2.get("content", "").lower()
        # LLM 应该能回忆起用户名字
        assert "frank" in response2 or "名字" in response2 or "刚才" in response2, \
            f"上下文未保持，响应: {response2[:200]}"


@pytest.mark.timeout(180)
@pytest.mark.integration
class TestLLMDrivenToolLoop:
    """Tool Loop 链路测试 —— 真实 LLM 判断是否需要工具并执行"""

    @pytest.mark.asyncio
    async def test_tool_loop_directory_list(self, real_governance_worker):
        """测试目录列表工具调用 —— LLM 应调用 directory_list"""
        worker = real_governance_worker
        session_id = f"test_dir_{int(time.time() * 1000)}"
        task = "请列出当前目录下有哪些文件"

        await _run_conversation(worker, session_id, task)

        # 验证 1: 有 chat.completed
        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None, "未收到 chat.completed"
        response = completed.get("content", "")
        assert response, "响应为空"

        # 验证 2: 响应中应包含目录相关信息（工具执行结果）
        # 由于 LLM 可能总结输出，我们检查是否包含一些常见目录名或描述
        response_lower = response.lower()
        has_dir_info = any(kw in response_lower for kw in [
            "目录", "文件夹", "file", "src", "test", "config", "docs",
            "api", "memory", "governance", "scheduler", "tools", "skills"
        ])
        assert has_dir_info, f"响应中未包含目录信息: {response[:300]}"

        # 验证 3: bus 中应有 stream chunk（工具执行进度或最终结果）
        chunks = _find_stream_chunks(worker.bus, session_id)
        assert len(chunks) > 0, "没有流式输出"

    @pytest.mark.asyncio
    async def test_tool_loop_file_read(self, real_governance_worker):
        """测试文件读取工具调用 —— LLM 应调用 file_read 读取 README"""
        worker = real_governance_worker
        session_id = f"test_file_{int(time.time() * 1000)}"
        task = "请读取 README.md 的内容，并告诉我里面写了什么"

        await _run_conversation(worker, session_id, task)

        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None, "未收到 chat.completed"
        response = completed.get("content", "")
        assert response, "响应为空"

        # 响应中应提到 readme、markdown、或内容相关词汇
        response_lower = response.lower()
        has_content = any(kw in response_lower for kw in [
            "readme", "markdown", "tent", "os", "文件", "内容", "行"
        ])
        assert has_content, f"响应中未包含文件内容信息: {response[:300]}"


@pytest.mark.timeout(120)
@pytest.mark.integration
class TestSpeculativeExecution:
    """推测执行链路测试"""

    @pytest.mark.asyncio
    async def test_speculative_directory_list_hit(self, real_governance_worker):
        """测试推测执行命中 —— "查看目录"意图应预执行 directory_list"""
        worker = real_governance_worker
        session_id = f"test_spec_{int(time.time() * 1000)}"
        task = "查看当前目录下有什么文件"

        await _run_conversation(worker, session_id, task)

        # 推测执行命中后，日志中应有 [GOV] 推测执行命中
        # 由于我们不直接断言日志，验证响应质量和速度即可
        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None
        response = completed.get("content", "")
        assert response

        # 响应应包含目录相关信息
        response_lower = response.lower()
        has_info = any(kw in response_lower for kw in [
            "目录", "文件", "folder", "file", "tent_os"
        ])
        assert has_info, f"推测执行未命中或结果未注入: {response[:300]}"


@pytest.mark.timeout(120)
@pytest.mark.integration
class TestLayeredSecurity:
    """LayeredSecurity 链路测试"""

    @pytest.mark.asyncio
    async def test_l3_strict_mode_tool_filtering(self, real_governance_worker):
        """测试 L3 strict 模式 —— 危险工具从工具池中被过滤（确定性验证）"""
        worker = real_governance_worker
        session_id = f"test_sec_{int(time.time() * 1000)}"

        if not hasattr(worker, 'mode_manager') or not worker.mode_manager:
            pytest.skip("PermissionModeManager 未初始化，跳过安全测试")

        # 1. 默认模式下获取全部工具
        default_tools = await worker._get_available_tools(session_id)
        default_names = {t.get("function", {}).get("name", "") for t in default_tools}
        # 默认应包含写入/执行类工具
        dangerous_tools = {"file_write", "shell", "render_ppt", "render_excel"}
        has_dangerous = bool(dangerous_tools & default_names)
        assert has_dangerous, f"默认模式下应包含危险工具，当前只有: {default_names}"

        # 2. 设置 strict 模式
        worker.mode_manager.set_mode(
            session_id, "strict",
            reason="测试 L3 strict 模式",
            task_hint="测试",
        )

        # 3. strict 模式下获取工具并验证过滤
        strict_tools = await worker._get_available_tools(session_id)
        strict_names = {t.get("function", {}).get("name", "") for t in strict_tools}

        readonly_tools = {"file_read", "directory_list", "web_search", "web_fetch", "memory_search", "memory_get"}
        for name in strict_names:
            assert name in readonly_tools, f"strict 模式下不应包含工具: {name}"

        # 4. 验证 strict 模式下 LLM 仍能正常对话（用简单任务避免 Tool Loop 多次迭代）
        await _run_conversation(worker, session_id, "你好")

        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None, "strict 模式下应能正常完成对话"
        assert completed.get("content"), "响应不应为空"

    @pytest.mark.asyncio
    async def test_l3_strict_mode_rejects_write_intent(self, real_governance_worker):
        """测试 strict 模式下写入意图被拒绝（端到端）"""
        worker = real_governance_worker
        session_id = f"test_sec2_{int(time.time() * 1000)}"

        if not hasattr(worker, 'mode_manager') or not worker.mode_manager:
            pytest.skip("PermissionModeManager 未初始化，跳过安全测试")

        worker.mode_manager.set_mode(
            session_id, "strict",
            reason="测试写入拒绝",
            task_hint="写入测试",
        )

        # 用简单任务验证对话仍可进行，不触发长时间 Tool Loop
        await _run_conversation(worker, session_id, "请创建一个文件")

        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None
        response = completed.get("content", "").lower()
        # LLM 在 strict 模式下看不到 file_write，应拒绝或解释无法执行
        is_safe = any(kw in response for kw in [
            "不能", "无法", "没有", "不允许", "权限", "strict", "只读", "readonly",
            "cannot", "can't", "unable", "not allowed", "permission", "read-only"
        ])
        # 如果 LLM 没有明确拒绝，至少不应声称已创建文件
        assert is_safe or "创建" not in response, f"strict 模式下不应执行写入: {response[:300]}"

    @pytest.mark.asyncio
    async def test_auto_classifier_security_assessment(self, real_governance_worker):
        """测试 AutoClassifier 安全评估 —— 危险任务触发安全评估"""
        worker = real_governance_worker
        session_id = f"test_auto_{int(time.time() * 1000)}"

        if not hasattr(worker, 'auto_classifier') or not worker.auto_classifier:
            pytest.skip("AutoClassifier 未初始化，跳过测试")

        # 使用简单问候语避免 Tool Loop，只验证安全评估是否被记录
        task = "你好"
        await _run_conversation(worker, session_id, task)

        # 验证安全评估被缓存到 state
        state = await worker.state_store.load(session_id)
        assessment = state.get("security_assessment", {})
        assert assessment.get("task") == task, "安全评估未缓存到 state"
        assert "safety_level" in assessment, "安全评估应包含 safety_level"

    @pytest.mark.asyncio
    async def test_auto_classifier_detects_dangerous_task(self, real_governance_worker):
        """测试 AutoClassifier 对危险任务的启发式检测"""
        worker = real_governance_worker
        session_id = f"test_auto2_{int(time.time() * 1000)}"

        if not hasattr(worker, 'auto_classifier') or not worker.auto_classifier:
            pytest.skip("AutoClassifier 未初始化，跳过测试")

        # 直接测试启发式评估（零成本，不调用 LLM）
        result = worker.auto_classifier._heuristic_evaluate("rm -rf /")
        assert result is not None, "rm -rf / 应被启发式检测命中"
        assert result.safety_level == "critical", f"应为 critical，实际: {result.safety_level}"
        assert result.suggested_mode == "strict", f"应为 strict，实际: {result.suggested_mode}"
        assert result.confidence > 0.9, f"置信度应 >0.9，实际: {result.confidence}"


@pytest.mark.timeout(120)
@pytest.mark.integration
class TestSessionContextSnapshot:
    """会话上下文快照测试 —— Control UI 数据链路"""

    @pytest.mark.asyncio
    async def test_ui_context_updated_after_chat(self, real_governance_worker):
        """测试对话完成后 ui_context 被正确写入 state_store"""
        worker = real_governance_worker
        session_id = f"test_ui_{int(time.time() * 1000)}"
        task = "你好"

        await _run_conversation(worker, session_id, task)

        state = await worker.state_store.load(session_id)
        ui_context = state.get("ui_context", {})

        assert ui_context, "ui_context 未写入 state_store"
        assert "timestamp" in ui_context, "ui_context 缺少 timestamp"
        assert "available_tools_count" in ui_context, "ui_context 缺少 available_tools_count"
        assert ui_context["available_tools_count"] > 0, "可用工具数不应为 0"

    @pytest.mark.asyncio
    async def test_ui_context_with_tool_call(self, real_governance_worker):
        """测试工具调用后 ui_context 包含正确信息"""
        worker = real_governance_worker
        session_id = f"test_ui2_{int(time.time() * 1000)}"
        task = "列出当前目录"

        await _run_conversation(worker, session_id, task)

        state = await worker.state_store.load(session_id)
        ui_context = state.get("ui_context", {})

        assert ui_context, "ui_context 未写入"
        # 工具调用后，消息数应 >= 2（user + assistant）
        messages = await worker.state_store.get_messages(session_id)
        assert len(messages) >= 2, "应有 user + assistant 消息"


@pytest.mark.timeout(120)
@pytest.mark.integration
class TestDekeywordizationPlanExecutor:
    """PlanExecutor 去关键词化测试 —— 真实 LLM 驱动
    
    核心验证：AutoClassifier.evaluate_complexity() 替代关键词匹配
    """

    @pytest.mark.asyncio
    async def test_complexity_simple_greeting(self, real_governance_worker):
        """简单问候 → 不应被判定为复杂任务"""
        worker = real_governance_worker

        if not hasattr(worker, 'auto_classifier') or not worker.auto_classifier:
            pytest.skip("AutoClassifier 未初始化")

        result = await worker.auto_classifier.evaluate_complexity("你好")
        assert result.is_complex is False, f"问候语不应复杂: {result.reasoning}"
        assert result.confidence > 0.7

    @pytest.mark.asyncio
    async def test_complexity_sequential_task(self, real_governance_worker):
        """含时序依赖的任务 → 应被判定为复杂（启发式路径）"""
        worker = real_governance_worker

        if not hasattr(worker, 'auto_classifier') or not worker.auto_classifier:
            pytest.skip("AutoClassifier 未初始化")

        task = "先读取配置文件，然后修改端口号，最后重启服务"
        result = await worker.auto_classifier.evaluate_complexity(task)
        assert result.is_complex is True, f"时序任务应复杂: {result.reasoning}"
        # 应走启发式路径（零成本）
        assert result.reasoning == "检测到明确的时序依赖（先/再/然后等）"

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_complexity_semantic_no_keywords(self, real_governance_worker):
        """语义复杂但无关键词 → LLM 判定为复杂（去关键词化核心验证）"""
        worker = real_governance_worker

        if not hasattr(worker, 'auto_classifier') or not worker.auto_classifier:
            pytest.skip("AutoClassifier 未初始化")

        # 这个任务不包含"先/再/然后"等关键词，但语义上是多步骤
        task = "帮我整理桌面文件，把图片移到相册文件夹，文档移到工作文件夹"
        result = await worker.auto_classifier.evaluate_complexity(task)
        assert result.is_complex is True, (
            f"语义多步骤任务应被判定为复杂: {result.reasoning}"
        )
        assert result.complexity_score > 0.5

    @pytest.mark.asyncio
    async def test_plan_executor_no_false_positives(self, real_governance_worker):
        """PlanExecutor 不应因关键词误触发（去关键词化验证）"""
        worker = real_governance_worker

        # 这个任务不包含任何 Plan 关键词，但也不是复杂任务
        task = "今天天气怎么样"
        needs_plan = await worker.executor.needs_plan(
            task, [], classifier=worker.auto_classifier
        )
        assert needs_plan is False, "简单查询不应触发 Plan 模式"

    @pytest.mark.asyncio
    async def test_plan_executor_uses_complexity_not_keywords(self, real_governance_worker):
        """PlanExecutor 使用 complexity_score 而非关键词字典"""
        worker = real_governance_worker

        # 这个任务不含"先/再/然后"等关键词，但语义复杂
        # 旧版关键词匹配会返回 False，新版应返回 True
        task = "把项目代码部署到生产环境并验证功能是否正常"
        needs_plan = await worker.executor.needs_plan(
            task, [], classifier=worker.auto_classifier
        )
        assert needs_plan is True, "语义复杂任务应触发 Plan 模式"
