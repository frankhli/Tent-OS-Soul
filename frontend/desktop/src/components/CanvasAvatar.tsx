import { useRef, useEffect, useCallback } from 'react';
import type { AvatarAction } from '@/types/avatar';
import type { AppearanceConfig } from './avatar/PartSystem';
import { Skeleton, createDefaultSkeleton } from './avatar/Bone';
import { Live2DPhysics } from './avatar/Physics';
import {
  drawSimpleBody, mixColor,
} from './avatar/Renderer3D';
import { computeActionPose, applyEmotionToPose, getSquashStretch } from './avatar/Actions';
import { getFaceForEmotion, type FaceParams, applyAsymmetry } from './avatar/FaceDeformation';
import { PartSystem } from './avatar/PartSystem';
import { createAvatarParts } from './avatar/PartDefs';

/** 元音口型映射 — 基于中文/英文元音的嘴型 */
function getCurrentPhoneme(sentence: string, phase: number): { open: number; width: number; curve: number } {
  // 将句子按时间分段，每段对应一个"音素"
  const chars = sentence.split('');
  const idx = Math.floor(phase * 3) % Math.max(1, chars.length);
  const ch = chars[idx] || ' ';
  
  // 元音映射：open=嘴张开程度, width=嘴宽度, curve=嘴角弧度
  const vowels: Record<string, { open: number; width: number; curve: number }> = {
    'a': { open: 0.7, width: 0.8, curve: 0.2 },
    'e': { open: 0.4, width: 0.6, curve: 0 },
    'i': { open: 0.2, width: 0.4, curve: 0.3 },
    'o': { open: 0.6, width: 0.5, curve: 0.1 },
    'u': { open: 0.3, width: 0.4, curve: -0.1 },
    '啊': { open: 0.8, width: 0.8, curve: 0.1 },
    '哦': { open: 0.6, width: 0.5, curve: 0 },
    '呃': { open: 0.3, width: 0.5, curve: 0 },
    '咿': { open: 0.2, width: 0.4, curve: 0.4 },
    '呜': { open: 0.3, width: 0.4, curve: -0.1 },
    '吧': { open: 0.3, width: 0.5, curve: 0.2 },
    '呢': { open: 0.2, width: 0.4, curve: 0.3 },
    '吗': { open: 0.3, width: 0.5, curve: 0.1 },
    '，': { open: 0.1, width: 0.3, curve: 0 },
    '。': { open: 0, width: 0.3, curve: 0 },
    ' ': { open: 0, width: 0.3, curve: 0 },
  };
  
  // 辅音/其他字符：轻微张嘴
  const consonant = { open: 0.15, width: 0.4, curve: 0 };
  
  // 查找当前字符和下一个字符，做插值
  const current = vowels[ch.toLowerCase()] || consonant;
  const nextCh = chars[(idx + 1) % chars.length] || ' ';
  const next = vowels[nextCh.toLowerCase()] || consonant;
  const t = (phase * 3) % 1;
  
  return {
    open: current.open + (next.open - current.open) * t,
    width: current.width + (next.width - current.width) * t,
    curve: current.curve + (next.curve - current.curve) * t,
  };
}

/** 场景 → 面部参数叠加 — 微表情系统 */
function getSceneFaceParams(scene: string, timer: number): Partial<FaceParams> {
  switch (scene) {
    case 'thinking': return {
      browLHeight: -0.1, browRHeight: -0.2, browLAngle: 0.1, browRAngle: 0.3,
      eyeLOpen: 0.5 + Math.sin(timer * 2) * 0.05,
      eyeROpen: 0.5 + Math.sin(timer * 2 + 0.5) * 0.05,
      eyeLPupil: 0.4, eyeRPupil: 0.4,
      eyeLSquint: 0.15, eyeRSquint: 0.2,
      mouthWidth: 0.3, mouthCurve: 0, mouthOpen: 0,
      faceTilt: 0.15 + Math.sin(timer) * 0.05,
    };
    case 'speaking': return {
      eyeLOpen: 0.9, eyeROpen: 0.9, eyeLPupil: 0.7, eyeRPupil: 0.7,
      eyeLSquint: 0, eyeRSquint: 0,
      mouthWidth: 0.7, mouthCurve: 0.3,
      faceTilt: Math.sin(timer * 3) * 0.05,
    };
    case 'petted': return {
      browLHeight: 0.2, browRHeight: 0.2, browLAngle: 0.3, browRAngle: 0.3,
      eyeLOpen: 0.6 + Math.sin(timer * 4) * 0.1,
      eyeROpen: 0.6 + Math.sin(timer * 4 + 1) * 0.1,
      eyeLPupil: 0.5, eyeRPupil: 0.5,
      mouthWidth: 0.5, mouthCurve: 0.5, mouthOpen: 0.1,
      cheekBlush: 0.3 + Math.sin(timer * 2) * 0.1,
    };
    case 'success': return {
      browLHeight: 0.5, browRHeight: 0.5, browLAngle: 0.4, browRAngle: 0.4,
      eyeLOpen: 1, eyeROpen: 1, eyeLPupil: 0.8, eyeRPupil: 0.8,
      mouthWidth: 0.8, mouthHeight: 0.2, mouthCurve: 0.9, mouthOpen: 0.4,
      cheekBlush: 0.4,
      faceTilt: Math.sin(timer * 4) * 0.1,
      starEyes: 0.4,
    };
    case 'fail': return {
      browLHeight: 0.1, browRHeight: 0.1, browLAngle: -0.2, browRAngle: -0.2,
      eyeLOpen: 0.5, eyeROpen: 0.5, eyeLPupil: 0.3, eyeRPupil: 0.3,
      eyeLSquint: 0.1, eyeRSquint: 0.1,
      mouthWidth: 0.3, mouthHeight: -0.1, mouthCurve: -0.1, mouthOpen: 0,
      cheekBlush: 0.6,
      faceTilt: -0.1,
      tearL: 0.3, tearR: 0.3,
    };
    case 'praised': return {
      browLHeight: 0.3, browRHeight: 0.3, browLAngle: 0.3, browRAngle: 0.3,
      eyeLOpen: 0.6, eyeROpen: 0.6, eyeLPupil: 0.5, eyeRPupil: 0.5,
      eyeLSquint: 0.15, eyeRSquint: 0.15,
      mouthWidth: 0.5, mouthCurve: 0.6, mouthOpen: 0.1,
      cheekBlush: 0.7,
      faceTilt: Math.sin(timer * 3) * 0.08,
      starEyes: 0.3,
    };
    case 'criticized': return {
      browLHeight: -0.4, browRHeight: -0.4, browLAngle: -0.3, browRAngle: -0.3,
      eyeLOpen: 0.5, eyeROpen: 0.5, eyeLPupil: 0.35, eyeRPupil: 0.35,
      mouthWidth: 0.3, mouthHeight: -0.2, mouthCurve: -0.5, mouthOpen: 0,
      cheekBlush: 0.2, faceTilt: 0.1,
      tearL: 0.4, tearR: 0.4,
    };
    default: return {};
  }
}

