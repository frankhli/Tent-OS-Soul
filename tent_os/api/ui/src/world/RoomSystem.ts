/**
 * RoomSystem — 房间坐标系 + 家具管理 + 路径规划
 */

import type { Room, Furniture, Point, WorldAvatarState } from './WorldTypes';
import { SYSTEM_ACTION_MAP } from './WorldTypes';

// ===== 路径规划 =====

interface PathNode {
  x: number;
  y: number;
  g: number; // 从起点到当前节点的代价
  h: number; // 启发式代价（到终点的直线距离）
  f: number; // g + h
  parent?: PathNode;
}

/** 在房间内进行 A* 路径规划（简化版，考虑家具避让） */
export function findPathInRoom(
  start: Point,
  end: Point,
  room: Room,
  gridSize = 20
): Point[] {
  // 如果直接连线不穿过家具，直接返回
  if (!lineIntersectsFurniture(start, end, room)) {
    return [start, end];
  }

  // 简化的 A*：在房间网格上搜索
  const openSet: PathNode[] = [];
  const closedSet = new Set<string>();
  const startNode: PathNode = { x: start.x, y: start.y, g: 0, h: heuristic(start, end), f: 0 };
  startNode.f = startNode.g + startNode.h;
  openSet.push(startNode);

  const maxIterations = 200;
  let iterations = 0;

  while (openSet.length > 0 && iterations < maxIterations) {
    iterations++;
    // 找到 f 值最小的节点
    openSet.sort((a, b) => a.f - b.f);
    const current = openSet.shift()!;
    const key = `${Math.round(current.x)},${Math.round(current.y)}`;

    if (closedSet.has(key)) continue;
    closedSet.add(key);

    // 到达目标（接近即可）
    if (Math.hypot(current.x - end.x, current.y - end.y) < gridSize) {
      return reconstructPath(current, start);
    }

    // 扩展邻居
    const neighbors = [
      { x: current.x + gridSize, y: current.y },
      { x: current.x - gridSize, y: current.y },
      { x: current.x, y: current.y + gridSize },
      { x: current.x, y: current.y - gridSize },
      { x: current.x + gridSize, y: current.y + gridSize },
      { x: current.x - gridSize, y: current.y - gridSize },
      { x: current.x + gridSize, y: current.y - gridSize },
      { x: current.x - gridSize, y: current.y + gridSize },
    ];

    for (const n of neighbors) {
      // 边界检查
      if (n.x < 0 || n.y < 0 || n.x > room.bounds.w || n.y > room.bounds.h) continue;
      // 家具碰撞检查（留出一些边距）
      if (isPointInFurniture(n, room, 15)) continue;

      const g = current.g + gridSize;
      const h = heuristic(n, end);
      const f = g + h;

      const existing = openSet.find(node => Math.abs(node.x - n.x) < 1 && Math.abs(node.y - n.y) < 1);
      if (existing && existing.f <= f) continue;

      openSet.push({ x: n.x, y: n.y, g, h, f, parent: current });
    }
  }

  // 如果 A* 没找到路径，返回直接连线（允许穿过家具）
  return [start, end];
}

function heuristic(a: Point, b: Point): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function reconstructPath(endNode: PathNode, start: Point): Point[] {
  const path: Point[] = [];
  let current: PathNode | undefined = endNode;
  while (current) {
    path.unshift({ x: current.x, y: current.y });
    current = current.parent;
  }
  // 确保起点正确
  if (path.length > 0) {
    path[0] = { ...start };
  }
  return path;
}

/** 检查线段是否穿过家具 */
function lineIntersectsFurniture(start: Point, end: Point, room: Room): boolean {
  const steps = 10;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = start.x + (end.x - start.x) * t;
    const y = start.y + (end.y - start.y) * t;
    if (isPointInFurniture({ x, y }, room, 10)) return true;
  }
  return false;
}

/** 检查点是否在家具内（带边距） */
function isPointInFurniture(p: Point, room: Room, padding: number): boolean {
  for (const f of room.furniture) {
    if (
      p.x >= f.position.x - padding &&
      p.x <= f.position.x + f.size.w + padding &&
      p.y >= f.position.y - padding &&
      p.y <= f.position.y + f.size.h + padding
    ) {
      return true;
    }
  }
  return false;
}

// ===== 家具交互 =====

/** 根据系统动作查找目标家具 */
export function findTargetFurniture(
  action: string,
  room: Room
): Furniture | null {
  const mapping = SYSTEM_ACTION_MAP[action];
  if (!mapping) return null;

  // 优先在当前房间查找
  const furniture = room.furniture.find(f => f.type === mapping.furnitureType && f.interactable);
  if (furniture) return furniture;

  return null;
}

