# 三巨头深度拆解 + Tent OS 化学反应路线图

> Claude Code × OpenClaw × Harness → 什么该学、什么不该学、什么只有 Tent OS 能做

---

## 一、三巨头核心能力矩阵

### 1.1 Claude Code（Anthropic，~512K行）

| 维度 | 实现深度 | 核心洞察 |
|------|----------|----------|
| **上下文压缩** | ⭐⭐⭐⭐⭐ 5层精细管道 | Budget→Snip→Microcompact→Collapse→AutoCompact，按成本排序触发 |
| **安全架构** | ⭐⭐⭐⭐⭐ 7层+Auto-Classifier | Tool Pre-filtering→Deny Rules→Permission Mode→Auto-Classifier→Sandbox→Non-restoration→Hooks |
| **Hook系统** | ⭐⭐⭐⭐⭐ 27事件点 | 零上下文成本，4种执行类型（shell/LLM/webhook/subagent） |
| **文件记忆** | ⭐⭐⭐⭐⭐ LLM召回 | 不用embedding，LLM扫描文件头选择相关记忆 |
| **子代理** | ⭐⭐⭐⭐⭐ Fork+Sidechain | 6种内置类型，byte-identical prompt缓存共享（省95% token） |
| **推测执行** | ⭐⭐⭐⭐⭐ 流式预执行 | 模型输出中检测意图，并行启动只读工具 |
| **Slot管理** | ⭐⭐⭐⭐⭐ 动态升级 | 8K→64K自动升级，99%请求保持8K |
| **IDE集成** | ⭐⭐⭐⭐⭐ 深度绑定 | VSCode/Terminal/文件diff渲染/命令补全 |
| **局限** | — | 单进程、无持久记忆（跨会话）、无物理触达、无多租户 |

### 1.2 OpenClaw（Peter Steinberger，Node.js/TS）

| 维度 | 实现深度 | 核心洞察 |
|------|----------|----------|
| **渠道集成** | ⭐⭐⭐⭐⭐ 25+渠道 | WhatsApp/Telegram/Slack/Discord/iMessage/Signal/Teams/飞书/Line/微信/QQ... |
| **Agent-native架构** | ⭐⭐⭐⭐⭐ 从 ground up | 不是chatbot加agent功能，而是为持久agent设计的内核 |
| **文件记忆** | ⭐⭐⭐⭐⭐ AGENTS.md/SOUL.md | 人类可读、可编辑、版本可控的注入文件 |
| **Skill系统** | ⭐⭐⭐⭐⭐ ClawHub | 技能市场，.skill文件定义，可安装/更新/分享 |
| **多代理路由** | ⭐⭐⭐⭐⭐ Workspace隔离 | 不同渠道/账户/peer路由到不同agent，session隔离 |
| **Voice** | ⭐⭐⭐⭐⭐ Wake+Talk | macOS/iOS/Android语音唤醒，ElevenLabs TTS |
| **Live Canvas** | ⭐⭐⭐⭐⭐ A2UI | Agent驱动的可视化工作空间 |
| **安全模型** | ⭐⭐⭐⭐ DM Pairing | 未知发送者需配对码，本地allowlist |
| **Companion Apps** | ⭐⭐⭐⭐⭐ 三端 | macOS menu bar + iOS node + Android node |
| **局限** | — | 单体Gateway（非多进程）、无物理执行者、无办公渲染、企业级安全弱 |

### 1.3 Harness（CI/CD平台，企业级）

| 维度 | 实现深度 | 核心洞察 |
|------|----------|----------|
| **Pipeline-native** | ⭐⭐⭐⭐⭐ CI/CD原生 | Agent不是外挂，是流水线里的原生步骤，改完代码自动走审批→扫描→灰度→回滚 |
| **OPA策略引擎** | ⭐⭐⭐⭐⭐ 设计即合规 | 自然语言描述规则→AI自动生成Rego代码→强制执行，ai_generated标签终身追溯 |
| **RBAC继承** | ⭐⭐⭐⭐⭐ 权限边界 | AI只能做用户本人有权限的事，没有"AI超级管理员" |
| **Knowledge Graph** | ⭐⭐⭐⭐⭐ 企业记忆 | 服务依赖、基础设施配置、历史部署、过往故障，Agent基于真实状态决策 |
| **BYOM** | ⭐⭐⭐⭐⭐ 模型无关 | Anthropic/OpenAI/Gemini/自托管，不同任务不同模型 |
| **MCP Gateway v2** | ⭐⭐⭐⭐⭐ 海关检查站 | 240+ API收敛成11个通用动词，内置内容审查+策略执行+写操作确认 |
| **故障自愈** | ⭐⭐⭐⭐⭐ 自验证+回滚 | linter→类型检查→单元测试→提交，循环检测（反复改同一个bug自动停止），部署异常自动回滚 |
| **审计追踪** | ⭐⭐⭐⭐⭐ 全生命周期 | 谁、什么时候、让AI做了什么、结果如何 |
| **局限** | — | SaaS平台（非自托管）、无物理触达、无实时对话、无办公渲染、渠道只有Webhook |

---

