# Tent OS vs OpenClaw 功能差异分析

> 分析日期: 2026-04-22
> 分析范围: Tent OS PRD 需求 vs 当前已实现 vs OpenClaw 全部功能

---

## 一、核心定位差异

| 维度 | Tent OS | OpenClaw |
|------|---------|----------|
| **定位** | 企业级 Agent 操作系统内核 | 个人 AI 助手 Gateway |
| **架构** | 三大进程隔离 + 全异步 + 状态外存 | 单体 Node.js 应用 + 插件化 |
| **目标用户** | Agent 开发者、企业自动化团队、机器人厂商 | 个人用户、极客 |
| **状态管理** | 无状态（Redis 外存），进程可任意重启 | 有状态（本地 SQLite + 文件） |
| **部署模式** | 服务端/容器化，多实例扩展 | 单机运行，个人设备 |
| **多租户** | Phase 3 目标 | 单用户设计 |
| **代码量** | ~5000 行 Python | ~6784 个 TS 文件 |

**结论**: 两者不是竞品，是不同层。OpenClaw 是"个人助手外壳"，Tent OS 是"Agent 操作系统内核"。

---

## 二、Tent OS PRD 需求 → 实现状态对照

### Phase 1 (0-2月): Mock 执行者全异步闭环验证

| PRD 需求 | 实现状态 | 验证方式 |
|----------|---------|---------|
| 三大进程（记忆/治理/调度）隔离运行 | ✅ 完成 | `main.py` 一键启动 |
| NATS JetStream 消息总线 | ✅ 完成 | Stream + Consumer 正确注册 |
| Redis 会话状态存储 | ✅ 完成 | `RedisSessionStateStore` |
| 记忆注入（异步 + 线程池） | ✅ 完成 | AI 回复引用"上次聊到酒店运营" |
| 记忆摄入（对话保存） | ✅ 完成 | `memory.ingest` → `TieredMemoryStore` |
| TieredMemoryStore L0/L1/L2 | ✅ 完成 | SQLite + 文件系统 |
| 程序记忆（ProceduralMemory） | ✅ 完成 | `procedural.py` 416 行完整实现 |
| 纯 Python 向量检索 | ✅ 完成 | `PurePythonVectorSearch`（余弦相似度） |
| Mock 执行者 | ✅ 完成 | `MockExecutor` |
| Webhook Gateway | ✅ 完成 | FastAPI + SQLite 查询 reply_to |
| Kill Switch 紧急停止 | ✅ 完成 | `emergency.stop` NATS 主题 |
| API Server (HTTP + WebSocket) | ✅ 完成 | 端口 8002/8003 |
| 前端 Control UI | ✅ 完成 | React 18 + Vite |
| Docker 部署 | ✅ 完成 | Dockerfile + docker-compose |
| 端到端延迟 < 15s | ✅ 达成 | 实测 ~10-15s |

### Phase 2 (2-4月): 真实执行者 + 向量检索 + Plan 审批界面

