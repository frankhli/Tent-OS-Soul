# 三大竞品深度研究：OpenClaw / Claude Code / Harness

**研究日期**: 2026-04-24  
**研究方法**: 源代码分析 + 官方文档 + 架构对比

---

## 一、OpenClaw —— "个人 AI 助理的 Gateway"

### 核心架构

OpenClaw 是一个 **Node.js/TypeScript 单进程 Gateway**，所有功能跑在一个进程里：

```
Gateway (单进程)
  ├── Channel Manager —— 25+ 渠道统一接入
  ├── Session Router —— per-sender 会话隔离
  ├── Agent Pool —— 多 Agent 动态路由
  ├── Tool Registry —— 工具注册与调用
  ├── Skill Loader —— 文件驱动 Skill 加载
  ├── Cron Scheduler —— 定时任务
  └── Control UI —— React SPA (端口 18789)
```

### 关键设计洞察

**1. 渠道抽象层（Channel Abstraction）**

OpenClaw 的核心差异化是**消息渠道的统一抽象**。所有渠道（WhatsApp、Telegram、Slack、Discord、微信、飞书等）都实现同一个 Channel 接口：

```typescript
interface Channel {
  send(message: OutboundMessage): Promise<void>;
  onMessage(handler: (msg: InboundMessage) => void): void;
}
```

**Tent OS 可借鉴**：Webhook Gateway 已经有一部分渠道抽象，但可以扩展到更多渠道类型（微信、飞书、钉钉等）。不过 Tent OS 的赛道不是"多渠道消息助理"，而是"操作系统内核"，所以不需要复制 25+ 渠道。

**2. 文件驱动配置（AGENTS.md / SOUL.md / TOOLS.md / USER.md）**

OpenClaw 的配置完全是文件驱动的：
- `AGENTS.md` —— 行为规则、任务模板
- `SOUL.md` —— 人格定义、声音风格
- `TOOLS.md` —— 工具配置、本地备注
- `USER.md` —— 用户画像、偏好
- `memory/YYYY-MM-DD.md` —— 每日记忆日志
- `MEMORY.md` —— 长期精选记忆

**Tent OS 已借鉴**：Tent OS 的 `FileDrivenPromptBuilder` 正是借鉴了这个模式，从 `workspace/SOUL.md` 和 `workspace/AGENTS.md` 读取配置。

**但 Tent OS 做得更深**：
- OpenClaw 的文件记忆是**纯文本**，没有结构化查询
- Tent OS 的 `FileMemoryStore` 有 YAML frontmatter + LLM 相关性召回

**3. Skill 系统**

OpenClaw 有 60+ 个 Skill，每个 Skill 是一个目录，包含 `SKILL.md`（定义）+ 可选代码文件。

Skill 匹配是**基于关键词 + 向量相似度**的：
```typescript
// 简化版
function matchSkill(input: string): Skill[] {
  const embedding = getEmbedding(input);
  return skills
    .map(s => ({ skill: s, score: cosineSimilarity(embedding, s.embedding) }))
    .filter(s => s.score > 0.7)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);
}
```

**Tent OS 对比**：Tent OS 的 `SkillRouter` 也是基于关键词匹配，但没有向量相似度。这是 Tent OS 的**劣势**——Skill 匹配精度可能不如 OpenClaw。

**4. DM Pairing 安全机制**

OpenClaw 的默认安全模型非常优雅：
- 未知发件人收到**配对码**，消息不处理
- 用户通过 CLI 批准：`openclaw pairing approve <channel> <code>`
- 批准后添加到本地 allowlist

**Tent OS 可借鉴**：当前 Tent OS 的 Webhook Gateway 没有类似的"未知来源配对"机制。任何知道 webhook URL 的人都可以发送消息。这是一个**安全风险**。

**5. Sandbox 安全**

OpenClaw 的 sandbox 是** Docker 容器**，非主会话在隔离环境中运行：
```json
{
  "agents.defaults.sandbox.mode": "non-main",
  "sandbox.backend": "docker"
}
```

**Tent OS 对比**：Tent OS 有 `LocalExecutor` 的 workspace_mode（full/workspace/readonly），但没有真正的容器隔离。这是 Tent OS 的**安全劣势**。

### OpenClaw 导航结构

```
chat
control → [overview, channels, instances, sessions, usage, cron]
agent → [agents, skills, nodes, dreams]
settings → [config, communications, appearance, automation, infrastructure, aiAgents, debug, logs]
```

