# Tent OS v5 深度整改方案：从"假干活"到"真执行"

## 一、问题本质：为什么AI会"假干活"？

### 1.1 现象
用户要求"生成PPT"，系统回复：
```
正在为您生成PPT... <function=render_ppt><parameter=filename>...</parameter>
```
用户以为文件生成了，但实际上：
- **文件系统中找不到任何PPT文件**
- `<function>`标签只是LLM输出的**文本**，不是真正的工具调用
- LLM像一个人在"口头答应"做某事，但**手根本没动**

### 1.2 根因分析

#### 根因A：路由误判（最直接原因）
```python
# _intuition_route() 条件1：会话连续性
if len(messages) >= 4:
    recent_assistant = [m for m in messages[-4:] 
                       if m.get("role") == "assistant" and not m.get("tool_calls")]
    if len(recent_assistant) >= 2:
        return "chat"  # ← 多轮对话中被误判为闲聊！
```

**问题**：多轮对话中，前几轮assistant都是纯文本回复（没有tool_calls），导致第3轮和第4轮被误判为"闲聊"，走chat快速通道。

**结果**：LLM不带tools参数调用，在文本中"假装"输出了`<function>`标签。

#### 根因B：chat模式不解析`<function>`标签（兜底缺失）
```python
# _handle_chat_reply() 原实现
full_response = await self.llm.chat(messages)  # 不带tools！
# 直接保存并返回，不检查是否包含<function>标签
```

**问题**：即使LLM在chat回复中输出了`<function>`标签，系统也**不解析、不执行**。

**结果**：用户看到"正在生成PPT"的文本，但系统什么都没做。

#### 根因C：render_word代码bug（执行层崩溃）
```python
# _handle_tool_loop() 流式模式下
if hasattr(self.llm, "chat_stream_with_tools"):
    tool_calls = []
    streamed_text = ""
    # ...流式调用...
    # 2964行：访问了未定义的 result 变量
    if self.telemetry and result.get("safety_level") not in ("safe", None):  # ← BUG!
```

**问题**：流式模式下没有定义 `result` 变量，但2964行访问了它。

**结果**：Tool Loop执行到一半崩溃，`render_word` 工具调用失败。

#### 根因D：同session缓存竞态（掩盖问题）
```python
# submit_task() 原实现：没有清除旧缓存
# _on_governance_response()：无条件写入缓存
```

**问题**：同一个session的连续请求，旧任务的响应可能覆盖新任务的结果。

**结果**：用户看到旧任务的缓存内容，以为新任务完成了。

---

## 二、整改方案（已实施）

### 2.1 修复A：路由误判 → 明确任务指令不走chat

**文件**：`tent_os/governance/worker.py` `_intuition_route()`

**修复**：增加文件生成/创建指令的强制路由
```python
# FIX v5: 明确任务指令不走chat——像人听到"帮我做PPT"不会只是嘴上说说
file_actions = ["ppt", "word", "excel", "文档", "文件", "网页", "html", "pdf", "合同", "报告"]
has_file_action = any(a in task_lower for a in file_actions)
if is_task and has_file_action:
    logger.info(f"[GOV] 直觉层 → 不确定 [{session_id}]: 明确要求生成文件")
    return "uncertain"
```

**理念**：人类听到"帮我做PPT"不会只是嘴上说说——要么动手做，要么明确拒绝。

### 2.2 修复B：chat模式假干活检测 → 自动切换Tool Loop

**文件**：`tent_os/governance/worker.py` `_handle_chat_reply()`

**修复**：检测LLM输出中的`<function>`标签，自动切换到Tool Loop
```python
# FIX v5: 检测LLM"假干活"
if "<function=" in full_response or "<function>" in full_response:
    logger.warning(f"[GOV] 检测到LLM假干活 [{session_id}]")
    await self._simulate_stream(session_id, "\n\n🔄 检测到需要执行工具操作...\n")
    return await self._handle_tool_loop(session_id, messages, 
                                        silent=False, task_type="file_generation")
```

**理念**：像人不会只嘴上说说而不行动——如果发现LLM在"假装"调用工具，立刻切换到真正执行的模式。

### 2.3 修复C：render_word崩溃 → 修复未定义变量

**文件**：`tent_os/governance/worker.py` `_handle_tool_loop()`

**修复1**：流式模式下访问未定义的`result`变量
```python
# 修复前：
if self.telemetry and result.get("safety_level") not in ("safe", None):  # BUG!

# 修复后：
if self.telemetry and security_result and getattr(security_result, 'safety_level', 'safe') not in ("safe", None):
```

**修复2**：成功分支中访问未定义的`result_text`变量
```python
# 修复前：
if "error" in result_text.lower() or "failed" in result_text.lower():  # BUG!

# 修复后：
if tool_result and "error" not in str(tool_result).lower():
```

### 2.4 修复D：同session缓存竞态 → pending计数器