| PRD 需求 | 实现状态 | 差距说明 |
|----------|---------|---------|
| **真实执行者** | | |
| LocalExecutor（shell/file/http/directory） | ✅ 完成 | 白名单 + 黑名单 + 路径限制 |
| SandboxExecutor（Docker 隔离） | ⚠️ 基础 | 有实现，但默认已关闭 |
| BrowserExecutor（Playwright） | ⚠️ 可选 | 代码完整，Playwright 未安装 |
| 睿尔曼机械臂执行者 | ❌ 未实现 | 只有 PRD 代码示例 |
| 闪送人类执行者 | ❌ 未实现 | 只有 PRD 代码示例 |
| **向量检索** | | |
| 纯 Python 向量搜索（L0 层） | ✅ 完成 | 余弦相似度计算 |
| Embedding 生成（真实语义向量） | ❌ 未实现 | 当前用关键词匹配，无 embedding 模型调用 |
| sqlite-vec 扩展支持 | ⚠️ 降级 | 安装失败时自动 fallback 到纯 Python |
| **治理增强** | | |
| ReAct Tool Loop | ✅ 完成 | 默认所有对话走 Tool Loop |
| Plan/Execute 判断 | ✅ 完成 | `needs_plan()` + `generate_plan()` |
| Evaluator 评估器 | ✅ 完成 | 5 维度评分 + 重试机制 |
| PolicyEngine 策略引擎 | ✅ 完成 | YAML 规则 + 确定性执行 |
| SegmentedPromptCache | ⚠️ 框架 | 有 6 层设计，但未真正对接 API cache_control |
| **多模型 Provider** | | |
| OpenAI 兼容 Provider | ✅ 完成 | DeepSeek/Groq/Together 等 |
| Anthropic Provider | ✅ 完成 | Claude API |
| Ollama Provider | ✅ 完成 | 本地模型 |
| Kimi Coding Provider | ✅ 完成 | SSE 流式 + reasoning_content + Tool Calling |
| **Skills 系统** | ✅ 完成 | 关键词匹配激活，2 个内置 Skill |
| **SOUL.md 驱动** | ✅ 完成 | `system_prompt.py` 动态读取 + 热更新 |
| **Compaction 自动摘要** | ✅ 完成 | 消息 > 15 条自动摘要 |
| **Dreaming 梦境模式** | ✅ 完成 | 定时任务，记忆自整理 |
| **CLI 工具** | ⚠️ 基础 | `init`/`worker`/`run`，无 doctor/onboard |
| **Plan 审批 UI** | ❌ 未实现 | 只有后端 `governance.approval.request` 消息 |
| **Plugin Manager** | ⚠️ 框架 | 有 `PluginManager` 类，未真正加载外部插件 |
| **MCP 客户端** | ⚠️ 框架 | `mcp_client.py` 有基础代码 |

### Phase 3 (4-6月): 多租户 + 企业版私有部署

| PRD 需求 | 实现状态 |
|----------|---------|
| 多租户隔离 | ❌ 未开始 |
| 企业版私有部署 | ❌ 未开始 |
| SSO/OAuth 集成 | ❌ 未开始 |
| 审计日志完整链路 | ⚠️ 部分（Kill Switch 有审计） |
| 水平扩展（多治理进程实例） | ⚠️ 架构支持（Redis 共享状态 + NATS 消费者组） |

---

## 三、OpenClaw 有 → Tent OS 没有的功能

### 3.1 消息渠道（OpenClaw 核心优势）

OpenClaw 支持 **25+ 消息渠道**：
WhatsApp、Telegram、Slack、Discord、iMessage、BlueBubbles、Google Chat、Signal、IRC、Microsoft Teams、Matrix、Feishu、LINE、Mattermost、Nextcloud Talk、Nostr、Synology Chat、Tlon、Twitch、Zalo、Zalo Personal、WeChat、QQ、WebChat、Voice Call

**Tent OS**: 只有 **WebSocket + HTTP API**。

**建议**: 如果 Tent OS 定位是"企业级内核"，消息渠道应该由上层应用接入，内核提供标准 Webhook/HTTP 接口即可。但如果是做个人助手，这是重大缺失。

### 3.2 多模态能力

| 能力 | OpenClaw | Tent OS |
|------|---------|---------|
| 图像生成 | ✅ (DALL-E, Stable Diffusion, ComfyUI, FAL) | ❌ |
| 视频生成 | ✅ | ❌ |
| 音乐生成 | ✅ | ❌ |
| 语音合成 (TTS) | ✅ (ElevenLabs, OpenAI, 本地 MLX) | ❌ |
| 语音识别 | ✅ (Deepgram, Whisper) | ❌ |
| 实时语音通话 | ✅ (Voice Call 插件) | ❌ |

**建议**: PRD 未明确要求多模态。如果目标用户是企业自动化/机器人厂商，多模态优先级低。如果扩展到个人助手场景，需要补充。

### 3.3 信息获取能力

| 能力 | OpenClaw | Tent OS |
|------|---------|---------|
| Web 搜索 | ✅ (Brave Search, DuckDuckGo, Exa, Firecrawl) | ⚠️ 只有 `http_request` 工具 |
| 网页抓取 | ✅ (Firecrawl, 内置 web-fetch) | ⚠️ 只有 `http_request` 工具 |
| 链接理解 | ✅ (`link-understanding` 模块) | ❌ |

