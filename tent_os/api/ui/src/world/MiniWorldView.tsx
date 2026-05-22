/**
 * MiniWorldView — AI 的家的缩略视图
 * 常驻在聊天面板右侧，自动聚焦 Avatar 所在房间
 * 复用 WorldRenderer 渲染管线，但限制渲染范围
 */

import { useRef, useEffect, useState } from 'react';
import { useAIState } from '@/contexts/AIStateContext';
import { useSpacetime } from '@/contexts/SpacetimeContext';
import type { WorldState } from './WorldTypes';
import { createWorldState } from './WorldState';
import { loadWorldState, loadUnlockedRooms } from './worldApi';
import { Map, Maximize2 } from 'lucide-react';

interface MiniWorldViewProps {
  onExpand?: () => void;
}

export function MiniWorldView({ onExpand }: MiniWorldViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const worldRef = useRef<WorldState>(createWorldState());
  const lastSceneKeyRef = useRef('');
  const [isLoaded, setIsLoaded] = useState(false);
  const [avatarAction, setAvatarAction] = useState('idle');
  const [currentRoomName, setCurrentRoomName] = useState('');

  const { state: aiState } = useAIState();
  const { state: spacetime, setScheduleMode } = useSpacetime();

  // 用 ref 缓存易变状态，避免 draw loop effect 因 aiState/spacetime 变化频繁重建
  const aiStateRef = useRef(aiState);
  aiStateRef.current = aiState;
  const spacetimeRef = useRef(spacetime);
  spacetimeRef.current = spacetime;

  // ===== 加载后端世界状态 =====
  useEffect(() => {
    let mounted = true;
    (async () => {
      const [backendState, unlockedRoomIds] = await Promise.all([
        loadWorldState(),
        loadUnlockedRooms(),
      ]);
      if (!mounted) return;

      const world = worldRef.current;

      // 应用已解锁房间
      if (unlockedRoomIds.length > 0) {
        for (const room of world.rooms) {
          room.unlocked = unlockedRoomIds.includes(room.id);
        }
      }

      // 应用后端 Avatar 状态
      if (backendState) {
        world.avatar.roomId = backendState.avatar.room_id;
        world.avatar.position = { ...backendState.avatar.position };
        world.avatar.currentAction = backendState.avatar.action;
        world.avatar.facing = backendState.avatar.facing;
        setAvatarAction(backendState.avatar.action);
      }

      // 设置初始相机位置
      const avatarRoom = world.rooms.find(r => r.id === world.avatar.roomId);
      if (avatarRoom) {
        world.camera.x = avatarRoom.bounds.x + avatarRoom.bounds.w / 2 - 160;
        world.camera.y = avatarRoom.bounds.y + avatarRoom.bounds.h / 2 - 120;
        setCurrentRoomName(avatarRoom.nameZh);
      }

      setIsLoaded(true);
    })();
    return () => { mounted = false; };
  }, []);

  // 办公室场景自动解锁
  useEffect(() => {
    if (spacetime.environment.detectedScene === 'office') {
      const officeRoom = worldRef.current.rooms.find(r => r.id === 'office');
      if (officeRoom && !officeRoom.unlocked) {
        officeRoom.unlocked = true;
      }
    }
  }, [spacetime.environment.detectedScene]);

  // 记忆锚点 → 智慧藏品同步
  useEffect(() => {
    const world = worldRef.current;
    for (const anchor of spacetime.memoryAnchors) {
      const room = world.rooms.find(r => r.id === anchor.roomId);
      if (!room) continue;
      if (room.artifacts.some(a => a.id === anchor.id)) continue;

      const tag = anchor.emotionalTag.toLowerCase();
      const visualType: import('./WorldTypes').ArtifactVisual =
        tag.includes('joy') || tag.includes('happy') || tag.includes('excited') ? 'crystal' :
        tag.includes('focus') || tag.includes('work') || tag.includes('thinking') ? 'book' :
        tag.includes('calm') || tag.includes('peace') ? 'plant' :
        tag.includes('creative') || tag.includes('inspired') ? 'painting' :
        'scroll';

      const category: import('./WorldTypes').ArtifactCategory =
        tag.includes('code') ? 'code' :
        tag.includes('writing') ? 'writing' :
        tag.includes('design') ? 'design' :
        tag.includes('analysis') ? 'analysis' :
        tag.includes('creative') ? 'creative' :
        'analysis';

      room.artifacts.push({
        id: anchor.id,
        name: anchor.emotionalTag,
        taskId: anchor.sessionId,
        category,
        position: { x: 30 + Math.random() * (room.bounds.w - 80), y: 30 + Math.random() * (room.bounds.h - 80) },
        visualType,
        createdAt: Date.now(),
        rarity: 'rare',
        description: `记忆锚点: ${anchor.memoryUri}`,
      });
    }
  }, [spacetime.memoryAnchors]);

  // ===== 主渲染循环 =====
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    let isVisible = false; // 默认不可见，由 IntersectionObserver 决定
    let needsResize = true;

    const resize = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (!rect || rect.width === 0 || rect.height === 0) {
        needsResize = true;
        return false;
      }
      needsResize = false;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return true;
    };

    // ResizeObserver 监听父容器尺寸变化
    const ro = new ResizeObserver(() => {
      needsResize = true;
    });
    if (canvas.parentElement) {
      ro.observe(canvas.parentElement);
    }

    // IntersectionObserver：只在可见时渲染
    const io = new IntersectionObserver(([entry]) => {
      const wasVisible = isVisible;
      isVisible = entry.isIntersecting;
      if (isVisible && !wasVisible) {
        needsResize = true;
        if (!timerRef.current) {
          timerRef.current = window.setTimeout(draw, 0);
        }
      }
    }, { threshold: 0 });
    io.observe(canvas);

    const timerRef = { current: 0 as number };

    const draw = () => {
      timerRef.current = 0;
      if (!isVisible) return;

      if (needsResize) {
        if (!resize()) {
          timerRef.current = window.setTimeout(draw, 1000);
          return;
        }
      }

      const rect = canvas.parentElement!.getBoundingClientRect();
      const vw = rect.width;
      const vh = rect.height;

      const world = worldRef.current;
      const room = world.rooms.find(r => r.id === world.avatar.roomId);
      const latestSpacetime = spacetimeRef.current;
      const latestAi = aiStateRef.current;

      // 场景变化检测：只有 roomId / action / dayPhase 变化时才重绘
      const sceneKey = `${world.avatar.roomId}_${world.avatar.currentAction}_${latestSpacetime.dayPhase}`;
      const sceneChanged = lastSceneKeyRef.current !== sceneKey || !lastSceneKeyRef.current || needsResize;

      if (sceneChanged && room && room.unlocked) {
        lastSceneKeyRef.current = sceneKey;
        needsResize = false;

        ctx.clearRect(0, 0, vw, vh);

        // 根据时间画背景
        ctx.fillStyle = PHASE_BG[latestSpacetime.dayPhase] || '#fefce8';
        ctx.fillRect(0, 0, vw, vh);

        // 计算缩放让房间占满 canvas（留 padding）
        const padding = 16;
        const availW = vw - padding * 2;
        const availH = vh - padding * 2;
        const scale = Math.min(availW / room.bounds.w, availH / room.bounds.h);

        const rx = padding + (availW - room.bounds.w * scale) / 2;
        const ry = padding + (availH - room.bounds.h * scale) / 2;
        const rw = room.bounds.w * scale;
        const rh = room.bounds.h * scale;

        // 画房间地板
        ctx.fillStyle = room.bgColor || '#f5f0e8';
        ctx.beginPath();
        roundRectPath(ctx, rx, ry, rw, rh, 8);
        ctx.fill();

        // 画墙壁边框
        ctx.strokeStyle = room.wallColor || '#e8e0d0';
        ctx.lineWidth = 2;
        ctx.stroke();

        // 画家具（简化色块）
        for (const f of room.furniture) {
          const fx = rx + f.position.x * scale;
          const fy = ry + f.position.y * scale;
          const fw = f.size.w * scale;
          const fh = f.size.h * scale;

          ctx.fillStyle = f.color || '#d4c8b8';
          if (f.shape === 'ellipse') {
            ctx.beginPath();
            ctx.ellipse(fx + fw / 2, fy + fh / 2, fw / 2, fh / 2, 0, 0, Math.PI * 2);
            ctx.fill();
          } else {
            ctx.beginPath();
            roundRectPath(ctx, fx, fy, fw, fh, 3);
            ctx.fill();
          }

          if (f.strokeColor) {
            ctx.strokeStyle = f.strokeColor;
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        }

        // 画 Avatar（简化小圆点）
        const ax = rx + (world.avatar.position.x - room.bounds.x) * scale;
        const ay = ry + (world.avatar.position.y - room.bounds.y) * scale;
        const avatarSize = Math.max(5, Math.min(9, scale * 7));

        // 影子
        ctx.fillStyle = 'rgba(0,0,0,0.1)';
        ctx.beginPath();
        ctx.ellipse(ax, ay + avatarSize * 0.5, avatarSize * 0.8, avatarSize * 0.25, 0, 0, Math.PI * 2);
        ctx.fill();

        // 身体
        const actionColor = ACTION_COLORS[world.avatar.currentAction] || '#34d399';
        ctx.fillStyle = actionColor;
        ctx.beginPath();
        ctx.arc(ax, ay, avatarSize, 0, Math.PI * 2);
        ctx.fill();

        // 眼睛
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(ax - avatarSize * 0.35, ay - avatarSize * 0.1, avatarSize * 0.3, 0, Math.PI * 2);
        ctx.arc(ax + avatarSize * 0.35, ay - avatarSize * 0.1, avatarSize * 0.3, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#333';
        ctx.beginPath();
        ctx.arc(ax - avatarSize * 0.35 + world.avatar.facing, ay - avatarSize * 0.1, avatarSize * 0.15, 0, Math.PI * 2);
        ctx.arc(ax + avatarSize * 0.35 + world.avatar.facing, ay - avatarSize * 0.1, avatarSize * 0.15, 0, Math.PI * 2);
        ctx.fill();

        // 思考光环
        if (latestAi.isThinking) {
          const t = performance.now() / 1000;
          ctx.strokeStyle = 'rgba(167,139,250,0.3)';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(ax, ay, avatarSize + 3 + Math.sin(t * 3) * 2, 0, Math.PI * 2);
          ctx.stroke();
        }

        // 状态气泡
        const actionText = getActionDisplayText(world.avatar.currentAction);
        ctx.font = 'bold 10px Inter, sans-serif';
        const textWidth = ctx.measureText(actionText).width;
        const bp = 6;
        const bubbleW = textWidth + bp * 2;
        const bubbleH = 18;
        const bubbleX = ax - bubbleW / 2;
        const bubbleY = ay - avatarSize - 18;
        ctx.fillStyle = 'rgba(13, 148, 136, 0.9)';
        ctx.beginPath();
        roundRectPath(ctx, bubbleX, bubbleY, bubbleW, bubbleH, 9);
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(ax - 3, bubbleY + bubbleH);
        ctx.lineTo(ax + 3, bubbleY + bubbleH);
        ctx.lineTo(ax, bubbleY + bubbleH + 4);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(actionText, ax, bubbleY + bubbleH / 2);
      }

      // 5 秒检查一次，平时完全不绘制
      timerRef.current = window.setTimeout(draw, 5000);
    };

    // 启动循环（IO 会决定实际是否渲染）
    timerRef.current = window.setTimeout(draw, 0);
    return () => {
      clearTimeout(timerRef.current);
      ro.disconnect();
      io.disconnect();
    };
    // 空依赖：aiState / spacetime 通过 ref 读取，避免 effect 频繁重建
  }, []);

  // ===== 同步 Avatar 动作到 MiniView =====
  useEffect(() => {
    const world = worldRef.current;
    world.avatar.currentAction = avatarAction;
  }, [avatarAction]);

  // ===== 从 SpacetimeContext 更新 Avatar 目标位置 =====
  useEffect(() => {
    const world = worldRef.current;
    let targetRoomId = world.avatar.roomId;
    let targetAction = 'idle';
    let targetPos = world.avatar.position;

    // 优先级1：时间表 sleep 模式 → 去卧室床上
    if (spacetime.scheduleMode === 'sleep') {
      targetRoomId = 'bedroom';
      targetAction = 'sleep';
      const bed = world.rooms.find(r => r.id === 'bedroom')?.furniture.find(f => f.type === 'bed');
      if (bed) {
        const room = world.rooms.find(r => r.id === 'bedroom')!;
        targetPos = {
          x: room.bounds.x + bed.position.x + bed.size.w / 2,
          y: room.bounds.y + bed.position.y + bed.size.h * 0.55,
        };
      }
    } else if (spacetime.currentActivity) {
      // 优先级2：当前活动
      const recommendation = spacetime.currentActivity;
      switch (recommendation.type) {
        case 'coding':
        case 'thinking':
          targetRoomId = 'study';
          targetAction = recommendation.type === 'thinking' ? 'think_deep' : 'operate';
          break;
        case 'monitoring':
          targetRoomId = 'living_room';
          targetAction = 'monitor';
          break;
        case 'dreaming':
        case 'resting':
          targetRoomId = 'bedroom';
          targetAction = recommendation.type === 'dreaming' ? 'sleep' : 'idle';
          break;
        case 'chatting':
          targetRoomId = 'study';
          targetAction = 'commune';
          break;
        default:
          targetAction = 'idle';
      }
    }

    const targetRoom = world.rooms.find(r => r.id === targetRoomId);
    if (targetRoom) {
      if (world.avatar.roomId !== targetRoomId) {
        world.avatar.roomId = targetRoomId;
      }
      // 如果指定了目标位置，移动到该位置
      if (targetPos !== world.avatar.position) {
        world.avatar.position = targetPos;
      }
      setCurrentRoomName(targetRoom.nameZh);
    }

    world.avatar.currentAction = targetAction;
    setAvatarAction(targetAction);
  }, [spacetime.currentActivity, spacetime.scheduleMode]);

  // ===== 状态文字 =====
  const activityLabel = spacetime.currentActivity
    ? `${spacetime.currentActivity.target}`
    : '待机中';

  const fatigueIndicator = spacetime.fatigue > 0.6
    ? 'text-amber-500'
    : spacetime.fatigue > 0.3
    ? 'text-yellow-500'
    : 'text-green-500';

  return (
    <div className="flex flex-col h-full bg-gray-50 border-l border-gray-200">
      {/* 头部 */}
      <div className="px-3 py-2.5 bg-white border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Map className="w-3.5 h-3.5 text-teal-600" />
          <span className="text-xs font-semibold text-gray-700">AI 的家</span>
        </div>
        <button
          onClick={onExpand}
          className="p-1 rounded-md text-gray-400 hover:text-teal-600 hover:bg-teal-50 transition-colors"
          title="展开完整地图"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Canvas 区域 */}
      <div className="flex-1 relative overflow-hidden bg-gradient-to-b from-gray-50 to-gray-100">
        {!isLoaded && (
          <div className="absolute inset-0 flex items-center justify-center text-gray-400 text-xs">
            加载世界中...
          </div>
        )}
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full"
          style={{ opacity: isLoaded ? 1 : 0, transition: 'opacity 0.3s' }}
        />
      </div>

      {/* 底部状态条 */}
      <div className="px-3 py-2.5 bg-white border-t border-gray-200 space-y-1.5">
        {/* 当前位置 */}
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-gray-500">
            📍 {currentRoomName || '未知位置'}
          </span>
          <span className={`text-[11px] font-medium ${fatigueIndicator}`}>
            {spacetime.fatigue > 0.6 ? '😫 疲劳' : spacetime.fatigue > 0.3 ? '😊 一般' : '⚡ 精力充沛'}
          </span>
        </div>

        {/* 当前活动 */}
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse" />
          <span className="text-[11px] text-gray-700 truncate" title={activityLabel}>
            {activityLabel}
          </span>
        </div>

        {/* 时间表 + 手动切换 */}
        <div className="flex items-center justify-between text-[10px]">
          <div className="flex items-center gap-1">
            <span className="text-gray-400">
              {spacetime.scheduleMode === 'work' && '💼 工作'}
              {spacetime.scheduleMode === 'rest' && '☕ 休息'}
              {spacetime.scheduleMode === 'sleep' && '🌙 睡眠'}
              {spacetime.scheduleMode === 'break' && '😌 小憩'}
            </span>
            {/* 手动切换按钮 */}
            <select
              value={spacetime.scheduleMode}
              onChange={(e) => setScheduleMode(e.target.value as 'work' | 'rest' | 'sleep' | 'break')}
              className="text-[10px] bg-gray-50 border border-gray-200 rounded px-1 py-0.5 text-gray-600 cursor-pointer hover:bg-gray-100 focus:outline-none focus:ring-1 focus:ring-teal-300"
              title="手动切换 AI 时间表"
            >
              <option value="work">💼 工作</option>
              <option value="rest">☕ 休息</option>
              <option value="sleep">🌙 睡眠</option>
              <option value="break">😌 小憩</option>
            </select>
          </div>
          <span className="text-gray-400">
            {spacetime.dayPhase === 'morning' && '🌅 早晨'}
            {spacetime.dayPhase === 'afternoon' && '☀️ 下午'}
            {spacetime.dayPhase === 'evening' && '🌆 傍晚'}
            {spacetime.dayPhase === 'night' && '🌃 夜晚'}
          </span>
        </div>

        {/* 自主决策提示 */}
        {spacetime.autonomyDecision && (
          <div className="px-2 py-1 bg-amber-50 border border-amber-200 rounded-md">
            <p className="text-[10px] text-amber-700">
              💭 {spacetime.autonomyDecision}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ===== 辅助函数 =====

function getActionDisplayText(action: string): string {
  const map: Record<string, string> = {
    idle: '待机中',
    walk: '走动中',
    alert: '处理告警',
    operate: '工作中',
    think_deep: '深度思考',
    monitor: '监控中',
    commune: '交流中',
    celebrate: '庆祝',
    sleep: '休息中',
    rest: '放松中',
  };
  return map[action] || action;
}

function roundRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

const PHASE_BG: Record<string, string> = {
  morning: '#fefce8',
  afternoon: '#fff7ed',
  evening: '#fdf2f8',
  night: '#1e1b4b',
};

const ACTION_COLORS: Record<string, string> = {
  idle: '#34d399',
  walk: '#60a5fa',
  alert: '#ef4444',
  operate: '#f59e0b',
  think_deep: '#a78bfa',
  monitor: '#3b82f6',
  commune: '#ec4899',
  celebrate: '#fbbf24',
  sleep: '#94a3b8',
  rest: '#22d3ee',
};