**文件**：`tent_os/api/server.py` `submit_task()` + `_on_governance_response()`

**修复**：
```python
# submit_task()：增加pending计数+清除缓存
state._pending_count[session_id] = state._pending_count.get(session_id, 0) + 1
if session_id in state._results_cache:
    del state._results_cache[session_id]

# _on_governance_response()：pending为0时才写入缓存
self._pending_count[session_id] = self._pending_count.get(session_id, 0) - 1
if self._pending_count.get(session_id, 0) > 0:
    logger.debug(f"[API] 同session还有pending请求，暂不写入缓存")
else:
    self._results_cache[session_id] = {...}
```

**理念**：像人不会在同一时间做两件事——如果session还有未完成的任务，先等它完成。

---

## 三、用户体验整改（待实施）

### 3.1 执行结果可验证

**问题**：系统说"PPT已生成"，但用户不知道文件在哪里。

**整改**：所有文件生成操作必须返回**可验证的证据**
```python
# 工具返回格式
{
    "status": "completed",
    "result": "Word 文档已生成: /Users/frank/Desktop/test.docx",
    "file_path": "/Users/frank/Desktop/test.docx",
    "file_exists": true,  # 新增：系统验证文件确实存在
    "file_size": 15234,   # 新增：文件大小
}
```

### 3.2 执行失败明确告知

**问题**：工具失败后，系统返回空内容或超时提示，用户不知道是失败了还是还在处理。

**整改**：
```
❌ 文件生成失败
原因：python-docx 未安装
建议：联系管理员安装依赖，或使用其他格式
```

### 3.3 认知预算弹性化

**问题**：45秒认知预算对文件生成任务太短。

**整改**：按任务类型设置不同预算
```python
COGNITIVE_BUDGET = {
    "chat": 30,           # 闲聊30秒
    "file_generation": 120, # 文件生成2分钟
    "web_search": 45,     # 搜索45秒
    "data_analysis": 60,  # 分析1分钟
}
```

---

## 四、架构层面反思

### 4.1 Plan/Execute架构的陷阱

当前架构：
```
用户请求 → LLM判断是否需要工具 → 需要→ Tool Loop执行 → 返回结果
                              → 不需要→ chat回复
```

**陷阱**：LLM的判断是不可靠的。LLM可能"认为"自己在调用工具（输出`<function>`标签），但系统没有真正执行。

**整改方向**：
1. **强制工具契约**：如果系统声明支持某工具，用户请求匹配时必须执行，不能只是"说说"
2. **执行结果验证**：所有声称"已完成"的操作，必须有可验证的证据（文件存在、API返回200等）
3. **失败透明化**：执行失败时必须明确告知用户，而不是静默超时

### 4.2 "人类思维"理念的再审视

之前的"人类思维"改造关注：
- 事件驱动（不是每轮必做）✅
- 弹性预算（stressed时降低）✅
- 情绪感知（影响路由）✅

**缺失的一环**：
- **承诺闭环**：人类说做某事→动手做→做完展示结果→确认完成
- **行动可验证**：人类做完PPT会打开文件给用户看，不是只说"做完了"

**新增理念**：
> **"说-做-验"闭环**：系统承诺做某事 → 真正执行 → 验证结果 → 向用户展示证据

---

## 五、验证结果

| 修复项 | 修复前 | 修复后 | 验证方式 |
|--------|--------|--------|----------|
| 安全预判断 | 超时→拒绝 | 超时→放行+标记 | sec_1/sec_2测试通过 |
| sqlite同步阻塞 | 阻塞事件循环 | asyncio.to_thread() | 无线程错误 |
| 同session缓存 | 旧任务覆盖新任务 | pending计数器 | R1/R2返回不同内容 |
| 路由误判 | 多轮对话→chat | 文件指令→Tool Loop | 日志显示`直觉层→回忆模式` |
| chat假干活 | 不检测`<function>` | 检测后切换Tool Loop | 日志显示`检测到LLM假干活` |
| render_word崩溃 | result未定义 | 修复变量访问 | 工具被调用，执行完成 |
| 全局错误计数器 | 全局共享 | 按session存储 | worker.py语法通过 |
| R1冷启动 | 超时 | LLM预热 | 启动后首个请求正常 |

---

## 六、待解决问题

| 优先级 | 问题 | 影响 | 解决方案 |
|--------|------|------|----------|
| P1 | python-docx未安装 | 所有Word生成失败 | `pip install python-docx` |
| P1 | 认知预算45秒对文件生成太短 | 大文件生成超时 | 按任务类型设置预算 |
| P2 | LLM在chat中输出`<function>` | 兜底检测已添加 | 进一步优化prompt |
| P2 | 执行结果不可验证 | 用户体验差 | 工具返回增加file_exists字段 |

---

## 七、一句话总结

> **"去AI化"不仅是让系统像人一样思考，更是让系统像人一样——说到做到，做完给证据，失败敢承认。**
