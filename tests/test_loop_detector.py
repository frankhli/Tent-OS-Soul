"""Loop Detector 单元测试 —— 零成本，不调用 LLM

验证 LoopDetector 的各种检测模式：
1. 参数重复
2. 工具序列重复
3. 响应重复
4. 停滞检测
5. 正常流程不触发
"""

import json
import pytest
from tent_os.governance.loop_detector import LoopDetector, LoopDetectionResult


class TestLoopDetector:
    """循环检测器单元测试"""
    
    @pytest.fixture
    def detector(self):
        return LoopDetector()
    
    def test_parameter_repeat(self, detector):
        """检测同一工具+相同参数被反复调用"""
        session_id = "test_param"
        tool_call = {
            "function": {"name": "file_read", "arguments": '{"path": "/tmp/test.txt"}'}
        }
        
        # 第1轮
        result = detector.check(session_id, 1, "读取文件", [tool_call], [{"status": "completed"}])
        assert not result.is_loop
        
        # 第2轮
        result = detector.check(session_id, 2, "再读一次", [tool_call], [{"status": "completed"}])
        assert not result.is_loop  # 阈值是2，第3次才触发
        
        # 第3轮
        result = detector.check(session_id, 3, "还是不行", [tool_call], [{"status": "completed"}])
        assert result.is_loop
        assert result.loop_type == "parameter_repeat"
        assert "file_read" in result.details
        assert result.confidence > 0.8
    
    def test_tool_sequence_repeat_period_2(self, detector):
        """检测 A→B→A→B 序列重复"""
        session_id = "test_seq"
        
        calls_a = [{"function": {"name": "file_read", "arguments": '{"path": "/a"}'}}]
        calls_b = [{"function": {"name": "directory_list", "arguments": '{"path": "/b"}'}}]
        
        # A → B → A → B（周期为2的重复）
        for i, calls in enumerate([calls_a, calls_b, calls_a, calls_b], 1):
            result = detector.check(session_id, i, f"step {i}", calls, [{"status": "completed"}])
        
        assert result.is_loop
        assert result.loop_type == "tool_sequence_repeat"
        assert "周期为 2" in result.details
    
    def test_same_tool_called_4_times(self, detector):
        """检测同一工具以不同参数被调用超过4次（只触发序列重复，不触发参数重复）"""
        session_id = "test_same"
        
        # 同一工具，不同参数 → 参数重复不触发，但工具序列重复触发
        for i in range(1, 5):
            calls = [{"function": {"name": "web_search", "arguments": json.dumps({"query": f"x{i}"})}}]
            result = detector.check(session_id, i, f"search {i}", calls, [{"status": "completed", "results": []}])
        
        assert result.is_loop
        assert result.loop_type == "tool_sequence_repeat"
        assert "web_search" in result.details
    
    def test_response_repeat(self, detector):
        """检测 LLM 响应内容重复（使用不同工具避免序列重复触发）"""
        session_id = "test_resp"
        
        tools = ["file_read", "web_search", "directory_list", "memory_search"]
        # 连续4轮输出几乎相同的响应，但使用完全不同的工具
        for i in range(1, 5):
            calls = [{"function": {"name": tools[i-1], "arguments": json.dumps({"query": f"x{i}"})}}]
            result = detector.check(
                session_id, i,
                "让我再检查一下文件内容，确保信息准确无误",
                calls,
                [{"status": "completed"}]
            )
        
        assert result.is_loop
        assert result.loop_type == "response_repeat"
        assert result.confidence > 0.8
    
    def test_same_tool_different_params_no_new_info(self, detector):
        """同一工具不同参数反复调用，但结果无变化——单一工具滥用"""
        session_id = "test_stag"
        
        # 连续4轮调用相同工具类型但不同参数，结果完全相同
        for i in range(1, 5):
            calls = [{"function": {"name": "file_read", "arguments": json.dumps({"path": f"/a{i}"})}}]
            result = detector.check(
                session_id, i,
                f"step {i}",
                calls,
                [{"status": "completed", "content": "same content"}]
            )
        
        assert result.is_loop
        assert result.loop_type == "tool_sequence_repeat"
        assert result.confidence > 0.8
        assert "file_read" in result.details
    
    def test_stagnation_with_sequence_change(self, detector):
        """停滞检测：工具序列变化了，但结果高度相似"""
        session_id = "test_stag2"
        
        # 使用不同工具，避免触发工具序列重复
        tools = ["file_read", "web_search", "directory_list"]
        for i in range(1, 5):
            calls = [{"function": {"name": tools[i % 3], "arguments": json.dumps({"query": f"x{i}"})}}]
            result = detector.check(
                session_id, i,
                f"step {i}",
                calls,
                [{"status": "completed", "content": "same content everywhere"}]
            )
        
        assert result.is_loop
        assert result.loop_type == "stagnation"
    
    def test_no_loop_normal_flow(self, detector):
        """正常流程不应触发循环检测"""
        session_id = "test_normal"
        
        # 模拟正常流程：不同工具、不同参数、不同结果
        rounds = [
            ([{"function": {"name": "directory_list", "arguments": '{"path": "/"}'}}], "列出目录", [{"status": "completed", "files": ["a", "b"]}]),
            ([{"function": {"name": "file_read", "arguments": '{"path": "/a"}'}}], "读取a", [{"status": "completed", "content": "content a"}]),
            ([{"function": {"name": "file_read", "arguments": '{"path": "/b"}'}}], "读取b", [{"status": "completed", "content": "content b"}]),
        ]
        
        for i, (calls, content, results) in enumerate(rounds, 1):
            result = detector.check(session_id, i, content, calls, results)
            assert not result.is_loop, f"第{i}轮不应触发循环检测"
    
    def test_reset_session_clears_history(self, detector):
        """reset_session 应清除历史记录"""
        session_id = "test_reset"
        tool_call = {"function": {"name": "x", "arguments": "{}"}}
        
        # 先记录一些历史
        detector.check(session_id, 1, "a", [tool_call], [{}])
        detector.check(session_id, 2, "b", [tool_call], [{}])
        
        # 重置
        detector.reset_session(session_id)
        
        # 再检测不应触发（历史已清空）
        result = detector.check(session_id, 1, "c", [tool_call], [{}])
        assert not result.is_loop
    
    def test_empty_tool_calls_no_false_positive(self, detector):
        """没有工具调用时不应触发序列重复检测"""
        session_id = "test_empty"
        
        for i in range(1, 6):
            result = detector.check(session_id, i, "纯聊天", [], [])
        
        assert not result.is_loop
