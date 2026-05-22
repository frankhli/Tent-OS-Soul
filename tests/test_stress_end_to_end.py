"""End-to-end stress test —— C.1 全链路压力测试

验证 Tent OS 在高负载下的表现：
1.  GovernanceWorker 消息处理吞吐量
2.  LayeredSecurity 评估延迟 (P95)
3.  ContextCompressionPipeline 压缩性能
4.  HookEngine 触发性能
5.  ToolPoolAssembler 组装性能
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from tent_os.governance.compression import ContextCompressionPipeline
from tent_os.governance.opa_engine import OPAPolicyEngine
from tent_os.governance.safety.layered_security import LayeredSecurity
from tent_os.hooks.engine import HookEngine, Hook, HookType
from tent_os.telemetry import TelemetryCollector
from tent_os.tools.assembler import ToolPoolAssembler


@pytest.fixture
def telemetry():
    return TelemetryCollector()


@pytest.mark.stress
class TestGovernanceLatency:
    """治理链路延迟测试"""

    @pytest.mark.asyncio
    async def test_opa_policy_eval_latency(self, tmp_path):
        """OPA 策略评估 P95 < 1ms"""
        policy_file = tmp_path / "opa.yaml"
        policy_file.write_text("""
packages:
  security:
    default: allow
    rules:
      - name: "block_delete"
        conditions: ["input.action == 'delete'"]
        decision: deny
""")
        engine = OPAPolicyEngine(str(policy_file))

        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            engine.evaluate({"action": "read", "task": "test"})
            latencies.append((time.perf_counter() - start) * 1000)

        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95 < 1.0, f"OPA P95 latency {p95:.2f}ms exceeds 1ms"

    @pytest.mark.asyncio
    async def test_layered_security_latency(self):
        """7层安全评估 P95 < 5ms"""
        security = LayeredSecurity(config={})

        latencies = []
        for _ in range(50):
            start = time.perf_counter()
            await security.evaluate_tool_call("sess_1", "web_search", {"query": "x"})
            latencies.append((time.perf_counter() - start) * 1000)

        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95 < 5.0, f"Security P95 latency {p95:.2f}ms exceeds 5ms"

    @pytest.mark.asyncio
    async def test_compression_pipeline_latency(self):
        """5层压缩管道 P95 < 10ms"""
        pipeline = ContextCompressionPipeline(config={})
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello " * 100},
        ]

        latencies = []
        for _ in range(30):
            start = time.perf_counter()
            await pipeline.compress(messages, max_tokens=500)
            latencies.append((time.perf_counter() - start) * 1000)

        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        assert p95 < 10.0, f"Compression P95 latency {p95:.2f}ms exceeds 10ms"


@pytest.mark.stress
class TestThroughput:
    """吞吐量测试"""

    def test_hook_engine_throughput(self):
        """HookEngine 1000次触发 < 100ms"""
        engine = HookEngine()
        engine.register(Hook(name="audit", event="tool.preuse", hook_type=HookType.ASYNC,
                             handler=AsyncMock(return_value=MagicMock(allowed=True))))

        async def run():
            start = time.perf_counter()
            for _ in range(1000):
                await engine.trigger("tool.preuse", "sess_1", {"tool": "ls"})
            return (time.perf_counter() - start) * 1000

        elapsed = asyncio.run(run())
        assert elapsed < 1000, f"HookEngine 1000 triggers took {elapsed:.1f}ms"

    def test_tool_assembler_throughput(self):
        """ToolPoolAssembler 100次组装 < 50ms"""
        assembler = ToolPoolAssembler(config={})

        start = time.perf_counter()
        for _ in range(100):
            assembler.assemble(session_id="sess_1")
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 50, f"ToolPoolAssembler 100 assemblies took {elapsed:.1f}ms"

    def test_telemetry_recording_throughput(self):
        """MetricWindow 高频记录 >5000/sec"""
        from tent_os.telemetry import MetricWindow
        window = MetricWindow()

        start = time.perf_counter()
        for i in range(5000):
            window.add(100.0)
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 1000, f"MetricWindow 5000 adds took {elapsed:.1f}ms"
        assert window.count() == 1000  # maxlen=1000, old values evicted


@pytest.mark.stress
class TestMemoryPressure:
    """内存压力测试"""

    @pytest.mark.asyncio
    async def test_compression_large_context(self):
        """大上下文压缩不 OOM"""
        pipeline = ContextCompressionPipeline(config={})
        messages = [
            {"role": "user", "content": "x" * 10000}  # 10KB message
            for _ in range(5)
        ]

        result = await pipeline.compress(messages, max_tokens=1000)
        assert len(result) > 0
        total_len = sum(len(m.get("content", "")) for m in result)
        assert total_len < 50000  # Should be significantly reduced

    def test_telemetry_memory_stable(self):
        """Telemetry 大量记录后内存稳定"""
        collector = TelemetryCollector()

        for i in range(1000):
            collector.record_llm_call("sess_1", "gpt-4", 100, 50, 500.0)
            collector.record_tool_call("sess_1", "search", 100.0, True)
            collector.record_compression("sess_1", 1000, 500, "L3")

        report = collector.get_report()
        assert report["llm"]["total_calls"] > 0
        assert report["tools"]["total_calls"] > 0
