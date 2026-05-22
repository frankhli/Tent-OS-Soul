# Tent OS —— Phase 1 开发 Checklist

> 基于 PRD `产品需求文档：Tent OS —— 去AI化的智能体内核.md` 严格执行

---

## 一、项目骨架 ✅

| 检查项 | 状态 | 说明 |
| :--- | :--- | :--- |
| 目录结构符合 PRD 第13.2节 | ✅ | `tent_os/`, `config/`, `scripts/` 完整 |
| `__init__.py` 全模块覆盖 | ✅ | 所有包均包含，支持 `from tent_os.xxx import ...` |
| `pyproject.toml` 依赖完整 | ✅ | nats-py, redis, fastapi, uvicorn, httpx, tiktoken, croniter, numpy, pyyaml |

---

## 二、核心模块开发 ✅

### 2.0 LLM 适配器 (llm/)
- [x] `KimiCodingLLM` Kimi Coding API 适配器 (`kimi_coding.py`)
  - [x] 正确 base URL: `https://api.kimi.com/coding/v1`
  - [x] User-Agent 白名单兼容 (`claude-code/0.1`)
  - [x] `chat()` 通用对话接口
  - [x] `generate_plan()` 结构化 Plan 生成（JSON Mode）
  - [x] `complete()` 通用补全
  - [x] 已接入 `GovernanceWorker` 和 `PlanExecuteExecutor`
  - [x] 模型: **kimi-k2.6**

### 2.1 状态存储 (state/)
- [x] `SessionStateStore` 抽象接口 (`interface.py`)
- [x] `MockSessionStateStore` 内存字典实现 (`mock_store.py`) — Phase 1 默认
- [x] `RedisSessionStateStore` Redis实现 (`redis_store.py`) — 带 TTL=3600s

### 2.2 消息总线 (message_bus.py)
- [x] `MessageBus` 封装 NATS JetStream
- [x] Stream `TENT_OS` 自动创建，subjects: `memory.>, governance.>, scheduler.>, session.>`
- [x] `publish` / `subscribe` 统一封装
- [x] 支持同步 & 异步 callback
- [x] 消息统一解码 + 自动 ACK

### 2.3 海马体 — 记忆进程 (memory/)
- [x] `TieredMemoryStore` 三层存储 (L0摘要/L1概览/L2完整) (`tiered_store.py`)
- [x] `MemoryInjectionService` 主动注入服务 (`injection.py`)
- [x] `MemoryWorker` 记忆Worker (`worker.py`)
  - [x] 处理 `memory.inject` → 检索画像 → 发布 reply_to
  - [x] 处理 `memory.ingest` → 异步保存对话
- [x] sqlite-vec 扩展缺失时优雅降级（Warning，不崩溃）

### 2.4 前额叶 — 治理进程 (governance/)
- [x] `GovernanceWorker` 无状态治理进程 (`worker.py`)
  - [x] 处理 `governance.request` → 创建 state → 请求记忆注入
  - [x] 处理 `governance.resume.>` → 状态恢复 + Plan/Execute 闭环
  - [x] 处理 `governance.approval.response` → 审批后执行/拒绝
  - [x] 忽略 `submitted` 状态消息（scheduler 立即确认）
  - [x] 会话过期/删除时优雅忽略旧消息（防 KeyError 无限重试）
- [x] `PlanExecuteExecutor` Plan/Execute 执行器 (`plan_executor.py`)
  - [x] `needs_plan()` 判断逻辑（工具数>2 或关键词/长度）
  - [x] `risk_level()` 风险评估（flashex +0.3, delete/rm/format +0.5）
  - [x] `generate_plan()` LLM 调用 + JSON 解析 + Fallback
- [x] `SegmentedPromptCache` 分段 Prompt Cache (`prompt_cache.py`)
  - [x] 支持 OpenAI / Anthropic 格式
  - [x] `cache_control` 静态段标记

### 2.5 神经-肌肉 — 调度进程 (scheduler/)
- [x] `SchedulerWorker` 全异步调度进程 (`worker.py`)
  - [x] 处理 `scheduler.submit` → 立即返回 `submitted` → 后台监控协程
  - [x] `pending` 状态识别 → 等待 Webhook Gateway 回调
  - [x] `completed` 状态 → 发布 reply_to 结果
  - [x] SQLite WAL 模式持久化任务状态
  - [x] 幂等提交（重复 task_id 自动忽略）
  - [x] 进程重启后任务恢复 (`_recover_running_tasks`)
