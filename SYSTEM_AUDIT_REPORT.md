# Tent OS 系统审查报告

## P0 严重问题（必须修复）

### 1. Scheduler Worker：sqlite同步阻塞事件循环
**位置**: `tent_os/scheduler/worker.py:24-258`
**问题**: `self.db = sqlite3.connect(db_path)` 创建同步连接，所有 `self.db.execute()` / `self.db.commit()` 在 async 方法中直接调用，阻塞整个事件循环。
**影响**: 任何数据库操作都会暂停所有并发任务的处理。在并发场景下性能断崖式下降。
**修复**: 使用 `aiosqlite` 或 `asyncio.to_thread()` 包装同步调用。

### 2. API Server：sqlite同步阻塞事件循环  
**位置**: `tent_os/api/server.py:178, 324-345, 578, 1155, 1219`
**问题**: `_query_tasks_by_session()` / `_query_all_tasks()` 是同步方法，在 `ui_tasks()`, `get_task_status()`, `get_task_result()` 等 async endpoint 中直接调用。
**影响**: 每次查询任务状态都阻塞事件循环，在高频轮询场景下（如测试脚本每0.1秒轮询）造成全局卡顿。
**修复**: 使用 `asyncio.to_thread()` 包装查询。

## P1 重要问题（建议修复）

### 3. bare except 吞异常
**位置**: `tent_os/governance/worker.py:3052`, `tent_os/governance/subagent.py:442`
**问题**: `except:` 捕获所有异常包括 `KeyboardInterrupt` 和 `SystemExit`，且吞掉异常信息。
**影响**: 生产环境中难以调试json解析失败等问题。
**修复**: 改为 `except Exception:` 并记录日志。

### 4. 全局错误计数器不按 session 区分
**位置**: `tent_os/governance/worker.py:111-112, 1087, 1102-1103, 1180, 3943`
**问题**: `_recent_message_count` / `_recent_error_count` 是 Worker 实例级变量，所有 session 共享。
**影响**: session A 的大量错误会提高全局错误率，导致 session B 的认知预算被错误地降低。
**修复**: 改为按 session 存储计数器。

### 5. `_compacting_sessions` 永不清理
**位置**: `tent_os/governance/worker.py:120, 941, 1849-1851`
**问题**: session_id 加入 set 后只在成功 compaction 后 discard。如果 compaction 失败或异常，永远留在 set 中。
**影响**: 长期来看，被污染的 session 永远无法再次触发 compaction。
**修复**: 使用 `try/finally` 确保 discard，或添加 TTL 过期机制。

### 6. R1 冷启动超时
**位置**: `tent_os/governance/worker.py:74-145` (初始化), `_handle_chat_message`
**问题**: Worker 初始化时加载大量模块（Brain v2, Claude Code, Session Scheduler, Promise Tracker, Adaptive Thresholds）。第一个请求触发完整流程（安全预判断→直觉路由→LLM调用），所有初始化都在请求路径上串行执行。
**影响**: 系统重启后首个请求超时（90秒不够）。
**修复**: 
- 添加预热机制（启动时发送一条 dummy 消息走完初始化）
- 或将重量级初始化移到 `start()` 中而非 `__init__`

## P2 优化建议

### 7. `asyncio.get_event_loop()` 已废弃
**位置**: `tent_os/api/server.py:149, 251, 263, 275, 292, 294, 307, 319, 385, 410, 419`
**问题**: Python 3.10+ 中 `asyncio.get_event_loop()` 在协程中已废弃，可能返回已关闭的 loop。
**修复**: 改为 `time.time()` 或 `asyncio.get_running_loop().time()`。

### 8. 全局 LLM Semaphore 可能饥饿
**位置**: `tent_os/scheduler/plan_executor.py`（推测）
**问题**: SessionScheduler 使用全局 Semaphore(8)，一个 session 的 Tool Loop 可能连续占用多个 slot。
**影响**: 极端并发下，某些 session 可能被饿死。
**修复**: 每个 session 限制最大并发 LLM 调用数（如每个 session 最多占 2 个 slot）。
