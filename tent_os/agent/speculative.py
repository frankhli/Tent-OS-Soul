"""Speculative Execution —— 推测执行引擎

核心洞察：在 LLM 流式输出中检测工具调用意图，不等完整响应，
先并行启动只读工具（如 file_read、directory_list、web_search）。

工作原理：
1. 监听 LLM 流式输出的每个 chunk
2. 用启发式模式匹配检测工具意图
3. 如果是只读工具，立即异步执行
4. 等 LLM 正式发起工具调用时，结果已经准备好了

只读工具白名单：
- file_read: 读取文件（安全，不修改）
- directory_list: 列出目录（安全）
- web_search: 网络搜索（安全）
- web_fetch: 抓取网页（安全）
- memory_search: 记忆搜索（安全）

Tent OS 差异化：
- 推测执行在治理进程内完成，结果直接注入上下文
- 与 Hook Engine 集成：tool.preuse 可以拦截推测执行
- JSONL Logger 记录每次推测执行的命中/浪费率

使用方式：
    speculative = SpeculativeExecutor(tool_executor)
    
    async def on_stream_chunk(chunk: str):
        intent = speculative.detect_intent(chunk)
        if intent:
            await speculative.execute_if_safe(intent, session_id="abc")
"""

import asyncio
import time
import re
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class SpeculativeIntent:
    """推测意图"""
    tool: str
    params: Dict[str, Any]
    confidence: float
    source_text: str


# 只读工具白名单
READONLY_TOOLS = {"file_read", "directory_list", "web_search", "web_fetch", "memory_search", "memory_get"}

# 意图检测模式
INTENT_PATTERNS = [
    # file_read 意图
    (r"(?:让我?看看?|查看|读取|打开|read|cat)\s*[【\[]?(.+?)(?:文件|目录|内容|file)?[】\]]?", 
     "file_read", "path"),
    (r"(?:看看|查看)\s*(.+?)\s*(?:文件|内容)?", "file_read", "path"),

    # directory_list 意图
    (r"(?:列出|看看|浏览|list|ls|dir)\s*(.+?)\s*(?:目录|文件夹|下的文件)?", 
     "directory_list", "path"),

    # web_search 意图
    (r"(?:搜索|查找|search|查一下)\s*(.+?)(?:信息|资料|内容|结果)?", 
     "web_search", "query"),

    # web_fetch 意图
    (r"(?:抓取|获取|fetch|访问)\s*(https?://\S+)", "web_fetch", "url"),

    # memory_search 意图
    (r"(?:搜索记忆|查找历史|memory_search)\s*(.+?)", "memory_search", "query"),
]


