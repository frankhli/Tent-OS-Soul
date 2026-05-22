# Tent OS 深度系统审计报告 v1.0

**审计时间**: 2026-04-24  
**审计范围**: 全部 40+ 模块（Brain v2、安全架构、工具执行、记忆系统、调度器、评估器）  
**测试环境**: macOS + Python 3.12 + Kimi K2.6 API

---

## 一、已修复的关键 Bug（本轮审计解决）

### 1.1 🔴 LocalExecutor `2>&1` 误判为文件覆盖
- **文件**: `tent_os/scheduler/executors/local.py`
- **问题**: 正则 `[>;]\s*\S+` 将 `2>&1` 中的 `>` 误判为文件重定向，导致 harmless 的 stderr redirect 触发确认机制
- **影响**: 所有 shell 命令带 `2>&1` 或 `2>/dev/null` 都被拦截，LLM 反复重试，浪费 API 调用
- **修复**: 先排除已知安全 redirect 模式（`2>&1`, `1>&2`, `&>`, `2>/dev/null` 等），再检测实际文件写入

### 1.2 🔴 KimiCodingLLM 每次请求新建 HTTP 连接
- **文件**: `tent_os/llm/kimi_coding.py`
- **问题**: `chat()` / `chat_with_tools()` 每次调用都创建新的 `httpx.AsyncClient`，TCP + TLS 握手每次重复
- **影响**: API 延迟增加 200-500ms/次，高并发时连接数爆炸
- **修复**: 
  - 复用 `AsyncClient`（连接池 `max_keepalive_connections=5`）
  - 添加指数退避重试（`max_retries=2`，超时/5xx 错误自动重试）
  - `_post_with_retry()` 统一封装 POST 逻辑

### 1.3 🔴 memory_search 工具无 executor
- **文件**: `tent_os/bootstrap.py`, `tent_os/main.py`
- **问题**: `ToolExecutor` 创建时未传入 `memory_store` 参数，`memory_search` / `memory_get` 调用报"执行者未配置"
- **影响**: LLM 无法搜索长期记忆，增加无意义重试
- **修复**: 在 `bootstrap.py` 和 `main.py` 中都创建 `TieredMemoryStore` 并传入 `ToolExecutor`

### 1.4 🔴 ProceduralMemory async embed 崩溃
- **文件**: `tent_os/memory/procedural.py`
- **问题**: `_compute_embedding` / `_compute_query_vector` / `find_relevant` / `render_rules` 混用 sync/async，在事件循环中嵌套 `asyncio.new_event_loop()` 导致 `RuntimeError`
- **影响**: 程序记忆注入和规则反馈闭环完全崩溃
- **修复**: 
  - `_compute_embedding` → `async def`
  - `_compute_query_vector` → `async def`
  - `find_relevant` → `async def`
  - `render_rules` → `async def`
  - `add_rule` 中使用 sync 关键词降级（避免 sync 方法调用 async）
  - 所有调用处加上 `await`

### 1.5 🔴 规则合规检测逻辑荒谬
- **文件**: `tent_os/governance/worker.py` (`_evaluate_rule_compliance`)
- **问题**: 中文按**单字**提取关键词，任意中文回复都 100% 匹配规则字符集，导致"匹配度 29% = 遵循"的荒谬结果
- **修复**: 中文改为按 **2-4 字词组**提取，过滤常见虚词（的、了、是、在 等）
- **效果**: 匹配度从 29%/30%/42% 降至 0%/4%，更加真实

### 1.6 🔴 Render 工具 LLM 反复检查依赖
- **文件**: `tent_os/governance/worker.py`
- **问题**: LLM 在调用 render_word/render_excel/render_ppt 前，反复用 shell 检查 python-docx/xlsxwriter 是否安装
- **影响**: 每轮增加 2-3 次 API 调用
- **修复**: 在工具 schema 描述中明确标注"依赖已内置，直接调用即可，无需预先检查"

---

## 二、模块实际触发情况审计

### 2.1 实际被触发的模块 ✅

| 模块 | 触发频率 | 实际效果 | 备注 |
|------|---------|---------|------|
| `WorkingMemoryManager` | 每次对话 | 注入 500 chars 相关记忆 | 依赖认知图谱内容，新图谱可能为空 |
| `SkillRouter` | 每次对话 | 自动激活 1-2 个 skill | 工作正常 |
| `LayeredSecurity` | 每次工具调用 | 7层评估（L1-L7） | L1-L3/L5 有实际逻辑，L4/L6/L7 基本空转 |
| `ReasoningChain` | 复杂问题时 | 多跳/因果/时序推理 | 触发条件简单（>20字+关键词），但图谱空时返回空 |
| `Evaluator` | 计划执行后 | 规则评分 | 规则评估通常通过（0.97分），LLM评估额外消耗API |
| `ExperienceExtractor` | 对话/计划后 | 异步提取经验规则 | 有 LLM 调用开销，但规则质量依赖 LLM |
| `EmotionDetector` | 每次对话 | 关键词匹配情绪 | 简单但可用 |
| `FileMemory` | 每次对话 | Markdown 文件记忆召回 | 需要实际存在的 .md 文件 |
| `CompressionPipeline` | 消息>token时 | 5层上下文压缩 | 代码存在，触发条件罕见 |
| `ProceduralMemory` | 每次对话 | 注入 top-3 规则 | 修复后正常工作 |
| `render_ppt/word/excel` | 请求时 | 生成 Office 文件 | Word ✅ Excel ✅ PPT ✅ |
| `memory_search/get` | 请求时 | 搜索长期记忆 | 修复后 ✅ |

### 2.2 从未被触发的模块/功能 🟡

