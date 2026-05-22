/**
 * HeadShape — Labubu 风格头部绘制
 * 参考风格：Labubu / 精灵系潮玩 / 毛茸茸怪物
 * 核心特征：毛茸茸边缘、精灵尖耳、圆润蛋形头、层次化毛发
 */

import { shadeColor } from './Renderer3D';

/** 绘制 Labubu 风格头部（圆润蛋形 + 有机轮廓） */
export function drawHumanHead(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, radius: number,
  color: string,
  lightDir: { x: number; y: number },
  headTilt: number,
  _facing: number,
  _emotion: string,
  opacity: number = 0.95,
  furPhase: number = 0 // 毛发抖动相位
) {
  const r = radius;
  ctx.save();
  ctx.globalAlpha = opacity;

  // 头部：圆润蛋形（宽略大于高，下巴微收）
  const headW = r * 1.25;
  const headH = r * 1.18;

  ctx.beginPath();
  // 蛋形：上半圆 + 下半略尖
  ctx.ellipse(x, y - r * 0.05, headW, headH * 0.55, headTilt * 0.03, Math.PI, 0);
  // 下巴收尖
  ctx.bezierCurveTo(
    x + headW * 0.7, y + r * 0.35,
    x + headW * 0.15, y + headH * 0.75,
    x, y + headH * 0.72
  );
  ctx.bezierCurveTo(
    x - headW * 0.15, y + headH * 0.75,
    x - headW * 0.7, y + r * 0.35,
    x - headW, y - r * 0.05
  );
  ctx.closePath();

  // 皮肤渐变：暖色调，从左上高光到右下阴影
  const grad = ctx.createRadialGradient(
    x - r * 0.15 + lightDir.x * r * 0.3,
    y - r * 0.2 + lightDir.y * r * 0.25,
    r * 0.08,
    x, y, r * 0.85
  );
  grad.addColorStop(0, shadeColor(color, 28));
  grad.addColorStop(0.4, color);
  grad.addColorStop(0.8, shadeColor(color, -15));
  grad.addColorStop(1, shadeColor(color, -28));
  ctx.fillStyle = grad;
  ctx.fill();

  // 柔和轮廓线
  ctx.strokeStyle = shadeColor(color, -35);
  ctx.lineWidth = 1.2;
  ctx.stroke();

  // 额头高光（更柔和的大面积）
  ctx.beginPath();
  ctx.ellipse(x - r * 0.2, y - r * 0.4, r * 0.28, r * 0.14, -0.15, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,255,255,0.18)';
  ctx.fill();

  // 脸颊次高光
  ctx.beginPath();
  ctx.ellipse(x + r * 0.25, y - r * 0.1, r * 0.15, r * 0.08, 0.2, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,255,255,0.08)';
  ctx.fill();

  // ===== 毛茸茸边缘效果 =====
  // 沿头部轮廓画一圈短毛
  const furCount = 48;
  ctx.strokeStyle = shadeColor(color, -20);
  ctx.lineWidth = 1;
  ctx.lineCap = 'round';

  for (let i = 0; i < furCount; i++) {
    const angle = (Math.PI * 2 * i) / furCount;
    // 跳过下巴区域（不需要毛）
    if (angle > Math.PI * 0.65 && angle < Math.PI * 1.35) continue;

    const furLen = 3 + Math.sin(i * 2.7 + furPhase) * 1.5;
    // 在头部椭圆上的点
    const bx = x + Math.cos(angle + headTilt * 0.03) * headW * 1.0;
    const by = y - r * 0.05 + Math.sin(angle) * headH * 0.55;
    // 毛发方向：沿法线向外 + 随机偏移
    const furAngle = angle + (Math.sin(i * 3.1) * 0.2);
    const ex = bx + Math.cos(furAngle) * furLen;
    const ey = by + Math.sin(furAngle) * furLen;

    ctx.beginPath();
    ctx.moveTo(bx, by);
    ctx.quadraticCurveTo(
      bx + Math.cos(furAngle + 0.1) * furLen * 0.6,
      by + Math.sin(furAngle + 0.1) * furLen * 0.6,
      ex, ey
    );
    ctx.globalAlpha = 0.5;
    ctx.stroke();
  }
  ctx.globalAlpha = opacity;

  ctx.restore();
}

