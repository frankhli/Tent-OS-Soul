"""Hook Engine —— 零上下文成本的事件拦截系统

借鉴 Claude Code 的 Hooks 系统，适配 Tent OS 的多进程架构：
- Hook 在配置加载时注册，运行时通过事件总线触发
- 不增加 LLM 上下文负担
- 支持 async function / shell / webhook 三种执行类型

事件点（精简到17个核心事件）：
Session 生命周期:
  - session.start      # 会话开始
  - session.end        # 会话结束
Memory:
  - memory.inject      # 记忆注入前（可修改注入内容）
  - memory.ingest      # 记忆摄入后
Plan:
  - plan.generate      # Plan 生成后
  - plan.approve       # Plan 审批时
Tool:
  - tool.assemble      # 工具池组装时（可增删改工具）
  - tool.prefilter     # 工具预过滤时
  - tool.preuse        # 工具调用前（可拦截/修改参数）★最关键
  - tool.postuse       # 工具调用后（可修改结果）
  - tool.error         # 工具报错时
Scheduler:
  - scheduler.submit   # 任务提交时
  - scheduler.complete # 任务完成时
  - scheduler.fail     # 任务失败时
Governance:
  - governance.reply   # 治理回复前（可修改回复内容）
System:
  - heartbeat.tick     # Heartbeat 触发时
  - system.error       # 系统错误时

应用场景：
- 内容审核 Hook：tool.postuse 拦截文件写入，检查敏感内容
- 成本监控 Hook：tool.preuse 记录每次 LLM 调用成本
- 自动记忆 Hook：session.end 触发对话摘要保存
- 物理安全 Hook：scheduler.submit 拦截高风险物理执行器
"""

import asyncio
import json
import subprocess
import time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum

import httpx

from tent_os.logging_config import get_logger

logger = get_logger()


class HookType(Enum):
    """Hook 执行类型"""
    ASYNC = "async"       # async function
    SHELL = "shell"       # shell command
    WEBHOOK = "webhook"   # HTTP webhook


