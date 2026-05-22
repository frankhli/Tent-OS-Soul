/**
 * PartDefs v3 — 极简精灵形象
 */

import type { PartDef, PartDrawContext } from './PartSystem';
import { BRAND_COLORS, shadeColor, getColors } from './PartSystem';

function drawHeadBase(ctx: CanvasRenderingContext2D, state: PartDrawContext) {
  const C = getColors(state);
  const r = 34;
  const grad = ctx.createRadialGradient(-5, -10, 3, 0, 0, r);
  grad.addColorStop(0, C.skinHighlight);
  grad.addColorStop(0.35, C.skin);
  grad.addColorStop(0.85, C.skinShadow);
  grad.addColorStop(1, shadeColor(C.skinShadow, -15));
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(100,80,70,0.08)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.beginPath();
  ctx.ellipse(-10, -16, 10, 5, -0.2, 0, Math.PI * 2);
  ctx.fill();
}

function drawEar(ctx: CanvasRenderingContext2D, side: 'left' | 'right', state: PartDrawContext) {
  const dir = side === 'left' ? -1 : 1;
  const emotion = state.emotion;
  ctx.save();
  
  const earH = 22;
  const baseX = dir * 30;
  const baseY = -10;
  let earAngle = 0;
  if (emotion === 'happy' || emotion === 'excited') earAngle = dir * -0.12;
  else if (emotion === 'sad') earAngle = dir * 0.2;
  else if (emotion === 'angry') earAngle = dir * 0.35;
  ctx.translate(baseX, baseY);
  ctx.rotate(earAngle);
  ctx.beginPath();
  ctx.moveTo(-dir * 6, 4);
  ctx.quadraticCurveTo(dir * 10, -4, dir * 4, -earH);
  ctx.quadraticCurveTo(0, -earH * 0.7, -dir * 6, 4);
  ctx.closePath();
  const C = getColors(state);
  const grad = ctx.createLinearGradient(0, 0, dir * 8, -earH);
  grad.addColorStop(0, C.skinShadow);
  grad.addColorStop(1, shadeColor(C.skinShadow, -15));
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.strokeStyle = 'rgba(100,80,70,0.1)';
  ctx.lineWidth = 0.8;
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(-dir * 2, 0);
  ctx.quadraticCurveTo(dir * 5, -4, dir * 2, -earH * 0.65);
  ctx.quadraticCurveTo(0, -earH * 0.4, -dir * 2, 0);
  ctx.closePath();
  ctx.fillStyle = 'rgba(200,170,155,0.4)';
  ctx.fill();
  if (emotion === 'happy' || emotion === 'excited' || emotion === 'love') {
    ctx.beginPath();
    ctx.ellipse(dir * 3, -10, 4, 6, dir * 0.3, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,170,180,0.35)';
    ctx.fill();
  }
  ctx.restore();
}

function drawHair(ctx: CanvasRenderingContext2D, state: PartDrawContext) {
  const time = state.time;
  const C = getColors(state);
  ctx.save();
  const clusters = [
    { x: -18, y: -24, rx: 18, ry: 14, rot: -0.3 },
    { x: 0, y: -30, rx: 20, ry: 15, rot: 0 },
    { x: 18, y: -24, rx: 18, ry: 14, rot: 0.3 },
    { x: -10, y: -32, rx: 12, ry: 10, rot: -0.2 },
    { x: 10, y: -32, rx: 12, ry: 10, rot: 0.2 },
  ];
  for (const c of clusters) {
    ctx.beginPath();
    ctx.ellipse(c.x, c.y, c.rx, c.ry, c.rot, Math.PI, Math.PI * 2);
    const grad = ctx.createRadialGradient(c.x - 3, c.y - 5, 2, c.x, c.y, Math.max(c.rx, c.ry));
    grad.addColorStop(0, C.hairLight);
    grad.addColorStop(0.5, C.hair);
    grad.addColorStop(1, C.hairDark);
    ctx.fillStyle = grad;
    ctx.fill();
  }
  const s = Math.sin(time * 3) * 0.12;
  ctx.beginPath();
  ctx.moveTo(2, -28);
  ctx.quadraticCurveTo(8 + s * 18, -44, 4 + s * 22, -38);
  ctx.strokeStyle = C.hairDark;
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.stroke();
  ctx.restore();
}