/** 绘制 Labubu 风格头发（毛茸茸簇状，不是圆盖） */
export function drawHair(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, headRadius: number,
  hairColor: string,
  lightDir: { x: number; y: number },
  _headTilt: number,
  emotion: string,
  furPhase: number = 0
) {
  const r = headRadius;
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // 基础头发色
  const baseColor = hairColor;
  const shadowColor = shadeColor(baseColor, -30);
  const highlightColor = shadeColor(baseColor, 20);

  // === 头发主体：覆盖头顶的毛绒区域 ===
  // 用多个椭圆叠加形成蓬松感
  const hairCenters = [
    { dx: 0, dy: -r * 0.55, rx: r * 0.75, ry: r * 0.45 },
    { dx: -r * 0.35, dy: -r * 0.45, rx: r * 0.5, ry: r * 0.38 },
    { dx: r * 0.35, dy: -r * 0.45, rx: r * 0.5, ry: r * 0.38 },
    { dx: -r * 0.15, dy: -r * 0.7, rx: r * 0.4, ry: r * 0.3 },
    { dx: r * 0.15, dy: -r * 0.7, rx: r * 0.4, ry: r * 0.3 },
  ];

  for (const c of hairCenters) {
    ctx.beginPath();
    ctx.ellipse(x + c.dx, y + c.dy, c.rx, c.ry, 0, Math.PI, Math.PI * 2);

    const grad = ctx.createRadialGradient(
      x + c.dx - lightDir.x * c.rx * 0.3,
      y + c.dy - lightDir.y * c.ry * 0.3,
      2,
      x + c.dx, y + c.dy, Math.max(c.rx, c.ry)
    );
    grad.addColorStop(0, highlightColor);
    grad.addColorStop(0.6, baseColor);
    grad.addColorStop(1, shadowColor);
    ctx.fillStyle = grad;
    ctx.fill();
  }

  // === 刘海：几簇不规则的毛发 ===
  const bangs = [
    { dx: -r * 0.45, dy: -r * 0.15, angle: -0.3, len: r * 0.35 },
    { dx: -r * 0.2, dy: -r * 0.05, angle: -0.1, len: r * 0.3 },
    { dx: r * 0.1, dy: -r * 0.08, angle: 0.15, len: r * 0.32 },
    { dx: r * 0.35, dy: -r * 0.2, angle: 0.35, len: r * 0.28 },
    { dx: 0, dy: -r * 0.1, angle: 0, len: r * 0.25 },
  ];

  // 情绪影响刘海：开心时扬起，生气时压低
  const emotionAngleOffset = emotion === 'happy' || emotion === 'excited' ? -0.25
    : emotion === 'angry' ? 0.2
    : emotion === 'sad' ? 0.1
    : 0;

  for (const b of bangs) {
    const sx = x + b.dx;
    const sy = y + b.dy;
    const angle = b.angle + emotionAngleOffset + Math.sin(furPhase + b.dx) * 0.05;
    const ex = sx + Math.sin(angle) * b.len;
    const ey = sy + Math.cos(angle) * b.len * 0.6;

    // 刘海主体
    ctx.beginPath();
    ctx.moveTo(sx - 4, sy);
    ctx.quadraticCurveTo(sx + Math.sin(angle + 0.2) * b.len * 0.5, sy - 3, ex, ey);
    ctx.quadraticCurveTo(sx + Math.sin(angle - 0.2) * b.len * 0.5, sy + 3, sx + 4, sy);
    ctx.closePath();

    const bGrad = ctx.createLinearGradient(sx, sy, ex, ey);
    bGrad.addColorStop(0, baseColor);
    bGrad.addColorStop(1, shadowColor);
    ctx.fillStyle = bGrad;
    ctx.fill();

    // 刘海边缘毛发
    ctx.beginPath();
    ctx.moveTo(sx - 3, sy);
    ctx.quadraticCurveTo(sx + Math.sin(angle) * b.len * 0.4, sy - 2, ex, ey);
    ctx.strokeStyle = shadeColor(baseColor, -25);
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // === 头发高光（顶部）===
  ctx.beginPath();
  ctx.ellipse(x - r * 0.1, y - r * 0.6, r * 0.2, r * 0.08, -0.1, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,255,255,0.15)';
  ctx.fill();

  // === 头顶呆毛（像 Labubu 的一撮毛）===
  const ahogeSway = Math.sin(furPhase * 2) * 0.15;
  ctx.beginPath();
  ctx.moveTo(x + r * 0.05, y - r * 0.85);
  ctx.quadraticCurveTo(
    x + r * 0.15 + ahogeSway * r,
    y - r * 1.15,
    x + r * 0.05 + ahogeSway * r * 1.5,
    y - r * 1.05
  );
  ctx.strokeStyle = baseColor;
  ctx.lineWidth = 3;
  ctx.stroke();

  // 呆毛高光
  ctx.beginPath();
  ctx.moveTo(x + r * 0.05, y - r * 0.85);
  ctx.quadraticCurveTo(
    x + r * 0.15 + ahogeSway * r,
    y - r * 1.12,
    x + r * 0.08 + ahogeSway * r * 1.3,
    y - r * 1.02
  );
  ctx.strokeStyle = highlightColor;
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.restore();
}

/** 绘制 Labubu 风格精灵大尖耳 */
export function drawEar(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, headRadius: number,
  side: 'left' | 'right',
  skinColor: string,
  _lightDir: { x: number; y: number },
  _headTilt: number,
  emotion: string,
  furPhase: number = 0
) {
  const r = headRadius;
  const dir = side === 'left' ? -1 : 1;
  ctx.save();

  // 耳朵位置：头顶两侧偏上
  const earBaseX = x + dir * r * 0.55;
  const earBaseY = y - r * 0.45;
  const earW = r * 0.55;
  const earH = r * 0.75;

  // 精灵耳形状：底部宽，向上收窄变尖，微向外弯
  const tipX = earBaseX + dir * earW * 0.9 + Math.sin(furPhase) * 2;
  const tipY = earBaseY - earH;

  ctx.beginPath();
  // 左/右边缘（外侧）
  ctx.moveTo(earBaseX - dir * earW * 0.35, earBaseY + earH * 0.15);
  ctx.quadraticCurveTo(
    earBaseX + dir * earW * 0.2,
    earBaseY - earH * 0.3,
    tipX,
    tipY
  );
  // 内边缘（内侧）
  ctx.quadraticCurveTo(
    earBaseX + dir * earW * 0.1,
    earBaseY - earH * 0.2,
    earBaseX + dir * earW * 0.25,
    earBaseY + earH * 0.1
  );
  ctx.closePath();

  // 耳朵渐变
  const grad = ctx.createLinearGradient(
    earBaseX - dir * earW * 0.3, earBaseY,
    tipX, tipY
  );
  grad.addColorStop(0, shadeColor(skinColor, -5));
  grad.addColorStop(0.5, skinColor);
  grad.addColorStop(1, shadeColor(skinColor, -15));
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.strokeStyle = shadeColor(skinColor, -30);
  ctx.lineWidth = 1;
  ctx.stroke();

  // 耳朵内部（凹陷区域）
  ctx.beginPath();
  ctx.moveTo(earBaseX - dir * earW * 0.05, earBaseY - earH * 0.05);
  ctx.quadraticCurveTo(
    earBaseX + dir * earW * 0.15,
    earBaseY - earH * 0.35,
    tipX - dir * earW * 0.1,
    tipY + earH * 0.1
  );
  ctx.quadraticCurveTo(
    earBaseX + dir * earW * 0.05,
    earBaseY - earH * 0.15,
    earBaseX + dir * earW * 0.15,
    earBaseY
  );
  ctx.closePath();
  ctx.fillStyle = shadeColor(skinColor, -18);
  ctx.fill();

  // 耳朵尖部毛发
  ctx.beginPath();
  ctx.moveTo(tipX, tipY);
  ctx.lineTo(tipX + dir * 3 + Math.sin(furPhase * 1.5) * 1.5, tipY - 4);
  ctx.strokeStyle = shadeColor(skinColor, -20);
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // 情绪影响耳朵：开心时耳朵竖起并外展，生气时耳朵后压
  if (emotion === 'happy' || emotion === 'excited') {
    // 耳朵内侧高光
    ctx.beginPath();
    ctx.ellipse(
      earBaseX + dir * earW * 0.15,
      earBaseY - earH * 0.35,
      earW * 0.15, earH * 0.12,
      dir * 0.3, 0, Math.PI * 2
    );
    ctx.fillStyle = 'rgba(255,200,200,0.25)';
    ctx.fill();
  } else if (emotion === 'angry') {
    // 耳朵后压的暗色
    ctx.beginPath();
    ctx.ellipse(
      earBaseX + dir * earW * 0.1,
      earBaseY - earH * 0.3,
      earW * 0.2, earH * 0.15,
      dir * 0.5, 0, Math.PI * 2
    );
    ctx.fillStyle = 'rgba(200,100,100,0.15)';
    ctx.fill();
  }

  ctx.restore();
}

/** 绘制短脖子（几乎不可见，Q版风格） */
export function drawNeck(
  ctx: CanvasRenderingContext2D,
  headX: number, headY: number, headRadius: number,
  _torsoX: number, _torsoY: number,
  _skinColor: string,
  _lightDir: { x: number; y: number }
) {
  const r = headRadius;
  ctx.save();

  // 脖子连接处阴影
  ctx.beginPath();
  ctx.ellipse(headX, headY + r * 0.55, r * 0.18, 3, 0, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(0,0,0,0.08)';
  ctx.fill();

  ctx.restore();
}

/** 完整头部绘制（Labubu 风格） */
export function drawFullHead(
  ctx: CanvasRenderingContext2D,
  headX: number, headY: number, headRadius: number,
  torsoX: number, torsoY: number,
  skinColor: string,
  hairColor: string,
  lightDir: { x: number; y: number },
  headTilt: number,
  facing: number,
  emotion: string,
  furPhase: number = 0
) {
  // 脖子（极短）
  drawNeck(ctx, headX, headY, headRadius, torsoX, torsoY, skinColor, lightDir);
  void facing; // 保留参数供未来使用

  // 耳朵（在头部后面）— Labubu 的大尖耳
  drawEar(ctx, headX, headY, headRadius, 'left', skinColor, lightDir, headTilt, emotion, furPhase);
  drawEar(ctx, headX, headY, headRadius, 'right', skinColor, lightDir, headTilt, emotion, furPhase);

  // 头部主体
  drawHumanHead(ctx, headX, headY, headRadius, skinColor, lightDir, headTilt, facing, emotion, 0.95, furPhase);

  // 头发（覆盖头顶）
  drawHair(ctx, headX, headY, headRadius, hairColor, lightDir, headTilt, emotion, furPhase);
}
