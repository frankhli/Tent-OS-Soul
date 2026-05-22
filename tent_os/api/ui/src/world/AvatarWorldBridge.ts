/**
 * AvatarWorldBridge — Avatar 意图系统 ↔ 世界坐标系统的桥接
 *
 * 核心职责：
 * 1. 屏幕坐标 ↔ 世界坐标的双向转换（用于 GlobalAvatarFree 与世界系统对接）
 * 2. 提供高级意图接口：去房间、去家具、探索、休息、工作
 * 3. 将 AIState 中的系统事件映射为世界 Avatar 动作
 * 4. 世界 Avatar 状态 → 屏幕位置的同步
 */

import type { Point, Room, Furniture, WorldAvatarState, Camera } from './WorldTypes';
import { SYSTEM_ACTION_MAP } from './WorldTypes';
import { worldToScreen, screenToWorld, roomToWorld } from './WorldState';

// ===== 意图类型 =====

export type WorldIntent =
  | 'goto_room'
  | 'goto_furniture'
  | 'explore_world'
  | 'rest_at'
  | 'work_at'
  | 'monitor_system'
  | 'think_deep'
  | 'commune'
  | 'alert_response';

export interface WorldIntentRequest {
  intent: WorldIntent;
  targetRoomId?: string;
  targetFurnitureId?: string;
  targetWorldPos?: Point;
  reason: string;
}

export interface WorldIntentResult {
  success: boolean;
  targetPos: Point | null;
  targetRoom: Room | null;
  targetFurniture: Furniture | null;
  suggestedAction: string;
  message: string;
}

// ===== 桥接状态 =====

export interface WorldBridgeState {
  /** 当前屏幕坐标（用于 GlobalAvatarFree 同步） */
  screenPos: Point;
  /** 当前世界坐标 */
  worldPos: Point;
  /** 是否在 world tab 中 */
  isInWorldTab: boolean;
  /** 当前激活的意图 */
  activeIntent: WorldIntentRequest | null;
  /** 意图开始时间 */
  intentStartTime: number;
}

export function createWorldBridgeState(): WorldBridgeState {
  return {
    screenPos: { x: 0, y: 0 },
    worldPos: { x: 0, y: 0 },
    isInWorldTab: false,
    activeIntent: null,
    intentStartTime: 0,
  };
}

// ===== 坐标桥接 =====

/**
 * 将世界坐标转换为屏幕坐标（用于在世界 Canvas 上定位 GlobalAvatarFree）
 */
export function worldToScreenPos(worldPos: Point, camera: Camera): Point {
  return worldToScreen(worldPos.x, worldPos.y, camera);
}

/**
 * 将屏幕坐标转换为世界坐标（用于将 GlobalAvatarFree 的点击/拖拽映射到世界）
 */
export function screenToWorldPos(screenPos: Point, camera: Camera): Point {
  return screenToWorld(screenPos.x, screenPos.y, camera);
}

/**
 * 计算 Avatar 在世界 Canvas 中的屏幕位置
 * 用于将 world Avatar 的渲染位置同步到 GlobalAvatarFree
 */
export function getAvatarScreenPos(
  avatar: WorldAvatarState,
  camera: Camera
): Point {
  return worldToScreen(avatar.position.x, avatar.position.y, camera);
}

/**
 * 判断屏幕位置是否在世界 Canvas 可见区域内
 */
export function isScreenPosInWorldView(
  screenPos: Point,
  canvasRect: { width: number; height: number }
): boolean {
  return (
    screenPos.x >= 0 &&
    screenPos.x <= canvasRect.width &&
    screenPos.y >= 0 &&
    screenPos.y <= canvasRect.height
  );
}

// ===== 意图解析 =====

/**
 * 解析高级意图，返回目标位置和建议动作
 */
