"""Tent OS Tool Calling 系统

参考 OpenAI function calling 格式，统一工具定义和执行。
工具 = LLM 可调用的能力单元，映射到具体执行者。
"""

from tent_os.tools.definitions import BUILTIN_TOOLS, get_tool_schemas, get_tools_for_executor
from tent_os.tools.executor import ToolExecutor

__all__ = ["BUILTIN_TOOLS", "get_tool_schemas", "get_tools_for_executor", "ToolExecutor"]
