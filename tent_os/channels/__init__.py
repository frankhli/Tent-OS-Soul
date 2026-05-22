"""消息渠道网关 —— 统一消息入口/出口

设计原则:
  • 框架免费，平台 key 按需配置（不可避免）
  • 核心是一个统一接口 + n8n webhook 模板
  • 用户零代码即可接入飞书/微信/Slack

架构:
  [飞书/微信/Slack] → Webhook → ChannelAdapter → Tent OS → AI 处理 → ChannelAdapter → 回复

支持的渠道:
  • webhook (通用，n8n 首选)
  • feishu (飞书，需 app_id/app_secret)
  • wechat_work (企业微信，需 corp_id/secret)
  • slack (Slack，需 bot_token)
  • discord (Discord，需 bot_token)
  • telegram (Telegram，需 bot_token)
"""
