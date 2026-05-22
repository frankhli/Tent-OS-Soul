/**
 * FaceV2 — 精灵系面部绘制系统
 * 设计目标：超大眼睛（占面部45%+）、多层高光、灵动有神
 * 支持：眼泪、星星眼、多种嘴型、大圆形腮红
 */

// import { shadeColor } from './Renderer3D';
import type { FaceParams } from './FaceDeformation';

// ============ 眼睛系统 ============

/** 绘制超灵动大眼睛 */
export function drawEyeV2(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, radius: number,
  openRatio: number, pupilScale: number, squint: number,
  lookX: number, lookY: number,
  asleep: boolean,
  tearAmount: number,
  starEyeAmount: number,
  _lightDir: { x: number; y: number },
  time: number
) {
  if (openRatio < 0.06) {
    // 闭眼：优美的弧线 + 睫毛
    ctx.beginPath();
    ctx.moveTo(cx - radius, cy);
    ctx.quadraticCurveTo(cx, cy + 3, cx + radius, cy);
    ctx.strokeStyle = '#1a1a2e';
    ctx.lineWidth = 2.2;
    ctx.stroke();

    // 下眼睑（很淡）
    ctx.beginPath();
    ctx.moveTo(cx - radius * 0.75, cy + 1.5);
    ctx.quadraticCurveTo(cx, cy + 4, cx + radius * 0.75, cy + 1.5);
    ctx.strokeStyle = 'rgba(26,26,46,0.25)';
    ctx.lineWidth = 1;
    ctx.stroke();

    // 眼泪（闭眼时从眼角滑落）
    if (tearAmount > 0.1) {
      drawTear(ctx, cx + radius * 0.6, cy + 2, tearAmount, time);
    }
    return;
  }

  const eyeH = radius * (0.42 + openRatio * 0.58);
  const squintY = squint * radius * 0.2;

  ctx.save();

  // === 眼白：有机形状（上弧下平）===
  ctx.beginPath();
  // 上半圆
  ctx.ellipse(cx, cy + squintY, radius * 0.92, eyeH, 0, Math.PI, 0);
  // 下眼睑（略平）
  ctx.bezierCurveTo(
    cx + radius * 0.9, cy + squintY + eyeH * 0.3,
    cx - radius * 0.9, cy + squintY + eyeH * 0.3,
    cx - radius * 0.92, cy + squintY
  );
  ctx.closePath();

  // 眼白渐变（不是纯白，带微微蓝灰）
  const eyeWhiteGrad = ctx.createRadialGradient(
    cx - radius * 0.2, cy + squintY - eyeH * 0.2, 2,
    cx, cy + squintY, radius
  );
  eyeWhiteGrad.addColorStop(0, '#ffffff');
  eyeWhiteGrad.addColorStop(0.7, '#f8fafc');
  eyeWhiteGrad.addColorStop(1, '#e2e8f0');
  ctx.fillStyle = eyeWhiteGrad;
  ctx.fill();

  // 眼白阴影（上缘）
  ctx.fillStyle = 'rgba(0,0,0,0.04)';
  ctx.beginPath();
  ctx.ellipse(cx, cy + squintY - eyeH * 0.15, radius * 0.85, eyeH * 0.35, 0, Math.PI, Math.PI * 2);
  ctx.fill();

  // === 上眼睑：有厚度的弧线 ===
  ctx.beginPath();
  ctx.moveTo(cx - radius, cy - eyeH * 0.35 + squintY);
  ctx.quadraticCurveTo(cx, cy - eyeH * 1.15 + squintY, cx + radius, cy - eyeH * 0.35 + squintY);
  ctx.strokeStyle = '#1a1a2e';
  ctx.lineWidth = 2.8;
  ctx.lineCap = 'round';
  ctx.stroke();

  // 上眼睑阴影（让眼睛有深邃感）
  ctx.beginPath();
  ctx.moveTo(cx - radius * 0.9, cy - eyeH * 0.3 + squintY);
  ctx.quadraticCurveTo(cx, cy - eyeH * 0.95 + squintY, cx + radius * 0.9, cy - eyeH * 0.3 + squintY);
  ctx.strokeStyle = 'rgba(26,26,46,0.15)';
  ctx.lineWidth = 4;
  ctx.stroke();

  // === 下眼睑 ===
  ctx.beginPath();
  ctx.moveTo(cx - radius * 0.85, cy + eyeH * 0.35 + squintY);
  ctx.quadraticCurveTo(cx, cy + eyeH * 0.75 + squintY, cx + radius * 0.85, cy + eyeH * 0.35 + squintY);
  ctx.strokeStyle = '#334155';
  ctx.lineWidth = 1.3;
  ctx.stroke();

  // === 双眼皮褶皱 ===
  if (openRatio > 0.25) {
    ctx.beginPath();
    ctx.moveTo(cx - radius * 0.65, cy - eyeH * 0.9 + squintY);
    ctx.quadraticCurveTo(cx, cy - eyeH * 1.35 + squintY, cx + radius * 0.65, cy - eyeH * 0.9 + squintY);
    ctx.strokeStyle = 'rgba(26,26,46,0.18)';
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  // === 睫毛（上眼睑外侧，更翘更明显）===
  if (openRatio > 0.4) {
    const lashCount = 6;
    for (let i = 0; i < lashCount; i++) {
      const t = (i + 1) / (lashCount + 1);
      const lx = cx - radius * 0.65 + radius * 1.3 * t;
      const ly = cy - eyeH * 0.55 + squintY;
      const angle = -Math.PI * 0.5 + t * Math.PI * 0.4;
      const lashLen = 5 + t * 3;

      ctx.beginPath();
      ctx.moveTo(lx, ly);
      ctx.quadraticCurveTo(
        lx + Math.cos(angle) * lashLen * 0.5,
        ly + Math.sin(angle) * lashLen * 0.3,
        lx + Math.cos(angle) * lashLen,
        ly + Math.sin(angle) * lashLen
      );
      ctx.strokeStyle = 'rgba(26,26,46,0.5)';
      ctx.lineWidth = 0.8 + (1 - Math.abs(t - 0.5) * 2) * 0.5;
      ctx.stroke();
    }
  }

  // === 瞳孔位置 ===
  const pupilR = radius * (0.2 + pupilScale * 0.3);
  const maxOffset = radius * 0.3;
  const px = cx + lookX * maxOffset;
  const py = cy + lookY * maxOffset * 0.55 + squintY;

  // === 虹膜（多层渐变，外深内浅）===
  const irisR = pupilR * 2.0;
  const irisColor = asleep ? '#64748b' : '#2d6a4f'; // 深绿色虹膜（精灵感）
  const irisInner = '#40916c';

  ctx.beginPath();
  ctx.arc(px, py, irisR, 0, Math.PI * 2);
  const irisGrad = ctx.createRadialGradient(
    px - irisR * 0.15, py - irisR * 0.15, 1,
    px, py, irisR
  );
  irisGrad.addColorStop(0, irisInner);
  irisGrad.addColorStop(0.6, irisColor);
  irisGrad.addColorStop(1, '#1b4332');
  ctx.fillStyle = irisGrad;
  ctx.fill();

  // 虹膜纹理（放射状细线）
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 0.6;
  for (let i = 0; i < 12; i++) {
    const angle = (i / 12) * Math.PI * 2 + time * 0.1;
    ctx.beginPath();
    ctx.moveTo(px + Math.cos(angle) * pupilR * 1.1, py + Math.sin(angle) * pupilR * 1.1);
    ctx.lineTo(px + Math.cos(angle) * irisR * 0.95, py + Math.sin(angle) * irisR * 0.95);
    ctx.stroke();
  }

  // 虹膜外环
  ctx.beginPath();
  ctx.arc(px, py, irisR * 0.9, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(27,67,50,0.3)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // === 瞳孔 ===
  ctx.beginPath();
  ctx.arc(px, py, pupilR, 0, Math.PI * 2);
  ctx.fillStyle = '#0d1b1a';
  ctx.fill();

  // 瞳孔内反光（极小的点）
  ctx.fillStyle = 'rgba(255,255,255,0.15)';
  ctx.beginPath();
  ctx.arc(px + pupilR * 0.2, py - pupilR * 0.15, pupilR * 0.15, 0, Math.PI * 2);
  ctx.fill();

  // === 高光系统（灵魂所在）===
  // 主高光：大、亮、偏移左上
  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.beginPath();
  ctx.ellipse(px - pupilR * 0.35, py - pupilR * 0.4, pupilR * 0.4, pupilR * 0.3, -0.3, 0, Math.PI * 2);
  ctx.fill();

  // 次高光：小、柔和、偏移右下
  ctx.fillStyle = 'rgba(255,255,255,0.5)';
  ctx.beginPath();
  ctx.arc(px + pupilR * 0.45, py + pupilR * 0.2, pupilR * 0.18, 0, Math.PI * 2);
  ctx.fill();

  // 环境反射：底部微光（模拟环境光）
  ctx.fillStyle = 'rgba(200,230,255,0.2)';
  ctx.beginPath();
  ctx.arc(px + pupilR * 0.1, py + pupilR * 0.5, pupilR * 0.25, 0, Math.PI * 2);
  ctx.fill();

  // === 星星眼效果（极度开心时）===
  if (starEyeAmount > 0.05) {
    drawStarEye(ctx, px, py, irisR, starEyeAmount, time);
  }

  // === 眯眼时的上眼睑覆盖 ===
  if (squint > 0.1) {
    const coverH = squint * eyeH * 0.5;
    ctx.fillStyle = `rgba(245,208,197,${squint * 0.5})`;
    ctx.beginPath();
    ctx.ellipse(cx, cy - eyeH * 0.2 + squintY, radius * 0.88, coverH, 0, 0, Math.PI * 2);
    ctx.fill();

    // 眯眼线
    ctx.beginPath();
    ctx.moveTo(cx - radius * 0.7, cy - eyeH * 0.1 + squintY);
    ctx.quadraticCurveTo(cx, cy - eyeH * 0.4 + squintY, cx + radius * 0.7, cy - eyeH * 0.1 + squintY);
    ctx.strokeStyle = `rgba(26,26,46,${squint * 0.5})`;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // === 眼泪 ===
  if (tearAmount > 0.05) {
    drawTear(ctx, cx + radius * 0.5, cy + eyeH * 0.3 + squintY, tearAmount, time);
  }

  ctx.restore();
}

/** 绘制眼泪 */
function drawTear(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  amount: number,
  time: number
) {
  const tearR = 3 + amount * 4;
  const slideY = (time * 20) % 25;

  ctx.save();
  ctx.globalAlpha = amount * 0.7;

  // 泪珠主体
  ctx.beginPath();
  ctx.arc(x, y + slideY, tearR, 0, Math.PI * 2);
  const tearGrad = ctx.createRadialGradient(x - 1, y + slideY - 1, 1, x, y + slideY, tearR);
  tearGrad.addColorStop(0, 'rgba(200,230,255,0.9)');
  tearGrad.addColorStop(1, 'rgba(150,200,255,0.5)');
  ctx.fillStyle = tearGrad;
  ctx.fill();

  // 泪珠高光
  ctx.fillStyle = 'rgba(255,255,255,0.8)';
  ctx.beginPath();
  ctx.arc(x - tearR * 0.3, y + slideY - tearR * 0.3, tearR * 0.25, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

/** 绘制星星眼 */
function drawStarEye(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  irisR: number,
  amount: number,
  time: number
) {
  ctx.save();
  ctx.globalAlpha = amount * 0.8;

  const starSize = irisR * 0.5;
  const rot = time * 2;

  // 左眼星星
  drawStar(ctx, cx - irisR * 0.3, cy - irisR * 0.2, starSize * 0.6, rot);
  drawStar(ctx, cx + irisR * 0.2, cy + irisR * 0.1, starSize * 0.4, -rot * 1.5);

  ctx.restore();
}

function drawStar(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  size: number,
  rotation: number
) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(rotation);

  ctx.fillStyle = '#ffd700';
  ctx.beginPath();
  for (let i = 0; i < 5; i++) {
    const angle = (i * Math.PI * 2) / 5 - Math.PI / 2;
    const innerAngle = angle + Math.PI / 5;
    if (i === 0) ctx.moveTo(Math.cos(angle) * size, Math.sin(angle) * size);
    else ctx.lineTo(Math.cos(angle) * size, Math.sin(angle) * size);
    ctx.lineTo(Math.cos(innerAngle) * size * 0.4, Math.sin(innerAngle) * size * 0.4);
  }
  ctx.closePath();
  ctx.fill();

  // 星星高光
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.beginPath();
  ctx.arc(-size * 0.1, -size * 0.1, size * 0.15, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

// ============ 眉毛系统 ============

/** 绘制粗短有力眉毛 */
export function drawBrowV2(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, width: number,
  height: number, angle: number
) {
  ctx.save();
  ctx.lineCap = 'round';

  const h = height * 5;
  const tilt = angle * 7;

  const x1 = cx - width / 2;
  const x2 = cx + width / 2;
  const y1 = cy + h + tilt;
  const y2 = cy + h - tilt;

  // 眉骨阴影（底层，更大更柔和）
  ctx.beginPath();
  ctx.moveTo(x1, y1 + 2);
  ctx.quadraticCurveTo(cx, cy + h * 0.35 + 2, x2, y2 + 2);
  ctx.strokeStyle = 'rgba(0,0,0,0.12)';
  ctx.lineWidth = 6;
  ctx.stroke();

  // 眉毛主体（更粗）
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.quadraticCurveTo(cx, cy + h * 0.3, x2, y2);
  ctx.strokeStyle = '#1a1a2e';
  ctx.lineWidth = 3.5;
  ctx.stroke();

  // 眉毛高光（上缘）
  ctx.beginPath();
  ctx.moveTo(x1, y1 - 1.5);
  ctx.quadraticCurveTo(cx, cy + h * 0.3 - 1.5, x2, y2 - 1.5);
  ctx.strokeStyle = 'rgba(255,255,255,0.3)';
  ctx.lineWidth = 1.2;
  ctx.stroke();

  ctx.restore();
}

// ============ 嘴巴系统 ============

/** 绘制灵活嘴巴（支持多种形状） */
export function drawMouthV2(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number, width: number,
  height: number, curve: number, openRatio: number,
  emotion: string
) {
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  const curveY = curve * 7 + height * 5;
  const halfW = width / 2;

  // 嘴角阴影
  ctx.fillStyle = 'rgba(0,0,0,0.05)';
  ctx.beginPath();
  ctx.ellipse(cx - halfW * 0.9, cy + curveY * 0.1, 3, 2, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(cx + halfW * 0.9, cy + curveY * 0.1, 3, 2, 0, 0, Math.PI * 2);
  ctx.fill();

  // 根据情绪选择嘴型
  if (emotion === 'angry' && openRatio < 0.1) {
    // 生气：倒V型
    ctx.beginPath();
    ctx.moveTo(cx - halfW, cy + 2);
    ctx.quadraticCurveTo(cx - halfW * 0.3, cy + curveY * 0.3, cx, cy - 2);
    ctx.quadraticCurveTo(cx + halfW * 0.3, cy + curveY * 0.3, cx + halfW, cy + 2);
    ctx.strokeStyle = '#4a5568';
    ctx.lineWidth = 2.2;
    ctx.stroke();
  } else if (emotion === 'sad' && openRatio < 0.1) {
    // 难过：波浪线（哭泣嘴）
    ctx.beginPath();
    ctx.moveTo(cx - halfW, cy);
    ctx.quadraticCurveTo(cx - halfW * 0.5, cy + 3, cx - halfW * 0.15, cy);
    ctx.quadraticCurveTo(cx + halfW * 0.15, cy - 3, cx + halfW * 0.5, cy);
    ctx.quadraticCurveTo(cx + halfW * 0.75, cy + 3, cx + halfW, cy);
    ctx.strokeStyle = '#4a5568';
    ctx.lineWidth = 2;
    ctx.stroke();
  } else if (openRatio > 0.6 && curve > 0.5) {
    // 大笑：嘴巴大张，可以看到舌头和小尖牙
    const mouthH = 5 + openRatio * 8;
    const mouthY = cy + curveY * 0.2 + 1;

    // 口腔内部
    ctx.beginPath();
    ctx.ellipse(cx, mouthY, halfW * 0.75, mouthH * 0.7, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#5a1a2a';
    ctx.fill();

    // 上唇线
    ctx.beginPath();
    ctx.moveTo(cx - halfW, cy + curveY * 0.05);
    ctx.quadraticCurveTo(cx - halfW * 0.3, cy + curveY * 0.15, cx, cy - 2);
    ctx.quadraticCurveTo(cx + halfW * 0.3, cy + curveY * 0.15, cx + halfW, cy + curveY * 0.05);
    ctx.strokeStyle = '#4a5568';
    ctx.lineWidth = 2;
    ctx.stroke();

    // 下唇线
    ctx.beginPath();
    ctx.moveTo(cx - halfW * 0.8, mouthY + mouthH * 0.3);
    ctx.quadraticCurveTo(cx, mouthY + mouthH * 0.8, cx + halfW * 0.8, mouthY + mouthH * 0.3);
    ctx.strokeStyle = '#4a5568';
    ctx.lineWidth = 1.8;
    ctx.stroke();

    // 舌头
    ctx.fillStyle = '#e8929c';
    ctx.beginPath();
    ctx.ellipse(cx, mouthY + mouthH * 0.25, halfW * 0.3, mouthH * 0.25, 0, 0, Math.PI * 2);
    ctx.fill();

    // 小尖牙（Labubu 特征！）
    ctx.fillStyle = '#f8fafc';
    ctx.beginPath();
    ctx.moveTo(cx - halfW * 0.25, cy + 1);
    ctx.lineTo(cx - halfW * 0.15, cy + 4);
    ctx.lineTo(cx - halfW * 0.05, cy + 1);
    ctx.closePath();
    ctx.fill();

    ctx.beginPath();
    ctx.moveTo(cx + halfW * 0.05, cy + 1);
    ctx.lineTo(cx + halfW * 0.15, cy + 4);
    ctx.lineTo(cx + halfW * 0.25, cy + 1);
    ctx.closePath();
    ctx.fill();

  } else {
    // 普通嘴型：上唇有唇珠
    ctx.beginPath();
    const cupidY = cy + curveY * 0.3 - Math.abs(curve) * 2;
    ctx.moveTo(cx - halfW, cy + curveY * 0.05);
    ctx.quadraticCurveTo(cx - halfW * 0.4, cy + curveY * 0.25, cx, cupidY);
    ctx.quadraticCurveTo(cx + halfW * 0.4, cy + curveY * 0.25, cx + halfW, cy + curveY * 0.05);
    ctx.strokeStyle = '#4a5568';
    ctx.lineWidth = 2;
    ctx.stroke();

    // 上唇填充
    ctx.fillStyle = 'rgba(226, 180, 180, 0.3)';
    ctx.fill();

    // 下唇/口腔
    if (openRatio > 0.05) {
      const mouthH = 4 + openRatio * 6;
      const mouthY = cy + curveY * 0.2 + 2;

      ctx.beginPath();
      ctx.moveTo(cx - halfW * 0.7, mouthY);
      ctx.quadraticCurveTo(cx, mouthY + mouthH * 1.2, cx + halfW * 0.7, mouthY);
      ctx.fillStyle = '#6b2c3a';
      ctx.fill();

      ctx.beginPath();
      ctx.moveTo(cx - halfW * 0.7, mouthY);
      ctx.quadraticCurveTo(cx, mouthY + mouthH * 0.9, cx + halfW * 0.7, mouthY);
      ctx.strokeStyle = '#4a5568';
      ctx.lineWidth = 1.8;
      ctx.stroke();

      ctx.fillStyle = 'rgba(226, 180, 180, 0.4)';
      ctx.fill();

      if (openRatio > 0.25) {
        ctx.fillStyle = '#e8929c';
        ctx.beginPath();
        ctx.ellipse(cx, mouthY + mouthH * 0.5, halfW * 0.25, mouthH * 0.25, 0, 0, Math.PI * 2);
        ctx.fill();
      }
    } else {
      ctx.beginPath();
      ctx.moveTo(cx - halfW * 0.5, cy + curveY * 0.1 + 1);
      ctx.quadraticCurveTo(cx, cy + curveY * 0.1 + 4, cx + halfW * 0.5, cy + curveY * 0.1 + 1);
      ctx.strokeStyle = 'rgba(74, 85, 104, 0.5)';
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }
  }

  ctx.restore();
}

// ============ 鼻子 ============

/** 绘制极小鼻头 */
function drawNose(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  size: number
) {
  ctx.save();
  ctx.fillStyle = 'rgba(200, 160, 150, 0.4)';
  ctx.beginPath();
  ctx.arc(x, y, size, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

// ============ 脸颊细节 ============

/** 绘制大圆形腮红 */
export function drawCheekDetail(
  ctx: CanvasRenderingContext2D,
  headX: number, headY: number, headRadius: number,
  side: 'left' | 'right',
  smileAmount: number,
  blushIntensity: number
) {
  const r = headRadius;
  const dir = side === 'left' ? -1 : 1;
  const cheekX = headX + dir * r * 0.52;
  const cheekY = headY + r * 0.22;

  ctx.save();

  // 大圆形腮红
  if (blushIntensity > 0.02) {
    const blushR = r * 0.22;
    const blushGrad = ctx.createRadialGradient(
      cheekX, cheekY, 1,
      cheekX, cheekY, blushR
    );
    // 根据 smileAmount 调整腮红颜色
    if (smileAmount > 0.5) {
      blushGrad.addColorStop(0, `rgba(255, 160, 170, ${blushIntensity * 0.5})`);
      blushGrad.addColorStop(1, `rgba(255, 160, 170, 0)`);
    } else if (smileAmount < -0.2) {
      blushGrad.addColorStop(0, `rgba(200, 150, 150, ${blushIntensity * 0.4})`);
      blushGrad.addColorStop(1, `rgba(200, 150, 150, 0)`);
    } else {
      blushGrad.addColorStop(0, `rgba(255, 170, 180, ${blushIntensity * 0.45})`);
      blushGrad.addColorStop(1, `rgba(255, 170, 180, 0)`);
    }

    ctx.fillStyle = blushGrad;
    ctx.beginPath();
    ctx.arc(cheekX, cheekY, blushR, 0, Math.PI * 2);
    ctx.fill();
  }

  // 酒窝（大笑时）
  if (smileAmount > 0.6) {
    ctx.beginPath();
    ctx.arc(cheekX + dir * r * 0.02, cheekY - r * 0.05, r * 0.08 * smileAmount, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(0,0,0,${0.04 * smileAmount})`;
    ctx.fill();
  }

  ctx.restore();
}

// ============ 完整面部绘制 ============

/** 完整面部 V2 绘制 */
export function drawFaceV2(
  ctx: CanvasRenderingContext2D,
  headX: number, headY: number, headRadius: number,
  face: FaceParams,
  lookX: number, lookY: number,
  emotion: string,
  mouthOpen: number,
  asleep: boolean,
  time: number
) {
  const r = headRadius;
  const eyeY = headY - r * 0.08;

  // 脸颊鼓起
  if (face.cheekPuff > 0.05) {
    const puffAlpha = face.cheekPuff * 0.3;
    const puffR = r * 0.28;
    const puffY = headY + r * 0.18;

    ctx.fillStyle = `rgba(255, 200, 180, ${puffAlpha})`;
    ctx.beginPath();
    ctx.ellipse(headX - r * 0.42, puffY, puffR, puffR * 0.48, -0.1, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(headX + r * 0.42, puffY, puffR, puffR * 0.48, 0.1, 0, Math.PI * 2);
    ctx.fill();
  }

  // 酒窝/腮红
  const smileAmount = Math.max(0, face.mouthCurve);
  drawCheekDetail(ctx, headX, headY, r, 'left', smileAmount, face.cheekBlush);
  drawCheekDetail(ctx, headX, headY, r, 'right', smileAmount, face.cheekBlush);

  // 头部倾斜
  const tiltOffset = face.faceTilt * r * 0.12;

  // 眉毛
  drawBrowV2(ctx, headX - r * 0.36, eyeY - r * 0.32 + tiltOffset, r * 0.3, face.browLHeight, face.browLAngle);
  drawBrowV2(ctx, headX + r * 0.36, eyeY - r * 0.32 - tiltOffset, r * 0.3, face.browRHeight, face.browRAngle);

  // 眼睛（更大更有神）
  const eyeRx = r * 0.28;
  drawEyeV2(
    ctx, headX - r * 0.3, eyeY, eyeRx,
    face.eyeLOpen, face.eyeLPupil, face.eyeLSquint,
    lookX, lookY, asleep, face.tearL, face.starEyes,
    { x: 0.3, y: -0.5 }, time
  );
  drawEyeV2(
    ctx, headX + r * 0.3, eyeY, eyeRx,
    face.eyeROpen, face.eyeRPupil, face.eyeRSquint,
    lookX, lookY, asleep, face.tearR, face.starEyes,
    { x: 0.3, y: -0.5 }, time
  );

  // 小鼻子（极小的点）
  drawNose(ctx, headX, headY + r * 0.18, r * 0.04);

  // 嘴巴
  const mouthY = headY + r * 0.38 + face.faceSquash * r * 0.08;
  const mouthW = r * (0.32 + face.mouthWidth * 0.32);
  drawMouthV2(ctx, headX, mouthY, mouthW, face.mouthHeight, face.mouthCurve, mouthOpen, emotion);
}