export function resolveWorldIntent(
  request: WorldIntentRequest,
  rooms: Room[]
): WorldIntentResult {
  const { intent, targetRoomId, targetFurnitureId } = request;

  switch (intent) {
    case 'goto_room': {
      const room = rooms.find(r => r.id === targetRoomId);
      if (!room) {
        return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '目标房间不存在' };
      }
      if (!room.unlocked) {
        return { success: false, targetPos: null, targetRoom: room, targetFurniture: null, suggestedAction: 'idle', message: '房间未解锁' };
      }
      const targetPos = {
        x: room.bounds.x + room.bounds.w / 2,
        y: room.bounds.y + room.bounds.h / 2,
      };
      return { success: true, targetPos, targetRoom: room, targetFurniture: null, suggestedAction: 'walk', message: `前往 ${room.nameZh}` };
    }

    case 'goto_furniture': {
      if (!targetRoomId || !targetFurnitureId) {
        return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '缺少目标房间或家具 ID' };
      }
      const room = rooms.find(r => r.id === targetRoomId);
      if (!room) {
        return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '目标房间不存在' };
      }
      const furniture = room.furniture.find(f => f.id === targetFurnitureId);
      if (!furniture) {
        return { success: false, targetPos: null, targetRoom: room, targetFurniture: null, suggestedAction: 'idle', message: '目标家具不存在' };
      }
      const targetPos = getFurnitureStandPos(furniture, room);
      const mapping = Object.entries(SYSTEM_ACTION_MAP).find(([, v]) => v.furnitureType === furniture.type);
      const suggestedAction = mapping ? mapping[1].action : 'idle';
      return { success: true, targetPos, targetRoom: room, targetFurniture: furniture, suggestedAction, message: `前往 ${furniture.name}` };
    }

    case 'rest_at': {
      const restFurniture = findFurnitureByFunction(rooms, 'rest');
      if (!restFurniture) {
        return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '没有可休息的家具' };
      }
      const targetPos = getFurnitureStandPos(restFurniture.furniture, restFurniture.room);
      return { success: true, targetPos, targetRoom: restFurniture.room, targetFurniture: restFurniture.furniture, suggestedAction: 'rest', message: `前往 ${restFurniture.furniture.name} 休息` };
    }

    case 'work_at': {
      const workFurniture = findFurnitureByFunction(rooms, 'work');
      if (!workFurniture) {
        return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '没有可工作的家具' };
      }
      const targetPos = getFurnitureStandPos(workFurniture.furniture, workFurniture.room);
      return { success: true, targetPos, targetRoom: workFurniture.room, targetFurniture: workFurniture.furniture, suggestedAction: 'operate', message: `前往 ${workFurniture.furniture.name} 工作` };
    }

    case 'monitor_system': {
      const monitorFurniture = findFurnitureByFunction(rooms, 'monitor');
      if (!monitorFurniture) {
        return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '没有监控设备' };
      }
      const targetPos = getFurnitureStandPos(monitorFurniture.furniture, monitorFurniture.room);
      return { success: true, targetPos, targetRoom: monitorFurniture.room, targetFurniture: monitorFurniture.furniture, suggestedAction: 'monitor', message: `前往 ${monitorFurniture.furniture.name} 监控` };
    }

    case 'think_deep': {
      const thinkFurniture = findFurnitureByFunction(rooms, 'think');
      if (!thinkFurniture) {
        // 如果没有思考专用家具，去任意房间中心
        const room = rooms.find(r => r.unlocked);
        if (!room) {
          return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '没有可用房间' };
        }
        const targetPos = { x: room.bounds.x + room.bounds.w / 2, y: room.bounds.y + room.bounds.h / 2 };
        return { success: true, targetPos, targetRoom: room, targetFurniture: null, suggestedAction: 'think_deep', message: '开始深度思考' };
      }
      const targetPos = getFurnitureStandPos(thinkFurniture.furniture, thinkFurniture.room);
      return { success: true, targetPos, targetRoom: thinkFurniture.room, targetFurniture: thinkFurniture.furniture, suggestedAction: 'think_deep', message: `前往 ${thinkFurniture.furniture.name} 思考` };
    }

    case 'explore_world': {
      const unlockedRooms = rooms.filter(r => r.unlocked);
      if (unlockedRooms.length === 0) {
        return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '没有可探索的房间' };
      }
      const randomRoom = unlockedRooms[Math.floor(Math.random() * unlockedRooms.length)];
      const targetPos = {
        x: randomRoom.bounds.x + 50 + Math.random() * (randomRoom.bounds.w - 100),
        y: randomRoom.bounds.y + 50 + Math.random() * (randomRoom.bounds.h - 100),
      };
      return { success: true, targetPos, targetRoom: randomRoom, targetFurniture: null, suggestedAction: 'walk', message: `探索 ${randomRoom.nameZh}` };
    }

    case 'alert_response': {
      // 告警响应：前往控制台
      const consoleFurniture = findFurnitureByType(rooms, 'console');
      if (!consoleFurniture) {
        return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'alert', message: '没有控制台' };
      }
      const targetPos = getFurnitureStandPos(consoleFurniture.furniture, consoleFurniture.room);
      return { success: true, targetPos, targetRoom: consoleFurniture.room, targetFurniture: consoleFurniture.furniture, suggestedAction: 'alert', message: `紧急响应：前往 ${consoleFurniture.furniture.name}` };
    }

    case 'commune': {
      // 交流：前往沙发或任意休息区
      const communeFurniture = findFurnitureByFunction(rooms, 'rest') || findFurnitureByFunction(rooms, 'display');
      if (!communeFurniture) {
        const room = rooms.find(r => r.unlocked);
        if (!room) {
          return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '没有可用房间' };
        }
        const targetPos = { x: room.bounds.x + room.bounds.w / 2, y: room.bounds.y + room.bounds.h / 2 };
        return { success: true, targetPos, targetRoom: room, targetFurniture: null, suggestedAction: 'commune', message: '准备交流' };
      }
      const targetPos = getFurnitureStandPos(communeFurniture.furniture, communeFurniture.room);
      return { success: true, targetPos, targetRoom: communeFurniture.room, targetFurniture: communeFurniture.furniture, suggestedAction: 'commune', message: `前往 ${communeFurniture.furniture.name} 交流` };
    }

    default:
      return { success: false, targetPos: null, targetRoom: null, targetFurniture: null, suggestedAction: 'idle', message: '未知意图' };
  }
}

