/**
 * WorldMapPanel — AI 的 2D 世界主面板
 * React 组件：Canvas 渲染 + 鼠标交互 + 相机控制
 */

import { useRef, useEffect, useState, useCallback } from 'react';
import { useAIState } from '@/contexts/AIStateContext';
import { useSpacetime } from '@/contexts/SpacetimeContext';
import { FridgeNotes } from '@/components/FridgeNotes';
import { CalendarWall } from '@/components/CalendarWall';
import { ProjectFrames } from '@/components/ProjectFrames';
import { LetterRack } from '@/components/LetterRack';
import { X } from 'lucide-react';
import type { WorldState, Point } from './WorldTypes';
import { WORLD_SIZE } from './WorldTypes';
import { createWorldState, screenToWorld, worldToScreen, findRoomAt, findFurnitureAt, findArtifactAt, findPropAt, clampCamera, loadVisualMemoryProps, loadDreamEntries } from './WorldState';
import { renderMapView, renderBuildingInterior } from './WorldRenderer';
import { renderWorldBackground } from './renderers/Background';
import { renderRoom } from './renderers/Room';
import { renderFurniture } from './renderers/Furniture';
import { worldAvatarRenderer } from './WorldAvatarRenderer';

import { decideAvatarBehavior, getAvatarStandPosition } from './RoomSystem';
import { SYSTEM_ACTION_MAP, PROP_ACTION_MAP } from './WorldTypes';
import { loadWorldState, saveAvatarState, loadWorldStats } from './worldApi';


