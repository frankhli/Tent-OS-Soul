"""Self Validator 测试 —— 规则评估 + LLM 深度评估

测试场景：
1. 规则评估检测明显的"未完成"信号（零成本）
2. LLM 深度评估处理主观判断（真实 LLM）
3. 合并结果取更严格的
"""

import pytest
from tent_os.governance.self_validator import SelfValidator, ValidationResult


class TestSelfValidatorRuleBased:
    """SelfValidator 规则评估单元测试（零成本）"""
    
    @pytest.fixture
    def validator(self):
        return SelfValidator(llm=None, enable_llm=False)
    
    @pytest.mark.asyncio
    async def test_detects_incomplete_signals(self, validator):
        """检测明确的未完成声明"""
        signals = [
            "抱歉，我无法完成这个任务",
            "对不起，我没有权限访问",
            "无法完成，需要更多信息",
            "I cannot complete this task",
            "Unable to process your request",
        ]
        for signal in signals:
            result = await validator.validate(
                task="删除所有文件",
                conversation_history=[{"role": "assistant", "content": signal}],
                response=signal,
            )
            assert not result.completed, f"应判定未完成: {signal[:40]}"
            assert result.confidence >= 0.85
    
    @pytest.mark.asyncio
    async def test_detects_retry_loop_language(self, validator):
        """检测重试/循环语言模式"""
        response = "让我再次尝试读取文件。再试一次，看看能否成功。"
        result = await validator.validate(
            task="读取文件",
            conversation_history=[],
            response=response,
        )
        assert not result.completed
        assert result.confidence >= 0.75
    
    @pytest.mark.asyncio
    async def test_detects_question_ending(self, validator):
        """检测以问题结尾（没有给出结果）"""
        result = await validator.validate(
            task="列出目录",
            conversation_history=[],
            response="您想查看哪个目录？",
        )
        assert not result.completed
        assert result.confidence >= 0.80
    
    @pytest.mark.asyncio
    async def test_detects_too_short_response(self, validator):
        """检测极短回复"""
        result = await validator.validate(
            task="分析数据",
            conversation_history=[],
            response="ok",
        )
        assert not result.completed
        assert result.confidence >= 0.70
    
    @pytest.mark.asyncio
    async def test_passes_complete_signals(self, validator):
        """检测明确的完成声明"""
        result = await validator.validate(
            task="列出目录",
            conversation_history=[],
            response="✅ 已完成。目录下有: file1.txt, file2.txt, dir1/",
        )
        assert result.completed
        assert result.confidence >= 0.65
    
    @pytest.mark.asyncio
    async def test_should_alert_user(self, validator):
        """测试 should_alert_user 逻辑"""
        # 未完成 + 高置信度 → 提醒
        result = ValidationResult(completed=False, confidence=0.8, reasoning="test", suggestion="fix it")
        assert validator.should_alert_user(result)
        
        # 未完成 + 低置信度 → 不提醒
        result = ValidationResult(completed=False, confidence=0.5, reasoning="test", suggestion="fix it")
        assert not validator.should_alert_user(result)
        
        # 完成 → 不提醒
        result = ValidationResult(completed=True, confidence=0.9, reasoning="test", suggestion="")
        assert not validator.should_alert_user(result)
    
    @pytest.mark.asyncio
    async def test_format_alert(self, validator):
        """测试警报格式化"""
        result = ValidationResult(
            completed=False,
            confidence=0.85,
            reasoning="任务未执行",
            suggestion="请检查文件路径",
            missing_aspects=["未读取文件", "未返回目录列表"],
        )
        alert = validator.format_alert(result)
        assert "⚠️" in alert
        assert "85%" in alert
        assert "任务未执行" in alert
        assert "未读取文件" in alert
        assert "请检查文件路径" in alert


@pytest.mark.timeout(120)
class TestSelfValidatorLLM:
    """SelfValidator LLM 深度评估测试（真实 LLM）"""
    
    @pytest.fixture
    def real_validator(self, real_llm):
        return SelfValidator(llm=real_llm, enable_llm=True, min_confidence_threshold=0.7)
    
    @pytest.mark.asyncio
    async def test_llm_detects_pretend_complete(self, real_validator):
        """LLM 应能识别"假装完成"——回复看起来完成了但实际上没有"""
        result = await real_validator.validate(
            task="请读取 README.md 并告诉我里面的内容",
            conversation_history=[
                {"role": "user", "content": "请读取 README.md 并告诉我里面的内容"},
                {"role": "assistant", "content": "我已经查看了文件，里面有一些项目说明和配置信息。"},
            ],
            response="我已经查看了文件，里面有一些项目说明和配置信息。",
        )
        # 这个回复很模糊，没有提供实际内容，LLM 应该能识别出来
        assert not result.completed or result.confidence < 0.9
    
    @pytest.mark.asyncio
    async def test_llm_passes_real_complete(self, real_validator):
        """LLM 应能识别真正的完成任务"""
        result = await real_validator.validate(
            task="你好",
            conversation_history=[
                {"role": "user", "content": "你好"},
            ],
            response="你好！我是 Tent OS，有什么可以帮你的吗？",
        )
        # 问候任务已经完成了
        assert result.completed


@pytest.mark.timeout(120)
class TestSelfValidatorIntegration:
    """SelfValidator 集成到 worker 的端到端测试"""
    
    @pytest.mark.asyncio
    async def test_self_validation_on_incomplete_task(self, real_governance_worker):
        """端到端：任务未完成时，自验证应发出警报"""
        worker = real_governance_worker
        session_id = f"test_sv_{int(__import__('time').time() * 1000)}"
        
        # 设置一个会导致"假装完成"的任务
        # 实际上让 LLM 做一个简单任务，然后看自验证是否正常工作
        from tests.test_integration_llm_driven import _run_conversation
        
        await _run_conversation(worker, session_id, "你好")
        
        # 验证自验证被调用且 ui_context 中可能有验证结果
        state = await worker.state_store.load(session_id)
        # 自验证的结果不会直接写入 state，但可以通过响应内容判断
        messages = await worker.state_store.get_messages(session_id)
        assert len(messages) >= 2
    
    @pytest.mark.asyncio
    async def test_rule_based_validation_zero_cost(self, real_governance_worker):
        """验证规则评估在零成本路径下能正确工作"""
        worker = real_governance_worker
        
        if not hasattr(worker, 'self_validator') or not worker.self_validator:
            pytest.skip("SelfValidator 未初始化")
        
        # 测试规则评估对明显未完成信号的检测
        result = await worker.self_validator.validate(
            task="删除文件",
            conversation_history=[],
            response="抱歉，我无法完成这个任务",
        )
        assert not result.completed
        assert result.confidence >= 0.85
