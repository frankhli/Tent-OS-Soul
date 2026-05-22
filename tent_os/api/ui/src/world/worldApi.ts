/**
 * World API Client —— 后端世界状态持久化接口
 */

const API_BASE = '';

export interface BackendWorldState {
  avatar: {
    room_id: string;
    position: { x: number; y: number };
    action: string;
    facing: number;
  };
  experience: number;
  level: number;
  tasks_completed: number;
  tasks_failed: number;
  streak_days: number;
  time_of_day: string;
  achievements: string[];
  decorations: string[];
  last_update: number;
}

export interface WorldStats {
  level: number;
  experience: number;
  tasks_completed: number;
  tasks_failed: number;
  streak_days: number;
  artifact_count: number;
  unlocked_room_count: number;
  active_time_today: number;
}

export interface ArtifactData {
  id: string;
  name: string;
  task_id: string | null;
  category: string;
  visual_type: string;
  rarity: string;
  room_id: string;
  position: { x: number; y: number };
  description: string | null;
  created_at: number;
}

/** 从后端加载世界状态 */
export async function loadWorldState(): Promise<BackendWorldState | null> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/state`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.world || null;
  } catch {
    return null;
  }
}

/** 保存 Avatar 状态到后端（增量更新） */
export async function saveAvatarState(params: {
  avatar_room_id?: string;
  avatar_position_x?: number;
  avatar_position_y?: number;
  avatar_action?: string;
  avatar_facing?: number;
}): Promise<void> {
  try {
    await fetch(`${API_BASE}/ui/api/world/state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  } catch {
    // 静默失败，不阻塞前端
  }
}

/** 获取世界统计 */
export async function loadWorldStats(): Promise<WorldStats | null> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/stats`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.stats || null;
  } catch {
    return null;
  }
}

/** 添加智慧藏品 */
export async function addArtifact(params: {
  name: string;
  task_id?: string;
  category?: string;
  visual_type?: string;
  rarity?: string;
  room_id?: string;
  position_x?: number;
  position_y?: number;
  description?: string;
}): Promise<{ artifact_id: string; exp_gain: number } | null> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/artifact`, {
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

/** 列出所有藏品 */
export async function listArtifacts(roomId?: string): Promise<ArtifactData[]> {
  try {
    const url = roomId
      ? `${API_BASE}/ui/api/world/artifacts?room_id=${roomId}`
      : `${API_BASE}/ui/api/world/artifacts`;
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    return data.artifacts || [];
  } catch {
    return [];
  }
}

/** 解锁房间 */
export async function unlockRoom(roomId: string, reason?: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/room/unlock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room_id: roomId, reason }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** 获取已解锁房间列表 */
export async function loadUnlockedRooms(): Promise<string[]> {
  try {
    const res = await fetch(`${API_BASE}/ui/api/world/rooms`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data.unlocked_rooms || []).map((r: { room_id: string }) => r.room_id);
  } catch {
    return [];
  }
}