## 二、Tent OS 现状 honest 评估

### 2.1 硬差异化（三者都没有，必须守住）

| 能力 |  competitors | Tent OS |
|------|-------------|---------|
| **三大进程物理隔离** | ❌ Claude Code单进程 / OpenClaw单体 / Harness SaaS | ✅ Memory+Governance+Scheduler独立进程，故障不传染 |
| **状态完全外存** | ❌ Claude Code内存状态 / OpenClaw本地文件 / Harness云端 | ✅ Redis TTL，进程无状态可任意重启 |
| **物理执行者** | ❌ 三者都没有 | ✅ 机器人(realman)+闪送(flashex)+人类骑手真实触达 |
| **办公渲染矩阵** | ❌ 三者都没有 | ✅ PPT+Excel+Word+Document+Contract（~5K行纯Python） |
| **全异步消息驱动** | ⚠️ OpenClaw部分异步 / Harness流水线异步 | ✅ NATS JetStream持久化+ACK+消费者组+死信队列 |
| **Webhook Gateway** | ⚠️ Harness有Webhook / OpenClaw有Gateway | ✅ 统一外部回调入口，查询数据库reply_to转发NATS |

**结论：这6项是 Tent OS 的护城河，不能丢。**

### 2.2 Phase 1-3 新增（骨架已搭，血肉待填）

| 模块 | 当前状态 | 差距分析 |
|------|----------|----------|
| JSONL Logger | ✅ 生产可用 | 与Claude Code持平，OpenClaw没有 |
| File Memory | ⚠️ 骨架 | OpenClaw有AGENTS.md/SOUL.md/TOOLS.md注入，我们只有基础读写 |
| 5层压缩 | ⚠️ 骨架 | 有完整分层逻辑，但缺生产调参和实际验证 |
| Hook Engine | ⚠️ 骨架 | 17事件点（Claude Code有27个），缺LLM hook类型 |
| Tool Pool Assembler | ⚠️ 骨架 | 5步组装完整，但MCP集成是stub |
| Permission Mode | ⚠️ 骨架 | 4档完整，但缺UI切换和审批流程 |
| Auto Classifier | ❌ 概念验证 | 只有LLM评估+启发式预筛，没有本地轻量模型 |
| 7层安全 | ⚠️ 骨架 | 评估顺序正确，但每层都是简化实现 |
| Slot Manager | ⚠️ 骨架 | 3档完整，但流式调用不支持 |
| Subagent Spawner | ❌ 概念验证 | 有生命周期管理，但ReAct循环是简化版 |
| Prompt Cache v2 | ⚠️ 骨架 | 6层分段+Redis共享，但未完全替换旧缓存 |
| Speculative Executor | ❌ 概念验证 | 8个正则表达式，没有真正的流式AST解析 |
| Telemetry | ⚠️ 骨架 | 多维度指标完整，但缺前端可视化 |

### 2.3 缺失的能力（对标三巨头）

| 缺失项 | 来源 | 重要性 | 是否 Tent OS 该做 |
|--------|------|--------|-------------------|
| 25+消息渠道 | OpenClaw | P1 | ❌ 不是我们的赛道 |
| Voice Wake/Talk | OpenClaw | P2 | ❌ 除非做硬件 |
| Live Canvas/A2UI | OpenClaw | P2 | ❌ 办公渲染已覆盖不同场景 |
| Skill市场(ClawHub) | OpenClaw | P1 | ✅ 我们的Skill系统可扩展 |
| DM Pairing安全 | OpenClaw | P1 | ✅ 可借鉴到API认证 |
| CI/CD Pipeline-native | Harness | P2 | ❌ 不是我们的赛道 |
| OPA策略引擎 | Harness | P1 | ✅ 替换简单PolicyEngine |
| RBAC继承 | Harness | P1 | ✅ 添加用户权限系统 |
| 企业Knowledge Graph | Harness | P1 | ✅ 扩展CognitiveGraph |
| MCP Gateway注册表 | Harness | P1 | ✅ 升级Tool Pool |
| 故障自愈(验证+回滚) | Harness | P1 | ✅ 添加到Scheduler |
| ai_generated标签追溯 | Harness | P1 | ✅ 添加到所有输出 |
| 512K上下文窗口 | Claude Code | P2 | ❌ 模型能力，非架构 |
| IDE深度集成 | Claude Code | P2 | ❌ 不是我们的赛道 |
| 精细文件diff渲染 | Claude Code | P2 | ❌ 办公渲染覆盖不同场景 |

---

## 三、化学反应路线图：Tent OS 的超越路径

### 3.1 核心原则

> **不要在三巨头的赛道上追赶，要让三巨头的能力在我们的赛道上产生他们没有的化学反应。**

### 3.2 五大化学反应

#### 反应1：多进程分布式 × OPA策略 = 分布式合规引擎

**Harness 的 OPA 是单进程内的策略检查。Tent OS 可以把它分布到三个进程中：**

```
治理进程（决策层策略）
  → "这个Plan是否允许执行？"
  
调度进程（执行层策略）
  → "这个物理操作是否符合安全规范？"
  
记忆进程（审计层策略）
  → "这个记忆是否符合隐私法规？"
```

