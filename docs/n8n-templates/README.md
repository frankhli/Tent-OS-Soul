# n8n 对接 Tent OS —— 零代码消息渠道

## 概述

通过 n8n + Tent OS Webhook，你可以**零代码**接入飞书、微信、Slack、Discord、Telegram 等任意消息平台。

**成本**: 仅需要 LLM API Key（Tent OS 的"一个 key"原则）

## 架构

```
[用户消息] → [飞书/Slack/微信] → [n8n 触发器] → [n8n HTTP Request] 
    → [Tent OS Webhook] → [AI 处理] → [n8n 接收回复] → [飞书/Slack/微信 发回]
```

## 通用 Webhook 模板

### 1. n8n 工作流配置

创建一个 HTTP Request 节点：

```
Method: POST
URL: http://your-tent-os:8002/api/v1/channels/webhook/webhook
Headers:
  Content-Type: application/json
Body (JSON):
  {
    "user_id": "{{$json.user_id}}",
    "user_name": "{{$json.user_name}}",
    "text": "{{$json.text}}",
    "thread_id": "{{$json.thread_id}}"
  }
```

### 2. Tent OS 回复格式

```json
{
  "status": "ok",
  "session_id": "webhook_user_xxx",
  "reply": "AI 的回复内容..."
}
```

## 飞书模板

### n8n 触发器：飞书机器人事件

使用 n8n 的 **Feishu Trigger** 节点或 **Webhook** 节点接收飞书事件推送。

### n8n HTTP Request → Tent OS

```json
{
  "user_id": "{{$json.event.sender.sender_id.open_id}}",
  "user_name": "{{$json.event.sender.sender_id.union_id}}",
  "text": "{{$json.event.message.content.text}}",
  "thread_id": "{{$json.event.message.chat_id}}",
  "message_id": "{{$json.event.message.message_id}}"
}
```

### n8n HTTP Request ← Tent OS 回复 → 飞书

使用 n8n 的 **Feishu** 节点回复消息：
- `receive_id`: `{{$json.thread_id}}`
- `content`: `{{$json.reply}}`

## Slack 模板

### n8n 触发器：Slack Trigger

使用 n8n 的 **Slack Trigger** 节点，Event Type 选 `message`。

### n8n HTTP Request → Tent OS

```json
{
  "user_id": "{{$json.event.user}}",
  "user_name": "{{$json.event.user}}",
  "text": "{{$json.event.text}}",
  "thread_id": "{{$json.event.channel}}",
  "ts": "{{$json.event.ts}}"
}
```

### n8n 回复到 Slack

使用 n8n 的 **Slack** 节点：
- Channel: `{{$json.thread_id}}`
- Text: `{{$json.reply}}`

## 企业微信模板

### n8n 触发器：Webhook

企业微信配置接收消息 URL 指向 n8n Webhook。

### n8n HTTP Request → Tent OS

```json
{
  "user_id": "{{$json.FromUserName}}",
  "user_name": "{{$json.FromUserName}}",
  "text": "{{$json.Content}}",
  "thread_id": "{{$json.FromUserName}}"
}
```

## 高级：保留上下文（多轮对话）

要让 AI 记住对话上下文，使用 `thread_id` 作为 session identifier：

```json
{
  "user_id": "{{$json.user_id}}",
  "text": "{{$json.text}}",
  "thread_id": "{{$json.user_id}}"  // 同一 user_id 共享上下文
}
```

## 高级：图片消息

Tent OS 支持图像理解，在 webhook 中传递图片 URL：

```json
{
  "user_id": "{{$json.user_id}}",
  "text": "描述这张图片",
  "image_url": "{{$json.image_url}}"
}
```

（需要 LLM 支持多模态，如 kimi-k2.6）

## 快速启动

1. 启动 Tent OS：`tent-os run`
2. 启动 n8n：`npx n8n start` 或 Docker
3. 在 n8n 中导入上述模板
4. 配置飞书/Slack 的 App 信息
5. 完成！