class SpeculativeExecutor:
    """推测执行引擎

    在 LLM 流式输出中检测工具意图，并行预执行只读工具。
    """

    def __init__(self,
                 tool_executor=None,
                 jsonl_logger=None,
                 max_concurrent: int = 3,
                 cooldown_seconds: float = 2.0):
        self.tool_executor = tool_executor
        self.jsonl_logger = jsonl_logger
        self.max_concurrent = max_concurrent
        self.cooldown = cooldown_seconds

        # 已推测执行的工具（避免重复）
        self._speculated: Dict[str, Set[str]] = {}  # session_id -> set of "tool:params_hash"

        # 正在执行的推测任务
        self._running: Dict[str, asyncio.Task] = {}

        # 结果缓存: session_id -> {"tool:params": result}
        self._results: Dict[str, Dict] = {}

        # 统计
        self._stats = {
            "intents_detected": 0,
            "executed": 0,
            "hits": 0,      # LLM 实际调用了推测的工具
            "wasted": 0,    # 推测了但 LLM 没调用
            "saved_ms": 0,  # 节省的时间
        }

    def detect_intent(self, text: str) -> Optional[SpeculativeIntent]:
        """从文本中检测工具意图

        Args:
            text: LLM 流式输出的文本 chunk

        Returns:
            SpeculativeIntent 或 None
        """
        text = text.strip()
        if len(text) < 5:
            return None

        for pattern, tool_name, param_key in INTENT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                param_value = match.group(1).strip() if match.groups() else ""
                if param_value:
                    # 清理参数值
                    param_value = param_value.strip("\"'[]【】")
                    # FIX v6: 参数质量门控——防止从代码/乱码中提取垃圾参数
                    if not self._is_valid_param(tool_name, param_value):
                        continue
                    return SpeculativeIntent(
                        tool=tool_name,
                        params={param_key: param_value},
                        confidence=0.7,
                        source_text=text,
                    )

        return None
    
    def _is_valid_param(self, tool_name: str, param_value: str) -> bool:
        """验证推测执行参数是否有效——防止垃圾调用消耗资源"""
        if not param_value or len(param_value) < 2:
            return False
        # 过滤明显是代码片段、XML标签、乱码的参数
        garbage_patterns = [
            r'^[\s\{\}\[\]<>\(\)\|&*+=^%$#@!~`\\/;:,\.\-\d]+$',  # 纯符号/数字
            r'^(param|parameter|name|value|arg|args|path|query|url)\s*[=>:]+',  # 参数名本身
            r'^[\w\s]{0,3}$',  # 太短（<=3字符且是单词字符）
        ]
        for pattern in garbage_patterns:
            if re.match(pattern, param_value, re.IGNORECASE):
                return False
        
        # file_read / directory_list: 参数应该像路径
        if tool_name in ("file_read", "directory_list"):
            # 拒绝单个非字母字符或明显不是路径的内容
            if len(param_value) <= 2 and not param_value.startswith('.'):
                return False
            # 拒绝 HTML/XML 标签片段
            if param_value.startswith('<') or param_value.startswith('>'):
                return False
        
        # web_search / web_fetch: 参数应该像查询词或URL
        if tool_name in ("web_search", "web_fetch"):
            # 拒绝单个汉字或字母（无意义搜索）
            if len(param_value) <= 3 and not param_value.startswith('http'):
                return False
        
        return True

    async def execute_if_safe(self, intent: SpeculativeIntent,
                              session_id: str) -> Optional[Any]:
        """如果安全，执行推测意图

        Args:
            intent: 推测的意图
            session_id: 会话ID

        Returns:
            工具执行结果（如果执行了）
        """
        # 1. 检查是否是只读工具
        if intent.tool not in READONLY_TOOLS:
            logger.debug(f"[Speculative] 非只读工具，跳过: {intent.tool}")
            return None

        # 2. 检查是否已推测过
        params_hash = self._hash_params(intent.params)
        spec_key = f"{intent.tool}:{params_hash}"

        if session_id not in self._speculated:
            self._speculated[session_id] = set()

        if spec_key in self._speculated[session_id]:
            logger.debug(f"[Speculative] 已推测过，跳过: {spec_key}")
            return None

        # 3. 检查并发限制
        running_count = sum(
            1 for t in self._running.values()
            if not t.done()
        )
        if running_count >= self.max_concurrent:
            logger.debug(f"[Speculative] 并发限制，跳过")
            return None

        # 4. 标记为已推测
        self._speculated[session_id].add(spec_key)
        self._stats["intents_detected"] += 1

        # 5. 异步执行
        task = asyncio.create_task(self._execute_tool(intent, session_id))
        task_key = f"{session_id}:{spec_key}"
        self._running[task_key] = task

        logger.info(f"[Speculative] 推测执行 [{session_id}]: {intent.tool}({intent.params})")

        # 6. 记录审计日志
        if self.jsonl_logger:
            asyncio.create_task(self.jsonl_logger.log_event(
                event="speculative.execute",
                session_id=session_id,
                tool=intent.tool,
                params=intent.params,
                confidence=intent.confidence,
            ))

        return task

    def get_result(self, session_id: str, tool: str, 
                   params: Dict[str, Any]) -> Optional[Any]:
        """获取推测执行的结果

        当 LLM 正式发起工具调用时，先检查是否已有推测结果。
        """
        params_hash = self._hash_params(params)
        spec_key = f"{tool}:{params_hash}"

        session_results = self._results.get(session_id, {})
        if spec_key in session_results:
            self._stats["hits"] += 1
            logger.info(f"[Speculative] 命中 [{session_id}]: {spec_key}")
            return session_results[spec_key]

        return None

    def mark_wasted(self, session_id: str):
        """标记当前会话的推测为浪费（LLM 没有调用推测的工具）"""
        # 统计浪费：有推测但未被使用的
        speculated = self._speculated.get(session_id, set())
        results = self._results.get(session_id, {})
        for spec_key in speculated:
            if spec_key not in results:
                self._stats["wasted"] += 1

    def reset_session(self, session_id: str):
        """重置会话的推测状态"""
        self._speculated.pop(session_id, None)
        self._results.pop(session_id, None)

        # 取消运行中的任务
        for key, task in list(self._running.items()):
            if key.startswith(f"{session_id}:"):
                task.cancel()
                self._running.pop(key, None)

    def get_stats(self) -> Dict:
        """获取推测执行统计"""
        total = self._stats["executed"]
        hits = self._stats["hits"]
        wasted = self._stats["wasted"]
        return {
            **self._stats,
            "hit_rate": round(hits / max(total, 1), 2),
            "waste_rate": round(wasted / max(total, 1), 2),
        }

    # ========== 内部实现 ==========

    async def _execute_tool(self, intent: SpeculativeIntent, session_id: str):
        """执行推测工具调用"""
        start_time = time.time()
        self._stats["executed"] += 1

        try:
            if not self.tool_executor:
                return

            # 调用工具执行器
            result = await self.tool_executor.execute(
                intent.tool, intent.params, session_id=session_id
            )

            # 缓存结果
            params_hash = self._hash_params(intent.params)
            spec_key = f"{intent.tool}:{params_hash}"

            if session_id not in self._results:
                self._results[session_id] = {}
            self._results[session_id][spec_key] = result

            elapsed_ms = (time.time() - start_time) * 1000
            self._stats["saved_ms"] += elapsed_ms

            logger.debug(f"[Speculative] 完成 [{session_id}]: {spec_key} ({elapsed_ms:.0f}ms)")

        except Exception as e:
            logger.debug(f"[Speculative] 执行失败 [{session_id}]: {e}")

    def _hash_params(self, params: Dict) -> str:
        """计算参数 hash"""
        import hashlib
        return hashlib.md5(
            str(sorted(params.items())).encode()
        ).hexdigest()[:8]
