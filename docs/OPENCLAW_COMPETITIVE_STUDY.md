# OpenClaw 竞争研究报告

> 研究范围：架构、Agent Loop、工具执行、沙箱、流式输出、安全模型
> 研究时间：2026-04-23
> 目标：提取可借鉴的 UX/工具执行 polish，同时巩固 Tent OS 的架构差异化优势

---

## 1. OpenClaw 架构概览

### 1.1 核心定位
OpenClaw 是一个**自托管 Gateway**，连接多种聊天应用（WhatsApp、Telegram、Slack、Discord、Signal、iMessage 等）到 AI coding agent（基于 Pi agent core）。

### 1.2 架构分层
```
Channels (WhatsApp/Telegram/Slack/...)
Gateway (Node.js, single process)
  - WebSocket Server (typed WS API)
  - Session Store (JSONL)
  - Plugin Runtime
Pi Agent Core (embedded)
  - Model selection / failover
  - Tool loop (ReAct)
  - Prompt assembly (bootstrap files)
Sandbox Backend (optional)
  - Docker (default) / SSH / OpenShell
```

### 1.3 关键设计决策
| 维度 | OpenClaw | Tent OS |
|------|----------|---------|
| 进程模型 | 单 Gateway 进程（Stateful） | 多 Worker 进程（Stateless） |
| 状态存储 | 本地 JSONL + 内存 | Redis + SQLite 混合 |
| 消息总线 | 内存（单进程内） | NATS JetStream |
| 物理执行器 | 无 | VDA 5050 + kill switch |
| 自主任务 | Cron 外部触发 | HeartbeatEngine + IntentionRegistry |
| 记忆系统 | Session transcript + Skill | L0/L1/L2 + 程序记忆闭环 |
| 沙箱 | Docker/SSH/OpenShell 三后端 | Docker + Local（两种） |

---

## 2. OpenClaw 的 UX / 工具执行亮点（可直接借鉴）

### 2.1 工具 Profile 系统（高优先级）
OpenClaw 的工具权限模型非常成熟：

```json5
{
  tools: {
    profile: "coding",
    allow: ["group:fs", "browser"],
    deny: ["exec"],
    byProvider: {
      "google-antigravity": { profile: "minimal" }
    }
  }
}
```

工具分组：group:runtime, group:fs, group:web, group:ui, group:automation, group:media

Tent OS 借鉴方案：
- 在 tent_os.yaml 中增加 tools.profile 和 tools.allow/deny
- GovernanceWorker 在组装 prompt 前应用工具过滤
- 物理执行器单独成组 group:physical

### 2.2 工具结果截断（高优先级）
OpenClaw 有专门的 tool-result-truncation.ts，防止 oversized tool results 撑爆 LLM 上下文。

Tent OS 当前问题：Tool Loop 中工具结果直接拼接进 messages，无大小限制。
借鉴方案：在 _handle_tool_loop 中截断 tool_result（>2000 chars 截断）。

### 2.3 Block Streaming + Chunk 合并（高优先级）
OpenClaw 的流式输出控制非常精细：
- blockStreamingChunk: 800-1200 chars
- 优先段落边界，其次换行，最后句子
- blockStreamingCoalesce: 空闲合并，减少单行 spam

Tent OS 当前：_simulate_stream 固定 chunk_size=5, delay=15ms，非常粗糙。
借鉴方案：支持段落/句子边界切割，添加 coalesce 逻辑。

### 2.4 模型故障转移（中优先级）
OpenClaw 有完整的 failover 体系：Auth Profile 轮换 + Provider/Model 故障转移。
Tent OS 当前：LLM 是单点，无 failover。

### 2.5 沙箱后端多样化（中优先级）
OpenClaw 支持 Docker / SSH / OpenShell 三种沙箱后端。
Tent OS 当前：只有 Docker 和 Local 两种。

### 2.6 Elevated Exec（中优先级）
OpenClaw 有 tools.elevated 作为显式沙箱逃逸舱口。物理执行器天然就是 elevated。

### 2.7 Session 维护与 Pruning（中优先级）
OpenClaw 自动 bounds session storage（pruneAfter: 30d, maxEntries: 500）。

### 2.8 DM Pairing 安全模型（低优先级）
OpenClaw 默认对未知发送者要求 pairing code。

---

## 3. Tent OS 必须保持的架构优势

### 3.1 物理执行器安全（OpenClaw 完全没有）
- VDA 5050 状态机
- KillSwitch 全局紧急停止
- Digital Twin 预演
- 3D 路由

### 3.2 无状态治理（OpenClaw 是 Stateful 单进程）
- Redis 外存，进程可任意重启/扩容
- 流式输出通过 NATS 广播

### 3.3 自主心跳/意图系统
- HeartbeatEngine 每 30 分钟解析 HEARTBEAT.md
- IntentionRegistry 长期意图追踪

### 3.4 程序记忆闭环
- ProceduralMemory + ExperienceExtractor
- RuleCompliance 检测

---

## 4. 行动建议（按优先级排序）

### Phase 1: 立即修复 P0 Bug（已完成）
1. Heartbeat 消息不再被丢弃
2. session.wake 重复触发已加幂等检查
3. 物理执行器 schema 已注入 Plan 生成流程

### Phase 2: 借鉴 OpenClaw UX（未来 2 周）
1. 工具结果截断（_handle_tool_loop）
2. Block Streaming 优化（段落边界 + coalesce）
3. 工具 Profile 系统（allow/deny + 分组）

### Phase 3: 架构深化（未来 1 个月）
1. 模型故障转移
2. SSH 沙箱后端（适合酒店集团多店部署）
3. Session 自动 Pruning
