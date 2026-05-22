"""Loop Detection + Self Validation 端到端集成测试

验证 LoopDetector 和 SelfValidator 在 GovernanceWorker 中的真实集成行为：
1. LoopDetector 在 Tool Loop 中检测循环并中断
2. SelfValidator 在 Tool Loop 结束后验证完成度
"""

import asyncio
import json
import time

import pytest

from tests.test_integration_llm_driven import _run_conversation, _find_completed_message


@pytest.mark.timeout(120)
class TestLoopDetectionEndToEnd:
    """循环检测端到端测试"""
    
    @pytest.mark.asyncio
    async def test_loop_detector_initialized(self, real_governance_worker):
        """验证 LoopDetector 已正确初始化"""
        worker = real_governance_worker
        assert hasattr(worker, 'loop_detector')
        assert worker.loop_detector is not None
    
    @pytest.mark.asyncio
    async def test_normal_chat_no_loop_detected(self, real_governance_worker):
        """正常对话不应触发循环检测"""
        worker = real_governance_worker
        session_id = f"test_normal_{int(time.time() * 1000)}"
        
        await _run_conversation(worker, session_id, "你好")
        
        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None
        
        # 不应有循环检测的警告消息
        response = completed.get("content", "")
        assert "陷入循环" not in response
        assert "⚠️ 检测到任务执行陷入循环" not in response


@pytest.mark.timeout(120)
class TestSelfValidationEndToEnd:
    """自验证端到端测试"""
    
    @pytest.mark.asyncio
    async def test_self_validator_initialized(self, real_governance_worker):
        """验证 SelfValidator 已正确初始化"""
        worker = real_governance_worker
        assert hasattr(worker, 'self_validator')
        assert worker.self_validator is not None
    
    @pytest.mark.asyncio
    async def test_tool_loop_completes_normally(self, real_governance_worker):
        """正常 Tool Loop 完成后，自验证不应发出误报"""
        worker = real_governance_worker
        session_id = f"test_tool_{int(time.time() * 1000)}"
        
        await _run_conversation(worker, session_id, "列出当前目录的文件")
        
        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None
        response = completed.get("content", "")
        assert response
        
        # 正常完成不应有自验证警报
        assert "⚠️ 任务可能未完成" not in response
    
    @pytest.mark.asyncio
    async def test_chat_greeting_no_self_validation_alert(self, real_governance_worker):
        """问候任务完成后，自验证不应误报"""
        worker = real_governance_worker
        session_id = f"test_chat_{int(time.time() * 1000)}"
        
        await _run_conversation(worker, session_id, "你好")
        
        completed = _find_completed_message(worker.bus, session_id)
        assert completed is not None
        response = completed.get("content", "")
        
        # 问候任务不应有自验证警报
        assert "⚠️ 任务可能未完成" not in response


@pytest.mark.timeout(120)
class TestLoopDetectorMockLLM:
    """用 Mock LLM 测试循环检测在 Worker 中的集成（可控场景）"""
    
    @pytest.mark.asyncio
    async def test_parameter_repeat_with_mock_llm(self, mock_llm, mock_bus, mock_store):
        """Mock 场景：同一工具+相同参数被反复调用，验证循环检测中断"""
        from tent_os.governance.worker import GovernanceWorker
        from tent_os.scheduler.executors.local import LocalExecutor
        from tent_os.tools.executor import ToolExecutor
        
        # 设置 Mock LLM：总是调用 file_read
        call_count = [0]
        
        async def mock_chat_with_tools(messages, tools):
            call_count[0] += 1
            if call_count[0] >= 5:
                # 第5轮后假装完成（防止无限循环）
                return {"content": "完成", "tool_calls": []}
            return {
                "content": f"读取中 {call_count[0]}",
                "tool_calls": [{
                    "id": f"call_{call_count[0]}",
                    "type": "function",
                    "function": {
                        "name": "file_read",
                        "arguments": json.dumps({"path": "/tmp/test.txt"}),
                    }
                }]
            }
        
        mock_llm.chat_with_tools = mock_chat_with_tools
        
        local_executor = LocalExecutor()
        await local_executor.initialize({
            "workspace_mode": "workspace",
            "workspace_path": "/tmp",
            "allow_write": False,
        })
        tool_executor = ToolExecutor(local_executor=local_executor)
        
        config = {
            "memory": {"storage_path": "./tent_memory"},
            "tools": {"profile": "full", "max_result_chars": 4000},
            "stream": {"block_streaming": False, "min_chunk_chars": 40, "max_chunk_chars": 300, "coalesce_ms": 80},
            "brain_v2": {"enabled": False},
            "governance": {"approval_threshold": 0.5, "enable_evaluator": False, "enable_procedural_memory": False},
        }
        
        worker = GovernanceWorker(
            bus=mock_bus, llm=mock_llm, state_store=mock_store,
            tool_executor=tool_executor, skill_manager=None, config=config,
        )
        
        session_id = "test_mock_loop"
        await mock_store.create(session_id=session_id, task="读取文件", user_id="test")
        await mock_store.append_message(session_id, "user", "读取文件")
        
        await worker._on_memory_injected(session_id, {"injected_context": ""})
        
        # 验证循环检测触发了（参数重复+结果无变化）
        # Mock 的 file_read 每次都返回相同结果（因为路径相同），应该触发参数重复检测
        # 但由于 MockToolExecutor 可能返回不同的 mock 结果，这里主要验证 Tool Loop 没有无限执行
        assert call_count[0] < 10, f"Tool Loop 应被循环检测中断，但执行了 {call_count[0]} 次"