**建议**: `web_search` 和 `web_fetch` 作为内置工具加入，优先级 **高**。这是 Agent 获取实时信息的基础能力。

### 3.4 自动化与扩展

| 能力 | OpenClaw | Tent OS |
|------|---------|---------|
| Cron 定时任务 | ✅ 成熟（`cron add/list/show/runs` CLI） | ⚠️ `BackgroundTaskScheduler` 基础版 |
| Hooks 事件驱动 | ✅ (command:new, reset, stop, lifecycle) | ❌ |
| Auto-reply 自动回复 | ✅ | ❌ |
| Taskflow 工作流 | ✅ | ❌ |
| Standing Orders | ✅ | ❌ |

**建议**: Cron 和 Hooks 对"自主后台任务"很重要。当前 `BackgroundTaskScheduler` 只是轮询 HEARTBEAT.md，没有持久化调度器。

### 3.5 用户体验

| 能力 | OpenClaw | Tent OS |
|------|---------|---------|
| Canvas 实时 UI | ✅ (A2UI 渲染，可交互画布) | ❌ |
| Onboarding 向导 | ✅ (`openclaw onboard` 交互式) | ❌ |
| Doctor 诊断工具 | ✅ (`openclaw doctor` 检查配置/健康) | ❌ |
| 移动端 App | ✅ (iOS, Android, macOS, Watch) | ❌ |
| TUI 终端界面 | ✅ | ❌ |
| 配置会话管理 | ✅ | ❌ |

**建议**: Canvas 和 Onboarding 对个人用户很重要。Doctor 工具对运维很重要。

### 3.6 开发者工具

| 能力 | OpenClaw | Tent OS |
|------|---------|---------|
| Plugin SDK | ✅ (完整 SDK + 类型定义 + 测试工具) | ⚠️ 基础抽象类 |
| Agent Harness | ✅ (沙盒化 Agent 测试框架) | ❌ |
| CLI Runner | ✅ | ❌ |
| 测试基础设施 | ✅ (Vitest + 大量测试配置) | ❌ |
| TypeScript 类型安全 | ✅ | N/A (Python) |

---

## 四、Tent OS 有 → OpenClaw 没有的功能

这些是 Tent OS 的核心差异化优势：

| 能力 | Tent OS | OpenClaw |
|------|---------|----------|
| **进程隔离架构** | ✅ 三大进程独立 | ❌ 单体应用 |
| **全异步无状态** | ✅ Redis 外存 + NATS 消息 | ❌ 有状态 |
| **Plan/Execute 强制规划** | ✅ 治理进程内置 | ❌ |
| **人类审批流程** | ✅ 消息驱动审批 | ❌ |
| **PolicyEngine 确定性策略** | ✅ <0.1ms 规则执行 | ❌ |
| **Evaluator 独立评估** | ✅ Generator-Evaluator 分离 | ❌ |
| **Prompt 分层缓存** | ✅ L1-L6 分段设计 | ❌ |
| **TieredMemory L0/L1/L2** | ✅ 三层记忆 + 向量检索 | ❌ (只有单一 memory 插件) |
| **程序记忆（经验学习）** | ✅ 从失败中提取规则 | ❌ |
| **Kill Switch 紧急停止** | ✅ 物理安全底线 | ❌ |
| **Saga 事务回滚** | ✅ 执行者状态机 | ❌ |
| **HEARTBEAT.md 自主任务** | ✅ Agent 读取待办 | ⚠️ 有 cron 但无自主模式 |
| **梦境模式** | ✅ 记忆自整理 | ❌ |
| **Compaction 自动摘要** | ✅ | ❌ |
| **Embedding 向量检索** | ⚠️ 框架 | ❌ |
| **多模型 Provider 统一** | ✅ 4 个 Provider | ⚠️ 插件化，无统一抽象 |
| **Docker 多服务部署** | ✅ | ❌ (只有 all-in-one) |

---

## 五、关键差距清单（按优先级排序）

### 🔴 P0 - 阻碍 Phase 2 验证

