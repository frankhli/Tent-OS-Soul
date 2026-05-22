# Tent OS — PRD/白皮书 vs 代码现状 Gap 分析报告

> 基于 PRD Final 2.0 + 永生延续白皮书 vs 当前代码 base（2026-05-14）

---

## 一、模型适配层（PRD §4）

### 现状
- ✅ `LLMProvider` 抽象基类（`chat`, `chat_stream`, `generate_plan`, `model_id`）
- ✅ 4个 Provider 实现：kimi_coding, openai_compatible, anthropic, ollama
- ✅ `bootstrap.py` 的 `create_llm()` 支持 provider 切换 + failover 链
- ✅ `soul_server.py` 通过 `create_llm()` 创建 LLM

### Gap
| # | 问题 | 影响 | 代码位置 |
|---|------|------|---------|
| 1.1 | `LLMProvider` 基类**缺少** `chat_with_tools` / `chat_stream_with_tools` 抽象方法 | 换 provider 后 tool calling 可能崩溃（运行时 `AttributeError`） | `llm/provider.py` line 15 |
| 1.2 | `AnthropicProvider` 有 `chat_with_tools` 但**缺少** `chat_stream_with_tools` | 切换到 anthropic 后流式 tool calling 失败 | `llm/anthropic_provider.py` |
| 1.3 | `OllamaProvider` 有 `chat_with_tools` 但**缺少** `chat_stream_with_tools` | 同上 | `llm/ollama_provider.py` line 134 |
| 1.4 | 没有**人格数据包自动注入**逻辑 | 换模型时需要手动 export/import，不是"修改配置即可" | PRD §4.2 要求 |

**结论**：模型适配层**基础设施已存在但接口不完整**，切换 provider 有风险。

---

## 二、Prompt Cache（PRD §6 + governance/prompt_cache_v2.py）

### 现状
- ✅ `governance/prompt_cache_v2.py` 有完整的 6 层分段缓存实现（L0-L5）
- ✅ `governance/worker.py` 使用了 `SegmentedPromptCache` v1，并在 Redis 可用时初始化 v2
- ✅ `governance/worker.py` 的 `_build_messages()` 使用了 prompt cache

### Gap
| # | 问题 | 影响 | 代码位置 |
|---|------|------|---------|
| 2.1 | **soul_server.py 的 `eternal_chat()` 完全未使用 prompt cache** | 每次永恒对话都重新拼接完整的 system prompt（~1500-3000字），Token 浪费严重 | `soul_server.py` lines 2182-2216 |
| 2.2 | **soul_server.py 的 `_handle_fast_chat()` 未使用 prompt cache** | 快速聊天模式同样重复构建 prompt | `soul_server.py` lines 260-280 |
| 2.3 | `SegmentedPromptCacheV2._load_from_files()` 的 segment 映射指向旧路径 | "config/IDENTITY.md"、".tent/IDENTITY.md" 等文件可能不存在，fallback 为空字符串 | `prompt_cache_v2.py` line 145 |
| 2.4 | 人格配置文件（PersonaProfile）未被纳入 prompt cache 的 segment | 最重的文本段（人格画像）没有缓存 | PRD §3.3 + §4 |

**结论**：Prompt Cache v2 是**"完整但孤立的模块"**——governance worker 用它，但 soul layer（灵魂对讲机核心）完全不用。这是最大的 Token 浪费点。

---

## 三、ASR / 语音对话完整链路（PRD §5.2 + 白皮书 §一.2）

### 现状
- ✅ 前端 `useVoiceRecorder` Hook：同时做语音识别（Web Speech API）+ 音频录制（MediaRecorder）+ 可视化
- ✅ ChatInterface 支持长按麦克风→识别文本→发送消息 + 上传音频样本
- ✅ TTS（edge-tts）完整可用
- ✅ 语音动画（AudioAnimator + CanvasAvatar lip sync）

### Gap
| # | 问题 | 影响 | 代码位置 |
|---|------|------|---------|
| 3.1 | **后端没有 ASR 服务** | 依赖浏览器 Web Speech API，质量差、不支持离线、跨浏览器不一致 | 无 |
| 3.2 | **EternalMode 没有语音输入** | 继承者无法语音与数字灵魂对话 | `EternalMode.tsx` |
| 3.3 | **没有"语音消息播放"功能** | 用户录制的语音不能回放，只能发文字 | `ChatInterface.tsx` Msg 类型有 `audioUrl` 字段但从未使用 |
| 3.4 | Web Speech API 识别结果不传递给后端 ASR | 如果后端有 ASR，可以做二次确认/纠错 | `useVoiceRecorder.ts` |

**结论**：语音链路"前端有、后端无、永恒模式缺"。PRD 要求的 ASR→LLM→TTS 端到端链路不完整。

---

## 四、前端体验（PRD §5）

### 现状
- ✅ 6 个导航页面：对话、记忆、关系、情绪、灵魂、设置
- ✅ MemoryPage 有完整知识库展示（搜索+筛选+展开）
- ✅ AppShell 有灵魂完整度进度条

