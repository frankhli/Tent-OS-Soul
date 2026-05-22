/**
 * PartSystem — 类 Spine 的纯代码 2D 骨骼部件系统
 * 核心思想：每个部位在局部坐标系绘制，通过骨骼变换到世界坐标
 * 解决"一个函数画全身"导致的比例崩坏和头身分离问题
 */

import type { Skeleton } from './Bone';
import type { FaceParams } from './FaceDeformation';

/** 部件绘制上下文 */
export interface PartDrawContext {
  emotion: string;
  time: number;
  face: FaceParams;
  mouthOpen: number;
  asleep: boolean;
  lookX: number;
  lookY: number;
  blinkOpen: number;
}

/** 单个部件定义 */
export interface PartDef {
  id: string;
  boneId: string;
  zIndex: number;
  draw: (ctx: CanvasRenderingContext2D, ctx2: PartDrawContext) => void;
}

/** 部件系统 */
export class PartSystem {
  parts: PartDef[] = [];

  constructor(parts: PartDef[]) {
    this.parts = [...parts].sort((a, b) => a.zIndex - b.zIndex);
  }

  /** 绘制所有部件 */
  draw(
    ctx: CanvasRenderingContext2D,
    skeleton: Skeleton,
    state: PartDrawContext
  ) {
    for (const part of this.parts) {
      const bone = skeleton.getWorld(part.boneId);
      if (!bone) continue;

      ctx.save();
      ctx.translate(bone.x, bone.y);
      ctx.rotate(bone.rotation);
      ctx.scale(bone.scaleX, bone.scaleY);

      part.draw(ctx, state);

      ctx.restore();
    }
  }
}

/** 颜色工具 */
export function shadeColor(hex: string, percent: number): string {
  const c = parseInt(hex.replace('#', ''), 16);
  const r = (c >> 16) & 255;
  const g = (c >> 8) & 255;
  const b = c & 255;
  const factor = 1 + percent / 100;
  const clamp = (v: number) => Math.min(255, Math.max(0, Math.round(v)));
  return '#' + [clamp(r * factor), clamp(g * factor), clamp(b * factor)]
    .map((x) => x.toString(16).padStart(2, '0')).join('');
}

/** 品牌色系 */
export const BRAND_COLORS = {
  skin: '#f5e6d8',        // 暖奶油肤色
  skinShadow: '#e8d4c4',
  skinHighlight: '#fff5ee',
  hair: '#4ecdc4',        // Tent OS 品牌青绿色
  hairDark: '#2d8a82',
  hairLight: '#7eede5',
  eyeWhite: '#ffffff',
  eyeIris: '#2d6a4f',
  eyePupil: '#1a1a2e',
  mouth: '#c97b7b',
  mouthInner: '#8b4545',
  blush: '#ffb6c1',
  body: '#5ee7df',        // 比头发稍亮的青绿
  bodyDark: '#3cbdb5',
  outline: '#2c3e50',
};