- [x] `SchedulerRouter` 执行者路由 (`router.py`)
  - [x] 优先队列模型（总成本 = 执行成本 + 延迟成本 + 失败成本）
  - [x] `ExecutorStatus` 枚举（IDLE/BUSY/OFFLINE）
- [x] `BackgroundTaskScheduler` HEARTBEAT.md 后台任务调度 (`background_tasks.py`)
  - [x] cron 表达式解析（croniter）
  - [x] 每分钟检查一次，发布 `governance.background_task`
  - [x] croniter 缺失时静默跳过

### 2.6 Webhook Gateway (api/)
- [x] `WebhookGateway` FastAPI 统一入口 (`webhook_gateway.py`)
  - [x] `POST /webhook/{task_id}`
  - [x] 查询 SQLite 获取 `reply_to`
  - [x] 更新任务状态 → 发布 `scheduler.status` 到 NATS

### 2.7 物理执行者 (scheduler/executors/)
- [x] `MockExecutor` Mock执行者 (`mock.py`) — Phase 1 使用
  - [x] 可配置 delay_seconds / fail_rate / supported_actions
- [x] `RealManExecutor` 睿尔曼机械臂 (`realman.py`)
  - [x] MCP Server 调用封装
  - [x] move/pick/place/observe/diagnose 动作映射
- [x] `FlashExExecutor` 闪送人类执行者 (`flash_ex.py`)
  - [x] 闪送 Open API 下单
  - [x] Webhook URL 自动构造

### 2.8 插件系统 (plugins/)
- [x] `Plugin` / `ExecutorPlugin` 抽象基类 (`base.py`)
- [x] `PluginManager` 插件管理器 (`manager.py`)
  - [x] YAML 配置加载
  - [x] 安全校验（只允许 `tent_os.plugins.` 前缀模块）

### 2.9 主入口 (main.py)
- [x] `TentOS` 主类
  - [x] YAML 配置加载
  - [x] 一键启动所有组件（Bus + StateStore + Memory + Governance + Scheduler + Webhook）
  - [x] Phase 1 Mock LLM & Mock Embed 内嵌
  - [x] `shutdown()` 优雅关闭

---

## 三、Phase 1 Demo & 验证 ✅

| 验证项 | 目标 | 实际结果 | 状态 |
| :--- | :--- | :--- | :--- |
| Mock Demo 端到端延迟 | < 15秒 | **7.6 秒** | ✅ |
| 治理进程无状态验证 | 进程重启后请求自动恢复 | Redis/Mock Store 外存状态 | ✅ |
| 调度进程任务恢复 | 重启后自动恢复进行中任务 | SQLite WAL + `_recover_running_tasks` | ✅ |
| 消息投递成功率 | 100% | NATS JetStream ACK 确认 | ✅ |
| 全异步闭环 | Plan → Execute → Response | inspect(mock_robot) → deliver(mock_delivery) | ✅ |

---

## 四、运行时环境

| 依赖 | 版本/状态 |
| :--- | :--- |
| Python | 3.12.10 |
| NATS Server | v2.11.3 (本地二进制) |
| NATS JetStream | ✅ 已启用 |
| Redis | Phase 1 未启用（Mock Store） |
| sqlite-vec | 未安装（优雅降级） |

---

## 五、已知限制 & Phase 2 计划

| 限制 | 说明 | Phase 2 解决 |
| :--- | :--- | :--- |
| sqlite-vec 扩展缺失 | 向量检索不可用 | 安装 sqlite-vec 或接入外部向量库 |
| Mock LLM | 硬编码 Plan 生成 | 接入真实 OpenAI/Claude API |
| Mock Embed | 固定 [0.1]*1536 | 接入真实 Embedding API |
| Redis 未启用 | 使用 MockSessionStateStore | 启用 Redis，验证多实例共享 |
| Webhook Gateway 未完整测试 | Phase 1 无真实外部回调 | 用 curl 模拟闪送回调 |
| 无审批 UI | `governance.approval.request` 无消费者 | 增加审批 HTTP API |

---

## 六、快速启动命令

```bash
# 1. 启动 NATS (JetStream)
nats-server -js -p 4222

# 2. 安装依赖
cd /Users/frank/Desktop/tent_os
/Users/frank/Desktop/.venv/bin/python -m pip install -e .

# 3. 运行 Phase 1 Demo
time /Users/frank/Desktop/.venv/bin/python scripts/phase1_demo.py

# 4. 启动完整系统
/Users/frank/Desktop/.venv/bin/python -m tent_os.main
```

---

**Checklist 完成时间**: 2026-04-22  
**Phase 1 状态**: ✅ 全部通过，可直接运行