interface CanvasAvatarProps {
  emotion?: string; persona?: string; size?: number;
  level?: number; xp?: number; xpToNext?: number;
  isSleeping?: boolean; showLevelRing?: boolean; showParticles?: boolean;
  isThinking?: boolean; isSpeaking?: boolean;
  vitals?: { heartRate: number; breathRate: number; intensity: number };
  isBeingPetted?: boolean; currentSentence?: string | null;
  action?: AvatarAction; facing?: number; scale?: number;
  appearanceConfig?: AppearanceConfig;
  onClick?: () => void; onLongPress?: () => void;
  onDoubleClick?: () => void; onPet?: () => void;
  className?: string;
  animated?: boolean; // false = 只画一帧静态图，不跑 RAF 动画
}

// ===== 情绪配置 =====
const EMOTION_CFG: Record<string, {
  core: string; glow: string; body: string; accent: string;
  bgFrom: string; bgTo: string; grid: string;
  animSpeed: number; bounce: number; particleSpeed: number;
  symbol: string;
}> = {
  happy:    { core:'#fbbf24', glow:'rgba(251,191,36,0.5)', body:'#f59e0b', accent:'#fde68a', bgFrom:'#1a0f00', bgTo:'#2d1b00', grid:'rgba(251,191,36,0.08)', animSpeed:1.8, bounce:10, particleSpeed:2.2, symbol:'+' },
  excited:  { core:'#f97316', glow:'rgba(249,115,22,0.6)', body:'#ea580c', accent:'#fdba74', bgFrom:'#1a0a00', bgTo:'#3d1a00', grid:'rgba(249,115,22,0.1)',  animSpeed:3,   bounce:14, particleSpeed:3.5, symbol:'*' },
  calm:     { core:'#60a5fa', glow:'rgba(96,165,250,0.5)',  body:'#3b82f6', accent:'#bfdbfe', bgFrom:'#0a0f1a', bgTo:'#0f1a2d', grid:'rgba(96,165,250,0.08)',  animSpeed:0.7, bounce:3,  particleSpeed:0.6, symbol:'~' },
  thinking: { core:'#a78bfa', glow:'rgba(167,139,250,0.5)', body:'#8b5cf6', accent:'#ddd6fe', bgFrom:'#110a1a', bgTo:'#1e0f2d', grid:'rgba(167,139,250,0.08)',  animSpeed:1.0, bounce:2,  particleSpeed:1.2, symbol:'?' },
  surprised:{ core:'#f472b6', glow:'rgba(244,114,182,0.6)', body:'#ec4899', accent:'#fbcfe8', bgFrom:'#1a0a14', bgTo:'#2d0f1e', grid:'rgba(244,114,182,0.1)',  animSpeed:3.5, bounce:16, particleSpeed:4,   symbol:'!' },
  sad:      { core:'#9ca3af', glow:'rgba(156,163,175,0.4)', body:'#6b7280', accent:'#e5e7eb', bgFrom:'#0f0f12', bgTo:'#1a1a1f', grid:'rgba(156,163,175,0.06)',  animSpeed:0.4, bounce:2,  particleSpeed:0.3, symbol:'·' },
  angry:    { core:'#f87171', glow:'rgba(248,113,113,0.6)', body:'#ef4444', accent:'#fecaca', bgFrom:'#1a0505', bgTo:'#2d0a0a', grid:'rgba(248,113,113,0.1)',  animSpeed:4,   bounce:6,  particleSpeed:3,   symbol:'!' },
  listening:{ core:'#34d399', glow:'rgba(52,211,153,0.5)',  body:'#10b981', accent:'#a7f3d0', bgFrom:'#0a1a0f', bgTo:'#0f2d1a', grid:'rgba(52,211,153,0.08)',  animSpeed:1.0, bounce:4,  particleSpeed:1,   symbol:'◉' },
  neutral:  { core:'#94a3b8', glow:'rgba(148,163,184,0.4)', body:'#64748b', accent:'#e2e8f0', bgFrom:'#0c0f14', bgTo:'#141821', grid:'rgba(148,163,184,0.06)',  animSpeed:0.6, bounce:2,  particleSpeed:0.5, symbol:'○' },
};

