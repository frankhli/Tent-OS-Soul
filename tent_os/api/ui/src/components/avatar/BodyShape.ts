/**
 * BodyShape — Labubu 风格身体绘制
 * 圆润短小的身体，粗短四肢，Q版潮玩比例
 * 核心特征：汤圆躯干、圆润关节、小短手、小短脚
 */

import { shadeColor } from './Renderer3D';

/** 绘制圆润躯干（汤圆形，短而圆） */
export function drawTorso(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  width: number, height: number,
  color: string,
  lightDir: { x: number; y: number }
) {
  ctx.save();

  // 躯干：更圆润的蛋形，肩膀和臀部都圆
  const grad = ctx.createRadialGradient(
    x + lightDir.x * width * 0.2,
    y + lightDir.y * height * 0.15,
    width * 0.08,
    x, y, width * 0.65
  );
  grad.addColorStop(0, shadeColor(color, 22));
  grad.addColorStop(0.45, color);
  grad.addColorStop(0.85, shadeColor(color, -20));
  grad.addColorStop(1, shadeColor(color, -32));
  ctx.fillStyle = grad;

  // 圆润躯干：上下收窄，中间略宽
  ctx.beginPath();
  ctx.ellipse(x, y, width * 0.48, height * 0.45, 0, 0, Math.PI * 2);
  ctx.fill();

  // 轮廓
  ctx.strokeStyle = shadeColor(color, -30);
  ctx.lineWidth = 1;
  ctx.stroke();

  // 衣服褶皱/细节（简单弧线）
  ctx.beginPath();
  ctx.arc(x, y - height * 0.1, width * 0.25, 0.1 * Math.PI, 0.9 * Math.PI);
  ctx.strokeStyle = 'rgba(0,0,0,0.06)';
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.restore();
}

/** 绘制圆润肢体段（粗短圆润，像小香肠） */
function drawLimbSegment(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number,
  x2: number, y2: number,
  r1: number, r2: number,
  color: string,
  _lightDir: { x: number; y: number }
) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 0.1) return;

  const nx = -dy / len;
  const ny = dx / len;

  ctx.save();

  // 主体填充
  ctx.beginPath();
  ctx.moveTo(x1 + nx * r1, y1 + ny * r1);
  ctx.lineTo(x2 + nx * r2, y2 + ny * r2);
  ctx.arc(x2, y2, r2, Math.atan2(ny, nx), Math.atan2(-ny, -nx));
  ctx.lineTo(x1 - nx * r1, y1 - ny * r1);
  ctx.arc(x1, y1, r1, Math.atan2(-ny, -nx), Math.atan2(ny, nx));
  ctx.closePath();

  // 圆柱体光照：侧面亮，背面暗
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const grad = ctx.createLinearGradient(
    midX + nx * r1 * 0.6, midY + ny * r1 * 0.6,
    midX - nx * r1 * 0.6, midY - ny * r1 * 0.6
  );
  grad.addColorStop(0, shadeColor(color, 18));
  grad.addColorStop(0.5, color);
  grad.addColorStop(1, shadeColor(color, -30));
  ctx.fillStyle = grad;
  ctx.fill();

  // 轮廓
  ctx.strokeStyle = shadeColor(color, -25);
  ctx.lineWidth = 0.8;
  ctx.stroke();

  ctx.restore();
}

/** 绘制手臂（上粗下细，圆润） */
export function drawArm(
  ctx: CanvasRenderingContext2D,
  shoulderX: number, shoulderY: number,
  elbowX: number, elbowY: number,
  handX: number, handY: number,
  upperW: number, forearmW: number,
  color: string,
  lightDir: { x: number; y: number }
) {
  drawLimbSegment(ctx, shoulderX, shoulderY, elbowX, elbowY, upperW, upperW * 0.85, color, lightDir);
  drawLimbSegment(ctx, elbowX, elbowY, handX, handY, upperW * 0.85, forearmW, color, lightDir);

  // 关节球（圆润连接）
  ctx.beginPath();
  ctx.arc(elbowX, elbowY, upperW * 0.7, 0, Math.PI * 2);
  const jointGrad = ctx.createRadialGradient(
    elbowX - 1, elbowY - 1, 1,
    elbowX, elbowY, upperW * 0.7
  );
  jointGrad.addColorStop(0, shadeColor(color, 10));
  jointGrad.addColorStop(1, shadeColor(color, -15));
  ctx.fillStyle = jointGrad;
  ctx.fill();
}

/** 绘制腿（圆润粗短） */
export function drawLeg(
  ctx: CanvasRenderingContext2D,
  hipX: number, hipY: number,
  kneeX: number, kneeY: number,
  footX: number, footY: number,
  thighW: number, calfW: number,
  color: string,
  lightDir: { x: number; y: number }
) {
  drawLimbSegment(ctx, hipX, hipY, kneeX, kneeY, thighW, thighW * 0.8, color, lightDir);
  drawLimbSegment(ctx, kneeX, kneeY, footX, footY, thighW * 0.8, calfW, color, lightDir);

  // 膝盖
  ctx.beginPath();
  ctx.arc(kneeX, kneeY, thighW * 0.6, 0, Math.PI * 2);
  const kneeGrad = ctx.createRadialGradient(
    kneeX - 1, kneeY - 1, 1,
    kneeX, kneeY, thighW * 0.6
  );
  kneeGrad.addColorStop(0, shadeColor(color, 8));
  kneeGrad.addColorStop(1, shadeColor(color, -18));
  ctx.fillStyle = kneeGrad;
  ctx.fill();
}

