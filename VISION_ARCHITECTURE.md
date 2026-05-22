# Tent OS 视觉系统架构：AI 的眼睛

## 核心哲学

> 摄像头不是"功能"，它是 AI 的**感官器官**。就像人类通过眼睛理解世界，AI 通过视觉系统感知环境、识别物体、理解空间、读取情绪。
>
> 今天的桌面摄像头 → 明天的移动机器人摄像头。架构必须兼容两者。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          前端视觉层 (Browser)                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ 视频流采集       │  │ FaceLandmarker  │  │ 拍照/截图       │             │
│  │ getUserMedia    │  │ 52 Blendshapes  │  │ FileReader      │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           │                    │                    │                       │
│           └────────────────────┼────────────────────┘                       │
│                                ▼                                            │
│                    ┌─────────────────────┐                                  │
│                    │   Vision Client     │                                  │
│                    │  (WebSocket binary) │                                  │
│                    └──────────┬──────────┘                                  │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                │ WebSocket / HTTP
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        后端视觉中枢 (VisionHub)                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ EmotionEngine   │  │ SceneAnalyzer   │  │ SpatialMemory   │             │
│  │ 情绪分析引擎     │  │ 场景理解引擎     │  │ 空间记忆库       │             │
│  │                 │  │                 │  │                 │             │
│  │ blendshapes→情绪 │  │ VLM多模态理解   │  │ 图片→向量嵌入    │             │
│  │ 用户情绪时间线   │  │ 物体/位置/状态  │  │ 语义检索        │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           │                    │                    │                       │
│           └────────────────────┼────────────────────┘                       │
│                                ▼                                            │
│                    ┌─────────────────────┐                                  │
│                    │   AI Character      │                                  │
│                    │  (情绪/记忆/反馈)    │                                  │
│                    └─────────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼ MCP Protocol
┌─────────────────────────────────────────────────────────────────────────────┐
│                        具身智能层 (Embodied AI)                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ 桌面摄像头       │  │ 移动机器人       │  │ 智能家居摄像头   │             │
│  │ (当前)          │  │ (未来)          │  │ (未来)          │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 核心模块

### 1. EmotionEngine（情绪分析引擎）

**输入**：MediaPipe FaceLandmarker 输出的 52 个 blendshape 系数（0-1 连续值）
**输出**：
- 基础情绪：happy / sad / angry / surprised / disgusted / fearful / neutral
- 复合情绪：confused（困惑=皱眉+歪头）、excited（兴奋=大眼+张嘴+挑眉）
- 情绪强度：0-1 置信度
- 情绪时间线：用于观察情绪波动趋势

**关键技术**：
- 不用简单规则，用 **加权 blendshape 组合**
- `_JawOpen` + `_MouthSmileLeft` + `_MouthSmileRight` → happy 强度
- `_EyeWideLeft` + `_EyeWideRight` + `_BrowsUp` → surprised 强度
- `_EyeBlinkLeft` + `_EyeBlinkRight` → 眨眼频率（疲劳指标）

### 2. SceneAnalyzer（场景理解引擎）

**输入**：单张图片或视频帧
**输出**：
```json
{
  "description": "一张客厅照片，茶几上放着遥控器和茶杯",
  "objects": [
    {"name": "遥控器", "location": "茶几左上角", "confidence": 0.95},
    {"name": "茶杯", "location": "茶几中央", "confidence": 0.88}
  ],
  "scene_type": "客厅",
  "lighting": "明亮",
  "people_count": 1,
  "activities": ["休息"]
}
```

**三个业务场景**：
- **凭证验证**：图片 + 任务需求 → pass/fail + 缺失元素
- **智能描述**：图片 → 结构化任务描述
- **场景扫描**：定期扫描 → 更新空间记忆

### 3. SpatialMemory（空间记忆库）

**核心能力**：
- 每次视觉输入 → CLIP 向量嵌入 → 存入 PostgreSQL + pgvector
- 语义检索：`"遥控器在哪里？"` → 向量相似度搜索 → 返回相关图片
- 物体追踪：记录物体最后出现的位置和时间
- 空间地图：逐步构建房间内的物体分布图

**数据表**：
```sql
-- 视觉记忆
CREATE TABLE visual_memory (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    image_url TEXT,
    description TEXT,
    embedding VECTOR(512),
    objects JSONB,
    scene_type TEXT,
    created_at TIMESTAMP
);

-- 物体清单（实时更新）
CREATE TABLE object_inventory (
    id SERIAL PRIMARY KEY,
    user_id TEXT,
    object_name TEXT,
    last_seen_location TEXT,
    last_seen_image_id INTEGER,
    confidence FLOAT,
    updated_at TIMESTAMP
);
```

## 实施路线图

### Phase 1: 情绪感知升级（现在）
- [ ] 前端：FaceMesh → FaceLandmarker（52 blendshapes）
- [ ] 后端：EmotionEngine 基于 blendshapes 的加权分析
- [ ] 后端：情绪时间线 API

### Phase 2: 视觉理解（下周）
- [ ] 后端：SceneAnalyzer 接入 VLM（GPT-4o / Qwen-VL）
- [ ] 前端：聊天页"拍照描述需求"按钮
- [ ] 前端：任务流"上传凭证"按钮
- [ ] 后端：凭证验证 API 完善

### Phase 3: 空间记忆（下下周）
- [ ] 后端：CLIP 向量嵌入服务
- [ ] 后端：visual_memory + object_inventory 数据表
- [ ] 后端：语义检索 API
- [ ] 前端："xxx 在哪里？" 查询界面

### Phase 4: 具身接口（未来）
- [ ] MCP Server 暴露视觉工具
- [ ] `scan_room()` → 返回场景描述
- [ ] `find_object("遥控器")` → 返回位置
- [ ] `verify_position("花瓶", "茶几上")` → true/false

## API 设计

```
POST /api/vision/emotion        # 接收 blendshapes → 返回情绪分析
POST /api/vision/analyze        # 接收图片 → 返回场景描述 + 物体列表
POST /api/vision/verify         # 接收图片 + 需求 → 凭证验证
POST /api/vision/describe       # 接收图片 → 结构化任务描述
POST /api/vision/memory/store   # 存储视觉记忆
GET  /api/vision/memory/query   # 语义查询视觉记忆
GET  /api/vision/objects        # 获取物体清单
```