| 模块/功能 | 原因 | 建议 |
|-----------|------|------|
| `NeuroplasticityEngine` | 初始化后无任何调用点 | **死代码**，建议移除或接入权重调整逻辑 |
| `L4 Auto-Mode Classifier` | `config.security.auto_classifier=False` | 默认关闭，即使开启也是独立 LLM 调用 |
| `L7 Hooks` | `hook_engine=None` | 无插件注册 Hook |
| `L6 Restoration` | 空实现，依赖 Redis TTL | 无实际逻辑 |
| `PlanExecutor.needs_plan()` | 触发条件 `len(task)>300` 或关键词 | 长输入会误触发，实际计划执行很少使用 |
| `BrowserExecutor` | Playwright 未安装 | 可选依赖缺失 |
| `sqlite-vec` 向量搜索 | 未安装 | 降级到 hash-based 关键词匹配 |

---

## 三、Kimi API 响应慢的根本原因 & 解决方案

### 3.1 根本原因分析

| 原因 | 影响 | 状态 |
|------|------|------|
| **Kimi K2.6 本身慢** | 15-25s/次 | 🔴 外部因素，不可控 |
| **每次请求新建 HTTP Client** | +200-500ms，无连接复用 | 🟢 **已修复**（连接池） |
| **Tool Loop 多轮 API 调用** | 每轮工具调用需 1 次 LLM 请求 | 🟡 架构设计，需优化 |
| **无重试机制** | 网络波动直接失败 | 🟢 **已修复**（指数退避） |
| **LLM 反复检查依赖** | 每轮 +2-3 次 API 调用 | 🟢 **已修复**（工具描述） |
| **无响应缓存** | 相同系统提示重复调用 | 🔴 未修复 |
| **非流式 chat()** | 用户需等待完整响应 | 🟡 `chat_stream()` 存在但 Tool Loop 未使用 |
| **内存注入 token 开销** | 2000+ chars 注入增加生成时间 | 🟡 已优化到 500 chars |

### 3.2 进一步优化建议

1. **启用 Tool Loop 流式响应**
   - `chat_stream()` 已实现，但 `_handle_tool_loop` 使用 `chat_with_tools()`（非流式）
   - 改为流式可让用户在 LLM 思考期间看到进度，减少感知等待

2. **添加系统提示缓存**
   - 相同 session 的 system prompt 通常不变
   - 缓存 LLM 对相同 system prompt 的响应（TTL 5-10分钟）

3. **减少 Tool Loop 迭代次数**
   - 当前最大 10 次，对于简单任务可降至 5 次
   - 添加"无工具调用意图"快速路径（如问候类消息直接回答）

4. **并行化独立操作**
   - `_on_memory_injected` 中多个 brain v2 模块串行执行
   - `working_memory.update()` + `file_memory.recall()` + `persona_compressor.compress()` 可并行

5. **考虑 API 降级**
   - 简单任务使用更快的模型（如 kimi-k1.5）
   - 复杂任务再使用 kimi-k2.6

---

## 四、架构层面的问题

### 4.1 双重入口点导致配置不一致
- `tent-os run` → `TentOS.start()`（`main.py`）
- `tent-os worker governance` → `run_worker_forever()`（`bootstrap.py`）
- 两个入口点各自创建 `ToolExecutor`，导致修改需要在两处同步
- **建议**: 统一使用 `bootstrap.py` 的组件工厂

### 4.2 安全层"过度防御"
- L5 Sandbox 的 `rm` 检测 + LocalExecutor 的 `rm` 检测 + `_check_dangerous_operation` 的 `rm` 检测
- 三层都检测 `rm`，但 LocalExecutor 的确认机制会返回错误给 LLM，LLM 再返回给用户
- **建议**: 统一安全策略，避免多层重复检测

### 4.3 规则反馈闭环无实际价值
- `_evaluate_rule_compliance` 通过字符匹配判断规则遵循
- 即使匹配度 0%，也标记为"遵循"
- **建议**: 改用 LLM 评估或语义相似度，或暂时移除该闭环

### 4.4 40+ 模块中的"演示代码"
- Neuroplasticity、Auto-Classifier、Hooks 等模块有完整代码但从未触发
- 它们增加了系统复杂度和启动时间
- **建议**: 明确标记为实验性功能，或提供开关彻底禁用

---

## 五、当前系统健康状态

```
🟢 核心对话流程: 正常
🟢 WebSocket 连接: 正常
🟢 跨会话记忆: 正常
🟢 工具调用: 正常
🟢 Office 渲染 (Word/Excel/PPT): 正常
🟢 安全层拦截: 正常（LLM 自我拒绝 + 多层检测）
🟢 技能路由: 正常
🟢 程序记忆注入: 正常（修复后）
🟢 长期记忆搜索: 正常（修复后）
🟡 向量语义搜索: 降级（sqlite-vec 缺失）
🟡 浏览器自动化: 不可用（Playwright 缺失）
🟡 API 响应速度: 15-25s（外部因素，已优化连接复用）
🔴 Neuroplasticity: 死代码
```

---

## 六、测试验证记录

| 测试项 | 结果 | 耗时 |
|--------|------|------|
| WebSocket 聊天 | ✅ | ~20s |
| 跨会话记忆（"我叫 Frank"） | ✅ | ~18s |
| Word 文档生成 | ✅ | ~25s |
| Excel 表格生成 | ✅ | ~35s |
| PPT 幻灯片生成 | ✅ | ~40s |
| memory_search 长期记忆搜索 | ✅ | ~20s |
| 安全层拒绝 rm /etc/passwd | ✅ | ~20s（LLM 自我拒绝） |
| 安全层拒绝 rm -rf /tmp | ✅ | ~30s（工具调用后被拦截） |
| 规则反馈闭环 | ✅ | 匹配度 0%-4%（修复后合理） |