/** 绘制手（小圆球 + 简单手指暗示） */
export function drawHand(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  color: string
) {
  ctx.save();

  // 手掌
  const grad = ctx.createRadialGradient(x - 1, y - 1, 1, x, y, radius);
  grad.addColorStop(0, shadeColor(color, 15));
  grad.addColorStop(1, shadeColor(color, -18));
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = shadeColor(color, -25);
  ctx.lineWidth = 0.6;
  ctx.stroke();

  // 小手指暗示（上方两个小弧线）
  ctx.beginPath();
  ctx.arc(x - radius * 0.3, y - radius * 0.4, radius * 0.25, 0.8 * Math.PI, 1.8 * Math.PI);
  ctx.strokeStyle = shadeColor(color, -20);
  ctx.lineWidth = 0.8;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(x + radius * 0.15, y - radius * 0.45, radius * 0.22, 0.9 * Math.PI, 1.9 * Math.PI);
  ctx.stroke();

  ctx.restore();
}

/** 绘制脚（小椭圆 + 脚趾暗示） */
export function drawFoot(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  color: string
) {
  ctx.save();

  const grad = ctx.createRadialGradient(x - 1, y - 2, 1, x, y, radius);
  grad.addColorStop(0, shadeColor(color, 12));
  grad.addColorStop(1, shadeColor(color, -22));
  ctx.fillStyle = grad;

  // 脚：略扁的椭圆，前端稍宽
  ctx.beginPath();
  ctx.ellipse(x, y + radius * 0.1, radius * 0.95, radius * 0.45, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = shadeColor(color, -25);
  ctx.lineWidth = 0.6;
  ctx.stroke();

  // 脚趾暗示
  ctx.beginPath();
  ctx.arc(x - radius * 0.2, y - radius * 0.1, radius * 0.15, 0, Math.PI);
  ctx.strokeStyle = shadeColor(color, -18);
  ctx.lineWidth = 0.6;
  ctx.stroke();

  ctx.restore();
}

/** 绘制小骨盆（圆润连接） */
export function drawPelvis(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  width: number, height: number,
  color: string
) {
  ctx.save();
  ctx.beginPath();
  ctx.ellipse(x, y, width, height, 0, 0, Math.PI * 2);
  const grad = ctx.createRadialGradient(x, y - 2, 2, x, y, width);
  grad.addColorStop(0, shadeColor(color, 10));
  grad.addColorStop(1, shadeColor(color, -20));
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.strokeStyle = shadeColor(color, -25);
  ctx.lineWidth = 0.6;
  ctx.stroke();
  ctx.restore();
}

/** 完整身体绘制（Labubu 比例：头身比约 2.5:1） */
export function drawFullBody(
  ctx: CanvasRenderingContext2D,
  skeleton: { getWorld: (id: string) => { x: number; y: number; rotation: number } },
  skinColor: string,
  clothColor: string,
  lightDir: { x: number; y: number }
) {
  const wpos = (id: string) => skeleton.getWorld(id);

  // 骨盆
  const pelvis = wpos('pelvis');
  drawPelvis(ctx, pelvis.x, pelvis.y, 14, 10, skinColor);

  // 躯干（极短圆润）
  const torso = wpos('torso');
  drawTorso(ctx, torso.x, torso.y, 20, 32, clothColor, lightDir);

  // 左臂（粗短圆润）
  const shoulderL = wpos('shoulder_L');
  const armL = wpos('arm_L');
  const forearmL = wpos('forearm_L');
  const handL = wpos('hand_L');
  drawArm(ctx, shoulderL.x, shoulderL.y, armL.x, armL.y, forearmL.x, forearmL.y, 4.5, 3, skinColor, lightDir);
  drawHand(ctx, handL.x, handL.y, 4, skinColor);

  // 右臂
  const shoulderR = wpos('shoulder_R');
  const armR = wpos('arm_R');
  const forearmR = wpos('forearm_R');
  const handR = wpos('hand_R');
  drawArm(ctx, shoulderR.x, shoulderR.y, armR.x, armR.y, forearmR.x, forearmR.y, 4.5, 3, skinColor, lightDir);
  drawHand(ctx, handR.x, handR.y, 4, skinColor);

  // 左腿（粗短）
  const thighL = wpos('thigh_L');
  const legL = wpos('leg_L');
  const footL = wpos('foot_L');
  drawLeg(ctx, pelvis.x - 6, pelvis.y + 3, thighL.x, thighL.y, legL.x, legL.y, 5, 3, skinColor, lightDir);
  drawFoot(ctx, footL.x, footL.y, 4, skinColor);

  // 右腿
  const thighR = wpos('thigh_R');
  const legR = wpos('leg_R');
  const footR = wpos('foot_R');
  drawLeg(ctx, pelvis.x + 6, pelvis.y + 3, thighR.x, thighR.y, legR.x, legR.y, 5, 3, skinColor, lightDir);
  drawFoot(ctx, footR.x, footR.y, 4, skinColor);
}