| # | 差距 | 影响 | 工作量 |
|---|------|------|--------|
| 1 | **Embedding 生成未接入** | 向量检索只有余弦计算框架，无真实语义向量 | 中 |
| 2 | **Plan 审批 UI 缺失** | 高风险任务无法人工确认，PolicyEngine 只能 Deny | 中 |
| 3 | **API 任务结果未回传** | `POST /api/v1/tasks` 后查询 `result: null` | 小 |
| 4 | **WebSocket 客户端代理问题** | 环境有 SOCKS 代理冲突，需绕过 | 小 |

### 🟡 P1 - Phase 2 完整度

| # | 差距 | 影响 | 工作量 |
|---|------|------|--------|
| 5 | **物理执行者（机械臂/闪送）** | PRD 示例代码，未真正集成 | 大 |
| 6 | **Plugin Manager 未加载外部插件** | 只有内置执行者，无法扩展 | 中 |
| 7 | **MCP 客户端不完整** | 无法对接外部 MCP 服务器 | 中 |
| 8 | **SegmentedPromptCache 未对接 API** | 有分层设计，无 cache_control 标记 | 中 |
| 9 | **Cron 系统不够成熟** | 只有 HEARTBEAT.md 轮询，无持久化调度器 | 中 |
| 10 | **Skills 动态加载** | 目前 2 个硬编码 Skill，需支持目录扫描 | 小 |

### 🟢 P2 - 体验增强（OpenClaw 启发）

| # | 差距 | 影响 | 工作量 |
|---|------|------|--------|
| 11 | **Web 搜索工具** | Agent 无法获取实时信息 | 小 |
| 12 | **Web 抓取工具** | Agent 无法读取网页内容 | 小 |
| 13 | **Doctor 诊断工具** | 运维困难，无法自检 | 中 |
| 14 | **Onboarding 向导** | 新用户上手成本高 | 中 |
| 15 | **Hooks 事件驱动** | 无法响应系统事件自动化 | 中 |
| 16 | **消息渠道扩展** | 只有 Web，无法对接 IM | 大 |
| 17 | **Canvas 实时 UI** | 无法展示复杂交互界面 | 大 |
| 18 | **语音/多模态** | 仅限文本交互 | 大 |

### ⚪ P3 - Phase 3 企业特性

| # | 差距 | 影响 | 工作量 |
|---|------|------|--------|
| 19 | **多租户隔离** | 无法服务多个团队 | 大 |
| 20 | **SSO/OAuth** | 企业集成困难 | 中 |
| 21 | **完整审计链路** | 合规要求 | 中 |
| 22 | **水平扩展** | 架构已支持，需验证 | 小 |

---

## 六、建议开发优先级

### 立即做（本周）
1. **修复 API 结果回传** - `TaskStatusResponse` 未正确返回 LLM 回复
2. **接入 Embedding 模型** - 用 OpenAI/Kimi Embedding API 生成真实向量
3. **添加 Web 搜索工具** - 集成 Brave/DuckDuckGo API

### 短期（2-4周）
4. **Plan 审批 UI** - 前端添加审批面板，后端完善 approval 流程
5. **Plugin Manager 加载外部插件** - 支持 `plugins/` 目录动态加载
6. **MCP 客户端完善** - 对接 mcporter 或自建 MCP 客户端
7. **Cron 持久化调度器** - 用 APScheduler 替代轮询

### 中期（1-2月）
8. **Doctor 诊断工具** - `tent-os doctor` 检查配置/健康/连通性
9. **Onboarding 向导** - 交互式首次配置引导
10. **SegmentedPromptCache 对接 API** - 真正利用 Anthropic cache_control

### 长期（按需）
11. 消息渠道扩展（Feishu/Slack/WebChat 等）
12. 多租户/企业版
13. 多模态（语音/图像）
14. Canvas 实时 UI

---

## 七、一句话总结

> **Tent OS 内核架构（进程隔离、全异步、状态外存、Plan/Execute、PolicyEngine）已全部落地，Phase 1 验证通过。当前最大缺口是：Embedding 语义检索、审批 UI、Web 搜索、Plugin 生态。OpenClaw 是个人助手外壳的标杆，Tent OS 不应复制它的功能，而应保持"内核"定位，让上层应用接入 OpenClaw 式的渠道和多模态能力。**
