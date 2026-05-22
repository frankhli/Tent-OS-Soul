/**
 * 骨骼系统 — 层级变换矩阵链
 * 每个骨骼有局部变换（相对于父级），世界变换通过递归父级链计算
 */

export interface BoneDef {
  id: string;
  parent?: string;
  x: number;
  y: number;
  rotation: number;
  scaleX: number;
  scaleY: number;
  length: number;
  visible: boolean;
}

export interface WorldTransform {
  x: number;
  y: number;
  rotation: number;
  scaleX: number;
  scaleY: number;
}

export class Skeleton {
  bones: Map<string, BoneDef> = new Map();
  private cache: Map<string, WorldTransform> = new Map();
  private dirty = true;

  constructor(defs: BoneDef[]) {
    for (const d of defs) this.bones.set(d.id, { ...d });
  }

  /** 设置单根骨骼的局部变换 */
  setLocal(boneId: string, patch: Partial<BoneDef>) {
    const b = this.bones.get(boneId);
    if (!b) return;
    if (patch.x !== undefined) b.x = patch.x;
    if (patch.y !== undefined) b.y = patch.y;
    if (patch.rotation !== undefined) b.rotation = patch.rotation;
    if (patch.scaleX !== undefined) b.scaleX = patch.scaleX;
    if (patch.scaleY !== undefined) b.scaleY = patch.scaleY;
    if (patch.length !== undefined) b.length = patch.length;
    if (patch.visible !== undefined) b.visible = patch.visible;
    this.dirty = true;
  }

  getLocal(boneId: string): BoneDef | undefined {
    return this.bones.get(boneId);
  }

  /** 计算世界变换（递归父级链） */
  getWorld(boneId: string): WorldTransform {
    if (!this.dirty) {
      const c = this.cache.get(boneId);
      if (c) return c;
    }
    const b = this.bones.get(boneId);
    if (!b) return { x: 0, y: 0, rotation: 0, scaleX: 1, scaleY: 1 };

    let wx = b.x;
    let wy = b.y;
    let wr = b.rotation;
    let wsx = b.scaleX;
    let wsy = b.scaleY;

    let parentId = b.parent;
    while (parentId) {
      const p = this.bones.get(parentId);
      if (!p) break;
      // 父级旋转下变换子级位置
      const cos = Math.cos(p.rotation);
      const sin = Math.sin(p.rotation);
      const rx = wx * cos - wy * sin;
      const ry = wx * sin + wy * cos;
      wx = p.x + rx * p.scaleX;
      wy = p.y + ry * p.scaleY;
      wr += p.rotation;
      wsx *= p.scaleX;
      wsy *= p.scaleY;
      parentId = p.parent;
    }

    const result = { x: wx, y: wy, rotation: wr, scaleX: wsx, scaleY: wsy };
    this.cache.set(boneId, result);
    return result;
  }

  /** 标记所有缓存失效 */
  invalidate() {
    this.dirty = true;
    this.cache.clear();
  }

  /** 批量设置姿态（用于关键帧） */
  applyPose(pose: Record<string, Partial<BoneDef>>) {
    for (const [id, patch] of Object.entries(pose)) {
      this.setLocal(id, patch);
    }
  }

  /** 遍历所有骨骼 */
  forEach(fn: (bone: BoneDef, world: WorldTransform) => void) {
    for (const b of this.bones.values()) {
      fn(b, this.getWorld(b.id));
    }
    this.dirty = false;
  }
}

/** 默认骨骼定义 — 拟人化几何体生命 */
export function createDefaultSkeleton(): BoneDef[] {
  return [
    // 根骨骼 — 控制整体位置/朝向（漫游时移动这个）
    { id: 'root', parent: undefined, x: 0, y: 0, rotation: 0, scaleX: 1, scaleY: 1, length: 0, visible: false },

    // 骨盆（重心基准）
    { id: 'pelvis', parent: 'root', x: 0, y: 35, rotation: 0, scaleX: 1, scaleY: 1, length: 20, visible: true },

    // 躯干（从骨盆向上）
    { id: 'torso', parent: 'pelvis', x: 0, y: -30, rotation: 0, scaleX: 1, scaleY: 1, length: 45, visible: true },

    // 颈部
    { id: 'neck', parent: 'torso', x: 0, y: -40, rotation: 0, scaleX: 1, scaleY: 1, length: 12, visible: true },

    // 头部
    { id: 'head', parent: 'neck', x: 0, y: -14, rotation: 0, scaleX: 1, scaleY: 1, length: 32, visible: true },

    // 左天线
    { id: 'antenna_L_base', parent: 'head', x: -14, y: -28, rotation: -0.3, scaleX: 1, scaleY: 1, length: 18, visible: true },
    { id: 'antenna_L_tip', parent: 'antenna_L_base', x: 0, y: -18, rotation: 0, scaleX: 1, scaleY: 1, length: 6, visible: true },

    // 右天线
    { id: 'antenna_R_base', parent: 'head', x: 14, y: -28, rotation: 0.3, scaleX: 1, scaleY: 1, length: 18, visible: true },
    { id: 'antenna_R_tip', parent: 'antenna_R_base', x: 0, y: -18, rotation: 0, scaleX: 1, scaleY: 1, length: 6, visible: true },

    // 左臂
    { id: 'shoulder_L', parent: 'torso', x: -22, y: -35, rotation: 0, scaleX: 1, scaleY: 1, length: 10, visible: true },
    { id: 'arm_L', parent: 'shoulder_L', x: 0, y: 0, rotation: 0.15, scaleX: 1, scaleY: 1, length: 22, visible: true },
    { id: 'forearm_L', parent: 'arm_L', x: 0, y: -22, rotation: -0.2, scaleX: 1, scaleY: 1, length: 20, visible: true },
    { id: 'hand_L', parent: 'forearm_L', x: 0, y: -20, rotation: 0, scaleX: 1, scaleY: 1, length: 8, visible: true },

    // 右臂
    { id: 'shoulder_R', parent: 'torso', x: 22, y: -35, rotation: 0, scaleX: 1, scaleY: 1, length: 10, visible: true },
    { id: 'arm_R', parent: 'shoulder_R', x: 0, y: 0, rotation: -0.15, scaleX: 1, scaleY: 1, length: 22, visible: true },
    { id: 'forearm_R', parent: 'arm_R', x: 0, y: -22, rotation: 0.2, scaleX: 1, scaleY: 1, length: 20, visible: true },
    { id: 'hand_R', parent: 'forearm_R', x: 0, y: -20, rotation: 0, scaleX: 1, scaleY: 1, length: 8, visible: true },

    // 左腿
    { id: 'thigh_L', parent: 'pelvis', x: -12, y: 10, rotation: 0, scaleX: 1, scaleY: 1, length: 26, visible: true },
    { id: 'leg_L', parent: 'thigh_L', x: 0, y: 26, rotation: 0, scaleX: 1, scaleY: 1, length: 24, visible: true },
    { id: 'foot_L', parent: 'leg_L', x: 0, y: 24, rotation: 0, scaleX: 1, scaleY: 1, length: 10, visible: true },

    // 右腿
    { id: 'thigh_R', parent: 'pelvis', x: 12, y: 10, rotation: 0, scaleX: 1, scaleY: 1, length: 26, visible: true },
    { id: 'leg_R', parent: 'thigh_R', x: 0, y: 26, rotation: 0, scaleX: 1, scaleY: 1, length: 24, visible: true },
    { id: 'foot_R', parent: 'leg_R', x: 0, y: 24, rotation: 0, scaleX: 1, scaleY: 1, length: 10, visible: true },
  ];
}