@dataclass
class HookEvent:
    """Hook 事件对象"""
    name: str
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict:
        return {
            "event": self.name,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class HookResult:
    """Hook 执行结果"""
    allowed: bool = True          # 是否允许继续
    modified: bool = False        # 是否修改了数据
    data: Dict[str, Any] = field(default_factory=dict)  # 修改后的数据
    error: Optional[str] = None   # 错误信息
    latency_ms: float = 0.0       # 执行耗时


@dataclass
class Hook:
    """Hook 定义"""
    name: str                     # Hook 名称
    event: str                    # 监听的事件
    hook_type: HookType           # 执行类型
    # ASYNC: async callable
    # SHELL: command template string
    # WEBHOOK: URL string
    handler: Union[Callable, str]
    priority: int = 0             # 优先级（越高越先执行）
    enabled: bool = True          # 是否启用
    timeout_ms: int = 5000        # 超时时间
    # 条件过滤：只在匹配时触发
    condition: Optional[Dict[str, Any]] = None


class HookEngine:
    """Hook 引擎
    
    关键设计：
    1. 注册阶段：Hook 在启动时注册，运行时通过事件名查找
    2. 执行阶段：按优先级排序，同步执行（但每个 Hook 可异步）
    3. 拦截机制：任何一个 Hook 返回 allowed=False 就会阻断后续
    4. 修改机制：Hook 可以修改 data，后续 Hook 看到修改后的版本
    
    使用方式：
        engine = HookEngine()
        
        # 注册 async hook
        @engine.on("tool.preuse", priority=10)
        async def audit_hook(event):
            logger.info(f"工具调用审计: {event.data['tool']}")
            return HookResult(allowed=True)
        
        # 注册 shell hook
        engine.register(Hook(
            name="notify-slack",
            event="scheduler.fail",
            hook_type=HookType.SHELL,
            handler="curl -X POST https://hooks.slack.com/... -d '{\"text\":\"Task failed\"}'"
        ))
        
        # 触发事件
        result = await engine.trigger("tool.preuse", session_id="abc", data={"tool": "shell"})
        if not result.allowed:
            print("被 Hook 拦截!")
    """
    
    # 预定义的事件名
    EVENTS = {
        "session.start", "session.end",
        "memory.inject", "memory.ingest",
        "plan.generate", "plan.approve",
        "tool.assemble", "tool.prefilter", "tool.preuse", "tool.postuse", "tool.error",
        "scheduler.submit", "scheduler.complete", "scheduler.fail",
        "governance.reply",
        "heartbeat.tick", "system.error",
    }
    
    def __init__(self):
        # event_name -> List[Hook]
        self._hooks: Dict[str, List[Hook]] = {event: [] for event in self.EVENTS}
        # event_name -> List[async callable]（装饰器注册的直接函数）
        self._async_handlers: Dict[str, List[tuple]] = {event: [] for event in self.EVENTS}
        # 全局统计
        self._stats: Dict[str, Dict] = {}
    
    # ========== 注册 API ==========
    
    def register(self, hook: Hook) -> "HookEngine":
        """注册一个 Hook"""
        if hook.event not in self.EVENTS:
            logger.warning(f"[Hook] 未知事件: {hook.event}")
            return self
        
        self._hooks[hook.event].append(hook)
        # 按优先级排序
        self._hooks[hook.event].sort(key=lambda h: h.priority, reverse=True)
        logger.info(f"[Hook] 注册: {hook.name} -> {hook.event} (priority={hook.priority})")
        return self
    
    def unregister(self, name: str, event: str = None):
        """注销 Hook"""
        events = [event] if event else list(self.EVENTS)
        for evt in events:
            self._hooks[evt] = [h for h in self._hooks[evt] if h.name != name]
            self._async_handlers[evt] = [
                (n, h, p) for n, h, p in self._async_handlers[evt] if n != name
            ]
    
    def on(self, event: str, priority: int = 0, name: str = None):
        """装饰器注册 async hook
        
        使用方式：
            @engine.on("tool.preuse", priority=10)
            async def my_hook(event):
                return HookResult(allowed=True)
        """
        def decorator(func):
            hook_name = name or func.__name__
            self._async_handlers[event].append((hook_name, func, priority))
            self._async_handlers[event].sort(key=lambda x: x[2], reverse=True)
            logger.info(f"[Hook] 装饰器注册: {hook_name} -> {event} (priority={priority})")
            return func
        return decorator
    
    # ========== 触发 API ==========
    
    async def trigger(self, event_name: str,
                      session_id: str = None,
                      task_id: str = None,
                      data: Dict[str, Any] = None) -> HookResult:
        """触发事件，执行所有匹配的 Hook
        
        Returns:
            HookResult: 最终处理结果
            - allowed=False 表示被某个 Hook 拦截
            - modified=True 表示数据被某个 Hook 修改
            - data 包含修改后的数据（如果有）
        """
        if event_name not in self.EVENTS:
            logger.debug(f"[Hook] 未知事件: {event_name}")
            return HookResult(allowed=True, data=data or {})
        
        event = HookEvent(
            name=event_name,
            session_id=session_id,
            task_id=task_id,
            data=data or {},
        )
        
        result = HookResult(allowed=True, data=dict(event.data))
        
        # 收集所有 handlers（Hook 对象 + 装饰器函数）
        all_handlers = []
        
        # 1. Hook 对象
        for hook in self._hooks[event_name]:
            if not hook.enabled:
                continue
            if self._match_condition(hook.condition, event.data):
                all_handlers.append((hook.priority, hook.name, hook))
        
        # 2. 装饰器注册的函数
        for name, func, priority in self._async_handlers[event_name]:
            all_handlers.append((priority, name, func))
        
        # 按优先级排序
        all_handlers.sort(key=lambda x: x[0], reverse=True)
        
        # 顺序执行
        for priority, name, handler in all_handlers:
            start = time.time()
            try:
                if isinstance(handler, Hook):
                    hook_result = await self._execute_hook(handler, event, result.data)
                else:
                    # 装饰器注册的 async 函数
                    hook_result = await handler(event)
                    if not isinstance(hook_result, HookResult):
                        # 如果函数没有返回 HookResult，假设允许通过
                        hook_result = HookResult(allowed=True, data=result.data)
                
                hook_result.latency_ms = (time.time() - start) * 1000
                
                # 更新统计
                self._update_stats(event_name, name, hook_result)
                
                # 检查拦截
                if not hook_result.allowed:
                    logger.info(f"[Hook] {name} 拦截了 {event_name}")
                    result.allowed = False
                    result.error = hook_result.error
                    break
                
                # 合并修改后的数据
                if hook_result.modified and hook_result.data:
                    result.data.update(hook_result.data)
                    result.modified = True
                    event.data = result.data  # 后续 Hook 看到修改后的数据
                    
            except asyncio.TimeoutError:
                logger.warning(f"[Hook] {name} 执行超时 ({event_name})")
                self._update_stats(event_name, name, HookResult(error="timeout"))
            except Exception as e:
                logger.error(f"[Hook] {name} 执行异常 ({event_name}): {e}")
                self._update_stats(event_name, name, HookResult(error=str(e)))
        
        return result
    
    async def trigger_fire_and_forget(self, event_name: str,
                                       session_id: str = None,
                                       task_id: str = None,
                                       data: Dict[str, Any] = None):
        """触发事件但不等待结果（fire-and-forget）
        
        用于不需要拦截/修改的场景，如审计、通知等。
        """
        asyncio.create_task(self.trigger(event_name, session_id, task_id, data))
    
    # ========== 内置 Hook 工厂 ==========
    
    def create_audit_hook(self, jsonl_logger) -> Hook:
        """创建审计日志 Hook"""
        async def audit_handler(event: HookEvent) -> HookResult:
            if event.name == "tool.preuse":
                await jsonl_logger.log_tool(
                    event="tool.preuse",
                    session_id=event.session_id,
                    tool=event.data.get("tool", ""),
                    params=event.data.get("params", {}),
                    decision="pending",
                    latency_ms=0,
                )
            elif event.name == "tool.postuse":
                await jsonl_logger.log_tool(
                    event="tool.postuse",
                    session_id=event.session_id,
                    tool=event.data.get("tool", ""),
                    params=event.data.get("params", {}),
                    decision="completed",
                    latency_ms=event.data.get("latency_ms", 0),
                )
            elif event.name == "tool.error":
                await jsonl_logger.log_error(
                    event="tool.error",
                    session_id=event.session_id,
                    error=event.data.get("error", ""),
                )
            return HookResult(allowed=True)
        
        # 返回一个 async handler（不是 Hook 对象），用于装饰器注册
        return audit_handler
    
    def create_cost_hook(self, callback: Callable) -> Hook:
        """创建成本监控 Hook"""
        async def cost_handler(event: HookEvent) -> HookResult:
            if event.name == "tool.preuse":
                tool = event.data.get("tool", "")
                if tool in ("llm_call", "chat", "completion"):
                    # 记录 LLM 调用成本
                    pass
            return HookResult(allowed=True)
        
        return cost_handler
    
    # ========== 内部执行 ==========
    
    async def _execute_hook(self, hook: Hook, event: HookEvent, 
                            current_data: Dict) -> HookResult:
        """执行单个 Hook"""
        if hook.hook_type == HookType.ASYNC:
            if asyncio.iscoroutinefunction(hook.handler):
                return await asyncio.wait_for(
                    hook.handler(event), timeout=hook.timeout_ms / 1000
                )
            else:
                return hook.handler(event)
        
        elif hook.hook_type == HookType.SHELL:
            # 渲染命令模板
            cmd = self._render_template(hook.handler, event, current_data)
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=hook.timeout_ms / 1000
                )
                if proc.returncode != 0:
                    return HookResult(
                        allowed=True,  # shell hook 不拦截
                        error=stderr.decode("utf-8", errors="replace")[:200],
                    )
                return HookResult(allowed=True)
            except asyncio.TimeoutError:
                proc.kill()
                raise
        
        elif hook.hook_type == HookType.WEBHOOK:
            url = self._render_template(hook.handler, event, current_data)
            async with httpx.AsyncClient(timeout=hook.timeout_ms / 1000) as client:
                resp = await client.post(url, json=event.to_dict())
                if resp.status_code >= 400:
                    return HookResult(
                        allowed=True,
                        error=f"Webhook failed: {resp.status_code}",
                    )
                return HookResult(allowed=True)
        
        return HookResult(allowed=True)
    
    def _match_condition(self, condition: Optional[Dict], data: Dict) -> bool:
        """检查条件是否匹配"""
        if not condition:
            return True
        
        for key, expected in condition.items():
            actual = data.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        
        return True
    
    def _render_template(self, template: str, event: HookEvent, data: Dict) -> str:
        """渲染模板字符串"""
        result = template
        # 简单替换: {{key}} -> value
        for key, value in {**data, **event.to_dict()}.items():
            if isinstance(value, str):
                result = result.replace(f"{{{{{key}}}}}", value)
        return result
    
    def _update_stats(self, event_name: str, hook_name: str, result: HookResult):
        """更新统计"""
        key = f"{event_name}:{hook_name}"
        if key not in self._stats:
            self._stats[key] = {"calls": 0, "errors": 0, "blocked": 0, "total_latency_ms": 0}
        
        self._stats[key]["calls"] += 1
        self._stats[key]["total_latency_ms"] += result.latency_ms
        if result.error:
            self._stats[key]["errors"] += 1
        if not result.allowed:
            self._stats[key]["blocked"] += 1
    
    # ========== 查询 API ==========
    
    def get_stats(self) -> Dict:
        """获取 Hook 执行统计"""
        return {
            key: {
                **stats,
                "avg_latency_ms": round(stats["total_latency_ms"] / max(stats["calls"], 1), 2),
            }
            for key, stats in self._stats.items()
        }
    
    def list_hooks(self, event: str = None) -> List[Dict]:
        """列出已注册的 Hook"""
        result = []
        events = [event] if event else list(self.EVENTS)
        
        for evt in events:
            for hook in self._hooks[evt]:
                result.append({
                    "name": hook.name,
                    "event": hook.event,
                    "type": hook.hook_type.value,
                    "priority": hook.priority,
                    "enabled": hook.enabled,
                })
            for name, _, priority in self._async_handlers[evt]:
                result.append({
                    "name": name,
                    "event": evt,
                    "type": "async_decorator",
                    "priority": priority,
                    "enabled": True,
                })
        
        return result
