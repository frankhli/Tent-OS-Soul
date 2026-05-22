"""JSONL 结构化日志系统 —— Claude Code 模式融合

核心设计：
1. Append-only JSONL —— 人类可读、grep友好、零依赖
2. 按日期和类别分目录 —— 便于归档和清理
3. 每个会话/任务/子代理独立文件 —— 便于 replay 和审计
4. 异步写入 —— 不阻塞主事件循环
5. 自动轮转 —— 单文件超过 10MB 自动切分

目录结构：
./tent_logs/
├── sessions/2026-04-23/sess_abc123.jsonl
├── tasks/2026-04-23/task_def456.jsonl
├── subagents/2026-04-23/agent_research_789.jsonl
├── system/2026-04-23.jsonl
└── audit/2026-04-23.jsonl

使用方式：
    logger = JSONLLogger("./tent_logs")
    await logger.log_event("session.start", session_id="abc", user_id="frank")
    await logger.log_tool("tool.preuse", session_id="abc", tool="shell", 
                          params={"cmd": "ls"}, decision="allow", latency_ms=12)
"""

import asyncio
import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import deque

from tent_os.logging_config import get_logger

logger = get_logger()


@dataclass
class LogEntry:
    """日志条目"""
    ts: float
    level: str
    event: str
    session_id: Optional[str]
    task_id: Optional[str]
    agent_id: Optional[str]
    data: Dict[str, Any]
    
    def to_jsonl(self) -> str:
        record = {
            "ts": self.ts,
            "level": self.level,
            "event": self.event,
            **self.data,
        }
        if self.session_id:
            record["session_id"] = self.session_id
        if self.task_id:
            record["task_id"] = self.task_id
        if self.agent_id:
            record["agent_id"] = self.agent_id
        return json.dumps(record, ensure_ascii=False, default=str)


