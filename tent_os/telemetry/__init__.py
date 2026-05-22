"""Telemetry —— 性能监控与指标收集

收集维度：
- Token 消耗：input/output/total
- 延迟：LLM 调用延迟、工具执行延迟、端到端延迟
- 缓存命中率：Prompt Cache 命中次数
- 压缩效果：压缩前后 token 数对比
- 安全统计：各层拦截次数
- 推测执行：命中率、节省时间

使用方式：
    telemetry = TelemetryCollector(jsonl_logger)
    
    # 记录 LLM 调用
    telemetry.record_llm_call(session_id="abc", input_tokens=1000, output_tokens=500, latency_ms=1200)
    
    # 获取报告
    report = telemetry.get_report()
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class MetricWindow:
    """时间窗口内的指标 — 使用 deque 保证 O(1) 性能"""
    values: deque = field(init=False)
    timestamps: deque = field(init=False)

    def __init__(self, max_size: int = 1000):
        self.values = deque(maxlen=max_size)
        self.timestamps = deque(maxlen=max_size)

    def add(self, value: float):
        self.values.append(value)
        self.timestamps.append(time.time())

    def sum(self) -> float:
        return sum(self.values)

    def avg(self) -> float:
        return sum(self.values) / max(len(self.values), 1)

    def count(self) -> int:
        return len(self.values)

    def last_minute(self) -> List[float]:
        cutoff = time.time() - 60
        return [v for v, t in zip(self.values, self.timestamps) if t > cutoff]


class TelemetryCollector:
    """性能指标收集器

    轻量级内存指标收集，定期 flush 到 JSONL。
    """

    def __init__(self, jsonl_logger=None):
        self.jsonl_logger = jsonl_logger

        # 指标窗口
        self._metrics: Dict[str, MetricWindow] = defaultdict(lambda: MetricWindow())

        # 会话级指标
        self._session_metrics: Dict[str, Dict[str, MetricWindow]] = defaultdict(
            lambda: defaultdict(lambda: MetricWindow())
        )

        # 启动时间
        self._start_time = time.time()

    # ========== 记录方法 ==========

    def record_llm_call(self,
                        session_id: str,
                        model: str,
                        input_tokens: int,
                        output_tokens: int,
                        latency_ms: float,
                        provider: str = "openai"):
        """记录 LLM 调用指标"""
        total = input_tokens + output_tokens

        self._metrics["llm_calls"].add(1)
        self._metrics["llm_input_tokens"].add(input_tokens)
        self._metrics["llm_output_tokens"].add(output_tokens)
        self._metrics["llm_total_tokens"].add(total)
        self._metrics["llm_latency_ms"].add(latency_ms)

        # 会话级
        self._session_metrics[session_id]["llm_calls"].add(1)
        self._session_metrics[session_id]["llm_total_tokens"].add(total)
        self._session_metrics[session_id]["llm_latency_ms"].add(latency_ms)

        # 成本估算（粗略）
        cost = self._estimate_cost(input_tokens, output_tokens, model, provider)
        self._metrics["llm_cost_usd"].add(cost)

    def record_tool_call(self,
                         session_id: str,
                         tool: str,
                         latency_ms: float,
                         success: bool = True):
        """记录工具调用指标"""
        self._metrics["tool_calls"].add(1)
        self._metrics["tool_latency_ms"].add(latency_ms)

        if not success:
            self._metrics["tool_errors"].add(1)

        self._session_metrics[session_id]["tool_calls"].add(1)

    def record_compression(self,
                           session_id: str,
                           original_tokens: int,
                           compressed_tokens: int,
                           layer: str):
        """记录压缩效果"""
        saved = original_tokens - compressed_tokens
        ratio = saved / max(original_tokens, 1)

        self._metrics["compression_saved_tokens"].add(saved)
        self._metrics["compression_ratio"].add(ratio)

    def record_cache_hit(self, segment: str, hit: bool):
        """记录缓存命中/未命中"""
        if hit:
            self._metrics["cache_hits"].add(1)
        else:
            self._metrics["cache_misses"].add(1)

    def record_security(self, layer: str, decision: str):
        """记录安全决策"""
        self._metrics[f"security_{layer}_{decision}"].add(1)

    def record_speculative(self, hit: bool, saved_ms: float):
        """记录推测执行"""
        if hit:
            self._metrics["speculative_hits"].add(1)
        else:
            self._metrics["speculative_misses"].add(1)
        self._metrics["speculative_saved_ms"].add(saved_ms)

    def record_slot_upgrade(self, session_id: str, from_tier: str, to_tier: str):
        """记录槽位升级"""
        self._metrics["slot_upgrades"].add(1)

    # ========== 报告方法 ==========

    def get_report(self, session_id: str = None) -> Dict:
        """获取性能报告"""
        if session_id:
            return self._get_session_report(session_id)

        uptime = time.time() - self._start_time

        return {
            "uptime_seconds": round(uptime, 0),
            "llm": {
                "total_calls": self._metrics["llm_calls"].count(),
                "total_input_tokens": int(self._metrics["llm_input_tokens"].sum()),
                "total_output_tokens": int(self._metrics["llm_output_tokens"].sum()),
                "total_tokens": int(self._metrics["llm_total_tokens"].sum()),
                "avg_latency_ms": round(self._metrics["llm_latency_ms"].avg(), 1),
                "p95_latency_ms": self._p95(self._metrics["llm_latency_ms"].values),
                "total_cost_usd": round(self._metrics["llm_cost_usd"].sum(), 4),
            },
            "tools": {
                "total_calls": self._metrics["tool_calls"].count(),
                "avg_latency_ms": round(self._metrics["tool_latency_ms"].avg(), 1),
                "errors": self._metrics["tool_errors"].count(),
            },
            "compression": {
                "total_saved_tokens": int(self._metrics["compression_saved_tokens"].sum()),
                "avg_ratio": round(self._metrics["compression_ratio"].avg(), 2),
            },
            "cache": {
                "hits": self._metrics["cache_hits"].count(),
                "misses": self._metrics["cache_misses"].count(),
                "hit_rate": self._hit_rate("cache_hits", "cache_misses"),
            },
            "speculative": {
                "hits": self._metrics["speculative_hits"].count(),
                "misses": self._metrics["speculative_misses"].count(),
                "hit_rate": self._hit_rate("speculative_hits", "speculative_misses"),
                "total_saved_ms": int(self._metrics["speculative_saved_ms"].sum()),
            },
            "slots": {
                "upgrades": self._metrics["slot_upgrades"].count(),
            },
        }

    def get_realtime_metrics(self) -> Dict:
        """获取实时指标（最近1分钟）"""
        return {
            "llm_calls_per_min": len(self._metrics["llm_calls"].last_minute()),
            "avg_latency_ms": round(self._metrics["llm_latency_ms"].avg(), 1),
            "active_sessions": len(self._session_metrics),
        }

    # ========== 内部方法 ==========

    def _get_session_report(self, session_id: str) -> Dict:
        """获取单个会话的报告"""
        metrics = self._session_metrics.get(session_id, {})
        return {
            "session_id": session_id,
            "llm_calls": metrics.get("llm_calls", MetricWindow()).count(),
            "total_tokens": int(metrics.get("llm_total_tokens", MetricWindow()).sum()),
            "avg_latency_ms": round(metrics.get("llm_latency_ms", MetricWindow()).avg(), 1),
            "tool_calls": metrics.get("tool_calls", MetricWindow()).count(),
        }

    def _estimate_cost(self, input_tokens: int, output_tokens: int,
                       model: str, provider: str) -> float:
        """估算 LLM 调用成本（USD）"""
        # 粗略估算，实际价格会变动
        prices = {
            "gpt-4o": (5 / 1_000_000, 15 / 1_000_000),
            "gpt-4o-mini": (0.15 / 1_000_000, 0.6 / 1_000_000),
            "claude-3-5-sonnet": (3 / 1_000_000, 15 / 1_000_000),
            "kimi": (1 / 1_000_000, 2 / 1_000_000),
        }

        input_price, output_price = prices.get(model, prices.get("gpt-4o-mini", (0, 0)))
        return input_tokens * input_price + output_tokens * output_price

    def _p95(self, values: List[float]) -> float:
        """计算 P95"""
        if not values:
            return 0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * 0.95)
        return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 1)

    def _hit_rate(self, hit_key: str, miss_key: str) -> float:
        """计算命中率"""
        hits = self._metrics[hit_key].count()
        misses = self._metrics[miss_key].count()
        total = hits + misses
        return round(hits / max(total, 1), 2)
