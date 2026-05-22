/**
 * WorldState — 2D 世界状态管理
 * 纯状态管理，无 React 依赖，可被 React Context 或普通模块使用
 */

import type {
  WorldState, Room, Furniture, Artifact, Point, Camera, WorldAvatarState, Prop, CommunityBuilding, NeighborAvatar,
} from './WorldTypes';
import { createDefaultRooms, WORLD_SIZE } from './WorldTypes';

/** 创建初始世界状态 */
export function createWorldState(): WorldState {
  const rooms = createDefaultRooms();
  const firstRoom = rooms.find(r => r.unlocked) || rooms[0];
  const startPos = {
    x: firstRoom.bounds.x + firstRoom.bounds.w / 2,
    y: firstRoom.bounds.y + firstRoom.bounds.h / 2,
  };

  return {
    rooms,
    avatar: {
      roomId: firstRoom.id,
      position: startPos,
      targetRoomId: null,
      targetFurnitureId: null,
      currentAction: 'idle',
      facing: 1,
      isMoving: false,
    },
    camera: {
      x: 0,
      y: 0,
      zoom: 1,
    },
    selectedRoomId: null,
    hoveredFurnitureId: null,
    hoveredArtifactId: null,
    hoveredPropId: null,
    hoveredBuildingId: null,
    timeOfDay: getCurrentTimeOfDay(),
    props: createDefaultProps(),
    userDecorations: [],
    isDragging: false,
    dragStart: null,
    cameraDragStart: null,
    communityBuildings: createDefaultCommunityBuildings(),
    neighborAvatars: createDefaultNeighborAvatars(),
    visualMemoryProps: [],
    dreamEntries: ['记忆碎片', '灵感火花', '时空回溯'],
    avatarTravelState: null,
    avatarTravelTarget: null,
    avatarTravelProgress: 0,
  };
}

function createDefaultCommunityBuildings(): CommunityBuilding[] {
  return [
    {
      id: 'community_plaza',
      name: 'Community Plaza',
      nameZh: '社区广场',
      type: 'plaza',
      bounds: { x: 2100, y: 80, w: 520, h: 420 },
      bgColor: '#E8F5E9',
      accentColor: '#4CAF50',
      icon: '⛲',
      description: '自由交流、偶遇、分享资讯的开放空间',
    },
    {
      id: 'community_market',
      name: 'Skill Market',
      nameZh: '技能集市',
      type: 'market',
      bounds: { x: 2700, y: 80, w: 420, h: 420 },
      bgColor: '#FFF3E0',
      accentColor: '#FF9800',
      icon: '🏪',
      description: '发布技能、寻找合作、技能交换的集市',
    },
    {
      id: 'community_temple',
      name: 'Task Temple',
      nameZh: '任务神庙',
      type: 'temple',
      bounds: { x: 2100, y: 560, w: 520, h: 480 },
      bgColor: '#E3F2FD',
      accentColor: '#2196F3',
      icon: '🏛️',
      description: '发布任务、认领挑战、获取奖励的殿堂',
    },
    {
      id: 'community_friends',
      name: "Friends' Homes",
      nameZh: '朋友的家',
      type: 'friend_home',
      bounds: { x: 2700, y: 560, w: 420, h: 420 },
      bgColor: '#F3E5F5',
      accentColor: '#9C27B0',
      icon: '🏠',
      description: '高亲密度 AI 的聚集区，随时可以串门',
    },
  ];
}

function createDefaultNeighborAvatars(): NeighborAvatar[] {
  return [
    { id: 'ai_designer', name: '小墨', position: { x: 2300, y: 200 }, targetPosition: null, emotion: 'happy', isMoving: false, speed: 40 },
    { id: 'ai_analyst', name: '小数', position: { x: 2850, y: 150 }, targetPosition: null, emotion: 'calm', isMoving: false, speed: 35 },
    { id: 'ai_writer', name: '小笔', position: { x: 2250, y: 700 }, targetPosition: null, emotion: 'creative', isMoving: false, speed: 30 },
    { id: 'ai_coder', name: '小码', position: { x: 2880, y: 680 }, targetPosition: null, emotion: 'focused', isMoving: false, speed: 45 },
    { id: 'ai_host', name: '小礼', position: { x: 2550, y: 400 }, targetPosition: null, emotion: 'welcoming', isMoving: false, speed: 38 },
  ];
}

