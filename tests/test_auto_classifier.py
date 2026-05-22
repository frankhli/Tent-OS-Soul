"""Tests for AutoModeClassifier —— 自动安全分类器"""

import pytest
from unittest.mock import AsyncMock

from tent_os.governance.auto_classifier import (
    AutoModeClassifier,
    ClassificationResult,
    ComplexityResult,
    SafetyLevel,
)


@pytest.fixture
def classifier():
    mock_llm = AsyncMock()
    return AutoModeClassifier(llm=mock_llm)


@pytest.mark.unit
class TestSafetyLevel:
    def test_levels(self):
        assert SafetyLevel.SAFE.value == "safe"
        assert SafetyLevel.DANGEROUS.value == "dangerous"
        assert SafetyLevel.CRITICAL.value == "critical"


@pytest.mark.unit
class TestAutoModeClassifier:
    @pytest.mark.asyncio
    async def test_evaluate_safe_task(self, classifier):
        # 设置 mock LLM 返回 safe 结果
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = (
            '{"safety_level": "safe", "confidence": 0.95, '
            '"reasoning": "safe query", "risks": []}'
        )
        classifier.llm = mock_llm
        classifier._cache.clear()
        result = await classifier.evaluate("今天天气怎么样？")
        assert result.safety_level == "safe"
        assert result.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_evaluate_dangerous_keywords(self, classifier):
        result = await classifier.evaluate("rm -rf /")
        assert hasattr(result, "confidence")

    @pytest.mark.asyncio
    async def test_evaluate_with_llm_response(self, classifier):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = (
            '{"safety_level": "dangerous", "confidence": 0.9, '
            '"reasoning": "risky", "risks": ["data_loss"]}'
        )
        classifier.llm = mock_llm
        classifier._cache.clear()
        # Use a non-heuristic-matching task to force LLM path
        result = await classifier.evaluate("some ambiguous task xyz123")
        assert result.safety_level == "dangerous"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_batch_evaluate(self, classifier):
        tasks = ["safe task 1", "safe task 2"]
        results = await classifier.batch_evaluate(tasks)
        assert len(results) == 2
        assert all(hasattr(r, "safety_level") for r in results)

    def test_heuristic_evaluate_dangerous(self, classifier):
        result = classifier._heuristic_evaluate("rm -rf /")
        assert result.safety_level in ["dangerous", "critical"]

    def test_heuristic_safe(self, classifier):
        # 短问句触发启发式 safe
        result = classifier._heuristic_evaluate("今天天气怎么样？")
        assert result.safety_level == "safe"

    def test_hash_task_consistency(self, classifier):
        h1 = classifier._hash_task("test task")
        h2 = classifier._hash_task("test task")
        assert h1 == h2

    def test_get_stats(self, classifier):
        stats = classifier.get_stats()
        assert "calls" in stats
        assert "cache_size" in stats

    def test_parse_response_valid_json(self, classifier):
        raw = '{"safety_level": "safe", "confidence": 0.5, "reasoning": "ok", "risks": []}'
        result = classifier._parse_response(raw)
        assert result.safety_level == "safe"

    def test_parse_response_invalid_returns_default(self, classifier):
        result = classifier._parse_response("not json")
        assert result.safety_level == "cautious"


@pytest.mark.unit
class TestComplexityEvaluation:
    """复杂度评估测试 —— De-keywordization 核心"""

    def test_heuristic_complexity_simple_greeting(self, classifier):
        """问候语 → 简单"""
        result = classifier._heuristic_complexity("你好")
        assert result is not None
        assert result.is_complex is False
        assert result.confidence > 0.8

    def test_heuristic_complexity_single_action(self, classifier):
        """单动作 → 简单"""
        result = classifier._heuristic_complexity("列出当前目录")
        assert result is not None
        assert result.is_complex is False
        assert result.confidence > 0.8

    def test_heuristic_complexity_sequential_markers(self, classifier):
        """时序依赖 → 复杂（不依赖关键词，而是通用时序词）"""
        result = classifier._heuristic_complexity(
            "先读取配置文件，然后修改端口号，最后重启服务"
        )
        assert result is not None
        assert result.is_complex is True
        assert result.indicators["sequential_markers"] > 0.5

    def test_heuristic_complexity_multi_verbs(self, classifier):
        """多动词 + 时序 → 复杂"""
        result = classifier._heuristic_complexity(
            "先搜索文档，再读取内容，然后分析结果，最后生成报告"
        )
        assert result is not None
        assert result.is_complex is True
        assert result.indicators["sequential_markers"] > 0.5

    def test_heuristic_complexity_uncertain_falls_back(self, classifier):
        """不确定 → 返回 None（降级到 LLM）"""
        # 中等长度、有动作但无明显时序/条件的模糊任务
        result = classifier._heuristic_complexity(
            "帮我看看这个文件的内容怎么样，然后给我一些修改建议"
        )
        # 不在高置信度范围内，返回 None
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_complexity_with_llm(self, classifier):
        """LLM 路径解析复杂度"""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = (
            '{"is_complex": true, "complexity_score": 0.8, '
            '"reasoning": "多步骤", "confidence": 0.9, '
            '"indicators": {"step_count": 5, "tool_diversity": 0.7}}'
        )
        classifier.llm = mock_llm
        classifier._cache.clear()

        # 使用不触发启发式的输入，强制走 LLM 路径
        result = await classifier.evaluate_complexity("some ambiguous task xyz123")
        assert isinstance(result, ComplexityResult)
        assert result.is_complex is True
        assert result.complexity_score == 0.8

    @pytest.mark.asyncio
    async def test_evaluate_complexity_cache_hit(self, classifier):
        """缓存命中"""
        # 第一次调用
        result1 = classifier._heuristic_complexity("你好")
        task_hash = classifier._hash_task("complexity:你好")
        classifier._cache[task_hash] = (result1, __import__("time").time())

        # 第二次应命中缓存
        result2 = await classifier.evaluate_complexity("你好")
        assert result2 is result1

    def test_default_complexity_result(self, classifier):
        """默认复杂度结果"""
        result = classifier._default_complexity_result("测试")
        assert result.is_complex is False
        assert result.complexity_score == 0.3

    def test_parse_complexity_response(self, classifier):
        """解析复杂度 JSON 响应"""
        raw = (
            '{"is_complex": true, "complexity_score": 0.75, '
            '"reasoning": "ok", "confidence": 0.8, '
            '"indicators": {"step_count": 3}}'
        )
        result = classifier._parse_complexity_response(raw)
        assert result.is_complex is True
        assert result.complexity_score == 0.75
        assert result.indicators["step_count"] == 3.0

    def test_parse_complexity_response_invalid(self, classifier):
        """解析失败 → 默认结果"""
        result = classifier._parse_complexity_response("not json")
        assert result.is_complex is False
        assert result.complexity_score == 0.3
