---
name: presentation
description: |
  Generate professional HTML slide decks from structured content.
  Use when: user asks to create PPT/presentation/slides, convert document to slides,
  or needs visual storytelling with charts, KPIs, icons, and SVG graphics.
  Triggers on: "做PPT", "生成PPT", "写PPT", "幻灯片", "演示文稿", "路演", "pitch deck",
  "presentation", "slides", "做汇报", "做报告".
  This skill covers the full pipeline: content analysis → visual design → JSON structure → HTML rendering.
version: "2.0.0"
author: Tent OS
category: content-generation
requires:
  tools: [render_ppt, shell, file_read, file_write]
  env: []
  bins: []
---

# Presentation Design Master

## When to Use
- 用户要求生成 PPT、演示文稿、幻灯片
- 需要将文档/报告转换为可视化演示
- 需要数据可视化（图表、KPI 卡片）
- 需要路演材料、产品演示、汇报 deck

## When NOT to Use
- 用户只是询问 PPT 制作技巧（纯聊天）
- 用户提供了不完整的/无意义的内容
- 用户要求"设计"但不提供任何内容

## Tools
- render_ppt
- shell
- file_read
- file_write

## Design Principles

### 1. 一页一观点
每页幻灯片只传达**一个核心观点**。不要在一页上塞多个主题。

### 2. 视觉优先于文字
- 能用图表不用列表
- 能用图标+关键词不用完整句子
- 能用视觉对比不用文字描述
- Bullet 不超过 5 条，每条不超过 15 字

### 3. 留白是设计的一部分
- 不要把页面填满
- 四周留边距（已由渲染器处理）
- 元素之间要有呼吸空间

### 4. 一致性
- 全文使用同一主题
- 同一层级的元素使用相同的视觉处理
- 配色不超过 3 种主色

## Slide Type 选择指南

| 内容类型 | 推荐 type | 说明 |
|---------|----------|------|
| 封面/标题 | `title` | 大标题+副标题+装饰 |
| 普通内容/要点 | `content` | 标题+bullets |
| 数据对比 | `comparison` | 左右分栏对比 |
| 数据图表 | `chart` | 柱状图/饼图/折线图 |
| 关键数字/KPI | `data` | 大数字卡片 |
| 名言引用 | `quote` | 居中大字引用 |
| 时间线 | `timeline` | 垂直时间轴 |
| 章节过渡 | `section_divider` | 大章节标题页 |
| 震撼开场 | `visual` | 大 SVG 背景+文字叠加 |
| 信息图 | `infographic` | 多元素自由组合 |
| 流程/步骤 | `process_flow` | 横向步骤流程 |
| 产品特性 | `gallery` | 卡片网格 |
| 金句/核心主张 | `statement` | 极简大字 |

## 主题系统

| 主题 | 风格 | 适用场景 |
|------|------|---------|
| `dark_modern` | 深蓝紫渐变，科技感 | 默认，科技产品、互联网 |
| `light_corporate` | 白色商务，专业稳重 | 传统行业、B2B、企业汇报 |
| `gradient_bold` | 深紫+橙色，大胆创新 | 创意行业、品牌路演 |
| `ocean_depth` | 深海蓝绿，冷静深邃 | 金融、咨询、数据分析 |
| `forest_moss` | 森林绿，自然可持续 | 环保、健康、农业 |

## 执行流程

Step 1: 用户确认
→ "好的，我来为您设计演示文稿。预计生成 X 页，大约需要 1-2 分钟。"

Step 2: 分析内容
→ 读取源文件 → 识别内容类型 → 提取关键数字、核心观点

Step 3: 设计视觉策略
→ 为每一页选择 slide type → 决定 SVG/图表/图标使用

Step 4: 生成结构化大纲
→ 输出 JSON 格式（必须包含 `sections` 字段）

Step 5: 调用 render_ppt
→ 传入 presentation_json 和 output_path

Step 6: 汇报结果
→ 生成页数、主题、文件位置

## JSON 格式铁律

1. **必须有 `sections` 字段**：顶层必须是 `sections` 数组
2. **slides 必须在 sections 内部**
3. **每个 section 必须有 slides 数组**
4. **theme 只能是**：`dark_modern`, `light_corporate`, `gradient_bold`, `ocean_depth`, `forest_moss`
5. **slide type 可以是**：`title`, `content`, `two_column`, `chart`, `data`, `quote`, `timeline`, `section_divider`, `visual`, `infographic`, `process_flow`, `comparison`, `gallery`, `statement`

## 重要约束

1. **页数控制**：一般演示 10-20 页，路演 deck 8-12 页
2. **零依赖**：所有渲染由 Tent OS 内置引擎完成
3. **必须调用 render_ppt**：不要尝试用 file_write 写 HTML
4. **SVG 必须简洁**：每个 SVG 控制在 2KB 以内
5. **内容空洞时直接拒绝**：不要强行生成无意义的 PPT

## 自检清单

- [ ] 每页是否只有一个核心观点？
- [ ] 是否有至少 3 页使用了 SVG 或图标？
- [ ] 数据页是否使用了图表或 KPI 卡片？
- [ ] 封面是否有视觉冲击力？
- [ ] 配色是否统一使用了主题色板？
- [ ] 文字是否足够精简？