**Tent OS 已借鉴**：分组导航（核心/认知/监控/系统）。

---

## 二、Claude Code —— "IDE 原生 AI 编码助手"

### 核心架构

Claude Code 是**单进程架构**，深度集成在 IDE 中：

```
IDE Extension (VSCode/JetBrains)
  ├── Context Manager —— 上下文压缩与缓存
  ├── Tool Loop —— ReAct 循环
  ├── Speculative Executor —— 推测执行
  ├── Subagent Spawner —— 子代理 fork
  ├── Permission Mode Manager —— 7 档权限
  ├── Hook Engine —— 27 事件点
  └── Auto-Mode Classifier —— 轻量风险评估
```

### 关键设计洞察

**1. 5 层 Context Compression（成本递进）**

Claude Code 的压缩管道是按**成本从低到高**排序的：

| 层级 | 名称 | 成本 | 触发条件 |
|------|------|------|---------|
| L1 | Budget Reduction | 零 | always active，每条消息大小上限 |
| L2 | Snip | 低 | feature-gated，截断老历史 |
| L3 | Microcompact | 中 | always active，缓存感知的细粒度压缩 |
| L4 | Context Collapse | 高 | feature-gated，只读虚拟投影 |
| L5 | Auto-Compact | 最高 | all-else-fails，模型生成摘要 |

**关键原则**："只有前面的层无法解决问题时才触发后面的层"。

**Tent OS 对比**：Tent OS 的 `CompressionPipeline` 也是 5 层，但触发条件是单一的 token 阈值（>6000）。没有按成本递进的设计。这是**可改进点**。

**2. Speculative Execution（结果注入）**

Claude Code 的核心洞察：**在模型流式输出时，不等完整响应，先并行启动只读工具**。

但文档明确指出当前 Tent OS 的缺口：
> "推测执行的结果需要自动注入到 LLM 上下文（当前只缓存未注入）"

**Tent OS 本次修复**：已在 `_preexecute_readonly()` 中实现结果注入到 messages。

**3. Subagent Spawner —— Prompt Cache Sharing**

Claude Code 的子代理与父代理**共享 system prompt 前缀**：
- Fork 代理共享 byte-identical prompt 前缀
- 缓存节省 95% token
- Sidechain 文件隔离，父代理只看摘要

**Tent OS 对比**：Tent OS 的 `SubagentSpawner` 有 585 行代码但从未被调用。需要接入 Tool Loop 才能真正工作。

**4. Permission Mode —— 7 种模式**

Claude Code 有 7 种模式：plan / default / acceptEdits / auto / dontAsk / bypassPermissions / bubble

**Tent OS 对比**：Tent OS 有 4 档（strict/standard/auto/unrestricted），但本次修复后已深度集成到 system prompt 和工具过滤中。

---

## 三、Harness —— "Pipeline-Native AI for DevOps"

### 核心架构

Harness 不是通用 AI Agent，而是**软件交付平台的 AI 增强**：

```
Harness Platform
  ├── Software Delivery Knowledge Graph ——  Schema-driven 知识图谱
  ├── HQL (Harness Query Language) —— 领域特定查询语言
  ├── MCP Gateway —— Model Context Protocol
  ├── OPA Policy Engine —— 实时策略评估
  ├── RBAC —— 权限继承
  └── AI Agent —— 自然语言驱动的 DevOps 操作
```

### 关键设计洞察

**1. Knowledge Graph > RAG**

Harness 的核心洞察：**结构化知识图谱比原始 RAG 更可靠**。

| 维度 | Knowledge Graph | Raw API (MCP) |
|------|----------------|---------------|
| Token 成本 | ~12,000 | ~250,000-350,000 |
| LLM 调用次数 | 2-3 次 | 5+ 次 |
| 确定性 | 高（schema-driven） | 低（LLM 推断） |
| 延迟 | 低 | 高 |

**Tent OS 对比**：Tent OS 的 `CognitiveGraph` 是 SQLite 存储的简单图结构，没有 schema 定义、没有 HQL 查询语言、没有确定性保证。这是**巨大差距**。

**2. OPA 策略引擎**

Harness 的 OPA 集成是**实时**的：
- AI 生成的 pipeline 保存/运行时自动评估
- 违规时**立即阻断** + 清晰反馈
- 用户可以在 AI 聊天中修复

