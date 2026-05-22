import { useRef, useEffect, useState, useCallback } from 'react';

import { CanvasAvatar } from './CanvasAvatar';
import { useAvatarHome } from '@/contexts/AvatarHomeContext';
import { useAIState } from '@/contexts/AIStateContext';
import {
  createIntentState, setIntent, updateMove,
} from './avatar/IntentEngine';
import {
  createLookAtState, setLookTarget, updateLookAt,
} from './avatar/LookAtSystem';
import {
  createArrivalState, startArrival, updateArrival,
} from './avatar/ArrivalBehavior';
import {
  createHomeState, updateHome, isInHomeRange, getHomeSnapTarget,
  startReturn,
} from './avatar/HomeSystem';
// import { createProactiveState } from './avatar/ProactiveBehavior';
import {
  createSystemEventState, emitEvent, hasPendingEvents, consumeNextEvent, eventToAvatarReaction,
} from './avatar/SystemEventBridge';
import {
  createBondState, addBond, decayBond,
} from './avatar/BondSystem';
// import { getGait } from './avatar/EmotionGait';
import { DigitalSoul } from './avatar/DigitalSoul';
import type { AvatarAction } from '@/contexts/AvatarHomeContext';

export function GlobalAvatarFree() {
  const { state: homeState, returnHome, hide, setFreePosition, setDragging, setDragOffset } = useAvatarHome();
  const { state: aiState, sendWs } = useAIState();
  const containerRef = useRef<HTMLDivElement>(null);

  // 新行为系统
  const moveRef = useRef(createIntentState(homeState.freePosition.x, homeState.freePosition.y));
  const lookRef = useRef(createLookAtState());
  const arrivalRef = useRef(createArrivalState());
  const soulRef = useRef(new DigitalSoul());
  const homeRef = useRef(createHomeState(homeState.homePosition.x, homeState.homePosition.y));
  const eventRef = useRef(createSystemEventState());
  const bondRef = useRef(createBondState());

  // 同步 home 位置（拖拽后圆框位置会变化）
  useEffect(() => {
    homeRef.current.x = homeState.homePosition.x;
    homeRef.current.y = homeState.homePosition.y;
  }, [homeState.homePosition]);

  const lastTimeRef = useRef(performance.now());
  const lastInteractRef = useRef(performance.now());
  const [displayAction, setDisplayAction] = useState<AvatarAction>('idle');

  // 环境感知
  const perceptionRef = useRef({
    mouseX: 0, mouseY: 0,
    screenW: window.innerWidth, screenH: window.innerHeight,
    userIdleMs: 0,
  });

  // 用 ref 缓存易变 AI 状态，避免 RAF loop 因 aiState 变化而频繁重建
  const aiStateRef = useRef(aiState);
  aiStateRef.current = aiState;
  const sendWsRef = useRef(sendWs);
  sendWsRef.current = sendWs;
  const setFreePositionRef = useRef(setFreePosition);
  setFreePositionRef.current = setFreePosition;

  // 同步位置
  useEffect(() => {
    if (homeState.mode === 'free') {
      moveRef.current.x = homeState.freePosition.x;
      moveRef.current.y = homeState.freePosition.y;
    }
  }, [homeState.mode]);

  // 主循环: Digital Soul + 意图引擎 + 注视链 + 到达行为
  useEffect(() => {
    if (homeState.mode !== 'free') return;

    let raf = 0;
    let frameCount = 0;
    let lastSentPos = { x: homeState.freePosition.x, y: homeState.freePosition.y };
    const TARGET_FPS = 30;
    const FRAME_INTERVAL = 1000 / TARGET_FPS;
    let lastFrameTime = 0;
    const loop = () => {
      // Tab 不可见或 5 秒无交互时完全暂停
      if (document.hidden || performance.now() - lastInteractRef.current > 5000) {
        raf = 0;
        setTimeout(() => { if (!document.hidden) raf = requestAnimationFrame(loop); }, 500);
        return;
      }
      const now = performance.now();
      // 帧率限制：30fps，降低 CPU 占用
      if (now - lastFrameTime < FRAME_INTERVAL) {
        raf = requestAnimationFrame(loop);
        return;
      }
      lastFrameTime = now;
      const dt = Math.min(0.05, (now - lastTimeRef.current) / 1000);
      lastTimeRef.current = now;

      const soul = soulRef.current;
      const move = moveRef.current;
      const look = lookRef.current;
      const arrival = arrivalRef.current;
      const p = perceptionRef.current;
      const latestAi = aiStateRef.current;
      const latestPerception = latestAi.systemPerception;

      // 更新 Digital Soul
      soul.update();

      // 亲密度衰减
      const bond = bondRef.current;
      decayBond(bond);

      // P0: 同步系统感知到 DigitalSoul
      soul.updateSystemPerception({
        health: latestPerception.lastAlert ? 'warning' : 'healthy',
        userDetected: latestPerception.userDetected,
        userEmotion: latestPerception.userEmotion,
      });
      soul.roleState.physicalTasks = latestPerception.physicalTasks.length;
      soul.roleState.systemLoad = Math.min(1, latestPerception.taskLoad.totalRecent / 20);

      // AI 状态驱动 soul
      if (latestAi.isThinking) soul.onThinkingStart();
      else if (latestAi.isSpeaking) soul.onUserSpeak();

      // 从 AI 状态解析系统事件
      const eventState = eventRef.current;
      if (latestAi.emotion === 'happy' || latestAi.emotion === 'excited') {
        emitEvent(eventState, { type: 'memory_praise', content: '' });
        addBond(bond, 1, '被夸奖');
      }

      // P0: 将系统感知事件注入事件桥
      if (latestPerception.lastAlert && latestPerception.alertSeverity === 'critical') {
        emitEvent(eventState, { type: 'system_error_spike', rate: 0.5 });
      }
      if (latestPerception.physicalTasks.length > 0) {
        const lastTask = latestPerception.physicalTasks[0];
        if (lastTask.status === 'assigned') {
          emitEvent(eventState, { type: 'physical_task_assigned', taskId: lastTask.taskId, provider: lastTask.provider, action: lastTask.action, targetLocation: lastTask.targetLocation });
        }
      }
      if (latestPerception.userDetected) {
        emitEvent(eventState, { type: 'vision_user_detected', confidence: 0.8 });
      }

      // 处理系统事件
      while (hasPendingEvents(eventState)) {
        const evt = consumeNextEvent(eventState);
        if (evt) {
          const reaction = eventToAvatarReaction(evt);
          if (reaction.intensity > 0.3) {
            soul.physiology.mood += reaction.intensity * 10;
          }
        }
      }

      // 用户离开检测
      if (p.userIdleMs > 30000) soul.onUserAway(p.userIdleMs / 1000);

      // 情绪驱动意图
      const emotion = soul.getEmotionLabel();
      const energy = soul.physiology.energy;

          // 意图决策 — 丰富的自主行为
      if (!homeState.isDragging && move.intent === 'idle') {
        // 能量极低 → 回家休息（最高优先级）
        if (energy < 10) {
          setIntent(move, 'goto_home', homeRef.current.x, homeRef.current.y, '太累了，想回家睡觉');
        }
        // 高亲密度 + 用户 idle 久 → 主动凑近
        else if (p.userIdleMs > 5000 && Math.random() < 0.002 && soul.physiology.bond > 40 && energy > 30) {
          setIntent(move, 'follow_user', p.mouseX - 60, p.mouseY - 80, '想陪陪用户');
        }
        // 好奇探索
        else if (Math.random() < 0.0008 && soul.physiology.curiosity > 50 && energy > 40) {
          const exploreX = 150 + Math.random() * (p.screenW - 400);
          const exploreY = 150 + Math.random() * (p.screenH - 400);
          setIntent(move, 'explore', exploreX, exploreY, '好奇，想去看看');
        }
        // 能量中等 → 原地玩耍
        else if (Math.random() < 0.0005 && energy > 50 && soul.physiology.mood > 30) {
          // 原地 dance 一小会儿
        }
        // 能量低 → 原地休息
        else if (energy < 25 && Math.random() < 0.001) {
          setIntent(move, 'rest', move.x, move.y, '累了，休息一下');
        }
      }

      // 更新注视链
      const isMoving = move.intent !== 'idle' && move.intent !== 'rest';
      setLookTarget(look, p.mouseX, p.mouseY, move.x, move.y, 1);
      updateLookAt(look, dt, isMoving);

      // 更新到达行为
      const distToTarget = Math.hypot(move.targetX - move.x, move.targetY - move.y);
      if (isMoving && distToTarget < 60 && arrival.phase === 'approaching') {
        startArrival(arrival, move.targetX, move.targetY, look.headCurrentAngle);
      }
      updateArrival(arrival, dt, distToTarget);

      // 注视链影响：未对齐时减速
      const alignmentSpeedFactor = look.alignmentProgress > 0.5 ? 1 : look.alignmentProgress * 2;

      // 更新移动
      if (!homeState.isDragging) {
        updateMove(move, dt, p.screenW, p.screenH, 150 * alignmentSpeedFactor, 400, emotion);
        // 节流 setFreePosition：每 3 帧或移动超过 1px 才更新 React state
        frameCount++;
        const dx = move.x - lastSentPos.x;
        const dy = move.y - lastSentPos.y;
        if (frameCount % 3 === 0 || Math.abs(dx) > 1 || Math.abs(dy) > 1) {
          setFreePositionRef.current({ x: move.x, y: move.y });
          lastSentPos.x = move.x;
          lastSentPos.y = move.y;
        }
      }

      // 更新家状态
      const home = homeRef.current;
      updateHome(home, dt, move.x, move.y);

      // 回家检测：到达家位置后自动切换 mode
      if (move.intent === 'goto_home' && distToTarget < 15) {
        startReturn(home);
        setTimeout(() => returnHome(), 800);
      }

      // P0: 系统角色状态 → 动作映射（核心改造：让动作反映系统角色）
      const speed = Math.hypot(move.vx, move.vy);
      let action: AvatarAction = 'idle';

      // 优先级 1: 系统紧急告警
      if (soul.roleState.mode === 'alert' || latestPerception.alertSeverity === 'critical') {
        action = 'alert';
      }
      // 优先级 2: 物理任务执行中
      else if (soul.roleState.physicalTasks > 0 || latestPerception.physicalTasks.length > 0) {
        action = 'operate';
      }
      // 优先级 3: 深度思考中（高系统负载）
      else if (latestAi.isThinking && soul.roleState.systemLoad > 0.5) {
        action = 'think_deep';
      }
      // 优先级 4: 监控系统（有负载但空闲）
      else if (soul.roleState.systemLoad > 0.2) {
        action = 'monitor';
      }
      // 优先级 5: 用户交互
      else if (latestPerception.userDetected) {
        action = 'commune';
      }
      // 优先级 6: 传统情绪动作（兜底）
      else if (energy < 15) {
        action = 'sleep';
      } else if (arrival.phase === 'looking_around') {
        action = 'idle';
      } else if (speed > 80) {
        action = 'run';
      } else if (speed > 5) {
        action = 'walk';
      } else if (emotion === 'excited') {
        action = energy > 50 ? 'dance' : 'jump';
      } else if (emotion === 'happy') {
        action = Math.random() < 0.3 ? 'wave' : 'idle';
      } else if (emotion === 'angry') {
        action = speed > 20 ? 'run' : 'sit';
      } else if (emotion === 'sad') {
        action = energy < 30 ? 'lie' : 'sit';
      } else if (emotion === 'surprised') {
        action = 'jump';
      } else if (emotion === 'tired' || emotion === 'sleepy') {
        action = energy < 25 ? 'sleep' : 'sit';
      } else if (latestAi.isThinking) {
        action = 'sit';
      } else if (latestAi.isSpeaking) {
        action = 'wave';
      }

      // 节流 action state 更新：只有 action 变化时才 setState
      if (action !== displayAction) {
        setDisplayAction(action);
      }

      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
    // 只依赖 mode 和 isDragging；aiState 通过 ref 读取
  }, [homeState.mode, homeState.isDragging]);

  // 鼠标追踪
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      lastInteractRef.current = performance.now();
      perceptionRef.current.mouseX = e.clientX;
      perceptionRef.current.mouseY = e.clientY;
      perceptionRef.current.userIdleMs = 0;
      soulRef.current.onUserBack();
    };
    const onKeyDown = () => { lastInteractRef.current = performance.now(); perceptionRef.current.userIdleMs = 0; };
    const idleInterval = setInterval(() => { perceptionRef.current.userIdleMs += 1000; }, 1000);

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('keydown', onKeyDown);
      clearInterval(idleInterval);
    };
  }, []);

  // 情绪变化驱动 soul — 用 ref 避免 effect 重建
  useEffect(() => {
    const emotion = aiStateRef.current.emotion;
    if (emotion === 'happy' || emotion === 'excited') soulRef.current.onPraise(0.3);
    if (emotion === 'sad') soulRef.current.onCriticism(0.2);
    if (emotion === 'angry') soulRef.current.onCriticism(0.4);
  }, []);

  // 拖拽逻辑
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setDragOffset({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    setDragging(true);
    e.preventDefault();
    e.stopPropagation();
  }, [setDragOffset, setDragging]);

  useEffect(() => {
    if (!homeState.isDragging) return;
    const onMove = (e: MouseEvent) => {
      setFreePosition({ x: e.clientX - homeState.dragOffset.x, y: e.clientY - homeState.dragOffset.y });
      moveRef.current.x = e.clientX - homeState.dragOffset.x;
      moveRef.current.y = e.clientY - homeState.dragOffset.y;
    };
    const onUp = () => {
      setDragging(false);
      // 磁吸检测：释放时如果在家的范围内，自动回家
      const home = homeRef.current;
      if (isInHomeRange(home, moveRef.current.x, moveRef.current.y)) {
        const snap = getHomeSnapTarget(home);
        setFreePosition(snap);
        moveRef.current.x = snap.x;
        moveRef.current.y = snap.y;
        startReturn(home);
        setTimeout(() => returnHome(), 600);
      }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [homeState.isDragging, homeState.dragOffset, setFreePosition, setDragging]);

  // 抚摸
  const handlePet = useCallback(() => {
    soulRef.current.onPet();
    const ws = sendWsRef.current;
    if (ws) ws('avatar.pet', { user_id: 'web_user' });
  }, []);

  if (homeState.mode !== 'free') return null;

  const move = moveRef.current;
  const soul = soulRef.current;
  const home = homeRef.current;

  return (
    <>
      {/* 家的视觉标识 */}
      <div
        className="fixed z-40 select-none pointer-events-none"
        style={{
          left: home.x,
          top: home.y,
          width: 1,
          height: 1,
        }}
      >
        <div
          className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{
            width: home.radius * 2,
            height: home.radius * 2,
            background: `radial-gradient(circle, rgba(148,163,184,${home.glowIntensity * 0.15}) 0%, rgba(148,163,184,${home.glowIntensity * 0.05}) 40%, transparent 70%)`,
            opacity: home.isVisible ? 1 : 0,
            transition: 'opacity 0.3s ease',
          }}
        />
        {/* 小窝底座 */}
        <div
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
          style={{
            width: home.radius * 0.8,
            height: home.radius * 0.3,
            background: `rgba(148,163,184,${0.1 + home.glowIntensity * 0.1})`,
            borderRadius: '50%',
            border: `1px solid rgba(148,163,184,${0.2 + home.glowIntensity * 0.15})`,
          }}
        />
        {/* 磁吸提示：Avatar 在家范围内时显示 */}
        {isInHomeRange(home, move.x, move.y) && homeState.isDragging && (
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-[10px] text-blue-400 whitespace-nowrap pointer-events-none">
            松手回家
          </div>
        )}
      </div>

      {/* Avatar 主体 */}
      <div
        ref={containerRef}
        className="fixed z-50 select-none pointer-events-none"
        style={{
          left: move.x,
          top: move.y,
          cursor: homeState.isDragging ? 'grabbing' : 'grab',
          transition: homeState.isDragging ? 'none' : 'left 0.15s ease-out, top 0.15s ease-out',
          transform: `scale(${move.scale})`,
        }}
      >
      {homeState.isDragging && (
        <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-[10px] text-gray-400 whitespace-nowrap bg-white/80 px-2 py-0.5 rounded-full shadow-sm pointer-events-none">
          释放定位
        </div>
      )}

      <div className="relative pointer-events-auto" onMouseDown={handleMouseDown}>
        <CanvasAvatar
          emotion={aiState.emotion}
          persona={aiState.persona}
          size={200}
          isThinking={aiState.isThinking}
          isSpeaking={aiState.isSpeaking}
          vitals={aiState.vitals}
          isBeingPetted={aiState.isBeingPetted}
          currentSentence={aiState.currentSentence}
          action={displayAction}
          facing={move.facing}
          showParticles={false}
          showLevelRing={false}
          onPet={handlePet}
        />

        {/* 状态气泡 — P0: 显示系统角色状态 */}
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-2.5 py-0.5 bg-gray-900/70 backdrop-blur-sm rounded-full text-[10px] text-white/80 whitespace-nowrap pointer-events-none opacity-0 hover:opacity-100 transition-opacity">
          <span>{soul.getEmotionLabel()}</span>
          <span className="text-white/40">·</span>
          <span className="text-white/50">{
            displayAction === 'idle' ? '待机' :
            displayAction === 'walk' ? '走路' :
            displayAction === 'run' ? '跑步' :
            displayAction === 'sit' ? '坐着' :
            displayAction === 'lie' ? '躺着' :
            displayAction === 'sleep' ? '睡觉' :
            displayAction === 'jump' ? '跳跃' :
            displayAction === 'dance' ? '跳舞' :
            displayAction === 'wave' ? '挥手' :
            displayAction === 'monitor' ? '监控中' :
            displayAction === 'operate' ? '调度中' :
            displayAction === 'think_deep' ? '深度思考' :
            displayAction === 'recall' ? '回忆中' :
            displayAction === 'alert' ? '警觉' :
            displayAction === 'scan' ? '扫描' :
            displayAction === 'commune' ? '交流中' :
            displayAction === 'report' ? '汇报中' :
            displayAction === 'console' ? '控制台' :
            displayAction === 'reach_out' ? '伸手' : ''
          }</span>
          {aiState.systemPerception.physicalTasks.length > 0 && (
            <span className="text-blue-400">· {aiState.systemPerception.physicalTasks.length}个物理任务</span>
          )}
          {aiState.systemPerception.alertSeverity === 'critical' && (
            <span className="text-red-400">· 系统告警</span>
          )}
        </div>
      </div>

      {/* 回家/隐藏按钮 */}
      <div className="absolute -bottom-2 right-0 flex gap-1 opacity-0 hover:opacity-100 transition-opacity pointer-events-auto">
        <button onClick={returnHome} className="p-1 rounded bg-gray-800/50 text-white/60 hover:text-white text-[10px]" title="回家">🏠</button>
        <button onClick={hide} className="p-1 rounded bg-gray-800/50 text-white/60 hover:text-white text-[10px]" title="隐藏">👋</button>
      </div>
    </div>
    </>
  );
}