const PERSONA_TINT: Record<string, { r: number; g: number; b: number; strength: number }> = {
  work:      { r: 59,  g: 130, b: 246, strength: 0.15 },
  casual:    { r: 249, g: 115, b: 22,  strength: 0.12 },
  emergency: { r: 239, g: 68,  b: 68,  strength: 0.20 },
  learning:  { r: 139, g: 92,  b: 246, strength: 0.15 },
  creative:  { r: 236, g: 72,  b: 153, strength: 0.15 },
};

function getCfg(e: string, persona?: string) {
  const base = EMOTION_CFG[e] || EMOTION_CFG.neutral;
  if (!persona || persona === 'work') return base;
  const tint = PERSONA_TINT[persona];
  if (!tint) return base;
  return {
    ...base,
    core: mixColor(base.core, tint),
    body: mixColor(base.body, tint),
    accent: mixColor(base.accent, tint),
  };
}

interface P {
  x: number; y: number; vx: number; vy: number;
  size: number; life: number; maxLife: number;
  type: 'orbit' | 'burst' | 'trail' | 'symbol' | 'spark' | 'dust';
  angle: number; orbitR: number; orbitSpeed: number;
  color: string; text?: string;
}

export function CanvasAvatar({
  emotion = 'neutral', persona = 'work', size = 240, level = 1, xp = 0, xpToNext = 100,
  isSleeping = false, showLevelRing = false, showParticles = true, isThinking = false,
  isSpeaking = false, vitals, isBeingPetted = false, currentSentence = null,
  action: propsAction, facing = 1, scale: propsScale = 1, appearanceConfig,
  onClick, onLongPress, onDoubleClick, onPet, className = '',
  animated = true,
}: CanvasAvatarProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const skeletonRef = useRef<Skeleton | null>(null);
  const physicsRef = useRef<Live2DPhysics | null>(null);
  const partSystemRef = useRef<PartSystem | null>(null);
  const lastActionRef = useRef<AvatarAction>('idle');
  const actionTimeRef = useRef(0);

  // 用 ref 存储易变 props，避免 useEffect 频繁 teardown/rebuild
  const latestPropsRef = useRef({
    emotion, persona, isSleeping, isThinking, isSpeaking,
    vitals, isBeingPetted, currentSentence, propsAction, facing, propsScale,
  });
  latestPropsRef.current = {
    emotion, persona, isSleeping, isThinking, isSpeaking,
    vitals, isBeingPetted, currentSentence, propsAction, facing, propsScale,
  };

  const state = useRef({
    mx: 0, my: 0, hover: false, drag: false,
    dx: 0, dy: 0, px: 0, py: 0,
    clickT: 0, combo: 0, comboTimer: 0,
    upgradeT: 0, shockwaveT: 0,
    particles: [] as P[], trails: [] as {x:number;y:number;age:number}[],
    time: 0, blink: 0, lastBlink: 0,
    ringAngle: 0, ringAngle2: 0,
    asleep: false, awakeTimer: 0,
    bgPulse: 0,
    mouthOpen: 0,
    longPressTimer: 0, isLongPressed: false,
    lastClickTime: 0,
    heartbeat: 0,
    petCount: 0, petTimer: 0,
    lastMx: 0, lastMy: 0,
    sentencePhase: 0,
    face: { ...getFaceForEmotion('neutral') },
    faceVel: {} as Partial<FaceParams>,
    scene: 'idle' as 'idle' | 'thinking' | 'speaking' | 'petted' | 'success' | 'fail' | 'praised' | 'criticized',
    sceneTimer: 0,
    // 视线微跳动（saccades）
    saccadeX: 0, saccadeY: 0, saccadeTimer: 0, saccadeTargetX: 0, saccadeTargetY: 0,
    // 呼吸面部影响
    breathPhase: 0,
    // 眨眼系统增强
    blinkPhase: 0, blinkSpeed: 0, isBlinking: false,
  });

  const initParticles = useCallback((n: number) => {
    const out: P[] = [];
    for (let i = 0; i < n; i++) {
      const a = (Math.PI * 2 * i) / n;
      out.push({
        x:0,y:0,vx:0,vy:0, size: Math.random()*2.5+1,
        life: Math.random()*200, maxLife: 200+Math.random()*100,
        type:'orbit', angle: a, orbitR: 50+Math.random()*70, orbitSpeed: (Math.random()-0.5)*0.015,
        color: '',
      });
    }
    return out;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d'); if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const RENDER_BASE = 240;
    const renderScale = size / RENDER_BASE;
    canvas.width = size * dpr; canvas.height = size * dpr;
    ctx.scale(dpr * renderScale, dpr * renderScale);

    // 初始化骨骼系统
    if (!skeletonRef.current) {
      skeletonRef.current = new Skeleton(createDefaultSkeleton());
    }
    if (!physicsRef.current) {
      physicsRef.current = new Live2DPhysics();
    }
    if (!partSystemRef.current) {
      partSystemRef.current = new PartSystem(createAvatarParts());
    }

    const S = state.current;
    S.px = RENDER_BASE / 2; S.py = RENDER_BASE / 2;
    if (S.particles.length === 0) S.particles = initParticles(showParticles ? 40 : 0);

    const onMove = (e: MouseEvent) => {
      lastInteract = performance.now();
      const r = canvas.getBoundingClientRect();
      const scaleFactor = RENDER_BASE / size;
      const mx = (e.clientX - r.left) * scaleFactor, my = (e.clientY - r.top) * scaleFactor;
      const dx = mx - S.lastMx, dy = my - S.lastMy;
      S.lastMx = mx; S.lastMy = my;
      S.mx = mx; S.my = my;
      S.hover = S.mx>=0 && S.mx<=RENDER_BASE && S.my>=0 && S.my<=RENDER_BASE;
      if (S.hover) { S.asleep = false; S.awakeTimer = 300; }
      const distToCenter = Math.sqrt((mx - RENDER_BASE/2)**2 + (my - RENDER_BASE/2)**2);
      if (distToCenter < 70 && Math.sqrt(dx*dx + dy*dy) > 0.5 && Math.sqrt(dx*dx + dy*dy) < 15) {
        S.petCount++; S.petTimer = 30;
        if (S.petCount >= 8 && S.petTimer > 0) {
          S.petCount = 0; onPet?.();
          for (let i = 0; i < 6; i++) {
            const a = (Math.PI*2*i)/6;
            S.particles.push({
              x: S.px, y: S.py, vx: Math.cos(a)*1.2, vy: Math.sin(a)*1.2 - 1.5,
              size: 5, life: 50, maxLife: 50, type: 'spark',
              angle:0, orbitR:0, orbitSpeed:0, color: '#f472b6',
            });
          }
        }
      }
      if (S.petTimer > 0) S.petTimer--; else S.petCount = 0;
    };

    const onDown = (e: MouseEvent) => {
      lastInteract = performance.now();
      const r = canvas.getBoundingClientRect();
      const scaleFactor = RENDER_BASE / size;
      const mx = (e.clientX - r.left) * scaleFactor, my = (e.clientY - r.top) * scaleFactor;
      const dx = mx - S.px, dy = my - S.py;
      if (Math.sqrt(dx*dx+dy*dy) < 70) {
        S.drag = true; S.dx = dx; S.dy = dy;
        S.clickT = 1; S.asleep = false; S.awakeTimer = 300;
        const now = performance.now();
        const dt = now - S.lastClickTime;
        S.lastClickTime = now;
        if (dt < 350) { S.shockwaveT = 1; S.combo += 2; onDoubleClick?.(); }
        else { S.comboTimer = 60; S.combo++; }
        S.longPressTimer = 40; S.isLongPressed = false;
        const cfg = getCfg(emotion, persona);
        const burstCount = 8 + S.combo * 2;
        for (let i = 0; i < burstCount; i++) {
          const a = (Math.PI*2*i)/burstCount + Math.random()*0.5;
          const spd = 2 + Math.random()*3 + S.combo*0.5;
          S.particles.push({
            x: S.px, y: S.py, vx: Math.cos(a)*spd, vy: Math.sin(a)*spd,
            size: Math.random()*4+2, life: 80, maxLife: 80, type: 'burst',
            angle:0, orbitR:0, orbitSpeed:0, color: cfg.accent,
          });
        }
        if (S.combo > 1) {
          S.particles.push({
            x: S.px, y: S.py - 50, vx: 0, vy: -1.5,
            size: 16, life: 50, maxLife: 50, type: 'symbol',
            angle:0, orbitR:0, orbitSpeed:0, color: cfg.accent, text: `${S.combo}x COMBO!`,
          });
        }
        if (S.combo >= 5) S.shockwaveT = 1;
        onClick?.();
      }
    };

    const onUp = () => { lastInteract = performance.now(); S.drag = false; };
    const onLeave = () => { lastInteract = performance.now(); S.hover = false; S.drag = false; };

    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('mousedown', onDown);
    canvas.addEventListener('mouseup', onUp);
    canvas.addEventListener('mouseleave', onLeave);

    let aid = 0;
    let isVisible = true;
    let lastInteract = performance.now();
    const IDLE_MS = 3000;
    const TARGET_FPS = 30;
    const FRAME_INTERVAL = 1000 / TARGET_FPS;
    let lastFrameTime = 0;
    const io = new IntersectionObserver(([entry]) => {
      const wasVisible = isVisible;
      isVisible = entry.isIntersecting;
      if (isVisible && !wasVisible && !aid) {
        lastInteract = performance.now();
        aid = requestAnimationFrame(draw);
      }
    }, { threshold: 0 });
    io.observe(canvas);

    const draw = () => {
      if (!isVisible || document.hidden) { aid = 0; return; }
      if (!animated) {
        // 静态模式：只画一帧，不启动 RAF 循环（避免 Sidebar Logo 持续耗电）
        // 但 IntersectionObserver 触发可见时仍需重绘一次
      }
      const now = performance.now();
      // 空闲超过 3 秒：完全停止 RAF，改为 setTimeout 低频率检查
      if (now - lastInteract > IDLE_MS) {
        aid = 0;
        setTimeout(() => { if (isVisible && !document.hidden) aid = requestAnimationFrame(draw); }, 500);
        return;
      }
      // 帧率限制：30fps，降低 GPU/CPU 占用
      if (now - lastFrameTime < FRAME_INTERVAL) {
        aid = requestAnimationFrame(draw);
        return;
      }
      lastFrameTime = now;
      // 通过 ref 读取最新 props，避免 useEffect 频繁重建
      const { emotion, persona, isSleeping, isThinking, isSpeaking,
              isBeingPetted, currentSentence, propsAction, facing, propsScale } = latestPropsRef.current;
      const dt = 0.016;
      const cfg = getCfg(emotion, persona);
      const w = RENDER_BASE, h = RENDER_BASE;
      const cx = S.px, cy = S.py;
      ctx.clearRect(0,0,w,h);
      S.time += dt * cfg.animSpeed;
      S.bgPulse += 0.016;

      // 物理步进
      const physics = physicsRef.current!;
      physics.step(0.016);

      // 更新动作姿态
      const action = (propsAction || 'idle') as AvatarAction;
      actionTimeRef.current += 0.016;
      if (lastActionRef.current !== action) {
        lastActionRef.current = action;
        actionTimeRef.current = 0;
      }

      // 计算目标姿态（动作 + 步态 + 情绪）
      let targetPose = computeActionPose(action, actionTimeRef.current);
      targetPose = applyEmotionToPose(targetPose, emotion);

      // 呼吸叠加
      const breath = physics.breathe(1);
      if (targetPose.torso) targetPose.torso.y = (targetPose.torso.y ?? -30) + breath.torsoY;
      if (targetPose.torso) targetPose.torso.scaleX = (targetPose.torso.scaleX ?? 1) * breath.chestScale;

      // 视线追踪
      const look = physics.trackLookAt(S.mx, S.my, cx, cy);
      if (targetPose.head) targetPose.head.rotation = (targetPose.head.rotation ?? 0) + look.headRot;
      if (targetPose.neck) targetPose.neck.rotation = (targetPose.neck.rotation ?? 0) + look.headTilt;

      // 天线物理
      const antBaseL = skeletonRef.current!.getLocal('antenna_L_base')?.rotation ?? -0.3;
      const antBaseR = skeletonRef.current!.getLocal('antenna_R_base')?.rotation ?? 0.3;
      const movementInt = action === 'run' ? 1 : action === 'walk' ? 0.5 : 0;
      const ant = physics.antennaPhysics(antBaseL, antBaseR, movementInt);
      if (targetPose.antenna_L_base) targetPose.antenna_L_base.rotation = ant.antL;
      if (targetPose.antenna_R_base) targetPose.antenna_R_base.rotation = ant.antR;

      // 应用姿态到骨骼（通过物理弹簧过渡）
      const skeleton = skeletonRef.current!;
      for (const [boneId, patch] of Object.entries(targetPose)) {
        const current = skeleton.getLocal(boneId);
        if (!current) continue;

        if (patch.rotation !== undefined) {
          const springId = `bone_${boneId}_rot`;
          const val = physics.lerp(springId, patch.rotation, 4);
          skeleton.setLocal(boneId, { rotation: val });
        }
        if (patch.x !== undefined) {
          const springId = `bone_${boneId}_x`;
          const val = physics.lerp(springId, patch.x, 4);
          skeleton.setLocal(boneId, { x: val });
        }
        if (patch.y !== undefined) {
          const springId = `bone_${boneId}_y`;
          const val = physics.lerp(springId, patch.y, 4);
          skeleton.setLocal(boneId, { y: val });
        }
        if (patch.scaleX !== undefined) {
          const springId = `bone_${boneId}_sx`;
          const val = physics.lerp(springId, patch.scaleX, 4);
          skeleton.setLocal(boneId, { scaleX: val });
        }
      }

      // 计算世界变换
      skeleton.invalidate();

      // 拖拽物理
      if (S.drag) { S.px = S.mx - S.dx; S.py = S.my - S.dy; }
      else { S.px += (w/2 - S.px) * 0.04; S.py += (h/2 - S.py) * 0.04; }

      if (S.comboTimer > 0) S.comboTimer--; else S.combo = 0;
      if (S.clickT > 0) S.clickT *= 0.9;
      if (S.longPressTimer > 0 && S.drag) {
        S.longPressTimer--;
        if (S.longPressTimer <= 0 && !S.isLongPressed) {
          S.isLongPressed = true; S.shockwaveT = 0.8; onLongPress?.();
          for (let i = 0; i < 12; i++) {
            const a = (Math.PI*2*i)/12;
            S.particles.push({
              x: S.px, y: S.py, vx: Math.cos(a)*1.5, vy: Math.sin(a)*1.5 - 1,
              size: 6, life: 60, maxLife: 60, type: 'spark',
              angle:0, orbitR:0, orbitSpeed:0, color: '#f472b6',
            });
          }
        }
      }
      S.heartbeat += 0.05;
      if (S.shockwaveT > 0) S.shockwaveT *= 0.94;
      if (S.upgradeT > 0) S.upgradeT *= 0.95;
      if (isSleeping) { S.asleep = true; }
      else if (S.awakeTimer > 0) S.awakeTimer--;
      else S.asleep = true;

      const petShake = isBeingPetted ? Math.sin(S.time * 20) * 0.015 : 0;
      const breathS = 1 + Math.sin(S.time*2) * 0.03 + petShake;
      const clickS = 1 + S.clickT * 0.15;
      const totalS = breathS * clickS * (S.asleep ? 0.85 : 1) * propsScale;

      // 透明背景 — Avatar 是独立生命体，不需要背景框
      ctx.clearRect(0, 0, w, h);

      // 坐标系移到 Avatar 中心（所有绘制以此为原点）
      ctx.save();
      ctx.translate(cx, cy);

      // 挤压拉伸形变（跳跃/点击）
      const squash = getSquashStretch(action, actionTimeRef.current, S.clickT);
      ctx.scale(squash.scaleX, squash.scaleY);

      // 冲击波（仅在点击时短暂出现）
      if (S.shockwaveT > 0.01) {
        ctx.beginPath(); ctx.arc(cx, cy, (1-S.shockwaveT)*120, 0, Math.PI*2);
        ctx.strokeStyle = cfg.accent; ctx.lineWidth = 3 * S.shockwaveT;
        ctx.globalAlpha = S.shockwaveT * 0.6; ctx.stroke(); ctx.globalAlpha = 1;
      }

      // 粒子（仅在情绪强烈或互动时出现）
      if (showParticles) {
        // 先清理死粒子（修复 forEach+splice 跳元素 bug）
        S.particles = S.particles.filter((p) => {
          p.life--;
          if (p.life <= 0) {
            if (p.type === 'burst' || p.type === 'symbol' || p.type === 'spark' || p.type === 'dust') {
              return false;
            }
            p.life = p.maxLife; p.type = 'orbit'; p.vx = 0; p.vy = 0;
            p.orbitR = 50 + Math.random()*70;
          }
          return true;
        });
        // 再绘制存活粒子
        S.particles.forEach((p) => {
          if (p.type === 'orbit') {
            p.angle += p.orbitSpeed + cfg.particleSpeed*0.008;
            const tilt = 0.4;
            p.x = Math.cos(p.angle) * p.orbitR * totalS;
            p.y = Math.sin(p.angle) * p.orbitR * totalS * tilt;
            ctx.beginPath(); ctx.arc(p.x, p.y, p.size, 0, Math.PI*2);
            ctx.fillStyle = cfg.accent; ctx.globalAlpha = 0.5; ctx.fill();
          } else if (p.type === 'burst') {
            p.x += p.vx; p.y += p.vy; p.vx *= 0.96; p.vy *= 0.96;
            ctx.beginPath(); ctx.arc(p.x, p.y, p.size * (p.life/p.maxLife), 0, Math.PI*2);
            ctx.fillStyle = p.color || cfg.accent; ctx.globalAlpha = p.life / p.maxLife * 0.8; ctx.fill();
          } else if (p.type === 'symbol') {
            p.x += p.vx; p.y += p.vy;
            ctx.font = `bold ${p.size}px Inter, sans-serif`; ctx.textAlign = 'center';
            ctx.fillStyle = p.color || cfg.accent; ctx.globalAlpha = p.life / p.maxLife;
            ctx.fillText(p.text || '', p.x, p.y);
          } else if (p.type === 'spark' || p.type === 'dust') {
            p.x += p.vx; p.y += p.vy; p.vy += 0.05;
            ctx.beginPath(); ctx.arc(p.x, p.y, p.size * (p.life/p.maxLife), 0, Math.PI*2);
            ctx.fillStyle = p.color || cfg.core; ctx.globalAlpha = p.life / p.maxLife; ctx.fill();
          }
          ctx.globalAlpha = 1;
        });
        if (Math.random() < 0.01 && !S.asleep) {
          S.particles.push({
            x: (Math.random()-0.5)*40, y: -50, vx: (Math.random()-0.5)*0.5, vy: -0.8 - Math.random()*0.5,
            size: 14, life: 80, maxLife: 80, type: 'symbol',
            angle:0, orbitR:0, orbitSpeed:0, color: cfg.accent, text: cfg.symbol,
          });
        }
      }

      // 思考动画
      if (isThinking && !S.asleep) {
        const tDots = 3, tRadius = 70 * totalS, tSpeed = S.time * 2;
        for (let i = 0; i < tDots; i++) {
          const a = tSpeed + (Math.PI * 2 * i) / tDots;
          const tx = Math.cos(a) * tRadius, ty = Math.sin(a) * tRadius * 0.4;
          ctx.beginPath(); ctx.arc(tx, ty, 3, 0, Math.PI * 2);
          ctx.fillStyle = cfg.accent; ctx.globalAlpha = 0.4 + Math.sin(tSpeed * 2 + i) * 0.3; ctx.fill();
        }
        ctx.globalAlpha = 1;
      }

      // 拖尾
      S.trails.push({ x: 0, y: 0, age: 0 });
      S.trails = S.trails.filter(t => { t.age++; return t.age < 20; });
      S.trails.forEach(t => {
        const a = 1 - t.age/20;
        ctx.beginPath(); ctx.arc(t.x, t.y, 3*a, 0, Math.PI*2);
        ctx.fillStyle = cfg.glow; ctx.globalAlpha = a * 0.3; ctx.fill();
      });
      ctx.globalAlpha = 1;

      // ========== PartSystem 骨骼部件绘制 ==========
      const skel = skeletonRef.current!;
      const isSmall = size < 80;

      if (isSmall) {
        drawSimpleBody(ctx, skel, cfg.core);
      } else {
        ctx.save();
        ctx.scale(totalS * facing, totalS);

        // 面部状态计算
        const lookX = physics.get('eye_x');
        const lookY = physics.get('eye_y');
        const blinkOpen = S.asleep ? 0.05 : (1 - S.blink);

        let targetScene: typeof S.scene = 'idle';
        if (isThinking) targetScene = 'thinking';
        else if (isSpeaking) targetScene = 'speaking';
        else if (isBeingPetted) targetScene = 'petted';
        else if (currentSentence) {
          const s = currentSentence.toLowerCase();
          if (s.includes('错误') || s.includes('抱歉') || s.includes('失败') || s.includes('sorry') || s.includes('error') || s.includes('bug') || s.includes('崩溃')) targetScene = 'fail';
          else if (s.includes('成功') || s.includes('完成') || s.includes('搞定') || s.includes('done') || s.includes('success') || s.includes('ok') || s.includes('yes')) targetScene = 'success';
          else if (s.includes('好') || s.includes('棒') || s.includes('厉害') || s.includes('优秀') || s.includes('good') || s.includes('great') || s.includes('awesome') || s.includes('love')) targetScene = 'praised';
          else if (s.includes('不对') || s.includes('错了') || s.includes('差') || s.includes('不好') || s.includes('bad') || s.includes('wrong') || s.includes('hate') || s.includes('stupid')) targetScene = 'criticized';
          else if (s.includes('?') || s.includes('什么') || s.includes('怎么') || s.includes('why') || s.includes('how')) targetScene = 'thinking';
        }
        if (targetScene !== S.scene) {
          S.scene = targetScene;
          S.sceneTimer = 0;
        } else {
          S.sceneTimer += dt;
        }

        const baseFace = getFaceForEmotion(emotion);
        const sceneFace = getSceneFaceParams(S.scene, S.sceneTimer);
        let lipSync = { open: 0, width: 0, curve: 0 };
        if (isSpeaking && currentSentence) {
          lipSync = getCurrentPhoneme(currentSentence, S.sentencePhase);
        }
        let targetFace: FaceParams = {
          ...baseFace,
          ...sceneFace,
          eyeLOpen: (sceneFace.eyeLOpen ?? baseFace.eyeLOpen) * blinkOpen,
          eyeROpen: (sceneFace.eyeROpen ?? baseFace.eyeROpen) * blinkOpen,
          mouthWidth: (sceneFace.mouthWidth ?? baseFace.mouthWidth) + lipSync.width * 0.3,
          mouthCurve: (sceneFace.mouthCurve ?? baseFace.mouthCurve) + lipSync.curve * 0.2,
        };
        // 应用表情不对称（真实人脸左右不完全对称）
        targetFace = applyAsymmetry(targetFace, S.time);
        const STIFFNESS = 8;
        const DAMPING = 0.7;
        const keys = Object.keys(targetFace) as (keyof FaceParams)[];
        for (const k of keys) {
          const target = targetFace[k];
          const current = S.face[k] ?? 0;
          const vel = (S.faceVel[k] ?? 0);
          const force = (target - current) * STIFFNESS;
          const newVel = (vel + force * dt) * DAMPING;
          S.faceVel[k] = newVel;
          (S.face as any)[k] = current + newVel * dt;
        }
        const breathOffset = Math.sin(S.breathPhase) * 0.02;
        const finalLookX = lookX + S.saccadeX;
        const finalLookY = lookY + S.saccadeY + breathOffset;
        (S.face as FaceParams).browLHeight += breathOffset * 0.5;
        (S.face as FaceParams).browRHeight += breathOffset * 0.5;

        // 使用 PartSystem 绘制所有部件
        const partSystem = partSystemRef.current!;
        partSystem.draw(ctx, skel, {
          emotion,
          time: S.time,
          face: S.face as FaceParams,
          mouthOpen: S.mouthOpen + lipSync.open * 0.5,
          asleep: S.asleep,
          lookX: finalLookX,
          lookY: finalLookY,
          blinkOpen,
          appearance: appearanceConfig,
        });

        ctx.restore();
      }

      // 睡眠 Zzz
      if (S.asleep) {
        ctx.font = 'bold 14px Inter, sans-serif';
        ctx.fillStyle = '#94a3b8';
        ctx.globalAlpha = 0.6 + Math.sin(S.time*3)*0.3;
        ctx.fillText('z', 25, -55);
        ctx.globalAlpha = 0.4 + Math.sin(S.time*3+1)*0.2;
        ctx.fillText('z', 35, -65);
        ctx.globalAlpha = 1;
      }

      // 恢复坐标系
      ctx.restore();

      // Avatar 是独立生命体，不需要游戏UI元素（等级条/经验条/HUD）
      // 生命体征通过 Avatar 的行为和表情表达，而不是数字显示

      // ===== 口型同步系统（基于元音检测） =====
      if (isSpeaking && !S.asleep) {
        if (currentSentence) {
          const phoneme = getCurrentPhoneme(currentSentence, S.sentencePhase);
          const beat = S.time * 8;
          S.mouthOpen = phoneme.open * (0.8 + Math.sin(beat) * 0.2);
          S.sentencePhase += 0.016 * (1 + currentSentence.length * 0.02);
        } else {
          S.mouthOpen = 0.4 + Math.sin(S.time * 12) * 0.3 + Math.sin(S.time * 7) * 0.2;
        }
      } else {
        S.mouthOpen *= 0.92;
        S.sentencePhase = 0;
      }

      // ===== 视线微跳动（saccades）=====  
      S.saccadeTimer -= dt;
      if (S.saccadeTimer <= 0) {
        S.saccadeTargetX = (Math.random() - 0.5) * 0.3;
        S.saccadeTargetY = (Math.random() - 0.5) * 0.2;
        S.saccadeTimer = 0.2 + Math.random() * 0.8;
      }
      S.saccadeX += (S.saccadeTargetX - S.saccadeX) * 0.15;
      S.saccadeY += (S.saccadeTargetY - S.saccadeY) * 0.15;

      // ===== 呼吸面部影响 =====
      S.breathPhase += dt * 1.5;

      // ===== 眨眼系统增强（三段式：预备-快速闭合-缓慢睁开） =====
      if (!S.isBlinking && now - S.lastBlink > (S.asleep ? 1500 : 2000 + Math.random() * 3000)) {
        S.isBlinking = true;
        S.blinkPhase = 0;
        S.blinkSpeed = 15; // 快速闭合
        S.lastBlink = now;
      }
      if (S.isBlinking) {
        S.blinkPhase += S.blinkSpeed * dt;
        if (S.blinkPhase >= Math.PI) {
          S.blinkPhase = 0;
          S.isBlinking = false;
          S.blink = 0;
        } else {
          // 三段式曲线：快速闭合(0~1.5) → 保持(1.5~1.8) → 缓慢睁开(1.8~π)
          if (S.blinkPhase < 1.5) {
            S.blink = Math.sin(S.blinkPhase / 1.5 * Math.PI * 0.5);
          } else if (S.blinkPhase < 1.8) {
            S.blink = 1;
          } else {
            S.blink = Math.cos((S.blinkPhase - 1.8) / (Math.PI - 1.8) * Math.PI * 0.5);
          }
        }
      } else {
        S.blink = 0;
      }

      if (animated) {
        aid = requestAnimationFrame(draw);
      } else {
        aid = 0;
      }
    };
    if (animated || isVisible) {
      aid = requestAnimationFrame(draw);
    }

    return () => {
      cancelAnimationFrame(aid);
      io.disconnect();
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('mousedown', onDown);
      canvas.removeEventListener('mouseup', onUp);
      canvas.removeEventListener('mouseleave', onLeave);
    };
  // 依赖数组只保留真正需要重建 effect 的项：
  // size 变化 → canvas 尺寸变化必须重建
  // 事件回调保留在依赖中（虽然变化频率低）
  // 情绪/说话内容等易变 prop 通过 latestPropsRef 读取，不再触发重建
  }, [size, onClick, onLongPress, onDoubleClick, onPet, initParticles]);

  const ringProgress = xpToNext > 0 ? Math.min(100, (xp / xpToNext) * 100) : 0;

  return (
    <div className="relative inline-block overflow-visible" style={{ width: size, height: size }}>
      <canvas
        ref={canvasRef}
        className={`rounded-2xl cursor-pointer select-none transition-transform hover:scale-[1.02] ${className}`}
        style={{ width: size, height: size }}
        title="点击互动！连击有惊喜~"
      />
      {showLevelRing && (
        <svg className="absolute inset-0 pointer-events-none" width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle cx={size / 2} cy={size / 2} r={size / 2 - 4} fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth={3} />
          <circle cx={size / 2} cy={size / 2} r={size / 2 - 4} fill="none" stroke={getCfg(emotion, persona).core}
            strokeWidth={3} strokeLinecap="round"
            strokeDasharray={`${(ringProgress / 100) * 2 * Math.PI * (size / 2 - 4)} ${2 * Math.PI * (size / 2 - 4)}`}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: 'stroke-dasharray 0.5s ease' }}
          />
          <text x={size / 2} y={size - 8} textAnchor="middle" fill={getCfg(emotion, persona).accent}
            fontSize={size > 100 ? 12 : 9} fontWeight="bold">Lv.{level}</text>
        </svg>
      )}
    </div>
  );
}

// Helper removed — shadeColor now lives in PartSystem.ts
