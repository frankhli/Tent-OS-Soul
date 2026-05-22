# Tent OS WebSocket API 协议规范

> 版本: v1.0  
> 协议端点: `ws://localhost:8002/ws`

---

## 消息格式

所有消息均为 JSON 格式，通过 WebSocket 发送/接收。

```json
{
  "type": "消息类型",
  "payload": {
    "session_id": "会话ID",
    ...
  }
}
```

---

## 客户端 → 服务端

### `chat.message`
发送用户消息。

```json
{
  "type": "chat.message",
  "payload": {
    "session_id": "唯一会话标识",
    "content": "用户输入内容",
    "user_id": "用户标识（可选）"
  }
}
```

**服务端响应**:
- `chat.message_accepted` — 消息已接收，开始处理

---

## 服务端 → 客户端

### `chat.message_accepted`
消息已接收确认。

```json
{
  "type": "chat.message_accepted",
  "payload": {
    "session_id": "会话ID",
    "has_images": false
  }
}
```

---

### `chat.stream_chunk`
LLM 生成的正式回复内容（流式）。

```json
{
  "type": "chat.stream_chunk",
  "payload": {
    "session_id": "会话ID",
    "chunk": "回复文本片段",
    "type": "content"
  }
}
```

**注意**: chunk 可能按段落/句子批量发送，不是逐字发送。

---

### `chat.stream_reasoning`
LLM 的思考过程（流式，可选）。

```json
{
  "type": "chat.stream_reasoning",
  "payload": {
    "session_id": "会话ID",
    "chunk": "思考文本片段",
    "type": "reasoning"
  }
}
```

**注意**: 
- reasoning 消息按批量发送（约 80 字符或 0.3 秒间隔）
- 客户端可选择展示或忽略 reasoning 内容
- reasoning 不影响最终回复的完整性

---

### `chat.completed`
单轮对话完成通知。

```json
{
  "type": "chat.completed",
  "payload": {
    "session_id": "会话ID",
    "content": "完整回复内容",
    "reasoning": "思考过程摘要（前500字符）"
  }
}
```

**注意**: 收到此消息后，本轮对话处理结束。但后续可能收到：
- 异步自验证的 alert 消息（如发现问题）
- 其他系统通知

---

### `chat.error`
对话处理出错。

```json
{
  "type": "chat.error",
  "payload": {
    "session_id": "会话ID",
    "error": "错误描述"
  }
}
```

---

### `approval.request`
需要用户确认的操作。

```json
{
  "type": "approval.request",
  "payload": {
    "session_id": "会话ID",
    "plan": {
      "steps": [
        {"action": "shell", "executor": "local", "params": {...}}
      ]
    },
    "reason": "需要确认的原因"
  }
}
```

**注意**: 
- 自动化模式下（`auto_approve: true`），此类消息不会发送
- 客户端需要实现 approval UI 或自动响应机制

---

### `task.completed`
任务（非对话）完成通知。

```json
{
  "type": "task.completed",
  "payload": {
    "session_id": "会话ID",
    "result": "任务结果"
  }
}
```

---

### `system.health`
系统心跳/健康状态。

```json
{
  "type": "system.health",
  "payload": {
    "status": "healthy",
    "timestamp": "ISO时间"
  }
}
```

---

## 消息时序示例

### 正常对话流程

```
客户端                              服务端
  |                                   |
  |── chat.message ──────────────────>|
  |<─ chat.message_accepted ─────────|
  |                                   |
  |<─ chat.stream_reasoning ─────────|  (可选，批量发送)
  |<─ chat.stream_reasoning ─────────|
  |                                   |
  |<─ chat.stream_chunk ─────────────|  (正式回复)
  |<─ chat.stream_chunk ─────────────|
  |                                   |
  |<─ chat.completed ────────────────|  (本轮完成)
```

### 需要 approval 的流程

```
客户端                              服务端
  |── chat.message ──────────────────>|
  |<─ chat.message_accepted ─────────|
  |<─ chat.stream_chunk ─────────────|
  |                                   |
  |<─ approval.request ──────────────|  (需要确认)
  |── approval.response ─────────────>|  (客户端响应)
  |                                   |
  |<─ chat.stream_chunk ─────────────|
  |<─ chat.completed ────────────────|
```

---

## 已知问题与注意事项

1. **消息丢失**: 旧版本存在 `chat.completed` 消息丢失问题（已修复）
2. **reasoning 消息量大**: 每轮可能产生 10-50 条 reasoning 消息，客户端应做好流控
3. **approval 阻塞**: 默认模式下，危险操作会阻塞等待 approval，自动化场景建议开启 `auto_approve`