**Tent OS 对比**：Tent OS 的 `PolicyEngine` 是简化版，没有真正的 OPA（Open Policy Agent）集成。`LayeredSecurity` L2 调用了 policy_engine，但实际逻辑是简单的 deny 列表。

**3. RBAC —— AI 权限 = 人类权限**

Harness 的原则：
> "RBAC applies to agents exactly as it does to people"
> "Least privilege is non-negotiable"

**Tent OS 对比**：Tent OS 有 `PermissionModeManager`，但没有 RBAC 继承。AI 的权限不基于用户的权限。这是**安全风险**。

**4. ai_generated 标签 + 审计追踪**

Harness 的每一条 AI 生成内容都自动打上标签：
```yaml
ai_generated: true
```

审计追踪记录：
- Who prompted（谁发起的）
- What was created（创建了什么）
- When（时间）
- How（AI-assisted）

**Tent OS 对比**：Tent OS 没有 ai_generated 标签机制。虽然 `JSONLLogger` 记录了操作，但没有明确标记哪些内容是 AI 生成的。

**5. 自主修复（Autonomous Remediation）**

Harness 的 AI 可以：
1. 检测 canary 部署错误率飙升
2. 查询 Knowledge Graph 找到影响范围
3. 检查 feature flag 是否可以隔离
4. 执行 rollback
5. 提交 incident，标记导致问题的 PR
6. 通知团队

**Tent OS 对比**：Tent OS 没有自主修复能力。Tool Loop 需要用户触发，没有主动监控和修复机制。

---

## 四、Tent OS 的差异化定位

### Tent OS 独有的（三巨头都没有）

| 能力 | 状态 | 说明 |
|------|------|------|
| **三大进程物理隔离** | ✅ | 海马体/前额叶/神经-肌肉真正分离 |
| **状态完全外存（Redis TTL）** | ✅ | 进程崩溃不丢状态 |
| **物理执行者（机器人/闪送）** | ✅ | 连接物理世界 |
| **办公渲染（PPT/Excel/Word）** | ✅ | 独有的办公自动化 |
| **NATS 全异步消息驱动** | ✅ | 真正的分布式架构 |
| **Webhook Gateway** | ✅ | HTTP API 接入 |
| **文件记忆 LLM 召回** | ✅ | Markdown + frontmatter + 相关性评估 |

### Tent OS 缺失的（应该借鉴的）

| 能力 | 来源 | 优先级 | 实施难度 |
|------|------|--------|---------|
| **RBAC 权限继承** | Harness | P1 | 中 |
| **ai_generated 标签** | Harness | P1 | 低 |
| **Knowledge Graph Schema** | Harness | P2 | 高 |
| **OPA 策略引擎** | Harness | P2 | 高 |
| **DM Pairing / 未知来源验证** | OpenClaw | P1 | 低 |
| **Docker Sandbox 隔离** | OpenClaw | P2 | 中 |
| **Skill 向量匹配** | OpenClaw | P2 | 中 |
| **Subagent Prompt Cache Sharing** | Claude Code | P2 | 中 |
| **Context Compression 成本递进** | Claude Code | P3 | 中 |
| **IDE 深度集成** | Claude Code | — | 非赛道 |
| **25+ 消息渠道** | OpenClaw | — | 非赛道 |
| **CI/CD Pipeline-native** | Harness | — | 非赛道 |

---

## 五、Actionable Insights

### 立即做（本周）

1. **Webhook Gateway 增加来源验证** —— 借鉴 OpenClaw 的 DM Pairing，未知来源的请求需要配对码
2. **ai_generated 标签** —— 所有 PPT/Excel/Word 输出自动添加标签，所有工具执行结果标记来源
3. **RBAC 基础** —— 在 PermissionMode 中增加用户权限继承（用户是什么权限，AI 就是什么权限）

### 短期做（本月）

4. **Docker Sandbox** —— 为 shell 执行提供可选的 Docker 隔离
5. **Skill 向量匹配** —— 用 embedding 替代纯关键词匹配
6. **Subagent 接入 Tool Loop** —— 让 `_run_subagent` 真正被调用

### 中期做（下月）

7. **Knowledge Graph Schema** —— 为 CognitiveGraph 增加 schema 定义和类型注解
8. **OPA 策略引擎** —— 接入真正的 Open Policy Agent
9. **自主修复** —— Heartbeat 检测 + 自动修复流程
