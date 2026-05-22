/**
 * Spacetime API Client —— 时空映射器后端接口
 * Phase 1：前端先定义接口，后端后续实现
 */

const API_BASE = '';

import type { ScheduleMode, DayPhase, WeatherType, ActivityType } from '@/contexts/SpacetimeContext';

// ===== 时空状态 =====

export interface SpacetimeStateDto {
  schedule_mode: ScheduleMode;
  schedule_next_change: number;
  day_phase: DayPhase;
  current_time: string;
  environment: {
    brightness: number;
    weather: WeatherType;
    detected_scene: string;
    people_count: number;
    key_objects: string[];
    temperature: number | null;
  };
  current_activity: {
    type: ActivityType;
    target: string;
    location: string;
    progress: number;
    since: number;
    session_id?: string;
  } | null;
  fatigue: number;
  last_high_load_at: number | null;
  autonomy_decision: string | null;
  autonomy_decision_until: number | null;
}

/** 获取当前时空状态 */
export async function loadSpacetimeState(): Promise<SpacetimeStateDto | null> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/spacetime/state`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.state || null;
  } catch {
    return null;
  }
}

/** 保存时空状态（增量更新） */
export async function saveSpacetimeState(params: Partial<SpacetimeStateDto>): Promise<void> {
  try {
    await fetch(`${API_BASE}/ui/api/spacetime/state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  } catch {
    // 静默失败
  }
}

// ===== 作息时间表 =====

export interface ScheduleSlotDto {
  mode: ScheduleMode;
  start_hour: number;
  end_hour: number;
  label: string;
}

/** 获取作息时间表 */
export async function loadSchedule(): Promise<ScheduleSlotDto[]> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/spacetime/schedule`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.schedule || [];
  } catch {
    return [];
  }
}

/** 设置作息时间表 */
export async function saveSchedule(slots: ScheduleSlotDto[]): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/spacetime/schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ schedule: slots }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ===== 收集癖 =====

export interface CollectibleDto {
  id: string;
  name: string;
  detected_at: number;
  detected_from: string;
  visual_form: string;
  placed_room_id: string;
  placed_position: { x: number; y: number };
}

/** 上报检测到的物体，生成收集品 */
export async function createCollectible(params: {
  name: string;
  detected_from: string;
  visual_form: string;
  placed_room_id: string;
  placed_position: { x: number; y: number };
}): Promise<{ collectible_id: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/collectible`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** 获取 AI 已收集的物品列表 */
export async function loadCollectibles(): Promise<CollectibleDto[]> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/collectibles`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.collectibles || [];
  } catch {
    return [];
  }
}

// ===== 回忆场景 =====

export interface MemorySceneDto {
  session_id: string;
  timestamp: number;
  messages: Array<{
    role: string;
    content: string;
    timestamp: number;
  }>;
  artifacts: Array<{
    id: string;
    name: string;
    visual_type: string;
    rarity: string;
  }>;
  ai_state: {
    emotion: string;
    location: string;
    activity: string;
  };
  environment: {
    day_phase: DayPhase;
    weather: WeatherType;
    brightness: number;
  };
  graph_snapshot: {
    key_nodes: string[];
    connections: string[];
  };
}

/** 获取回忆场景 */
export async function loadMemoryScene(sessionId: string): Promise<MemorySceneDto | null> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/memory/scene/${encodeURIComponent(sessionId)}`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.scene || null;
  } catch {
    return null;
  }
}

/** 标记会话为"重要"（生成回忆场景入口） */
export async function markSessionSignificant(sessionId: string, significant = true): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/memory/scene/${encodeURIComponent(sessionId)}/significant`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ significant }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ===== 记忆锚点 =====

export interface MemoryAnchorDto {
  id: string;
  memory_uri: string;
  session_id: string;
  artifact_id: string;
  room_id: string;
  emotional_tag: string;
  spacetime_snapshot: {
    day_phase: DayPhase;
    weather: WeatherType;
    schedule_mode: ScheduleMode;
    location: string;
  };
}

/** 创建记忆锚点 */
export async function createMemoryAnchor(params: Omit<MemoryAnchorDto, 'id'>): Promise<{ anchor_id: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/memory/anchor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** 获取记忆锚点列表 */
export async function loadMemoryAnchors(): Promise<MemoryAnchorDto[]> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/memory/anchors`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.anchors || [];
  } catch {
    return [];
  }
}

// ===== 机制二-1: 空间记忆 =====

export interface SpatialMemoryDto {
  id: string;
  room_id: string;
  x: number;
  y: number;
  label: string;
  memory_type: string;
  description: string | null;
  emotional_tag: string | null;
  created_at: string;
  access_count: number;
}

export interface ObjectInventoryDto {
  id: string;
  room_id: string;
  name: string;
  object_type: string;
  x: number;
  y: number;
  state: string;
  detected_at: string;
  detected_from: string | null;
}

/** 获取空间记忆 */
export async function loadSpatialMemory(): Promise<SpatialMemoryDto[]> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/spatial-memory`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.memories || [];
  } catch {
    return [];
  }
}

/** 获取物体清单 */
export async function loadObjectInventory(): Promise<ObjectInventoryDto[]> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/object-inventory`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.objects || [];
  } catch {
    return [];
  }
}

// ===== 机制二-2: 用户改造 =====

export interface UserDecorationDto {
  id: string;
  room_id: string;
  decoration_type: string;
  name: string;
  x: number;
  y: number;
  size_w: number;
  size_h: number;
  color: string;
  created_at: string;
}

/** 获取用户装饰 */
export async function loadUserDecorations(): Promise<UserDecorationDto[]> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/user-decorations`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.decorations || [];
  } catch {
    return [];
  }
}

/** 创建用户装饰 */
export async function createUserDecoration(params: Omit<UserDecorationDto, 'id' | 'created_at'>): Promise<{ id: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/user-decorations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** 删除用户装饰 */
export async function deleteUserDecoration(decorationId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/user-decorations/${decorationId}`, {
      method: 'DELETE',
    });
    return res.ok;
  } catch {
    return false;
  }
}