**超越点**：Harness 只能检查软件操作，Tent OS 可以检查物理操作（"机器人是否在人附近移动？"）。

#### 反应2：物理触达 × 故障自愈 = 物理世界自愈

**Harness 的故障自愈是软件层面的（代码回滚）。Tent OS 可以做物理层面的：**

```
机器人执行失败 → 自动切换备用机器人
闪送配送失败 → 自动重新下单 / 切换配送平台
物理操作超时 → 自动通知现场人员
```

**超越点**：Harness/OpenClaw/Claude Code 都只能处理数字世界的故障，Tent OS 可以处理物理世界的故障。

#### 反应3：办公渲染 × Agent-native = 端到端生产力自动化

**OpenClaw 有 Live Canvas（可视化），但只是展示。Tent OS 的 PPT/Excel/Word 是真正的生产力输出：**

```
"生成一份Q1财报PPT"
  → Agent拉取ERP数据
  → 生成Excel数据表
  → 渲染PPT幻灯片
  → 自动邮件发送给CFO
  → 记忆归档"Q1财报已生成"
```

**超越点**：三者都没有"数据→分析→渲染→分发"的端到端能力。

#### 反应4：分布式 × Knowledge Graph = 跨机器共享认知

**Harness 的 KG 是集中式的。Tent OS 的 CognitiveGraph 可以分布到记忆进程中：**

```
机器A的Agent发现"这个配置会导致故障"
  → 通过NATS广播到CognitiveGraph
  → 机器B的Agent自动获得这个知识
  → 不需要重新训练模型
```

**超越点**：Harness 的 KG 是只读的，Tent OS 的 KG 是实时共享的。

#### 反应5：文件记忆 × 多租户 = 企业级记忆隔离

**OpenClaw 的文件记忆是个人级的。Tent OS 可以做多租户级：**

```
./tent_memory/
├── tenant_acme/
│   ├── projects/
│   ├── users/
│   └── experiences/
├── tenant_techcorp/
│   ├── projects/
│   ├── users/
│   └── experiences/
```

**超越点**：OpenClaw 是个人助手，Tent OS 可以成为企业级多租户平台。

---

## 四、具体实施优先级

### Phase A：填血肉（4-6周）— 把骨架做深

| # | 任务 | 来源 | 目标 |
|---|------|------|------|
| A1 | OPA策略引擎替换PolicyEngine | Harness | 自然语言→Rego代码→强制执行 |
| A2 | RBAC用户权限系统 | Harness | AI只能做用户有权限的事 |
| A3 | 故障自愈（验证+回滚） | Harness | Scheduler添加自验证、循环检测、自动回滚 |
| A4 | File Memory注入文件规范 | OpenClaw | 支持AGENTS.md/SOUL.md/TOOLS.md自动注入 |
| A5 | Speculative Execution流式解析 | Claude Code | 接入LLM provider的stream回调 |
| A6 | Subagent完整ReAct循环 | Claude Code | 复用_handle_tool_loop逻辑 |

### Phase B：造差异化（4-6周）— 三巨头做不到的

| # | 任务 | 化学反应 |
|---|------|----------|
| B1 | 物理故障自愈 | 机器人/闪送失败自动切换 |
| B2 | 跨机器CognitiveGraph共享 | NATS广播知识更新 |
| B3 | 办公渲染端到端自动化 | 数据→分析→PPT/Excel→邮件 |
| B4 | 多租户记忆隔离 | tenant级别的File Memory |
| B5 | 分布式OPA策略 | 三个进程各自策略检查 |

### Phase C：生态扩展（6-8周）— Skill市场和渠道

| # | 任务 | 来源 |
|---|------|------|
| C1 | Skill市场（ClawHub模式） | OpenClaw |
| C2 | 企业微信/钉钉/飞书渠道接入 | OpenClaw |
| C3 | MCP Gateway注册表 | Harness |
| C4 | ai_generated标签终身追溯 | Harness |
| C5 | 前端Telemetry可视化 | 自研 |

---

## 五、诚实结论

### Tent OS 当前 vs 三巨头

| 维度 | Claude Code | OpenClaw | Harness | Tent OS |
|------|-------------|----------|---------|---------|
| **代码量** | 512K | ~50K | ~100K | 31K |
| **架构成熟度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **功能深度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **差异化壁垒** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **生产就绪度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

### 关键认知

1. **代码量差距不是能力差距**：Claude Code 的 512K 行中，60% 是 IDE 集成+UI+测试，这些不是我们的赛道。

2. **骨架是对的，血肉不够**：我们的 5层压缩、7层安全、Hook Engine 的架构方向与三巨头一致，但每个模块需要 2-3 倍代码来覆盖边缘情况。

3. **真正的超越不在功能数量，在化学反应**：三巨头各自有明确边界（IDE/消息渠道/CI-CD），Tent OS 的边界是"多进程分布式+物理触达+办公渲染"，这个交叉点只有我们能做。

4. **当前最危险的不是缺功能，是缺测试和可观测性**：31K 行代码中测试代码占比接近 0%，这是生产环境最大的风险。