// ===== AIState → 世界意图映射 =====

export interface AIStateSnapshot {
  isThinking: boolean;
  isSpeaking: boolean;
  emotion: string;
  alertSeverity: string | null;
  physicalTasks: number;
  userDetected: boolean;
  systemLoad: number;
}

/**
 * 根据 AIState 快照推断 Avatar 应该执行的世界意图
 */
export function inferWorldIntentFromAIState(
  aiState: AIStateSnapshot,
  _currentRoomId: string
): WorldIntentRequest | null {
  // 优先级 1：系统告警
  if (aiState.alertSeverity === 'critical' || aiState.alertSeverity === 'high') {
    return { intent: 'alert_response', reason: '系统严重告警' };
  }

  // 优先级 2：深度思考中
  if (aiState.isThinking && aiState.systemLoad > 0.6) {
    return { intent: 'think_deep', reason: 'AI 正在深度思考' };
  }

  // 优先级 3：用户交流中
  if (aiState.isSpeaking || aiState.userDetected) {
    return { intent: 'commune', reason: '用户在场交流' };
  }

  // 优先级 4：物理任务调度
  if (aiState.physicalTasks > 0) {
    return { intent: 'work_at', reason: '有物理任务需要调度' };
  }

  // 优先级 5：系统监控（低负载时）
  if (aiState.alertSeverity === 'medium' || aiState.alertSeverity === 'low') {
    return { intent: 'monitor_system', reason: '系统有轻微告警' };
  }

  // 默认：探索或休息
  if (Math.random() < 0.3) {
    return { intent: 'explore_world', reason: '随机探索' };
  }

  return null;
}

/**
 * 将 AIState 中的 emotion 映射为 Avatar 动作
 */
export function emotionToWorldAction(emotion: string): string {
  const map: Record<string, string> = {
    happy: 'celebrate',
    sad: 'rest',
    angry: 'alert',
    anxious: 'monitor',
    focused: 'think_deep',
    relaxed: 'rest',
    curious: 'explore_world',
    grateful: 'commune',
    neutral: 'idle',
  };
  return map[emotion] || 'idle';
}

// ===== 工具函数 =====

function getFurnitureStandPos(furniture: Furniture, room: Room): Point {
  if (furniture.avatarAnchor) {
    return roomToWorld(furniture.avatarAnchor.x, furniture.avatarAnchor.y, room);
  }
  // 默认站在家具前方
  return roomToWorld(
    furniture.position.x + furniture.size.w / 2,
    furniture.position.y + furniture.size.h + 20,
    room
  );
}

function findFurnitureByFunction(
  rooms: Room[],
  func: string
): { room: Room; furniture: Furniture } | null {
  for (const room of rooms) {
    if (!room.unlocked) continue;
    for (const furniture of room.furniture) {
      if (furniture.functions.includes(func as any)) {
        return { room, furniture };
      }
    }
  }
  return null;
}

function findFurnitureByType(
  rooms: Room[],
  type: string
): { room: Room; furniture: Furniture } | null {
  for (const room of rooms) {
    if (!room.unlocked) continue;
    for (const furniture of room.furniture) {
      if (furniture.type === type) {
        return { room, furniture };
      }
    }
  }
  return null;
}

// ===== GlobalAvatarFree 同步 =====

/**
 * 将 world Avatar 状态同步到 GlobalAvatarFree 的屏幕位置
 * 返回：{ screenX, screenY, action, visible }
 */
export function syncWorldAvatarToScreen(
  avatar: WorldAvatarState,
  camera: Camera,
  canvasRect: { width: number; height: number }
): { screenX: number; screenY: number; action: string; visible: boolean } {
  const screenPos = getAvatarScreenPos(avatar, camera);
  const visible = isScreenPosInWorldView(screenPos, canvasRect);
  return {
    screenX: screenPos.x,
    screenY: screenPos.y,
    action: avatar.currentAction,
    visible,
  };
}

/**
 * 当 GlobalAvatarFree 在屏幕自由移动时，将其位置同步到世界坐标
 * 用于将 GlobalAvatarFree 的"自由意志"映射到世界系统
 */
export function syncScreenAvatarToWorld(
  screenX: number,
  screenY: number,
  camera: Camera
): Point {
  return screenToWorld(screenX, screenY, camera);
}