/** 获取 Avatar 使用家具时的站立位置 */
export function getAvatarStandPosition(furniture: Furniture, room: Room): Point {
  // 床：Avatar 躺在床中心
  if (furniture.type === 'bed') {
    return {
      x: room.bounds.x + furniture.position.x + furniture.size.w / 2,
      y: room.bounds.y + furniture.position.y + furniture.size.h * 0.55,
    };
  }

  // 沙发：Avatar 坐在沙发中心
  if (furniture.type === 'sofa') {
    return {
      x: room.bounds.x + furniture.position.x + furniture.size.w / 2,
      y: room.bounds.y + furniture.position.y + furniture.size.h * 0.5,
    };
  }

  if (furniture.avatarAnchor) {
    return {
      x: room.bounds.x + furniture.avatarAnchor.x,
      y: room.bounds.y + furniture.avatarAnchor.y,
    };
  }
  // 默认站在家具前方
  return {
    x: room.bounds.x + furniture.position.x + furniture.size.w / 2,
    y: room.bounds.y + furniture.position.y + furniture.size.h + 20,
  };
}

// ===== 房间间移动 =====

/** 计算两个房间之间的入口点 */
export function getRoomConnectionPoint(from: Room, to: Room): Point {
  // 简单实现：找两个房间最近的边界中点
  const fromCx = from.bounds.x + from.bounds.w / 2;
  const fromCy = from.bounds.y + from.bounds.h / 2;
  const toCx = to.bounds.x + to.bounds.w / 2;
  const toCy = to.bounds.y + to.bounds.h / 2;

  // 找最近的边界
  const dx = toCx - fromCx;
  const dy = toCy - fromCy;

  if (Math.abs(dx) > Math.abs(dy)) {
    // 水平方向更近
    if (dx > 0) {
      // to 在 from 右边
      return {
        x: from.bounds.x + from.bounds.w,
        y: fromCy,
      };
    } else {
      return {
        x: from.bounds.x,
        y: fromCy,
      };
    }
  } else {
    // 垂直方向更近
    if (dy > 0) {
      return {
        x: fromCx,
        y: from.bounds.y + from.bounds.h,
      };
    } else {
      return {
        x: fromCx,
        y: from.bounds.y,
      };
    }
  }
}

/** 获取房间的中心点（世界坐标） */
export function getRoomCenter(room: Room): Point {
  return {
    x: room.bounds.x + room.bounds.w / 2,
    y: room.bounds.y + room.bounds.h / 2,
  };
}

// ===== Avatar 自主行为决策 =====

export interface BehaviorDecision {
  targetPos: Point;
  action: string;
  reason: string;
}

/** 根据系统状态决策 Avatar 的行为 */
export function decideAvatarBehavior(
  _avatar: WorldAvatarState,
  room: Room,
  systemState: {
    alertSeverity: string | null;
    physicalTasks: number;
    isThinking: boolean;
    systemLoad: number;
    userDetected: boolean;
    emotion: string;
  }
): BehaviorDecision | null {
  // P1: 系统告警 → 控制台
  if (systemState.alertSeverity === 'critical') {
    const console = room.furniture.find(f => f.type === 'console');
    if (console) {
      return {
        targetPos: getAvatarStandPosition(console, room),
        action: 'alert',
        reason: '系统紧急告警',
      };
    }
  }

  // P2: 物理任务执行中 → 工作台/书桌
  if (systemState.physicalTasks > 0) {
    const workFurniture = room.furniture.find(f =>
      (f.type === 'desk' || f.type === 'workbench') && f.interactable
    );
    if (workFurniture) {
      return {
        targetPos: getAvatarStandPosition(workFurniture, room),
        action: 'operate',
        reason: '执行物理任务',
      };
    }
  }

  // P3: 深度思考 + 高负载 → 沙发
  if (systemState.isThinking && systemState.systemLoad > 0.5) {
    const sofa = room.furniture.find(f => f.type === 'sofa');
    if (sofa) {
      return {
        targetPos: getAvatarStandPosition(sofa, room),
        action: 'think_deep',
        reason: '深度思考中',
      };
    }
  }

  // P4: 监控模式 → 控制台
  if (systemState.systemLoad > 0.2) {
    const console = room.furniture.find(f => f.type === 'console');
    if (console) {
      return {
        targetPos: getAvatarStandPosition(console, room),
        action: 'monitor',
        reason: '监控系统状态',
      };
    }
  }

  // P5: 用户检测到 → 走向房间入口附近
  if (systemState.userDetected) {
    return {
      targetPos: {
        x: room.bounds.x + room.bounds.w / 2,
        y: room.bounds.y + room.bounds.h - 60,
      },
      action: 'commune',
      reason: '迎接用户',
    };
  }

  // P6: 情绪低落 → 情绪角落（优先）或沙发
  if (systemState.emotion === 'sad' || systemState.emotion === 'tired' || systemState.emotion === 'stressed') {
    const corner = room.furniture.find(f => f.type === 'emotional_corner');
    if (corner) {
      return {
        targetPos: getAvatarStandPosition(corner, room),
        action: 'idle',
        reason: '在情绪角落疗愈',
      };
    }
    const sofa = room.furniture.find(f => f.type === 'sofa');
    if (sofa) {
      return {
        targetPos: getAvatarStandPosition(sofa, room),
        action: 'idle',
        reason: '休息恢复',
      };
    }
  }

  return null;
}