class JSONLLogger:
    """JSONL 结构化日志记录器
    
    特性：
    - 批量异步写入（每100ms或100条刷新）
    - 自动按日期分目录
    - 文件大小轮转（10MB）
    - 内存缓冲区（防丢数据）
    """
    
    # 事件类别映射
    CATEGORIES = {
        # Session 生命周期
        "session.start": "sessions",
        "session.end": "sessions",
        "session.resume": "sessions",
        # Memory
        "memory.inject": "sessions",
        "memory.ingest": "sessions",
        "memory.recall": "sessions",
        # Plan
        "plan.generate": "tasks",
        "plan.approve": "tasks",
        "plan.execute": "tasks",
        # Tool
        "tool.assemble": "sessions",
        "tool.prefilter": "sessions",
        "tool.preuse": "audit",
        "tool.postuse": "audit",
        "tool.error": "audit",
        # Scheduler
        "scheduler.submit": "tasks",
        "scheduler.complete": "tasks",
        "scheduler.fail": "tasks",
        "scheduler.recover": "tasks",
        # Governance
        "governance.reply": "sessions",
        "governance.stream": "sessions",
        # Heartbeat
        "heartbeat.tick": "system",
        "heartbeat.complete": "system",
        # System
        "system.start": "system",
        "system.stop": "system",
        "system.config_change": "system",
        "system.error": "system",
        # Subagent
        "subagent.spawn": "subagents",
        "subagent.complete": "subagents",
        "subagent.fail": "subagents",
        # Audit
        "audit.permission_change": "audit",
        "audit.approval_request": "audit",
        "audit.approval_response": "audit",
    }
    
    def __init__(self, base_dir: str = "./tent_logs", 
                 flush_interval_ms: float = 100,
                 max_buffer_size: int = 1000,
                 max_file_size_mb: float = 10.0):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.flush_interval_ms = flush_interval_ms
        self.max_buffer_size = max_buffer_size
        self.max_file_size = max_file_size_mb * 1024 * 1024
        
        # 内存缓冲区: category -> deque[LogEntry]
        self._buffers: Dict[str, deque] = {}
        # 打开的文件句柄: path -> file object
        self._files: Dict[str, Any] = {}
        # 文件大小跟踪
        self._file_sizes: Dict[str, int] = {}
        # 写入锁（按类别）
        self._locks: Dict[str, asyncio.Lock] = {}
        # 后台刷新任务
        self._flush_task: Optional[asyncio.Task] = None
        self._shutdown: bool = False
    
    async def start(self):
        """启动后台刷新循环"""
        self._shutdown = False
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"[JSONL] 日志系统启动: {self.base_dir}")
    
    async def stop(self):
        """优雅关闭，刷完所有缓冲"""
        self._shutdown = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_all()
        # 关闭所有文件句柄
        for f in self._files.values():
            try:
                f.close()
            except Exception:
                pass
        self._files.clear()
        logger.info("[JSONL] 日志系统已关闭")
    
    # ========== 便捷日志方法 ==========
    
    async def log_event(self, event: str, level: str = "info", 
                        session_id: str = None, task_id: str = None,
                        agent_id: str = None, **kwargs):
        """记录通用事件"""
        entry = LogEntry(
            ts=time.time(),
            level=level,
            event=event,
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            data=kwargs,
        )
        await self._enqueue(entry)
    
    async def log_tool(self, event: str, session_id: str, tool: str,
                       params: Dict, decision: str, latency_ms: float,
                       **kwargs):
        """记录工具调用事件（审计专用）"""
        await self.log_event(
            event=event,
            level="info",
            session_id=session_id,
            tool=tool,
            params=params,
            decision=decision,
            latency_ms=latency_ms,
            **kwargs
        )
    
    async def log_security(self, event: str, session_id: str, 
                           action: str, reason: str, **kwargs):
        """记录安全事件"""
        await self.log_event(
            event=event,
            level="warning",
            session_id=session_id,
            action=action,
            reason=reason,
            **kwargs
        )
    
    async def log_llm(self, event: str, session_id: str, 
                      model: str, input_tokens: int, output_tokens: int,
                      latency_ms: float, cost_usd: float = 0.0, **kwargs):
        """记录 LLM 调用事件（成本追踪）"""
        await self.log_event(
            event=event,
            level="info",
            session_id=session_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            **kwargs
        )
    
    async def log_error(self, event: str, session_id: str = None,
                        error: str = "", traceback: str = "", **kwargs):
        """记录错误事件"""
        await self.log_event(
            event=event,
            level="error",
            session_id=session_id,
            error=error,
            traceback=traceback[:2000] if traceback else "",  # 限制长度
            **kwargs
        )
    
    # ========== 内部实现 ==========
    
    async def _enqueue(self, entry: LogEntry):
        """将日志条目加入缓冲区"""
        category = self.CATEGORIES.get(entry.event, "system")
        
        if category not in self._buffers:
            self._buffers[category] = deque(maxlen=self.max_buffer_size)
            self._locks[category] = asyncio.Lock()
        
        self._buffers[category].append(entry)
        
        # 如果缓冲区满了，立即刷新
        if len(self._buffers[category]) >= self.max_buffer_size:
            await self._flush_category(category)
    
    async def _flush_loop(self):
        """后台定时刷新循环"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.flush_interval_ms / 1000)
                await self._flush_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[JSONL] 刷新循环异常: {e}")
    
    async def _flush_all(self):
        """刷新所有类别的缓冲区"""
        for category in list(self._buffers.keys()):
            await self._flush_category(category)
    
    async def _flush_category(self, category: str):
        """刷新单个类别的缓冲区到磁盘"""
        if category not in self._buffers or not self._buffers[category]:
            return
        
        async with self._locks[category]:
            entries = list(self._buffers[category])
            self._buffers[category].clear()
        
        if not entries:
            return
        
        try:
            # 按日期分组（同一天的事件写入同一文件）
            by_date: Dict[str, List[LogEntry]] = {}
            for entry in entries:
                date_str = datetime.fromtimestamp(entry.ts).strftime("%Y-%m-%d")
                by_date.setdefault(date_str, []).append(entry)
            
            for date_str, day_entries in by_date.items():
                await self._write_entries(category, date_str, day_entries)
                
        except Exception as e:
            logger.error(f"[JSONL] 刷新失败: {e}")
    
    async def _write_entries(self, category: str, date_str: str, 
                             entries: List[LogEntry]):
        """将条目写入具体文件"""
        # 确定文件路径
        if category in ("sessions", "tasks", "subagents"):
            # 这些类别按 session_id/task_id/agent_id 分文件
            by_id: Dict[str, List[LogEntry]] = {}
            for entry in entries:
                id_key = entry.session_id or entry.task_id or entry.agent_id or "unknown"
                by_id.setdefault(id_key, []).append(entry)
            
            for id_key, id_entries in by_id.items():
                file_path = self._get_file_path(category, date_str, id_key)
                await self._append_to_file(file_path, id_entries)
        else:
            # system, audit 按日期统一文件
            file_path = self._get_file_path(category, date_str)
            await self._append_to_file(file_path, entries)
    
    def _get_file_path(self, category: str, date_str: str, 
                       id_key: str = None) -> Path:
        """获取日志文件路径"""
        dir_path = self.base_dir / category / date_str
        dir_path.mkdir(parents=True, exist_ok=True)
        
        if id_key:
            # 检查是否需要轮转（文件太大）
            base_file = dir_path / f"{id_key}.jsonl"
            if base_file.exists() and base_file.stat().st_size > self.max_file_size:
                # 轮转：重命名旧文件，创建新文件
                idx = 1
                while (dir_path / f"{id_key}.{idx}.jsonl").exists():
                    idx += 1
                base_file.rename(dir_path / f"{id_key}.{idx}.jsonl")
            return base_file
        else:
            return dir_path / f"{category}.jsonl"
    
    async def _append_to_file(self, file_path: Path, entries: List[LogEntry]):
        """追加写入文件"""
        path_str = str(file_path)
        
        # 获取或创建文件句柄
        if path_str not in self._files:
            self._files[path_str] = open(file_path, "a", encoding="utf-8")
            self._file_sizes[path_str] = file_path.stat().st_size if file_path.exists() else 0
        
        f = self._files[path_str]
        lines = [e.to_jsonl() + "\n" for e in entries]
        text = "".join(lines)
        
        # 在 executor 中执行同步 IO
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, f.write, text)
        await loop.run_in_executor(None, f.flush)
        
        self._file_sizes[path_str] = self._file_sizes.get(path_str, 0) + len(text.encode("utf-8"))
    
    # ========== 查询工具 ==========
    
    def query(self, date_str: Optional[str] = None,
              event: Optional[str] = None,
              session_id: Optional[str] = None,
              level: Optional[str] = None,
              limit: int = 1000) -> List[Dict]:
        """同步查询日志（用于命令行工具）"""
        results = []
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        for category_dir in self.base_dir.iterdir():
            if not category_dir.is_dir():
                continue
            date_dir = category_dir / date_str
            if not date_dir.exists():
                continue
            
            for log_file in date_dir.iterdir():
                if not log_file.suffix == ".jsonl":
                    continue
                
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            
                            # 过滤
                            if event and record.get("event") != event:
                                continue
                            if session_id and record.get("session_id") != session_id:
                                continue
                            if level and record.get("level") != level:
                                continue
                            
                            results.append(record)
                            if len(results) >= limit:
                                return results
                except Exception as e:
                    logger.warning(f"[JSONL] 读取日志文件失败 {log_file}: {e}")
        
        return results
    
    def replay_session(self, session_id: str, date_str: Optional[str] = None) -> List[Dict]:
        """Replay 单个会话的完整事件流"""
        return self.query(date_str=date_str, session_id=session_id, limit=10000)
    
    def get_stats(self, date_str: Optional[str] = None) -> Dict:
        """获取日志统计"""
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        stats = {
            "date": date_str,
            "total_events": 0,
            "events_by_type": {},
            "sessions": set(),
            "files": 0,
        }
        
        for category_dir in self.base_dir.iterdir():
            if not category_dir.is_dir():
                continue
            date_dir = category_dir / date_str
            if not date_dir.exists():
                continue
            
            for log_file in date_dir.iterdir():
                if not log_file.suffix == ".jsonl":
                    continue
                stats["files"] += 1
                
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            
                            stats["total_events"] += 1
                            event_type = record.get("event", "unknown")
                            stats["events_by_type"][event_type] = stats["events_by_type"].get(event_type, 0) + 1
                            
                            sid = record.get("session_id")
                            if sid:
                                stats["sessions"].add(sid)
                except Exception:
                    pass
        
        stats["sessions"] = len(stats["sessions"])
        return stats


# 全局单例
_jsonl_logger: Optional[JSONLLogger] = None


def get_jsonl_logger(base_dir: str = "./tent_logs") -> JSONLLogger:
    """获取全局 JSONLLogger 实例"""
    global _jsonl_logger
    if _jsonl_logger is None:
        _jsonl_logger = JSONLLogger(base_dir)
    return _jsonl_logger