function drawStar(ctx: CanvasRenderingContext2D, x: number, y: number, size: number, rot: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(rot);
  ctx.fillStyle = '#ffd700';
  ctx.beginPath();
  for (let i = 0; i < 5; i++) {
    const a = (i * Math.PI * 2) / 5 - Math.PI / 2;
    const ia = a + Math.PI / 5;
    if (i === 0) ctx.moveTo(Math.cos(a) * size, Math.sin(a) * size);
    else ctx.lineTo(Math.cos(a) * size, Math.sin(a) * size);
    ctx.lineTo(Math.cos(ia) * size * 0.4, Math.sin(ia) * size * 0.4);
  }
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawEye(ctx: CanvasRenderingContext2D, side: 'left' | 'right', state: PartDrawContext) {
  const dir = side === 'left' ? -1 : 1;
  const face = state.face;
  const asleep = state.asleep;
  const blinkOpen = state.blinkOpen;
  const time = state.time;
  const cx = dir * 13;
  const cy = -2;
  const r = 10;
  const open = side === 'left' ? face.eyeLOpen * blinkOpen : face.eyeROpen * blinkOpen;

  if (open < 0.06) {
    ctx.beginPath();
    ctx.moveTo(cx - r + 2, cy);
    ctx.quadraticCurveTo(cx, cy + 2, cx + r - 2, cy);
    ctx.strokeStyle = '#2c3e50';
    ctx.lineWidth = 1.8;
    ctx.stroke();
    return;
  }

  const eyeH = r * (0.35 + open * 0.65);
  ctx.save();

  ctx.beginPath();
  ctx.ellipse(cx, cy, r * 0.9, eyeH, 0, 0, Math.PI * 2);
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.strokeStyle = 'rgba(44,62,80,0.15)';
  ctx.lineWidth = 0.8;
  ctx.stroke();

  const C = getColors(state);
  const lookX = state.lookX * 2.5;
  const lookY = state.lookY * 1.8;
  const pupilScale = side === 'left' ? face.eyeLPupil : face.eyeRPupil;
  const pupilR = 3.5 + pupilScale * 2.5;
  const px = cx + lookX;
  const py = cy + lookY;
  const irisR = pupilR * 1.8;

  ctx.beginPath();
  ctx.arc(px, py, irisR, 0, Math.PI * 2);
  const irisGrad = ctx.createRadialGradient(px - 1.5, py - 1.5, 1, px, py, irisR);
  irisGrad.addColorStop(0, shadeColor(C.eyeIris, 30));
  irisGrad.addColorStop(0.5, asleep ? '#64748b' : C.eyeIris);
  irisGrad.addColorStop(1, shadeColor(C.eyeIris, -30));
  ctx.fillStyle = irisGrad;
  ctx.fill();

  ctx.beginPath();
  ctx.arc(px, py, pupilR, 0, Math.PI * 2);
  ctx.fillStyle = C.eyePupil;
  ctx.fill();

  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.beginPath();
  ctx.ellipse(px - 1.5, py - 2, 2.2, 1.6, -0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.45)';
  ctx.beginPath();
  ctx.arc(px + 2, py + 0.5, 1, 0, Math.PI * 2);
  ctx.fill();

  const stars = face.starEyes;
  if (stars > 0.05) {
    ctx.globalAlpha = stars * 0.8;
    drawStar(ctx, px - 2, py - 2, 2.5, time * 3);
    drawStar(ctx, px + 2, py + 1, 1.8, -time * 2.5);
    ctx.globalAlpha = 1;
  }

  const tear = side === 'left' ? face.tearL : face.tearR;
  if (tear > 0.05) {
    const ty = (time * 18) % 14;
    ctx.globalAlpha = tear * 0.6;
    ctx.fillStyle = 'rgba(160,200,255,0.7)';
    ctx.beginPath();
    ctx.arc(cx + r * 0.5, cy + 4 + ty, 2.2, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  const lidY = cy - eyeH * 0.45;
  ctx.beginPath();
  ctx.moveTo(cx - r + 1, lidY);
  ctx.quadraticCurveTo(cx, lidY - eyeH * 0.4, cx + r - 1, lidY);
  ctx.strokeStyle = 'rgba(44,62,80,0.2)';
  ctx.lineWidth = 1.2;
  ctx.stroke();

  ctx.restore();
}

function drawBrow(ctx: CanvasRenderingContext2D, side: 'left' | 'right', state: PartDrawContext) {
  const dir = side === 'left' ? -1 : 1;
  const face = state.face;
  const h = side === 'left' ? face.browLHeight : face.browRHeight;
  const a = side === 'left' ? face.browLAngle : face.browRAngle;
  const cx = dir * 12;
  const cy = -12 + h * 2.5;
  ctx.save();
  ctx.lineCap = 'round';
  const tilt = a * 3;
  ctx.beginPath();
  ctx.moveTo(cx - dir * 5, cy + tilt);
  ctx.quadraticCurveTo(cx, cy - 0.5, cx + dir * 5, cy - tilt);
  ctx.strokeStyle = 'rgba(44,62,80,0.3)';
  ctx.lineWidth = 1.2;
  ctx.stroke();
  ctx.restore();
}

function drawMouth(ctx: CanvasRenderingContext2D, state: PartDrawContext) {
  const face = state.face;
  const emotion = state.emotion;
  const mouthOpen = state.mouthOpen;
  const cx = 0;
  const cy = 12;
  const w = 9 + face.mouthWidth * 8;
  const curve = face.mouthCurve;
  const open = face.mouthOpen + mouthOpen * 0.5;

  ctx.save();
  ctx.lineCap = 'round';

  if (emotion === 'angry' && open < 0.1) {
    ctx.beginPath();
    ctx.moveTo(cx - w, cy + 2);
    ctx.quadraticCurveTo(cx - w * 0.3, cy + 3, cx, cy - 1);
    ctx.quadraticCurveTo(cx + w * 0.3, cy + 3, cx + w, cy + 2);
    ctx.strokeStyle = '#5a4a42';
    ctx.lineWidth = 1.8;
    ctx.stroke();
  } else if (emotion === 'sad' && open < 0.1) {
    ctx.beginPath();
    ctx.moveTo(cx - w, cy);
    ctx.quadraticCurveTo(cx - w * 0.5, cy + 2, cx, cy);
    ctx.quadraticCurveTo(cx + w * 0.5, cy - 2, cx + w, cy);
    ctx.strokeStyle = '#5a4a42';
    ctx.lineWidth = 1.6;
    ctx.stroke();
  } else if (open > 0.45 && curve > 0.3) {
    const mh = 3 + open * 5;
    ctx.beginPath();
    ctx.ellipse(cx, cy + 1, w * 0.65, mh * 0.55, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#8b4545';
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(cx - w, cy - 1);
    ctx.quadraticCurveTo(cx - w * 0.3, cy - 3, cx, cy - 3);
    ctx.quadraticCurveTo(cx + w * 0.3, cy - 3, cx + w, cy - 1);
    ctx.strokeStyle = '#5a4a42';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = '#e8929c';
    ctx.beginPath();
    ctx.ellipse(cx, cy + 2, w * 0.25, mh * 0.2, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.moveTo(cx - 3, cy - 1);
    ctx.lineTo(cx - 2, cy + 1.5);
    ctx.lineTo(cx - 1, cy - 1);
    ctx.closePath();
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(cx + 1, cy - 1);
    ctx.lineTo(cx + 2, cy + 1.5);
    ctx.lineTo(cx + 3, cy - 1);
    ctx.closePath();
    ctx.fill();
  } else {
    const cY = curve * 3.5;
    ctx.beginPath();
    ctx.moveTo(cx - w, cy);
    ctx.quadraticCurveTo(cx - w * 0.3, cy + cY * 0.5, cx, cy + cY * 0.7);
    ctx.quadraticCurveTo(cx + w * 0.3, cy + cY * 0.5, cx + w, cy);
    ctx.strokeStyle = '#5a4a42';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    if (open > 0.05) {
      const mh = 1.5 + open * 3.5;
      ctx.beginPath();
      ctx.moveTo(cx - w * 0.55, cy + cY * 0.3);
      ctx.quadraticCurveTo(cx, cy + cY * 0.3 + mh, cx + w * 0.55, cy + cY * 0.3);
      ctx.fillStyle = '#8b4545';
      ctx.fill();
      ctx.strokeStyle = '#5a4a42';
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }
  ctx.restore();
}

function drawBlush(ctx: CanvasRenderingContext2D, side: 'left' | 'right', state: PartDrawContext) {
  const dir = side === 'left' ? -1 : 1;
  const amount = state.face.cheekBlush;
  if (amount < 0.02) return;
  const C = getColors(state);
  ctx.save();
  const x = dir * 20;
  const y = 8;
  const r = 9;
  // 将 blush 颜色转为 rgba
  const blushHex = C.blush.replace('#', '');
  const br = parseInt(blushHex.slice(0, 2), 16);
  const bg = parseInt(blushHex.slice(2, 4), 16);
  const bb = parseInt(blushHex.slice(4, 6), 16);
  const grad = ctx.createRadialGradient(x, y, 1, x, y, r);
  grad.addColorStop(0, `rgba(${br}, ${bg}, ${bb}, ${amount * 0.55})`);
  grad.addColorStop(1, `rgba(${br}, ${bg}, ${bb}, 0)`);
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawBody(ctx: CanvasRenderingContext2D, _state: PartDrawContext) {
  ctx.save();
  const C = BRAND_COLORS;
  const grad = ctx.createRadialGradient(-3, -8, 2, 0, 0, 26);
  grad.addColorStop(0, '#6ceedf');
  grad.addColorStop(0.5, C.body);
  grad.addColorStop(1, C.bodyDark);
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.ellipse(0, 0, 20, 30, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(44,62,80,0.08)';
  ctx.lineWidth = 0.8;
  ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,0.2)';
  ctx.beginPath();
  ctx.ellipse(-5, -10, 6, 3, -0.2, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawNeckConnect(ctx: CanvasRenderingContext2D, _state: PartDrawContext) {
  ctx.save();
  const grad = ctx.createLinearGradient(0, -5, 0, 5);
  grad.addColorStop(0, '#e8d4c4');
  grad.addColorStop(1, '#d4c0b0');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.ellipse(0, 0, 10, 7, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawLimbSmooth(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number,
  x2: number, y2: number,
  w1: number, w2: number,
  color: string
) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 0.1) return;
  const nx = -dy / len;
  const ny = dx / len;
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(x1 + nx * w1, y1 + ny * w1);
  ctx.lineTo(x2 + nx * w2, y2 + ny * w2);
  ctx.arc(x2, y2, w2, Math.atan2(ny, nx), Math.atan2(-ny, -nx));
  ctx.lineTo(x1 - nx * w1, y1 - ny * w1);
  ctx.arc(x1, y1, w1, Math.atan2(-ny, -nx), Math.atan2(ny, nx));
  ctx.closePath();
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  const grad = ctx.createLinearGradient(
    midX + nx * w1, midY + ny * w1,
    midX - nx * w1, midY - ny * w1
  );
  grad.addColorStop(0, shadeColor(color, 10));
  grad.addColorStop(0.5, color);
  grad.addColorStop(1, shadeColor(color, -18));
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.strokeStyle = 'rgba(44,62,80,0.06)';
  ctx.lineWidth = 0.5;
  ctx.stroke();
  ctx.restore();
}

function drawArmPart(ctx: CanvasRenderingContext2D, side: 'left' | 'right', state: PartDrawContext) {
  const dir = side === 'left' ? -1 : 1;
  const emotion = state.emotion;
  ctx.save();
  const sx = dir * 22;
  const sy = -14;
  const hx = dir * 30;
  const hy = 18;
  let offset = 0;
  if (emotion === 'happy') offset = dir * -4;
  else if (emotion === 'sad') offset = dir * 3;
  drawLimbSmooth(ctx, sx, sy, hx + offset, hy, 5, 3.5, '#f5e6d8');
  ctx.beginPath();
  ctx.arc(hx + offset, hy, 4, 0, Math.PI * 2);
  const hg = ctx.createRadialGradient(hx + offset - 1, hy - 1, 1, hx + offset, hy, 4);
  hg.addColorStop(0, '#fff0e0');
  hg.addColorStop(1, '#d4c0b0');
  ctx.fillStyle = hg;
  ctx.fill();
  ctx.restore();
}

function drawLegPart(ctx: CanvasRenderingContext2D, side: 'left' | 'right', state: PartDrawContext) {
  const dir = side === 'left' ? -1 : 1;
  const emotion = state.emotion;
  ctx.save();
  const hx = dir * 10;
  const hy = 4;
  const fx = dir * 14;
  const fy = 34;
  let offset = 0;
  if (emotion === 'sad') offset = dir * -2;
  drawLimbSmooth(ctx, hx, hy, fx + offset, fy, 5.5, 4.5, '#f5e6d8');
  ctx.beginPath();
  ctx.ellipse(fx + offset, fy + 2, 5, 3, 0, 0, Math.PI * 2);
  const fg = ctx.createRadialGradient(fx + offset - 1, fy, 1, fx + offset, fy + 2, 5);
  fg.addColorStop(0, '#fff0e0');
  fg.addColorStop(1, '#d4c0b0');
  ctx.fillStyle = fg;
  ctx.fill();
  ctx.restore();
}

export function createAvatarParts(): PartDef[] {
  return [
    { id: 'body', boneId: 'torso', zIndex: 10, draw: drawBody },
    { id: 'armL', boneId: 'arm_L', zIndex: 11, draw: (ctx, s) => drawArmPart(ctx, 'left', s) },
    { id: 'armR', boneId: 'arm_R', zIndex: 11, draw: (ctx, s) => drawArmPart(ctx, 'right', s) },
    { id: 'legL', boneId: 'leg_L', zIndex: 9, draw: (ctx, s) => drawLegPart(ctx, 'left', s) },
    { id: 'legR', boneId: 'leg_R', zIndex: 9, draw: (ctx, s) => drawLegPart(ctx, 'right', s) },
    { id: 'neck', boneId: 'neck', zIndex: 20, draw: drawNeckConnect },
    { id: 'head', boneId: 'head', zIndex: 30, draw: drawHeadBase },
    { id: 'earL', boneId: 'head', zIndex: 36, draw: (ctx, s) => drawEar(ctx, 'left', s) },
    { id: 'earR', boneId: 'head', zIndex: 36, draw: (ctx, s) => drawEar(ctx, 'right', s) },
    { id: 'hair', boneId: 'head', zIndex: 35, draw: drawHair },
    { id: 'blushL', boneId: 'head', zIndex: 31, draw: (ctx, s) => drawBlush(ctx, 'left', s) },
    { id: 'blushR', boneId: 'head', zIndex: 31, draw: (ctx, s) => drawBlush(ctx, 'right', s) },
    { id: 'eyeL', boneId: 'head', zIndex: 33, draw: (ctx, s) => drawEye(ctx, 'left', s) },
    { id: 'eyeR', boneId: 'head', zIndex: 33, draw: (ctx, s) => drawEye(ctx, 'right', s) },
    { id: 'browL', boneId: 'head', zIndex: 34, draw: (ctx, s) => drawBrow(ctx, 'left', s) },
    { id: 'browR', boneId: 'head', zIndex: 34, draw: (ctx, s) => drawBrow(ctx, 'right', s) },
    { id: 'mouth', boneId: 'head', zIndex: 33, draw: drawMouth },
  ];
}
