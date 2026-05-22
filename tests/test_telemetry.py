"""Tests for TelemetryCollector —— 性能监控与指标收集"""

import time
import pytest

from tent_os.telemetry import TelemetryCollector, MetricWindow


@pytest.fixture
def telemetry():
    return TelemetryCollector(jsonl_logger=None)


@pytest.mark.unit
class TestTelemetryCollector:

    def test_initialization(self, telemetry):
        assert telemetry.jsonl_logger is None
        assert telemetry._start_time > 0
        assert len(telemetry._metrics) == 0
        assert len(telemetry._session_metrics) == 0

    def test_record_llm_call(self, telemetry):
        telemetry.record_llm_call(
            session_id="sess_1",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=1200,
            provider="openai",
        )
        assert telemetry._metrics["llm_calls"].count() == 1
        assert telemetry._metrics["llm_input_tokens"].sum() == 1000
        assert telemetry._metrics["llm_output_tokens"].sum() == 500
        assert telemetry._metrics["llm_total_tokens"].sum() == 1500
        assert telemetry._metrics["llm_latency_ms"].count() == 1
        assert telemetry._session_metrics["sess_1"]["llm_calls"].count() == 1

    def test_record_llm_call_cost_estimation(self, telemetry):
        telemetry.record_llm_call(
            session_id="sess_1",
            model="gpt-4o-mini",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            latency_ms=1000,
        )
        cost = telemetry._metrics["llm_cost_usd"].sum()
        assert cost > 0

    def test_record_tool_call(self, telemetry):
        telemetry.record_tool_call("sess_1", "shell", 150.0, success=True)
        assert telemetry._metrics["tool_calls"].count() == 1
        assert telemetry._metrics["tool_latency_ms"].count() == 1
        assert telemetry._metrics["tool_errors"].count() == 0
        assert telemetry._session_metrics["sess_1"]["tool_calls"].count() == 1

    def test_record_tool_call_failure(self, telemetry):
        telemetry.record_tool_call("sess_1", "shell", 200.0, success=False)
        assert telemetry._metrics["tool_errors"].count() == 1

    def test_record_compression(self, telemetry):
        telemetry.record_compression("sess_1", original_tokens=1000, compressed_tokens=600, layer="L3")
        assert telemetry._metrics["compression_saved_tokens"].sum() == 400
        assert telemetry._metrics["compression_ratio"].values[0] == pytest.approx(0.4)

    def test_record_cache_hit(self, telemetry):
        telemetry.record_cache_hit("system", hit=True)
        telemetry.record_cache_hit("tools", hit=True)
        telemetry.record_cache_hit("dynamic", hit=False)
        assert telemetry._metrics["cache_hits"].count() == 2
        assert telemetry._metrics["cache_misses"].count() == 1

    def test_record_security(self, telemetry):
        telemetry.record_security("L1", "deny")
        telemetry.record_security("L2", "deny")
        telemetry.record_security("L1", "deny")
        assert telemetry._metrics["security_L1_deny"].count() == 2
        assert telemetry._metrics["security_L2_deny"].count() == 1

    def test_get_report_overall(self, telemetry):
        telemetry.record_llm_call("sess_1", "gpt-4o", 100, 50, 500, "openai")
        telemetry.record_tool_call("sess_1", "shell", 100.0, success=True)
        telemetry.record_compression("sess_1", 1000, 800, "L2")
        telemetry.record_cache_hit("system", hit=True)
        telemetry.record_cache_hit("tools", hit=False)
        report = telemetry.get_report()
        assert report["uptime_seconds"] >= 0
        assert report["llm"]["total_calls"] == 1
        assert report["llm"]["total_tokens"] == 150
        assert report["tools"]["total_calls"] == 1
        assert report["compression"]["total_saved_tokens"] == 200
        assert report["cache"]["hits"] == 1
        assert report["cache"]["misses"] == 1
        assert report["cache"]["hit_rate"] == 0.5
        assert "p95_latency_ms" in report["llm"]
        assert "total_cost_usd" in report["llm"]

    def test_get_report_session(self, telemetry):
        telemetry.record_llm_call("sess_a", "gpt-4o", 200, 100, 800, "openai")
        telemetry.record_tool_call("sess_a", "web_search", 300.0, success=True)
        report = telemetry.get_report(session_id="sess_a")
        assert report["session_id"] == "sess_a"
        assert report["llm_calls"] == 1
        assert report["total_tokens"] == 300
        assert report["avg_latency_ms"] == 800.0
        assert report["tool_calls"] == 1

    def test_get_realtime_metrics(self, telemetry):
        telemetry.record_llm_call("sess_1", "gpt-4o", 100, 50, 600, "openai")
        metrics = telemetry.get_realtime_metrics()
        assert "llm_calls_per_min" in metrics
        assert "avg_latency_ms" in metrics
        assert metrics["active_sessions"] == 1

    def test_metric_window_add_and_trim(self):
        mw = MetricWindow(max_size=3)
        mw.add(1.0)
        mw.add(2.0)
        mw.add(3.0)
        mw.add(4.0)
        assert mw.count() == 3
        assert list(mw.values) == [2.0, 3.0, 4.0]
        assert mw.sum() == 9.0
        assert mw.avg() == 3.0

    def test_metric_window_last_minute(self):
        mw = MetricWindow()
        mw.add(10.0)
        mw.add(20.0)
        assert len(mw.last_minute()) == 2
        mw.timestamps[0] = time.time() - 120
        assert len(mw.last_minute()) == 1

    def test_p95_calculation(self, telemetry):
        values = list(range(1, 101))
        p95 = telemetry._p95(values)
        assert p95 == 96.0

    def test_p95_empty(self, telemetry):
        assert telemetry._p95([]) == 0

    def test_hit_rate(self, telemetry):
        telemetry.record_cache_hit("a", hit=True)
        telemetry.record_cache_hit("b", hit=True)
        telemetry.record_cache_hit("c", hit=False)
        rate = telemetry._hit_rate("cache_hits", "cache_misses")
        assert rate == pytest.approx(0.67, rel=1e-2)

    def test_hit_rate_no_data(self, telemetry):
        assert telemetry._hit_rate("cache_hits", "cache_misses") == 0.0

    def test_record_speculative(self, telemetry):
        telemetry.record_speculative(hit=True, saved_ms=150.0)
        telemetry.record_speculative(hit=False, saved_ms=0.0)
        assert telemetry._metrics["speculative_hits"].count() == 1
        assert telemetry._metrics["speculative_misses"].count() == 1
        assert telemetry._metrics["speculative_saved_ms"].sum() == 150.0

    def test_record_slot_upgrade(self, telemetry):
        telemetry.record_slot_upgrade("sess_1", "default", "extended")
        assert telemetry._metrics["slot_upgrades"].count() == 1