### Gap
| # | 问题 | 影响 | 代码位置 |
|---|------|------|---------|
| 4.1 | **TodoPanel 是孤儿组件**（完整实现但无人 import） | 快捷面板缺失，聊天页右侧空荡荡 | `components/TodoPanel.tsx` |
| 4.2 | **KnowledgePanel 是孤儿组件**（完整实现但无人 import） | 知识库快捷入口缺失 | `components/KnowledgePanel.tsx` |
| 4.3 | **ChatPage 仅渲染 ChatInterface，无右侧面板** | PRD §5.1 要求的"快捷面板"不存在 | `pages/ChatPage.tsx` |
| 4.4 | 记忆之书缺少**时间线视图** | 只有卡片网格，没有时间脉络 | `pages/MemoryPage.tsx` |
| 4.5 | 永恒模式欢迎页缺少**语音问候** | 白皮书 §6.1 要求的"好久不见"没有声音 | `EternalMode.tsx` |

---

## 五、后端代码质量

### Gap
| # | 问题 | 影响 | 代码位置 |
|---|------|------|---------|
| 5.1 | `authorization.py` **两个 `activate_will` 方法重复** | 代码冗余，维护风险 | `soul/authorization.py` lines 145, 199 |
| 5.2 | `soul_server.py` 2405 行过大 | 单文件维护困难，路由/逻辑/工具全混在一起 | `api/soul_server.py` |
| 5.3 | `eternal_chat()` 的记忆检索用**简单关键词匹配**（非语义搜索） | 相关记忆召回质量低 | `soul_server.py` lines 2162-2174 |

---

## 六、白皮书要求（未在 PRD 中但已承诺）

| # | 白皮书要求 | 现状 | 差距 |
|---|-----------|------|------|
| 6.1 | 声纹建模（后台异步，speaker embedding + 韵律分析） | ❌ 只有样本收集 | 需要 GPU 或 cloud API |
| 6.2 | 实时合成（流式 TTS，首音延迟 <0.3s） | ⚠️ edge-tts 可用但非流式 | 可用 but 延迟 ~1-2s |
| 6.3 | 3D 面部重建（DECA/FLAME） | ❌ 无 GPU 无法运行 | 硬件限制 |
| 6.4 | 实时视频驱动（SoulX-FlashTalk/Hallo-Live） | ❌ 无 GPU 无法运行 | 硬件限制 |
| 6.5 | 衰老模拟（时间流逝后形象变化） | ❌ 未实现 | 中 |
| 6.6 | WebRTC 视频对话 | ❌ 未实现 | 高 |
| 6.7 | MCP 接口（仿生机器人） | ❌ 未实现 | 高 |
| 6.8 | 副语言插入（口头禅、叹息） | ⚠️ edge-tts 不支持 | 需要声纹克隆模型 |
| 6.9 | 情感依赖守护（DependencyGuardian） | ✅ 已实现 | — |
| 6.10 | 身份透明（"我已不在了"） | ✅ 已实现 | — |

---

## 七、Gap 优先级矩阵

```
影响大 + 工作量小  →  立即做
影响大 + 工作量大  →  计划做
影响小 + 工作量小  →  顺手做
影响小 + 工作量大  →  不做
```

| 优先级 | 项目 | 影响 | 工作量 | 原因 |
|--------|------|------|--------|------|
| **P0** | 修复 LLMProvider 抽象接口（+chat_with_tools） | 高 | 小 | 模型切换会崩溃 |
| **P0** | eternal_chat 接入 Prompt Cache | 高 | 中 | Token 浪费最严重 |
| **P1** | 挂载 TodoPanel + KnowledgePanel 到 ChatPage | 高 | 小 | 组件已写好，只需挂载 |
| **P1** | EternalMode 增加语音输入（Web Speech API） | 高 | 小 | 前端已有 hook，只需复用 |
| **P1** | eternal_chat 记忆检索改用语义搜索 | 高 | 小 | 现有 embedding 可用 |
| **P2** | 后端 ASR（whisper 或 API） | 中 | 中 | 不依赖浏览器 |
| **P2** | soul_server.py 拆分（路由/业务/工具分离） | 中 | 中 | 代码维护 |
| **P2** | 语音消息播放功能 | 中 | 小 | Msg.audioUrl 字段已存在 |
| **P3** | MCP 接口设计 | 低 | 高 | PRD §5.4 远期 |
| **P3** | WebRTC 视频对话 | 低 | 高 | 硬件限制 |
| **P3** | 衰老模拟 | 低 | 中 | 锦上添花 |

---

## 八、最小可执行优化集（1-2 天可完成）

如果只选最重要的几个：

1. **修复 LLMProvider 接口**（~30min）→ 防止 provider 切换崩溃
2. **挂载 TodoPanel + KnowledgePanel**（~1h）→ 聊天页立刻变实用
3. **EternalMode 语音输入**（~2h）→ 继承者体验质变
4. **eternal_chat 接入 Prompt Cache**（~3h）→ 节省 Token
5. **eternal_chat 语义记忆检索**（~1h）→ 记忆召回质量提升
6. **语音消息播放**（~1h）→ 完整语音链路

**总计：约 1-2 天，影响最大。**
