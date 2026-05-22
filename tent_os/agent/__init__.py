"""Tent OS Agent Core — 对话引擎核心

参考架构:
- Claude Code: 极简 Agent Loop + 丰富的外围系统
- LangGraph: State + Reducers + Checkpoint
- OpenClaw: Per-session queues + Gateway dispatch
"""

from .context_assembly import ContextAssemblyPipeline

__all__ = ["ContextAssemblyPipeline"]