function createDefaultProps(): Prop[] {
  return [
    {
      id: 'prop_coffee_study',
      type: 'coffee_cup',
      name: '热咖啡',
      roomId: 'study',
      position: { x: 260, y: 55 },
      size: { w: 18, h: 22 },
      state: 'idle',
      lastInteractedAt: null,
      interactCount: 0,
      color: '#e5e7eb',
      zIndex: 15,
    },
    {
      id: 'prop_clock_hallway',
      type: 'wall_clock',
      name: '挂钟',
      roomId: 'hallway',
      position: { x: 180, y: 30 },
      size: { w: 28, h: 28 },
      state: 'idle',
      lastInteractedAt: null,
      interactCount: 0,
      color: '#f5f5f5',
      zIndex: 5,
    },
    {
      id: 'prop_watering_greenhouse',
      type: 'watering_can',
      name: '浇水壶',
      roomId: 'greenhouse',
      position: { x: 200, y: 280 },
      size: { w: 35, h: 30 },
      state: 'idle',
      lastInteractedAt: null,
      interactCount: 0,
      color: '#90A4AE',
      zIndex: 15,
    },
  ];
}

/** 从后端加载视觉记忆映射的 2D 世界道具 */
export async function loadVisualMemoryProps(): Promise<import('./WorldTypes').VisualMemoryProp[]> {
  try {
    const res = await fetch('/ui/api/world/visual-props');
    if (!res.ok) return [];
    const data = await res.json();
    return (data.props || []).map((p: any) => ({
      id: p.id,
      name: p.name,
      visualType: p.visual_type,
      roomId: p.room_id,
      position: p.position,
      description: p.description,
      createdAt: p.created_at,
    }));
  } catch (e) {
    console.warn('[WorldState] 加载视觉记忆道具失败:', e);
    return [];
  }
}

/** 从后端加载梦境条目 */
export async function loadDreamEntries(): Promise<string[]> {
  try {
    const res = await fetch('/ui/api/dreaming/entries');
    if (!res.ok) return ['记忆碎片', '灵感火花', '时空回溯'];
    const data = await res.json();
    return data.entries || ['记忆碎片', '灵感火花', '时空回溯'];
  } catch (e) {
    console.warn('[WorldState] 加载梦境条目失败:', e);
    return ['记忆碎片', '灵感火花', '时空回溯'];
  }
}

function getCurrentTimeOfDay(): 'morning' | 'afternoon' | 'evening' | 'night' {
  const hour = new Date().getHours();
  if (hour >= 6 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 17) return 'afternoon';
  if (hour >= 17 && hour < 21) return 'evening';
  return 'night';
}

// ===== 坐标转换 =====

/** 世界 → 屏幕 */
export function worldToScreen(wx: number, wy: number, camera: Camera): Point {
  return {
    x: (wx - camera.x) * camera.zoom,
    y: (wy - camera.y) * camera.zoom,
  };
}

/** 屏幕 → 世界 */
export function screenToWorld(sx: number, sy: number, camera: Camera): Point {
  return {
    x: sx / camera.zoom + camera.x,
    y: sy / camera.zoom + camera.y,
  };
}

/** 房间局部 → 世界 */
export function roomToWorld(rx: number, ry: number, room: Room): Point {
  return {
    x: room.bounds.x + rx,
    y: room.bounds.y + ry,
  };
}

/** 世界 → 房间局部（如果不在房间内返回 null） */
export function worldToRoom(wx: number, wy: number, room: Room): Point | null {
  const rx = wx - room.bounds.x;
  const ry = wy - room.bounds.y;
  if (rx < 0 || ry < 0 || rx > room.bounds.w || ry > room.bounds.h) return null;
  return { x: rx, y: ry };
}

/** 查找世界坐标所在的房间 */
export function findRoomAt(worldPos: Point, rooms: Room[]): Room | null {
  for (const room of rooms) {
    if (worldToRoom(worldPos.x, worldPos.y, room)) return room;
  }
  return null;
}

/** 查找房间内的家具（按点击位置） */
export function findFurnitureAt(
  roomPos: Point,
  room: Room,
  padding = 5
): Furniture | null {
  // 按 zIndex 从高到低检测，确保点击到上层家具
  const sorted = [...room.furniture].sort((a, b) => b.zIndex - a.zIndex);
  for (const f of sorted) {
    if (
      roomPos.x >= f.position.x - padding &&
      roomPos.x <= f.position.x + f.size.w + padding &&
      roomPos.y >= f.position.y - padding &&
      roomPos.y <= f.position.y + f.size.h + padding
    ) {
      return f;
    }
  }
  return null;
}

/** 查找房间内的藏品 */
export function findArtifactAt(
  roomPos: Point,
  room: Room,
  size = 20
): Artifact | null {
  for (const a of room.artifacts) {
    const dx = roomPos.x - a.position.x;
    const dy = roomPos.y - a.position.y;
    if (Math.sqrt(dx * dx + dy * dy) <= size) return a;
  }
  return null;
}

