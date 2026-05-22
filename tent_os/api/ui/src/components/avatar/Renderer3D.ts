/**
 * 3D 形体绘制 — 用 Canvas 2D 模拟 3D 球体/椭球体
 * 虚拟光源从左上方向照射
 */

export interface ColorRGB { r: number; g: number; b: number; }
export interface LightDir { x: number; y: number; }

/** 默认光源方向：左上 */
export const DEFAULT_LIGHT: LightDir = { x: -0.6, y: -0.8 };

export function hexToRgb(hex: string): ColorRGB {
  const v = hex.replace('#', '');
  const n = parseInt(v, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

export function rgbToHex(r: number, g: number, b: number): string {
  return '#' + [r, g, b].map((x) => Math.max(0, Math.min(255, x | 0)).toString(16).padStart(2, '0')).join('');
}

export function mixColor(hex: string, tint: { r: number; g: number; b: number; strength: number }): string {
  const c = hexToRgb(hex);
  const s = tint.strength;
  return rgbToHex(
    Math.round(c.r * (1 - s) + tint.r * s),
    Math.round(c.g * (1 - s) + tint.g * s),
    Math.round(c.b * (1 - s) + tint.b * s)
  );
}

/** 调整颜色亮度 */
export function shadeColor(hex: string, percent: number): string {
  const c = hexToRgb(hex);
  const factor = 1 + percent / 100;
  return rgbToHex(
    Math.min(255, Math.round(c.r * factor)),
    Math.min(255, Math.round(c.g * factor)),
    Math.min(255, Math.round(c.b * factor))
  );
}

/** 绘制 3D 球体 */
export function drawSphere(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, radius: number,
  color: string, lightDir: LightDir = DEFAULT_LIGHT,
  opacity = 1
) {
  ctx.save();
  ctx.globalAlpha = opacity;

  // 高光偏移（与光源反向）
  const hlX = -radius * 0.35 * lightDir.x;
  const hlY = -radius * 0.35 * lightDir.y;

  // 基础球体（径向渐变）
  const baseGrad = ctx.createRadialGradient(
    cx + hlX, cy + hlY, radius * 0.05,
    cx, cy, radius
  );
  baseGrad.addColorStop(0, shadeColor(color, 40));   // 高光
  baseGrad.addColorStop(0.4, color);                  // 基础色
  baseGrad.addColorStop(0.85, shadeColor(color, -25)); // 阴影
  baseGrad.addColorStop(1, shadeColor(color, -50));    // 边缘暗

  ctx.fillStyle = baseGrad;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();

  // 边缘光（rim light）— 光源反向的边缘
  const rimGrad = ctx.createRadialGradient(
    cx - radius * 0.4 * lightDir.x,
    cy - radius * 0.4 * lightDir.y,
    radius * 0.6,
    cx, cy, radius
  );
  rimGrad.addColorStop(0, 'transparent');
  rimGrad.addColorStop(0.75, 'transparent');
  rimGrad.addColorStop(1, shadeColor(color, 30) + '30');

  ctx.fillStyle = rimGrad;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();

  // 高光点（specular）
  ctx.fillStyle = 'rgba(255,255,255,0.25)';
  ctx.beginPath();
  ctx.ellipse(cx + hlX * 0.6, cy + hlY * 0.6, radius * 0.2, radius * 0.12, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

/** 绘制 3D 椭球体 */
export function drawEllipsoid(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, rx: number, ry: number,
  color: string, lightDir: LightDir = DEFAULT_LIGHT,
  rotation = 0, opacity = 1
) {
  ctx.save();
  ctx.globalAlpha = opacity;
  ctx.translate(cx, cy);
  ctx.rotate(rotation);

  // 将光源方向转换到椭球的局部坐标
  const cos = Math.cos(-rotation);
  const sin = Math.sin(-rotation);
  const localLightX = (lightDir.x * cos - lightDir.y * sin) * (ry / rx);
  const localLightY = (lightDir.x * sin + lightDir.y * cos);
  const lightLen = Math.sqrt(localLightX * localLightX + localLightY * localLightY) || 1;
  const lnx = localLightX / lightLen;
  const lny = localLightY / lightLen;

  const hlOffX = -rx * 0.35 * lnx;
  const hlOffY = -ry * 0.35 * lny;

  const baseGrad = ctx.createRadialGradient(
    hlOffX, hlOffY, Math.min(rx, ry) * 0.05,
    0, 0, Math.max(rx, ry)
  );
  baseGrad.addColorStop(0, shadeColor(color, 40));
  baseGrad.addColorStop(0.4, color);
  baseGrad.addColorStop(0.85, shadeColor(color, -25));
  baseGrad.addColorStop(1, shadeColor(color, -50));

  ctx.fillStyle = baseGrad;
  ctx.beginPath();
  ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();

  // 边缘光
  const rimGrad = ctx.createRadialGradient(
    -rx * 0.4 * lnx, -ry * 0.4 * lny,
    Math.min(rx, ry) * 0.6,
    0, 0, Math.max(rx, ry)
  );
  rimGrad.addColorStop(0, 'transparent');
  rimGrad.addColorStop(0.75, 'transparent');
  rimGrad.addColorStop(1, shadeColor(color, 30) + '30');

  ctx.fillStyle = rimGrad;
  ctx.beginPath();
  ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();

  // 高光
  ctx.fillStyle = 'rgba(255,255,255,0.22)';
  ctx.beginPath();
  ctx.ellipse(hlOffX * 0.6, hlOffY * 0.6, rx * 0.18, ry * 0.1, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

/** 绘制 3D 胶囊体（四肢用） */
export function drawCapsule(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number, x2: number, y2: number,
  radius: number, color: string,
  lightDir: LightDir = DEFAULT_LIGHT, opacity = 1
) {
  ctx.save();
  ctx.globalAlpha = opacity;

  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 0.1) {
    drawSphere(ctx, x1, y1, radius, color, lightDir, opacity);
    ctx.restore();
    return;
  }

  const angle = Math.atan2(dy, dx);
  const perpX = -dy / len;
  const perpY = dx / len;

  // 绘制胶囊体主体（两端半圆 + 中间矩形）
  ctx.beginPath();
  ctx.moveTo(x1 + perpX * radius, y1 + perpY * radius);
  ctx.lineTo(x2 + perpX * radius, y2 + perpY * radius);
  ctx.arc(x2, y2, radius, angle + Math.PI / 2, angle - Math.PI / 2);
  ctx.lineTo(x1 - perpX * radius, y1 - perpY * radius);
  ctx.arc(x1, y1, radius, angle - Math.PI / 2, angle + Math.PI / 2);
  ctx.closePath();

  // 胶囊体渐变（模拟圆柱体光照）
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;

  const grad = ctx.createLinearGradient(
    midX + perpX * radius * 0.5, midY + perpY * radius * 0.5,
    midX - perpX * radius * 0.5, midY - perpY * radius * 0.5
  );
  grad.addColorStop(0, shadeColor(color, 25));
  grad.addColorStop(0.5, color);
  grad.addColorStop(1, shadeColor(color, -35));

  ctx.fillStyle = grad;
  ctx.fill();

  // 两端关节球
  drawSphere(ctx, x1, y1, radius * 0.85, color, lightDir, opacity * 0.9);
  drawSphere(ctx, x2, y2, radius * 0.85, color, lightDir, opacity * 0.9);

  ctx.restore();
}

/** 绘制眼睛（带高光和瞳孔追踪） */
export function drawEye(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, radius: number,
  lookX: number, lookY: number,
  openRatio: number, isSleeping: boolean,
  lightDir: LightDir = DEFAULT_LIGHT
) {
  if (isSleeping || openRatio < 0.05) {
    // 闭眼 — 一条弧线
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0.1 * Math.PI, 0.9 * Math.PI);
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = 2;
    ctx.stroke();
    return;
  }

  // 眼白（球体）
  drawSphere(ctx, cx, cy, radius, '#f8fafc', lightDir);

  // 瞳孔位置（受 lookX/lookY 影响）
  const pupilR = radius * 0.45;
  const maxOff = radius * 0.35;
  const px = cx + Math.max(-maxOff, Math.min(maxOff, lookX));
  const py = cy + Math.max(-maxOff, Math.min(maxOff, lookY));

  // 瞳孔（深色球体）
  drawSphere(ctx, px, py, pupilR, '#1e293b', lightDir);

  // 高光点
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.beginPath();
  ctx.arc(px - pupilR * 0.25, py - pupilR * 0.25, pupilR * 0.3, 0, Math.PI * 2);
  ctx.fill();

  // 上眼睑阴影
  if (openRatio < 1) {
    ctx.fillStyle = 'rgba(0,0,0,0.15)';
    ctx.beginPath();
    ctx.ellipse(cx, cy - radius * 0.3, radius * 0.9, radius * (1 - openRatio) * 0.5, 0, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** 绘制嘴巴（情绪 + 口型同步） */
export function drawMouth(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, width: number,
  expression: 'smile' | 'sad' | 'surprised' | 'angry' | 'neutral',
  openRatio: number
) {
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  let curveY = 0;
  switch (expression) {
    case 'smile': curveY = 4 + openRatio * 3; break;
    case 'sad': curveY = -3 - openRatio; break;
    case 'surprised': curveY = 6 + openRatio * 4; break;
    case 'angry': curveY = -2; break;
    default: curveY = openRatio * 2;
  }

  // 嘴巴线条
  ctx.beginPath();
  ctx.moveTo(cx - width / 2, cy);
  ctx.quadraticCurveTo(cx, cy + curveY, cx + width / 2, cy);
  ctx.strokeStyle = '#374151';
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // 张开时的口腔内部
  if (openRatio > 0.15) {
    const h = Math.abs(curveY) * 0.6 + openRatio * 3;
    ctx.beginPath();
    ctx.ellipse(cx, cy + curveY * 0.3, width * 0.35, h * 0.5, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#334155';
    ctx.fill();
  }

  ctx.restore();
}

/** 简化版绘制 — 用于小尺寸（<80px） */
export function drawSimpleBody(
  ctx: CanvasRenderingContext2D,
  skeleton: { getWorld: (id: string) => { x: number; y: number; rotation: number } },
  color: string
) {
  // 小尺寸回退：简单线条+圆球，保证性能
  const head = skeleton.getWorld('head');
  const torso = skeleton.getWorld('torso');

  // 头
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(head.x, head.y, 18, 0, Math.PI * 2);
  ctx.fill();

  // 身体
  ctx.fillStyle = shadeColor(color, -15);
  ctx.beginPath();
  ctx.ellipse(torso.x, torso.y + 15, 20, 28, 0, 0, Math.PI * 2);
  ctx.fill();

  // 四肢简化为线条
  ctx.strokeStyle = shadeColor(color, -10);
  ctx.lineWidth = 4;
  ctx.lineCap = 'round';

  const drawLimb = (upper: string, lower: string) => {
    const u = skeleton.getWorld(upper);
    const l = skeleton.getWorld(lower);
    ctx.beginPath();
    ctx.moveTo(u.x, u.y);
    ctx.lineTo(l.x, l.y);
    ctx.stroke();
  };

  drawLimb('arm_L', 'forearm_L');
  drawLimb('arm_R', 'forearm_R');
  drawLimb('thigh_L', 'leg_L');
  drawLimb('thigh_R', 'leg_R');
}
/**
 * 面部绘制系统 — 参数化五官（眉毛、眼睛、嘴巴、脸颊）
 * 基于 FaceDeformation 的 16 维参数驱动
 */
import type { FaceParams } from './FaceDeformation';

export function drawFace(
  ctx: CanvasRenderingContext2D,
  headX: number, headY: number, headRadius: number,
  face: FaceParams,
  lookX: number, lookY: number,
  _lightDir: { x: number; y: number },
  _emotion: string,
  mouthOpenOverride: number,
  asleep: boolean
) {
  const r = headRadius;
  const eyeY = headY - r * 0.05;

  // 脸颊红晕
  if (face.cheekBlush > 0.05) {
    const blushAlpha = face.cheekBlush * 0.5;
    const blushR = r * 0.35;
    const blushY = headY + r * 0.1;

    // 左脸颊
    ctx.fillStyle = `rgba(255, 150, 160, ${blushAlpha})`;
    ctx.beginPath();
    ctx.ellipse(headX - r * 0.55, blushY, blushR, blushR * 0.6, -0.2, 0, Math.PI * 2);
    ctx.fill();

    // 右脸颊
    ctx.beginPath();
    ctx.ellipse(headX + r * 0.55, blushY, blushR, blushR * 0.6, 0.2, 0, Math.PI * 2);
    ctx.fill();
  }

  // 脸颊鼓起
  if (face.cheekPuff > 0.05) {
    const puffAlpha = face.cheekPuff * 0.35;
    const puffR = r * 0.3;
    const puffY = headY + r * 0.15;

    ctx.fillStyle = `rgba(255, 200, 180, ${puffAlpha})`;
    ctx.beginPath();
    ctx.ellipse(headX - r * 0.45, puffY, puffR, puffR * 0.5, -0.1, 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    ctx.ellipse(headX + r * 0.45, puffY, puffR, puffR * 0.5, 0.1, 0, Math.PI * 2);
    ctx.fill();
  }

  // 头部倾斜（带动整个面部偏移）
  const tiltOffset = face.faceTilt * r * 0.15;

  // --- 眉毛 ---
  drawEyebrow(ctx, headX - r * 0.42, eyeY - r * 0.35 + tiltOffset, r * 0.35, face.browLHeight, face.browLAngle);
  drawEyebrow(ctx, headX + r * 0.42, eyeY - r * 0.35 - tiltOffset, r * 0.35, face.browRHeight, face.browRAngle);

  // --- 眼睛 ---
  const eyeRx = r * 0.28;
  drawDeformedEye(ctx, headX - r * 0.35, eyeY, eyeRx, face.eyeLOpen, face.eyeLPupil, face.eyeLSquint, lookX, lookY, asleep);
  drawDeformedEye(ctx, headX + r * 0.35, eyeY, eyeRx, face.eyeROpen, face.eyeRPupil, face.eyeRSquint, lookX, lookY, asleep);

  // --- 嘴巴 ---
  const mouthY = headY + r * 0.45 + face.faceSquash * r * 0.1;
  const mouthW = r * (0.4 + face.mouthWidth * 0.4);
  const openAmount = face.mouthOpen + mouthOpenOverride * 0.5;
  drawDeformedMouth(ctx, headX, mouthY, mouthW, face.mouthHeight, face.mouthCurve, openAmount);
}

/** 绘制眉毛 */
function drawEyebrow(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, width: number,
  height: number, angle: number
) {
  ctx.save();
  ctx.lineCap = 'round';

  const h = height * 4;
  const tilt = angle * 6;

  const x1 = cx - width / 2;
  const x2 = cx + width / 2;
  const y1 = cy + h + tilt;
  const y2 = cy + h - tilt;

  // 眉骨阴影（底层）
  ctx.beginPath();
  ctx.moveTo(x1, y1 + 1);
  ctx.quadraticCurveTo(cx, cy + h * 0.3 + 1, x2, y2 + 1);
  ctx.strokeStyle = 'rgba(0,0,0,0.08)';
  ctx.lineWidth = 4;
  ctx.stroke();

  // 眉毛主体
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.quadraticCurveTo(cx, cy + h * 0.3, x2, y2);
  ctx.strokeStyle = '#2d3748';
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // 眉毛高光
  ctx.beginPath();
  ctx.moveTo(x1, y1 - 1);
  ctx.quadraticCurveTo(cx, cy + h * 0.3 - 1, x2, y2 - 1);
  ctx.strokeStyle = 'rgba(255,255,255,0.3)';
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.restore();
}

/** 绘制变形眼睛（支持开合、瞳孔缩放、眯眼） */
function drawDeformedEye(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, radius: number,
  openRatio: number, pupilScale: number, squint: number,
  lookX: number, lookY: number,
  asleep: boolean
) {
  if (openRatio < 0.05) {
    // 闭眼：画一条线
    ctx.beginPath();
    ctx.moveTo(cx - radius, cy);
    ctx.quadraticCurveTo(cx, cy + 1, cx + radius, cy);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 2;
    ctx.stroke();
    return;
  }

  const eyeH = radius * (0.4 + openRatio * 0.6);
  const squintY = squint * radius * 0.3;

  // 眼白（椭圆）
  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.ellipse(cx, cy + squintY, radius, eyeH, 0, 0, Math.PI * 2);
  ctx.fill();

  // 眼白阴影（上缘）
  ctx.fillStyle = 'rgba(0,0,0,0.06)';
  ctx.beginPath();
  ctx.ellipse(cx, cy + squintY - eyeH * 0.2, radius * 0.9, eyeH * 0.5, 0, Math.PI, Math.PI * 2);
  ctx.fill();

  // 瞳孔位置
  const pupilR = radius * (0.25 + pupilScale * 0.25);
  const maxOffset = radius * 0.4;
  const px = cx + lookX * maxOffset;
  const py = cy + lookY * maxOffset * 0.6 + squintY;

  // 虹膜（有色环）
  const irisR = pupilR * 1.8;
  const irisColor = asleep ? '#4a5568' : '#3b82f6';
  ctx.fillStyle = irisColor;
  ctx.beginPath();
  ctx.arc(px, py, irisR, 0, Math.PI * 2);
  ctx.fill();

  // 虹膜细节环
  ctx.strokeStyle = shadeColor(irisColor, -20);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(px, py, irisR * 0.7, 0, Math.PI * 2);
  ctx.stroke();

  // 瞳孔
  ctx.fillStyle = '#0f172a';
  ctx.beginPath();
  ctx.arc(px, py, pupilR, 0, Math.PI * 2);
  ctx.fill();

  // 高光（两个）
  ctx.fillStyle = 'rgba(255,255,255,0.85)';
  ctx.beginPath();
  ctx.arc(px - pupilR * 0.3, py - pupilR * 0.3, pupilR * 0.35, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = 'rgba(255,255,255,0.4)';
  ctx.beginPath();
  ctx.arc(px + pupilR * 0.4, py + pupilR * 0.15, pupilR * 0.2, 0, Math.PI * 2);
  ctx.fill();

  // 眯眼时的眼睑线
  if (squint > 0.1) {
    ctx.beginPath();
    ctx.moveTo(cx - radius, cy - eyeH * 0.3 + squintY);
    ctx.quadraticCurveTo(cx, cy - eyeH * 0.8 + squintY, cx + radius, cy - eyeH * 0.3 + squintY);
    ctx.strokeStyle = `rgba(45, 55, 72, ${squint * 0.6})`;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // 上眼睑阴影
  if (openRatio < 1) {
    const lidH = (1 - openRatio) * eyeH * 0.8;
    ctx.fillStyle = 'rgba(0,0,0,0.12)';
    ctx.beginPath();
    ctx.ellipse(cx, cy - eyeH * 0.4 + squintY, radius * 0.9, lidH, 0, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** 绘制变形嘴巴 */
function drawDeformedMouth(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, width: number,
  height: number, curve: number, openRatio: number
) {
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  const curveY = curve * 6 + height * 4;
  const halfW = width / 2;

  // 嘴角阴影
  ctx.fillStyle = 'rgba(0,0,0,0.05)';
  ctx.beginPath();
  ctx.ellipse(cx - halfW * 0.9, cy + curveY * 0.1, 3, 2, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(cx + halfW * 0.9, cy + curveY * 0.1, 3, 2, 0, 0, Math.PI * 2);
  ctx.fill();

  // 嘴唇上沿
  ctx.beginPath();
  ctx.moveTo(cx - halfW, cy);
  ctx.quadraticCurveTo(cx - halfW * 0.3, cy + curveY * 0.5, cx, cy + curveY * 0.7);
  ctx.quadraticCurveTo(cx + halfW * 0.3, cy + curveY * 0.5, cx + halfW, cy);
  ctx.strokeStyle = '#374151';
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // 下嘴唇（开口时）
  if (openRatio > 0.1) {
    const mouthH = 3 + openRatio * 5;
    const mouthY = cy + curveY * 0.3;

    // 口腔内部
    ctx.beginPath();
    ctx.moveTo(cx - halfW * 0.7, mouthY);
    ctx.quadraticCurveTo(cx, mouthY + mouthH, cx + halfW * 0.7, mouthY);
    ctx.fillStyle = '#4a1c24';
    ctx.fill();

    // 下唇线
    ctx.beginPath();
    ctx.moveTo(cx - halfW * 0.7, mouthY);
    ctx.quadraticCurveTo(cx, mouthY + mouthH * 0.8, cx + halfW * 0.7, mouthY);
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = 2;
    ctx.stroke();

    // 舌头
    if (openRatio > 0.3) {
      ctx.fillStyle = '#e8929c';
      ctx.beginPath();
      ctx.ellipse(cx, mouthY + mouthH * 0.4, halfW * 0.3, mouthH * 0.3, 0, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  ctx.restore();
}