export function WorldMapPanel() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const staticCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const staticDirtyRef = useRef(true);

  const worldStateRef = useRef<WorldState>(createWorldState());
  const animFrameRef = useRef(0);

  const mouseRef = useRef<Point>({ x: 0, y: 0 });
  const pathRef = useRef<Point[]>([]);
  const pathIndexRef = useRef(0);
  const arrivalTimerRef = useRef(0); // 到达后的停留计时器

  // 道具交互状态（机制一-3）
  const propInteractionRef = useRef<{
    propId: string | null;
    startTime: number;
    duration: number;
    isInteracting: boolean;
  }>({ propId: null, startTime: 0, duration: 0, isInteracting: false });

  // 相机动画状态
  const cameraAnimRef = useRef<{
    targetX: number; targetY: number; targetZoom: number;
    isAnimating: boolean; startTime: number; duration: number;
    fromX: number; fromY: number; fromZoom: number;
  } | null>(null);

  const { state: aiState } = useAIState();
  const { state: spacetime, getRecommendedAction } = useSpacetime();
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const [avatarAction, setAvatarActionRaw] = useState('idle');
  const [activePopup, setActivePopup] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'map' | 'room'>('map');
  const viewModeRef = useRef(viewMode);
  useEffect(() => {
    viewModeRef.current = viewMode;
    staticDirtyRef.current = true;
  }, [viewMode]);

  const [currentRoomId, setCurrentRoomId] = useState<string | null>(null);
  const currentRoomIdRef = useRef(currentRoomId);
  useEffect(() => {
    currentRoomIdRef.current = currentRoomId;
    staticDirtyRef.current = true;
  }, [currentRoomId]);

  const [currentBuildingId, setCurrentBuildingId] = useState<string | null>(null);
  const currentBuildingIdRef = useRef(currentBuildingId);
  useEffect(() => {
    currentBuildingIdRef.current = currentBuildingId;
    staticDirtyRef.current = true;
  }, [currentBuildingId]);

  // 地图模式相机状态（支持拖拽）
  const mapCameraRef = useRef({ x: 0, y: 0, zoom: 0.4, initialized: false });

  const avatarStateRef = useRef<string>('IDLE');

  // PRD 缺口: Avatar 行为日志持久化
  const setAvatarAction = useCallback((action: string) => {
    setAvatarActionRaw(action);
    const world = worldStateRef.current;
    fetch('/ui/api/world/avatar-logs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        emotion: aiState.emotion,
        room_id: world.avatar.roomId,
        x: world.avatar.position.x,
        y: world.avatar.position.y,
      }),
    }).catch(() => {});
  }, [aiState.emotion]);
  const [worldStats, setWorldStats] = useState<{ level: number; exp: number; tasks: number; artifacts: number } | null>(null);

  // PRD 缺口: Avatar 拖拽 + 状态气泡
  const avatarDragRef = useRef<{ isDragging: boolean; offsetX: number; offsetY: number; fromRoomId: string | null }>({ isDragging: false, offsetX: 0, offsetY: 0, fromRoomId: null });
  const [avatarBubble, setAvatarBubble] = useState<{ x: number; y: number; text: string } | null>(null);
  const bubbleTimerRef = useRef<number | null>(null);

  // 加载后端世界状态
  useEffect(() => {
    let mounted = true;
    (async () => {
      const [backendState, stats, visualProps, dreamEntries] = await Promise.all([
        loadWorldState(),
        loadWorldStats(),
        loadVisualMemoryProps(),
        loadDreamEntries(),
      ]);
      if (!mounted) return;

      const world = worldStateRef.current;

      // 加载视觉记忆映射的虚实道具
      world.visualMemoryProps = visualProps;
      world.dreamEntries = dreamEntries;

      // 应用后端 Avatar 状态
      if (backendState) {
        world.avatar.roomId = backendState.avatar.room_id;
        world.avatar.position = { ...backendState.avatar.position };
        world.avatar.currentAction = backendState.avatar.action;
        world.avatar.facing = backendState.avatar.facing;
      }

      // 应用统计
      if (stats) {
        setWorldStats({
          level: stats.level,
          exp: stats.experience,
          tasks: stats.tasks_completed,
          artifacts: stats.artifact_count,
        });
      }
    })();
    return () => { mounted = false; };
  }, []);

  // 定期保存 Avatar 状态到后端（每 10 秒）
  useEffect(() => {
    const interval = setInterval(() => {
      const avatar = worldStateRef.current.avatar;
      saveAvatarState({
        avatar_room_id: avatar.roomId,
        avatar_position_x: Math.round(avatar.position.x),
        avatar_position_y: Math.round(avatar.position.y),
        avatar_action: avatar.currentAction,
        avatar_facing: avatar.facing,
      });
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  // 记忆锚点 → 智慧藏品同步
  useEffect(() => {
    const world = worldStateRef.current;
    for (const anchor of spacetime.memoryAnchors) {
      const room = world.rooms.find(r => r.id === anchor.roomId);
      if (!room) continue;
      // 避免重复添加
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

  // Avatar 行为决策（每 3 秒）
  useEffect(() => {
    const interval = setInterval(() => {
      const world = worldStateRef.current;
      const room = world.rooms.find(r => r.id === world.avatar.roomId);
      if (!room) return;

      // 如果有路径在执行中，不重新决策
      if (pathRef.current.length > 0 && pathIndexRef.current < pathRef.current.length) return;

      // ===== PRD D2.0: 化身状态引擎 =====
      // 根据 scheduleMode + emotion + activity 推导 avatar_state
      const newState = deriveAvatarState(
        spacetime.scheduleMode,
        spacetime.currentActivity,
        aiState.emotion,
        aiState.isThinking
      );
      if (newState !== avatarStateRef.current) {
        avatarStateRef.current = newState;
        // 状态变化时显示气泡
        const stateLabels: Record<string, string> = {
          WORKING: '🔧 进入专注模式',
          RESTING: '🛋️ 需要休息一下',
          SLEEPING: '🌙 进入梦境',
          EMOTIONAL_LOW: '💙 情绪有点低落',
          EXCITED: '✨ 超兴奋！',
          IDLE: '🌀 空闲中',
        };
        const canvas = canvasRef.current;
        if (canvas) {
          const world = worldStateRef.current;
          const avatarScreen = worldToScreen(world.avatar.position.x, world.avatar.position.y, world.camera);
          setAvatarBubble({ x: avatarScreen.x, y: avatarScreen.y - 50, text: stateLabels[newState] || newState });
          if (bubbleTimerRef.current) window.clearTimeout(bubbleTimerRef.current);
          bubbleTimerRef.current = window.setTimeout(() => setAvatarBubble(null), 4000);
        }
      }

      // ===== 时空映射器优先 =====
      // 先询问 SpacetimeContext 的推荐动作
      const spacetimeRec = getRecommendedAction && getRecommendedAction();
      if (spacetimeRec) {
        const mapping = SYSTEM_ACTION_MAP[spacetimeRec.action];
        if (mapping) {
          let targetRoom = room;
          let furniture = room.furniture.find(f => f.type === mapping.furnitureType && f.interactable);

          // 如果当前房间没有目标家具，跨房间查找
          if (!furniture) {
            const foundRoom = world.rooms.find(r =>
              r.unlocked && r.furniture.some(f => f.type === mapping.furnitureType && f.interactable)
            );
            if (foundRoom) {
              targetRoom = foundRoom;
              furniture = foundRoom.furniture.find(f => f.type === mapping.furnitureType && f.interactable)!;
              // 瞬移到目标房间入口附近
              world.avatar.roomId = foundRoom.id;
              world.avatar.position = {
                x: foundRoom.bounds.x + foundRoom.bounds.w / 2,
                y: foundRoom.bounds.y + foundRoom.bounds.h / 2,
              };
            }
          }

          if (furniture) {
            const targetPos = getAvatarStandPosition(furniture, targetRoom);
            pathRef.current = [world.avatar.position, targetPos];
            pathIndexRef.current = 0;
            world.avatar.currentAction = spacetimeRec.action;
            world.avatar.isMoving = true;
            setAvatarAction(spacetimeRec.action);
            return;
          }
        }
        // 如果是 autonomy 决策（去休息），找沙发或床
        if (spacetimeRec.action === 'autonomy' || spacetimeRec.action === 'rest') {
          const restFurniture = room.furniture.find(f => f.type === 'sofa' || f.type === 'bed');
          if (restFurniture) {
            const targetPos = getAvatarStandPosition(restFurniture, room);
            pathRef.current = [world.avatar.position, targetPos];
            pathIndexRef.current = 0;
            world.avatar.currentAction = 'idle';
            world.avatar.isMoving = true;
            setAvatarAction('idle');
            return;
          }
        }
      }

      // ===== 机制一-3: 道具交互 =====
      if (!propInteractionRef.current.isInteracting && world.props) {
        const now = Date.now();
        const roomProps = world.props.filter(p =>
          p.roomId === room.id &&
          (p.state === 'idle' || p.state === 'used') &&
          (!p.lastInteractedAt || now - p.lastInteractedAt > 60000) // 60s cooldown
        );
        if (roomProps.length > 0 && Math.random() < 0.4) {
          const prop = roomProps[Math.floor(Math.random() * roomProps.length)];
          const propAction = PROP_ACTION_MAP[prop.type];
          if (propAction) {
            // 根据道具类型调整目标位置
            const isWallMounted = prop.type === 'wall_clock';
            const targetPos = {
              x: room.bounds.x + prop.position.x + prop.size.w / 2,
              y: isWallMounted
                ? room.bounds.y + prop.position.y + prop.size.h + 40 // 墙下站立
                : room.bounds.y + prop.position.y + prop.size.h + 15, // 道具前方
            };
            pathRef.current = [world.avatar.position, targetPos];
            pathIndexRef.current = 0;
            world.avatar.currentAction = propAction.action as any;
            world.avatar.isMoving = true;
            setAvatarAction(propAction.action);
            propInteractionRef.current = {
              propId: prop.id,
              startTime: Date.now(),
              duration: propAction.duration,
              isInteracting: false, // 到达后才开始
            };
            prop.state = 'in_use';
            return;
          }
        }
      }

      // ===== 回退到原有决策逻辑 =====
      const decision = decideAvatarBehavior(world.avatar, room, {
        alertSeverity: aiState.systemPerception.alertSeverity,
        physicalTasks: aiState.systemPerception.physicalTasks.length,
        isThinking: aiState.isThinking,
        systemLoad: aiState.systemPerception.taskLoad.totalRecent / 20,
        userDetected: aiState.systemPerception.userDetected,
        emotion: aiState.emotion,
      });

      if (decision) {
        pathRef.current = [world.avatar.position, decision.targetPos];
        pathIndexRef.current = 0;
        world.avatar.currentAction = decision.action;
        world.avatar.isMoving = true;
        setAvatarAction(decision.action);
      } else {
        // 空闲时随机微动作
        if (Math.random() < 0.3) {
          const idleAction = avatarStateRef.current === 'EXCITED' ? 'celebrate' : 'idle';
          world.avatar.currentAction = idleAction;
          world.avatar.isMoving = false;
          setAvatarAction(idleAction);
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [aiState, getRecommendedAction]);

  // Avatar 移动路径执行
  useEffect(() => {
    let raf = 0;
    let isVisible = true;
    let io: IntersectionObserver | null = null;
    const canvas = canvasRef.current;
    if (canvas) {
      io = new IntersectionObserver(([entry]) => {
        const wasVisible = isVisible;
        isVisible = entry.isIntersecting;
        if (isVisible && !wasVisible && !raf) {
          raf = requestAnimationFrame(moveLoop);
        }
      }, { threshold: 0 });
      io.observe(canvas);
    }

    const moveLoop = () => {
      if (!isVisible) { raf = 0; return; }
      const world = worldStateRef.current;
      const path = pathRef.current;
      const idx = pathIndexRef.current;

      // ===== 串门动画状态机 =====
      if (world.avatarTravelState && world.avatarTravelState !== 'home') {
        const speed = 100; // 外出时走得更快
        const dt = 0.016;
        const current = world.avatar.position;

        if (world.avatarTravelState === 'travelling') {
          // 走向目标建筑
          const building = world.communityBuildings?.find(b => b.id === world.avatarTravelTarget);
          if (building) {
            const targetX = building.bounds.x + building.bounds.w / 2;
            const targetY = building.bounds.y + building.bounds.h / 2 + 60;
            const dx = targetX - current.x;
            const dy = targetY - current.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 10) {
              world.avatarTravelState = 'visiting';
              world.avatarTravelProgress = 0;
              arrivalTimerRef.current = 5; // 停留 5 秒
              world.avatar.currentAction = 'commune';
              setAvatarAction('commune');
            } else {
              world.avatar.position.x += (dx / dist) * speed * dt;
              world.avatar.position.y += (dy / dist) * speed * dt;
              world.avatar.facing = dx > 0 ? 1 : -1;
              world.avatar.isMoving = true;
            }
          }
        } else if (world.avatarTravelState === 'visiting') {
          // 停留倒计时
          arrivalTimerRef.current -= dt;
          world.avatar.isMoving = false;
          if (arrivalTimerRef.current <= 0) {
            world.avatarTravelState = 'returning';
            world.avatar.currentAction = 'walk';
            setAvatarAction('walk');
          }
        } else if (world.avatarTravelState === 'returning') {
          // 返回家中（走向大门，然后回家中心）
          const homeRoom = world.rooms.find(r => r.id === 'living_room');
          if (homeRoom) {
            const targetX = homeRoom.bounds.x + homeRoom.bounds.w / 2;
            const targetY = homeRoom.bounds.y + homeRoom.bounds.h / 2;
            const dx = targetX - current.x;
            const dy = targetY - current.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 10) {
              world.avatarTravelState = 'home';
              world.avatarTravelTarget = null;
              world.avatar.isMoving = false;
              world.avatar.currentAction = 'idle';
              setAvatarAction('idle');
              world.avatar.roomId = 'living_room';
            } else {
              world.avatar.position.x += (dx / dist) * speed * dt;
              world.avatar.position.y += (dy / dist) * speed * dt;
              world.avatar.facing = dx > 0 ? 1 : -1;
              world.avatar.isMoving = true;
            }
          }
        }
      } else if (path.length > 1 && idx < path.length - 1) {
        const current = world.avatar.position;
        const target = path[idx + 1];
        const dx = target.x - current.x;
        const dy = target.y - current.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const speed = 80; // 像素/秒
        const dt = 0.016;

        if (dist < 5) {
          pathIndexRef.current++;
          if (pathIndexRef.current >= path.length - 1) {
            // 到达目标！
            world.avatar.isMoving = false;
            world.avatar.targetRoomId = null;
            // 睡眠动作：一直停留，直到外部条件改变
            if (world.avatar.currentAction === 'sleep' || world.avatar.currentAction === 'dreaming') {
              arrivalTimerRef.current = Infinity;
            } else if (propInteractionRef.current.propId && !propInteractionRef.current.isInteracting) {
              // 机制一-3: 道具交互——到达后开始计时
              arrivalTimerRef.current = propInteractionRef.current.duration;
              propInteractionRef.current.isInteracting = true;
            } else {
              // 其他动作：启动停留计时器（3-5秒）
              arrivalTimerRef.current = 3 + Math.random() * 2;
            }
          }
        } else {
          const moveX = (dx / dist) * speed * dt;
          const moveY = (dy / dist) * speed * dt;
          world.avatar.position.x += moveX;
          world.avatar.position.y += moveY;
          world.avatar.facing = dx > 0 ? 1 : -1;

          // 更新所在房间
          const newRoom = findRoomAt(world.avatar.position, world.rooms);
          if (newRoom) {
            world.avatar.roomId = newRoom.id;
          }
        }
      } else if (arrivalTimerRef.current > 0) {
        // 到达后停留倒计时
        arrivalTimerRef.current -= 0.016;
        if (arrivalTimerRef.current <= 0) {
          // 机制一-3: 道具交互完成
          if (propInteractionRef.current.isInteracting && propInteractionRef.current.propId) {
            const prop = world.props?.find(p => p.id === propInteractionRef.current.propId);
            if (prop) {
              prop.state = 'used';
              prop.lastInteractedAt = Date.now();
              prop.interactCount++;
              // 向后端发送交互记录
              fetch('/ui/api/world/prop-interaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  prop_id: prop.id,
                  prop_type: prop.type,
                  action: world.avatar.currentAction,
                  room_id: prop.roomId,
                }),
              }).catch(() => {});
            }
            propInteractionRef.current = { propId: null, startTime: 0, duration: 0, isInteracting: false };
          }
          // 停留结束，恢复 idle
          world.avatar.currentAction = 'idle';
          world.avatar.targetFurnitureId = null;
          setAvatarAction('idle');
          pathRef.current = []; // 清空路径
        }
      }

      // 只有在地图模式或有活跃移动时才高频更新
      const isMapMode = viewModeRef.current === 'map' || currentBuildingIdRef.current !== null;
      const isTravelling = world.avatarTravelState && world.avatarTravelState !== 'home';
      const hasPath = path.length > 1 && idx < path.length - 1;
      const hasTimer = arrivalTimerRef.current > 0;

      if (isMapMode || isTravelling || hasPath || hasTimer) {
        raf = requestAnimationFrame(moveLoop);
      } else {
        // 房间模式下 Avatar 静止，每秒检查一次即可
        raf = window.setTimeout(moveLoop, 1000);
      }
    };
    raf = requestAnimationFrame(moveLoop);
    return () => {
      cancelAnimationFrame(raf);
      if (io) io.disconnect();
    };
  }, []);

  // 主渲染循环
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;

    // 初始化静态缓存 canvas
    if (!staticCanvasRef.current) {
      staticCanvasRef.current = document.createElement('canvas');
    }
    const staticCanvas = staticCanvasRef.current;

    const resize = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (!rect) return;
      const w = Math.floor(rect.width * dpr);
      const h = Math.floor(rect.height * dpr);
      canvas.width = w;
      canvas.height = h;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // 同步静态缓存 canvas 尺寸
      if (staticCanvas.width !== w || staticCanvas.height !== h) {
        staticCanvas.width = w;
        staticCanvas.height = h;
        staticDirtyRef.current = true;
      }
    };
    resize();

    // 初始化地图相机：基于内容边界自动计算最佳 zoom，确保内容完整显示且居中
    const world = worldStateRef.current;
    const initRect = canvas.parentElement?.getBoundingClientRect();
    if (initRect) {
      const contentPad = 60;
      const contentW = 3200 + contentPad * 2; // 0 ~ 3200 + padding
      const contentH = 1100 + contentPad * 2;
      const fitZoomX = initRect.width / contentW;
      const fitZoomY = initRect.height / contentH;
      const bestZoom = Math.min(fitZoomX, fitZoomY, 0.45); // 上限 0.45，避免过大
      const bestZoomRounded = Math.round(bestZoom * 100) / 100;
      mapCameraRef.current.zoom = Math.max(0.25, bestZoomRounded);
      mapCameraRef.current.x = WORLD_SIZE.w / 2 - initRect.width / 2 / mapCameraRef.current.zoom;
      mapCameraRef.current.y = WORLD_SIZE.h / 2 - initRect.height / 2 / mapCameraRef.current.zoom;
      mapCameraRef.current.initialized = true;
      world.camera.x = mapCameraRef.current.x;
      world.camera.y = mapCameraRef.current.y;
      world.camera.zoom = mapCameraRef.current.zoom;
    }

    // 首次加载引导：3 秒后缓慢平移到社区大门，提示用户社区存在
    const hasSeenCommunityGuide = localStorage.getItem('tent_os_community_guide');
    if (!hasSeenCommunityGuide) {
      setTimeout(() => {
        const rect = canvas.parentElement?.getBoundingClientRect();
        if (!rect) return;
        const targetZoom = 0.8;
        const targetX = 1800 - rect.width / 2 / targetZoom;
        const targetY = 300 - rect.height / 2 / targetZoom;
        cameraAnimRef.current = {
          targetX, targetY, targetZoom,
          isAnimating: true,
          startTime: performance.now(),
          duration: 2500,
          fromX: world.camera.x,
          fromY: world.camera.y,
          fromZoom: world.camera.zoom,
        };
        localStorage.setItem('tent_os_community_guide', '1');
      }, 3000);
    }

    let isVisible = false;
    const io = new IntersectionObserver(([entry]) => {
      const wasVisible = isVisible;
      isVisible = entry.isIntersecting;
      if (isVisible && !wasVisible && !animFrameRef.current) {
        animFrameRef.current = requestAnimationFrame(draw);
      }
    }, { threshold: 0 });
    io.observe(canvas);

    const draw = () => {
      if (!isVisible) {
        animFrameRef.current = 0;
        return; // 完全停止，等待 IntersectionObserver 恢复
      }

      const rect = canvas.parentElement?.getBoundingClientRect();
      if (!rect) {
        animFrameRef.current = requestAnimationFrame(draw);
        return;
      }
      const vw = rect.width;
      const vh = rect.height;
      const time = performance.now() / 1000;

      if (viewModeRef.current === 'map') {
        // 地图模式：使用 mapCameraRef 支持拖拽
        worldStateRef.current.camera.x = mapCameraRef.current.x;
        worldStateRef.current.camera.y = mapCameraRef.current.y;
        worldStateRef.current.camera.zoom = mapCameraRef.current.zoom;

        // 地图模式下 Avatar 是简化渲染，跳过复杂的骨骼动画更新以节省性能
        renderMapView(ctx, worldStateRef.current, vw, vh, time);
      } else if (currentBuildingIdRef.current) {
        // 社区建筑内部模式
        const building = worldStateRef.current.communityBuildings?.find(b => b.id === currentBuildingIdRef.current);
        if (building) {
          renderBuildingInterior(ctx, building, vw, vh, time);
        }
      } else {
        // 房间模式：只画当前房间，保留完整美术风格
        const roomId = currentRoomIdRef.current;
        const room = roomId ? worldStateRef.current.rooms.find(r => r.id === roomId) : null;
        if (room) {
          // 设置相机聚焦当前房间（只占满视野）
          const margin = 1.05;
          const zoomX = vw / (room.bounds.w * margin);
          const zoomY = vh / (room.bounds.h * margin);
          const targetZoom = Math.min(zoomX, zoomY, 2.0);
          worldStateRef.current.camera.zoom = targetZoom;
          worldStateRef.current.camera.x = room.bounds.x + room.bounds.w / 2 - vw / 2 / targetZoom;
          worldStateRef.current.camera.y = room.bounds.y + room.bounds.h / 2 - vh / 2 / targetZoom;
          worldStateRef.current.selectedRoomId = roomId;

          // 更新 Avatar 动画状态
          if (worldStateRef.current.avatar.isMoving) {
            worldAvatarRenderer.update(0.016, worldStateRef.current.avatar, time, aiState.emotion);
          }

          // Layer 0: 背景
          renderWorldBackground(ctx, vw, vh, spacetime.dayPhase);

          // Layer 1: 只画当前房间（保留完整美术：阴影、纹理、标签）
          renderRoom(ctx, room, worldStateRef.current.camera, true, time);

          // Layer 2-3: 只画当前房间的家具（保留完整美术：便利贴、冰箱贴、日志...）
          for (const f of room.furniture) {
            if (f.type !== 'rug') {
              renderFurniture(ctx, f, room, worldStateRef.current.camera, false, time);
            }
          }
          // 地毯在 Avatar 下面
          for (const f of room.furniture) {
            if (f.type === 'rug') {
              renderFurniture(ctx, f, room, worldStateRef.current.camera, false, time);
            }
          }

          // Layer 4: Avatar（完整版）
          worldAvatarRenderer.render(ctx, worldStateRef.current.avatar, worldStateRef.current.camera);
        }
      }

      // 地图/建筑模式用 RAF，房间模式用 setTimeout 降频
      if (viewModeRef.current === 'map' || currentBuildingIdRef.current) {
        animFrameRef.current = requestAnimationFrame(draw);
      } else {
        animFrameRef.current = window.setTimeout(draw, 200);
      }
    };
    animFrameRef.current = requestAnimationFrame(draw);

    window.addEventListener('resize', resize);
    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener('resize', resize);
      io.disconnect();
      animFrameRef.current = 0;
    };
  }, []);

  // 鼠标交互
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    mouseRef.current = { x: sx, y: sy };

    const world = worldStateRef.current;
    const wPos = screenToWorld(sx, sy, world.camera);

    // 检测 hover
    const room = findRoomAt(wPos, world.rooms);
    if (room) {
      const roomPos = {
        x: wPos.x - room.bounds.x,
        y: wPos.y - room.bounds.y,
      };
      const furniture = findFurnitureAt(roomPos, room, 5 / world.camera.zoom);
      const artifact = findArtifactAt(roomPos, room, 20 / world.camera.zoom);
      const prop = findPropAt(roomPos, room, 5 / world.camera.zoom);

      world.hoveredFurnitureId = furniture?.id || null;
      world.hoveredArtifactId = artifact?.id || null;
      world.hoveredPropId = prop?.id || null;
      world.hoveredBuildingId = null;

      if (furniture) {
        setTooltip({ x: sx + 12, y: sy - 8, text: `${furniture.name} · ${getFunctionText(furniture.functions)}` });
      } else if (prop) {
        setTooltip({ x: sx + 12, y: sy - 8, text: `${prop.name} · 点击交互` });
      } else if (artifact) {
        setTooltip({ x: sx + 12, y: sy - 8, text: `${artifact.name} · ${getRarityText(artifact.rarity)}` });
      } else {
        setTooltip(null);
      }
    } else {
      world.hoveredFurnitureId = null;
      world.hoveredArtifactId = null;
      world.hoveredPropId = null;
      // 检测社区建筑 hover
      const building = world.communityBuildings?.find(b =>
        wPos.x >= b.bounds.x && wPos.x <= b.bounds.x + b.bounds.w &&
        wPos.y >= b.bounds.y && wPos.y <= b.bounds.y + b.bounds.h
      );
      world.hoveredBuildingId = building?.id || null;
      if (building) {
        setTooltip({ x: sx + 12, y: sy - 8, text: `${building.nameZh} · ${building.description}` });
      } else {
        setTooltip(null);
      }
    }

    // PRD 缺口: Avatar 拖拽中
    if (avatarDragRef.current.isDragging) {
      const newScreenX = sx - avatarDragRef.current.offsetX;
      const newScreenY = sy - avatarDragRef.current.offsetY;
      const newWorldPos = screenToWorld(newScreenX, newScreenY, world.camera);
      world.avatar.position = newWorldPos;
      const newRoom = findRoomAt(newWorldPos, world.rooms);
      if (newRoom) {
        world.avatar.roomId = newRoom.id;
      }
    }

    // 相机拖拽
    if (world.isDragging && world.cameraDragStart) {
      const dx = (sx - world.cameraDragStart.x) / world.camera.zoom;
      const dy = (sy - world.cameraDragStart.y) / world.camera.zoom;
      world.camera.x -= dx;
      world.camera.y -= dy;
      world.cameraDragStart = { x: sx, y: sy };
      clampCamera(world.camera, rect.width, rect.height);
      // 同步回 mapCameraRef（地图模式）
      if (viewModeRef.current === 'map') {
        mapCameraRef.current.x = world.camera.x;
        mapCameraRef.current.y = world.camera.y;
      }
    }
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const world = worldStateRef.current;
    const wPos = screenToWorld(sx, sy, world.camera);

    // ===== 地图模式：点击建筑进入 / 空白处拖拽 =====
    if (viewModeRef.current === 'map') {
      // 检测点击的房间建筑
      const room = world.rooms.find(r =>
        wPos.x >= r.bounds.x && wPos.x <= r.bounds.x + r.bounds.w &&
        wPos.y >= r.bounds.y && wPos.y <= r.bounds.y + r.bounds.h
      );
      if (room) {
        setCurrentRoomId(room.id);
        setViewMode('room');
        world.selectedRoomId = room.id;
        return;
      }
      // 检测点击的社区建筑
      const building = world.communityBuildings?.find(b =>
        wPos.x >= b.bounds.x && wPos.x <= b.bounds.x + b.bounds.w &&
        wPos.y >= b.bounds.y && wPos.y <= b.bounds.y + b.bounds.h
      );
      if (building) {
        setCurrentBuildingId(building.id);
        setViewMode('room');
        return;
      }
      // 空白处：开始拖拽相机
      world.isDragging = true;
      world.cameraDragStart = { x: sx, y: sy };
      return;
    }

    // ===== 房间模式：原有交互逻辑 =====

    // PRD 缺口: 检测是否点击了 Avatar（拖拽 Avatar）
    const avatarScreen = worldToScreen(world.avatar.position.x, world.avatar.position.y, world.camera);
    const avatarSize = 25 * world.camera.zoom; // Avatar 屏幕半径约 25px
    const distToAvatar = Math.sqrt((sx - avatarScreen.x) ** 2 + (sy - avatarScreen.y) ** 2);
    if (distToAvatar < avatarSize) {
      // PRD 缺口: 点击 Avatar 显示状态气泡
      showAvatarBubble();
      // 开始拖拽 Avatar
      avatarDragRef.current = {
        isDragging: true,
        offsetX: sx - avatarScreen.x,
        offsetY: sy - avatarScreen.y,
        fromRoomId: world.avatar.roomId,
      };
      // 清除路径，停止自动移动
      pathRef.current = [];
      pathIndexRef.current = 0;
      world.avatar.isMoving = false;
      return;
    }

    // 检测点击的房间
    const room = findRoomAt(wPos, world.rooms);
    if (room) {
      world.selectedRoomId = room.id;

      // 相机动画聚焦到该房间（仅在非拖拽模式下）
      if (!avatarDragRef.current.isDragging) {
        const cRect = canvas.getBoundingClientRect();
        const targetZoom = 1.8;
        const targetX = room.bounds.x + room.bounds.w / 2 - cRect.width / 2 / targetZoom;
        const targetY = room.bounds.y + room.bounds.h / 2 - cRect.height / 2 / targetZoom;
        cameraAnimRef.current = {
          targetX, targetY, targetZoom,
          isAnimating: true,
          startTime: performance.now(),
          duration: 800,
          fromX: world.camera.x,
          fromY: world.camera.y,
          fromZoom: world.camera.zoom,
        };
      }

      // 检测点击的家具
      const roomPos = { x: wPos.x - room.bounds.x, y: wPos.y - room.bounds.y };
      const furniture = findFurnitureAt(roomPos, room, 5 / world.camera.zoom);

      if (furniture?.interactable) {
        // PRD D2.0: memory_board 类型的家具点击时弹出面板，不移动 Avatar
        if (furniture.type === 'memory_board') {
          setActivePopup(furniture.id);
          return;
        }
        const targetPos = getAvatarStandPosition(furniture, room);
        pathRef.current = [world.avatar.position, targetPos];
        pathIndexRef.current = 0;
        world.avatar.isMoving = true;
        world.avatar.targetFurnitureId = furniture.id;
        const mapping = Object.entries(SYSTEM_ACTION_MAP).find(([, v]) => v.furnitureType === furniture.type);
        if (mapping) {
          world.avatar.currentAction = mapping[1].action;
          setAvatarAction(mapping[1].action);
        }
      } else {
        pathRef.current = [world.avatar.position, wPos];
        pathIndexRef.current = 0;
        world.avatar.isMoving = true;
        world.avatar.currentAction = 'walk';
        setAvatarAction('walk');
      }
    } else {
      // 检测点击社区建筑
      const building = world.communityBuildings?.find(b =>
        wPos.x >= b.bounds.x && wPos.x <= b.bounds.x + b.bounds.w &&
        wPos.y >= b.bounds.y && wPos.y <= b.bounds.y + b.bounds.h
      );
      if (building) {
        world.selectedRoomId = null;
        // 相机动画聚焦到建筑
        const cRect = canvas.getBoundingClientRect();
        const targetZoom = 1.5;
        const targetX = building.bounds.x + building.bounds.w / 2 - cRect.width / 2 / targetZoom;
        const targetY = building.bounds.y + building.bounds.h / 2 - cRect.height / 2 / targetZoom;
        cameraAnimRef.current = {
          targetX, targetY, targetZoom,
          isAnimating: true,
          startTime: performance.now(),
          duration: 1000,
          fromX: world.camera.x,
          fromY: world.camera.y,
          fromZoom: world.camera.zoom,
        };
        // 如果 Avatar 在家，启动外出串门动画
        if (!world.avatarTravelState || world.avatarTravelState === 'home') {
          startAvatarTravel(world, building.id);
        }
      } else {
        world.isDragging = true;
        world.cameraDragStart = { x: sx, y: sy };
      }
    }
  }, []);

  const handleMouseUp = useCallback(() => {
    const world = worldStateRef.current;
    world.isDragging = false;
    world.cameraDragStart = null;

    // Avatar 拖拽释放：如果不在任何房间内，snap 回原来的房间
    if (avatarDragRef.current.isDragging && avatarDragRef.current.fromRoomId) {
      const currentRoom = findRoomAt(world.avatar.position, world.rooms);
      if (!currentRoom) {
        const fromRoom = world.rooms.find(r => r.id === avatarDragRef.current.fromRoomId);
        if (fromRoom) {
          world.avatar.position.x = fromRoom.bounds.x + fromRoom.bounds.w / 2;
          world.avatar.position.y = fromRoom.bounds.y + fromRoom.bounds.h / 2;
          world.avatar.roomId = fromRoom.id;
        }
      }
    }
    avatarDragRef.current.isDragging = false;
    avatarDragRef.current.fromRoomId = null;
  }, []);

  // 机制二-2: 右键放置装饰
  const handleContextMenu = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const world = worldStateRef.current;
    const wPos = screenToWorld(sx, sy, world.camera);
    const room = findRoomAt(wPos, world.rooms);
    if (!room || !room.unlocked) return;

    const roomPos = { x: wPos.x - room.bounds.x, y: wPos.y - room.bounds.y };
    const decorationTypes = ['sticker', 'poster', 'plant'];
    const colors = ['#F87171', '#FBBF24', '#34D399', '#60A5FA', '#A78BFA', '#F472B6'];
    const type = decorationTypes[Math.floor(Math.random() * decorationTypes.length)];
    const color = colors[Math.floor(Math.random() * colors.length)];

    const newDec = {
      roomId: room.id,
      decorationType: type,
      name: '用户装饰',
      position: roomPos,
      size: { w: 30, h: 30 },
      color,
      createdAt: new Date().toISOString(),
    };

    // 更新前端状态
    world.userDecorations = [...world.userDecorations, { ...newDec, id: `temp_${Date.now()}` }];

    // 向后端保存
    fetch('/ui/api/world/user-decorations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        room_id: newDec.roomId,
        decoration_type: newDec.decorationType,
        name: newDec.name,
        x: newDec.position.x,
        y: newDec.position.y,
        size_w: newDec.size.w,
        size_h: newDec.size.h,
        color: newDec.color,
      }),
    }).catch(() => {});
  }, []);

  // PRD 缺口: 双击房间放大
  const handleDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const world = worldStateRef.current;
    const wPos = screenToWorld(sx, sy, world.camera);
    const room = findRoomAt(wPos, world.rooms);

    if (room?.unlocked) {
      const targetZoom = 2.0;
      const targetX = room.bounds.x + room.bounds.w / 2 - rect.width / 2 / targetZoom;
      const targetY = room.bounds.y + room.bounds.h / 2 - rect.height / 2 / targetZoom;
      cameraAnimRef.current = {
        targetX, targetY, targetZoom,
        isAnimating: true,
        startTime: performance.now(),
        duration: 600,
        fromX: world.camera.x,
        fromY: world.camera.y,
        fromZoom: world.camera.zoom,
      };
    }
  }, []);

  // PRD 缺口: 点击 Avatar 显示状态气泡
  const showAvatarBubble = useCallback(() => {
    const world = worldStateRef.current;
    const avatarScreen = worldToScreen(world.avatar.position.x, world.avatar.position.y, world.camera);
    const emotion = aiState.emotion || 'neutral';
    const activity = spacetime.currentActivity?.target || '空闲中';
    const text = `情绪: ${emotion} | ${activity}`;
    setAvatarBubble({ x: avatarScreen.x, y: avatarScreen.y - 40, text });
    if (bubbleTimerRef.current) window.clearTimeout(bubbleTimerRef.current);
    bubbleTimerRef.current = window.setTimeout(() => setAvatarBubble(null), 3000);
  }, [aiState.emotion, spacetime.currentActivity]);

  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const world = worldStateRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    // 以鼠标位置为中心缩放
    const wPos = screenToWorld(sx, sy, world.camera);
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.max(0.3, Math.min(2.0, world.camera.zoom * zoomFactor));

    world.camera.x = wPos.x - sx / newZoom;
    world.camera.y = wPos.y - sy / newZoom;
    world.camera.zoom = newZoom;
    clampCamera(world.camera, rect.width, rect.height);
  }, []);

  const handleBackToMap = useCallback(() => {
    setViewMode('map');
    setCurrentRoomId(null);
    setCurrentBuildingId(null);
    worldStateRef.current.selectedRoomId = null;
    // 重置地图相机到自适应位置
    const canvas = canvasRef.current;
    if (canvas) {
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        const contentPad = 60;
        const contentW = 3200 + contentPad * 2;
        const contentH = 1100 + contentPad * 2;
        const fitZoomX = rect.width / contentW;
        const fitZoomY = rect.height / contentH;
        const bestZoom = Math.min(fitZoomX, fitZoomY, 0.45);
        const bestZoomRounded = Math.round(bestZoom * 100) / 100;
        mapCameraRef.current.zoom = Math.max(0.25, bestZoomRounded);
        mapCameraRef.current.x = WORLD_SIZE.w / 2 - rect.width / 2 / mapCameraRef.current.zoom;
        mapCameraRef.current.y = WORLD_SIZE.h / 2 - rect.height / 2 / mapCameraRef.current.zoom;
      }
    }
  }, []);

  return (
    <div className="relative w-full h-full bg-gray-50 overflow-hidden">
      {/* 返回按钮（仅在 room 模式显示）*/}
      {viewMode === 'room' && (
        <button
          onClick={handleBackToMap}
          className="absolute top-3 left-3 z-30 px-3 py-1.5 bg-white/90 backdrop-blur-sm rounded-lg text-sm text-gray-700 shadow-sm hover:bg-white transition-colors flex items-center gap-1.5"
        >
          ← 返回地图
        </button>
      )}

      <canvas
        ref={canvasRef}
        className="absolute inset-0 cursor-grab active:cursor-grabbing"
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onContextMenu={handleContextMenu}
        onDoubleClick={handleDoubleClick}
        onWheel={handleWheel}
      />

      {/* Tooltip */}
      {tooltip && (
        <div
          className="absolute pointer-events-none z-50 px-2.5 py-1 bg-gray-900/80 backdrop-blur-sm rounded-lg text-xs text-white whitespace-nowrap"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}

      {/* PRD 缺口: Avatar 状态气泡 */}
      {avatarBubble && (
        <div
          className="absolute pointer-events-none z-50 px-3 py-1.5 bg-white/90 backdrop-blur-sm rounded-xl border border-teal-200 shadow-lg text-xs text-teal-800 whitespace-nowrap"
          style={{ left: avatarBubble.x, top: avatarBubble.y, transform: 'translateX(-50%)' }}
        >
          <span className="inline-block w-2 h-2 rounded-full bg-teal-400 mr-1.5 animate-pulse" />
          {avatarBubble.text}
        </div>
      )}

      {/* 底部状态栏 */}
      <div className="absolute bottom-0 left-0 right-0 h-10 bg-white/80 backdrop-blur-sm border-t border-gray-200 flex items-center px-4 gap-4 text-xs text-gray-600 z-10">
        <span className="font-medium text-teal-600">
          👤 小腾正在{getActionText(avatarAction)}
        </span>
        <span className="text-gray-400">|</span>
        <span>
          当前位置：{worldStateRef.current.rooms.find(r => r.id === worldStateRef.current.avatar.roomId)?.nameZh || '未知'}
        </span>
        {worldStats && (
          <>
            <span className="text-gray-400">|</span>
            <span className="text-amber-600">⭐ Lv.{worldStats.level}</span>
            <span className="text-gray-400">|</span>
            <span>🎯 {worldStats.tasks} 任务</span>
            <span className="text-gray-400">|</span>
            <span>💎 {worldStats.artifacts} 藏品</span>
          </>
        )}
      </div>

      {/* PRD D2.0: 家园物品悬浮面板 */}
      {activePopup && (
        <div
          className="absolute inset-0 z-40 bg-black/30 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) setActivePopup(null);
          }}
        >
          <div className="relative w-full max-w-2xl h-[80vh] bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden flex flex-col">
            {/* 面板头部 */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50/50">
              <span className="text-sm font-semibold text-gray-700">
                {activePopup === 'fridge_board' && '📝 冰箱贴墙'}
                {activePopup === 'calendar_wall' && '📅 日历墙'}
                {activePopup === 'project_frame' && '🖼️ 项目画廊'}
                {activePopup === 'letter_rack' && '✉️ 信件架'}
              </span>
              <button
                onClick={() => setActivePopup(null)}
                className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {/* 面板内容 */}
            <div className="flex-1 overflow-hidden">
              {activePopup === 'fridge_board' && <FridgeNotes />}
              {activePopup === 'calendar_wall' && <CalendarWall />}
              {activePopup === 'project_frame' && <ProjectFrames />}
              {activePopup === 'letter_rack' && <LetterRack />}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ===== 辅助函数 =====

function getFunctionText(functions: string[]): string {
  const map: Record<string, string> = {
    rest: '休息',
    work: '工作',
    think: '思考',
    monitor: '监控',
    store: '存储',
    display: '展示',
  };
  return functions.map(f => map[f] || f).join(' · ');
}

function getRarityText(rarity: string): string {
  const map: Record<string, string> = {
    common: '普通',
    rare: '稀有',
    epic: '史诗',
    legendary: '传说',
  };
  return map[rarity] || rarity;
}

function getActionText(action: string): string {
  const map: Record<string, string> = {
    idle: '待机中',
    walk: '走动中',
    alert: '处理告警',
    operate: '调度任务',
    think_deep: '深度思考',
    monitor: '监控系统',
    commune: '等待交流',
    celebrate: '庆祝成果',
    sleep: '休息中',
  };
  return map[action] || action;
}

function startAvatarTravel(world: import('./WorldTypes').WorldState, buildingId: string): void {
  world.avatarTravelState = 'travelling';
  world.avatarTravelTarget = buildingId;
  world.avatarTravelProgress = 0;
  world.avatar.currentAction = 'walk';
  world.avatar.isMoving = true;
}

// PRD D2.0: 化身状态引擎 — 根据时空节律推导 Avatar 状态
function deriveAvatarState(
  scheduleMode: string,
  currentActivity: { type: string; progress: number } | null,
  emotion: string,
  isThinking: boolean
): string {
  // 最高优先级：睡眠
  if (scheduleMode === 'sleep') return 'SLEEPING';
  // 情绪极端状态
  if (emotion === 'excited' || emotion === 'happy' || emotion === 'joy') return 'EXCITED';
  if (emotion === 'sad' || emotion === 'anxious' || emotion === 'depressed' || emotion === 'tired') return 'EMOTIONAL_LOW';
  // 深度思考或工作中
  if (isThinking || (currentActivity && currentActivity.progress > 0)) return 'WORKING';
  // 休息模式
  if (scheduleMode === 'rest' || scheduleMode === 'break') return 'RESTING';
  // 默认空闲
  return 'IDLE';
}