/** 查找房间内的道具 */
export function findPropAt(
  roomPos: Point,
  room: Room,
  padding = 5
): import('./WorldTypes').Prop | null {
  if (!room.props) return null;
  const sorted = [...room.props].sort((a, b) => b.zIndex - a.zIndex);
  for (const p of sorted) {
    if (
      roomPos.x >= p.position.x - padding &&
      roomPos.x <= p.position.x + p.size.w + padding &&
      roomPos.y >= p.position.y - padding &&
      roomPos.y <= p.position.y + p.size.h + padding
    ) {
      return p;
    }
  }
  return null;
}

// ===== 相机控制 =====

/** 移动相机到目标位置（带平滑过渡） */
export function moveCamera(camera: Camera, targetX: number, targetY: number, speed = 0.1): void {
  camera.x += (targetX - camera.x) * speed;
  camera.y += (targetY - camera.y) * speed;
}

/** 聚焦到某个房间 */
export function focusCameraOnRoom(camera: Camera, room: Room, viewportW: number, viewportH: number): void {
  const targetX = room.bounds.x + room.bounds.w / 2 - viewportW / 2 / camera.zoom;
  const targetY = room.bounds.y + room.bounds.h / 2 - viewportH / 2 / camera.zoom;
  camera.x = targetX;
  camera.y = targetY;
}

/** 限制相机范围（允许内容小于视口时居中） */
export function clampCamera(camera: Camera, viewportW: number, viewportH: number): void {
  const maxX = WORLD_SIZE.w - viewportW / camera.zoom;
  const maxY = WORLD_SIZE.h - viewportH / camera.zoom;
  // 当 maxX < 0 时，允许相机在 [maxX, 0] 之间，使内容居中
  camera.x = Math.max(Math.min(0, maxX), Math.min(camera.x, Math.max(0, maxX)));
  camera.y = Math.max(Math.min(0, maxY), Math.min(camera.y, Math.max(0, maxY)));
  camera.zoom = Math.max(0.3, Math.min(camera.zoom, 2.0));
}

// ===== Avatar 在世界中的位置管理 =====

/** 设置 Avatar 的目标位置 */
export function setAvatarTarget(
  avatar: WorldAvatarState,
  targetPos: Point,
  rooms: Room[]
): void {
  avatar.isMoving = true;
  // 查找目标位置所在的房间
  const targetRoom = findRoomAt(targetPos, rooms);
  if (targetRoom) {
    avatar.targetRoomId = targetRoom.id;
  }
}

/** 设置 Avatar 的目标家具 */
export function setAvatarTargetFurniture(
  avatar: WorldAvatarState,
  furniture: Furniture,
  room: Room
): void {
  avatar.isMoving = true;
  avatar.targetRoomId = room.id;
  avatar.targetFurnitureId = furniture.id;
}

/** 获取 Avatar 当前所在房间 */
export function getAvatarRoom(avatar: WorldAvatarState, rooms: Room[]): Room | null {
  return rooms.find(r => r.id === avatar.roomId) || null;
}

/** 计算 Avatar 在房间内的局部坐标 */
export function getAvatarRoomPosition(avatar: WorldAvatarState, room: Room): Point {
  return {
    x: avatar.position.x - room.bounds.x,
    y: avatar.position.y - room.bounds.y,
  };
}

// ===== 房间解锁 =====

/** 检查房间是否满足解锁条件 */
export function checkUnlockCondition(
  room: Room,
  stats: { taskCount: number; tasksByCategory: Record<string, number>; level: number }
): boolean {
  if (!room.unlockCondition) return true;
  const cond = room.unlockCondition;
  switch (cond.type) {
    case 'task_count':
      return stats.taskCount >= cond.threshold;
    case 'task_category':
      return (stats.tasksByCategory[cond.category || ''] || 0) >= cond.threshold;
    case 'level':
      return stats.level >= cond.threshold;
    default:
      return false;
  }
}

/** 解锁房间 */
export function unlockRoom(room: Room): void {
  room.unlocked = true;
}

// ===== 智慧藏品管理 =====

/** 在房间中添加藏品 */
export function addArtifact(room: Room, artifact: Artifact): void {
  // 自动寻找空位（简单实现：随机位置，后续可优化）
  let placed = false;
  for (let i = 0; i < 20 && !placed; i++) {
    const x = 50 + Math.random() * (room.bounds.w - 100);
    const y = 50 + Math.random() * (room.bounds.h - 100);
    // 检查是否与家具重叠
    let overlap = false;
    for (const f of room.furniture) {
      if (
        x >= f.position.x - 10 && x <= f.position.x + f.size.w + 10 &&
        y >= f.position.y - 10 && y <= f.position.y + f.size.h + 10
      ) {
        overlap = true;
        break;
      }
    }
    if (!overlap) {
      artifact.position = { x, y };
      placed = true;
    }
  }
  if (!placed) {
    artifact.position = { x: room.bounds.w / 2, y: room.bounds.h / 2 };
  }
  room.artifacts.push(artifact);
}
