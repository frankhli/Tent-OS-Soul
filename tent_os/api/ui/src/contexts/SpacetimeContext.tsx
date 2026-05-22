/**
 * SpacetimeContext — 时空映射器
 * AI 的"数字生命"核心调度层：时间表、环境感知、活动状态、疲劳与自主决策
 * 它读取 AIStateContext 的瞬时状态，将其转换为有节奏、有空间感的生命状态
 */

import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import { useAIState } from './AIStateContext';
import { loadSpacetimeState, loadCollectibles, loadMemoryAnchors, loadSpatialMemory, loadObjectInventory, loadUserDecorations } from '@/world/spacetimeApi';

// ===== 类型定义 =====

export type ScheduleMode = 'work' | 'rest' | 'sleep' | 'break';
export type DayPhase = 'morning' | 'afternoon' | 'evening' | 'night';
export type ActivityType = 'chatting' | 'coding' | 'thinking' | 'monitoring' | 'dreaming' | 'idle' | 'resting' | 'commuting';
export type WeatherType = 'clear' | 'rain' | 'cloudy' | 'snow' | null;

export interface EnvironmentState {
  brightness: number;      // 环境亮度 0-1（来自摄像头或时间推断）
  weather: WeatherType;    // 推断天气
  detectedScene: string;   // 场景标签: home/office/outdoor/unknown
  peopleCount: number;     // 检测到的人数
  keyObjects: string[];    // 关键物体: ['cat', 'plant', 'coffee_cup']
  temperature: number | null; // 感知温度（如果有传感器）
}

export interface CurrentActivity {
  type: ActivityType;
  target: string;          // 目标描述: "生成 Python 脚本"
  location: string;        // 所在房间/家具: "书房·书桌"
  progress: number;        // 进度 0-1
  since: number;           // 开始时间戳
  sessionId?: string;      // 关联的会话 ID
}

export interface ScheduleSlot {
  mode: ScheduleMode;
  startHour: number;       // 0-23
  endHour: number;
  label: string;           // 显示标签: "工作时间"
}

export interface SpacetimeState {
  // 时间节律
  scheduleMode: ScheduleMode;
  scheduleNextChange: number;
  dayPhase: DayPhase;
  currentTime: Date;

  // 环境感知
  environment: EnvironmentState;

  // AI 当前活动
  currentActivity: CurrentActivity | null;

  // 疲劳与自主决策
  fatigue: number;
  lastHighLoadAt: number | null;
  autonomyDecision: string | null;
  autonomyDecisionUntil: number | null;

  // 收集癖（视觉感知到的物体 → AI 家中的收集品）
  collectedObjects: CollectedObject[];

  // 记忆锚点（与 2D 世界中的智慧藏品关联）
  memoryAnchors: MemoryAnchor[];

  // 认知地图标签
  cognitiveLabels: CognitiveLabel[];

  // 思维导图节点（reasoning 流）
  reasoningNodes: string[];

  // 空间记忆（机制二-1）
  spatialMemory: SpatialMemory[];
  objectInventory: ObjectInventoryItem[];

  // 用户改造（机制二-2）
  userDecorations: UserDecoration[];

  // 视觉感知（机制二-3：摄像头 → VLM → 空间记忆）
  visionPerception: VisionPerception | null;
}

export interface VisionPerception {
  roomId: string;
  sceneType: string;
  sceneDescription: string;
  objects: Array<{ name: string; location: string; confidence: number }>;
  peopleCount: number;
  lighting: string;
  mood: string;
  timestamp: string;
}

export interface UserDecoration {
  id: string;
  roomId: string;
  decorationType: string;
  name: string;
  position: { x: number; y: number };
  size: { w: number; h: number };
  color: string;
  createdAt: string;
}

export interface SpatialMemory {
  id: string;
  roomId: string;
  x: number;
  y: number;
  label: string;
  memoryType: string;
  description: string | null;
  emotionalTag: string | null;
  createdAt: string;
  accessCount: number;
}

export interface ObjectInventoryItem {
  id: string;
  roomId: string;
  name: string;
  objectType: string;
  x: number;
  y: number;
  state: string;
  detectedAt: string;
  detectedFrom: string | null;
}

export interface CognitiveLabel {
  x: number;
  y: number;
  label: string;
  type: 'rest' | 'energy' | 'work' | 'social' | 'unknown';
  confidence: number; // 0-1
  discoveredAt: number; // timestamp
}

export interface CollectedObject {
  id: string;
  name: string;
  detectedAt: number;
  detectedFrom: string;    // 摄像头画面描述
  visualForm: string;      // 在 2D 世界中的形态: 'sticker', 'figurine', 'photo'
  placedRoomId: string;
  placedPosition: { x: number; y: number };
}

export interface MemoryAnchor {
  id: string;
  memoryUri: string;
  sessionId: string;
  artifactId: string;
  roomId: string;
  emotionalTag: string;
  spacetimeSnapshot: {
    dayPhase: DayPhase;
    weather: WeatherType;
    scheduleMode: ScheduleMode;
    location: string;
  };
}

interface SpacetimeContextValue {
  state: SpacetimeState;
  // actions
  setScheduleMode: (mode: ScheduleMode, nextChange?: number) => void;
  setEnvironment: (env: Partial<EnvironmentState>) => void;
  setCurrentActivity: (activity: CurrentActivity | null) => void;
  updateActivityProgress: (progress: number) => void;
  recordHighLoad: () => void;
  makeAutonomyDecision: (decision: string, durationSeconds?: number) => void;
  clearAutonomyDecision: () => void;
  addCollectedObject: (obj: Omit<CollectedObject, 'id'>) => void;
  addMemoryAnchor: (anchor: Omit<MemoryAnchor, 'id'>) => void;
  addReasoningNode: (chunk: string) => void;
  clearReasoningNodes: () => void;
  addSpatialMemory: (memory: Omit<SpatialMemory, 'id'>) => void;
  addObjectInventory: (obj: Omit<ObjectInventoryItem, 'id'>) => void;
  addUserDecoration: (dec: Omit<UserDecoration, 'id'>) => void;
  removeUserDecoration: (id: string) => void;
  setVisionPerception: (perception: VisionPerception | null) => void;
  // derived
  getRecommendedAction: () => { action: string; reason: string } | null;
}

// ===== 默认时间表（可配置）=====
const DEFAULT_SCHEDULE: ScheduleSlot[] = [
  { mode: 'sleep', startHour: 0, endHour: 7, label: '梦境模式' },
  { mode: 'work', startHour: 7, endHour: 12, label: '上午工作' },
  { mode: 'rest', startHour: 12, endHour: 13, label: '午间休息' },
  { mode: 'work', startHour: 13, endHour: 18, label: '下午工作' },
  { mode: 'break', startHour: 18, endHour: 20, label: '傍晚小憩' },
  { mode: 'work', startHour: 20, endHour: 22, label: '夜间工作' },
  { mode: 'rest', startHour: 22, endHour: 24, label: '睡前放松' },
];

// ===== 辅助函数 =====

function getDayPhase(date: Date): DayPhase {
  const h = date.getHours();
  if (h >= 5 && h < 11) return 'morning';
  if (h >= 11 && h < 17) return 'afternoon';
  if (h >= 17 && h < 20) return 'evening';
  return 'night';
}

function getScheduleMode(date: Date, schedule: ScheduleSlot[] = DEFAULT_SCHEDULE): ScheduleMode {
  const h = date.getHours();
  const m = date.getMinutes();
  const decimalHour = h + m / 60;
  for (const slot of schedule) {
    if (decimalHour >= slot.startHour && decimalHour < slot.endHour) {
      return slot.mode;
    }
  }
  // 跨天边界处理
  const firstSlot = schedule[0];
  if (firstSlot && decimalHour < firstSlot.startHour) {
    // 在第一个时段之前，取前一天的最后一个时段
    const lastSlot = schedule[schedule.length - 1];
    return lastSlot?.mode || 'rest';
  }
  return 'rest';
}

function getNextScheduleChange(date: Date, schedule: ScheduleSlot[] = DEFAULT_SCHEDULE): number {
  const h = date.getHours();
  const m = date.getMinutes();
  const decimalHour = h + m / 60;
  for (const slot of schedule) {
    if (decimalHour < slot.endHour) {
      const next = new Date(date);
      next.setHours(Math.floor(slot.endHour), (slot.endHour % 1) * 60, 0, 0);
      return next.getTime();
    }
  }
  // 已经是最后一个时段，取明天的第一个时段
  const tomorrow = new Date(date);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const firstSlot = schedule[0];
  if (firstSlot) {
    tomorrow.setHours(Math.floor(firstSlot.startHour), (firstSlot.startHour % 1) * 60, 0, 0);
  } else {
    tomorrow.setHours(9, 0, 0, 0);
  }
  return tomorrow.getTime();
}

function inferWeatherFromVision(detectedObjects: string[], brightness: number): WeatherType {
  // 简单的启发式推断
  if (detectedObjects.some(o => o.includes('umbrella') || o.includes('rain'))) return 'rain';
  if (detectedObjects.some(o => o.includes('snow'))) return 'snow';
  if (brightness < 0.3 && detectedObjects.some(o => o.includes('cloud'))) return 'cloudy';
  return 'clear';
}

// ===== 默认状态 =====

const defaultState: SpacetimeState = {
  scheduleMode: 'work',
  scheduleNextChange: Date.now() + 3600000,
  dayPhase: 'morning',
  currentTime: new Date(),
  environment: {
    brightness: 0.8,
    weather: 'clear',
    detectedScene: 'unknown',
    peopleCount: 0,
    keyObjects: [],
    temperature: null,
  },
  currentActivity: null,
  fatigue: 0,
  lastHighLoadAt: null,
  autonomyDecision: null,
  autonomyDecisionUntil: null,
  collectedObjects: [],
  memoryAnchors: [],
  cognitiveLabels: [],
  reasoningNodes: [],
  spatialMemory: [],
  objectInventory: [],
  userDecorations: [],
  visionPerception: null,
};

// ===== Context =====

const SpacetimeContext = createContext<SpacetimeContextValue>({
  state: defaultState,
  setScheduleMode: () => {},
  setEnvironment: () => {},
  setCurrentActivity: () => {},
  updateActivityProgress: () => {},
  recordHighLoad: () => {},
  makeAutonomyDecision: () => {},
  clearAutonomyDecision: () => {},
  addCollectedObject: () => {},
  addMemoryAnchor: () => {},
  addReasoningNode: () => {},
  clearReasoningNodes: () => {},
  addSpatialMemory: () => {},
  addObjectInventory: () => {},
  addUserDecoration: () => {},
  removeUserDecoration: () => {},
  setVisionPerception: () => {},
  getRecommendedAction: () => null,
});

export function SpacetimeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SpacetimeState>(() => {
    const now = new Date();
    const schedule = DEFAULT_SCHEDULE;
    return {
      ...defaultState,
      scheduleMode: getScheduleMode(now, schedule),
      scheduleNextChange: getNextScheduleChange(now, schedule),
      dayPhase: getDayPhase(now),
      currentTime: now,
    };
  });

  // 初始化时从后端加载持久化状态
  useEffect(() => {
    let mounted = true;
    (async () => {
      const [backendState, collectibles, anchors, spatialMem, objInv, decorations] = await Promise.all([
        loadSpacetimeState(),
        loadCollectibles(),
        loadMemoryAnchors(),
        loadSpatialMemory(),
        loadObjectInventory(),
        loadUserDecorations(),
      ]);
      if (!mounted) return;
      setState((prev) => ({
        ...prev,
        ...(backendState ? {
          scheduleMode: backendState.schedule_mode,
          scheduleNextChange: backendState.schedule_next_change,
          dayPhase: backendState.day_phase,
          environment: {
            ...prev.environment,
            brightness: backendState.environment.brightness,
            weather: backendState.environment.weather,
            detectedScene: backendState.environment.detected_scene,
            peopleCount: backendState.environment.people_count,
            keyObjects: backendState.environment.key_objects,
            temperature: backendState.environment.temperature,
          },
          currentActivity: backendState.current_activity ? {
            type: backendState.current_activity.type,
            target: backendState.current_activity.target,
            location: backendState.current_activity.location,
            progress: backendState.current_activity.progress,
            since: backendState.current_activity.since,
            sessionId: backendState.current_activity.session_id,
          } : null,
          fatigue: backendState.fatigue,
          lastHighLoadAt: backendState.last_high_load_at,
          autonomyDecision: backendState.autonomy_decision,
          autonomyDecisionUntil: backendState.autonomy_decision_until,
        } : {}),
        collectedObjects: collectibles.length > 0 ? collectibles.map(c => ({
          id: c.id,
          name: c.name,
          detectedAt: c.detected_at,
          detectedFrom: c.detected_from,
          visualForm: c.visual_form,
          placedRoomId: c.placed_room_id,
          placedPosition: c.placed_position,
        })) : prev.collectedObjects,
        memoryAnchors: anchors.length > 0 ? anchors.map(a => ({
          id: a.id,
          memoryUri: a.memory_uri,
          sessionId: a.session_id,
          artifactId: a.artifact_id,
          roomId: a.room_id,
          emotionalTag: a.emotional_tag,
          spacetimeSnapshot: {
            dayPhase: a.spacetime_snapshot.day_phase,
            weather: a.spacetime_snapshot.weather,
            scheduleMode: a.spacetime_snapshot.schedule_mode,
            location: a.spacetime_snapshot.location,
          },
        })) : prev.memoryAnchors,
        spatialMemory: spatialMem.length > 0 ? spatialMem.map(m => ({
          id: m.id,
          roomId: m.room_id,
          x: m.x,
          y: m.y,
          label: m.label,
          memoryType: m.memory_type,
          description: m.description,
          emotionalTag: m.emotional_tag,
          createdAt: m.created_at,
          accessCount: m.access_count,
        })) : prev.spatialMemory,
        objectInventory: objInv.length > 0 ? objInv.map(o => ({
          id: o.id,
          roomId: o.room_id,
          name: o.name,
          objectType: o.object_type,
          x: o.x,
          y: o.y,
          state: o.state,
          detectedAt: o.detected_at,
          detectedFrom: o.detected_from,
        })) : prev.objectInventory,
        userDecorations: decorations.length > 0 ? decorations.map(d => ({
          id: d.id,
          roomId: d.room_id,
          decorationType: d.decoration_type,
          name: d.name,
          position: { x: d.x, y: d.y },
          size: { w: d.size_w, h: d.size_h },
          color: d.color,
          createdAt: d.created_at,
        })) : prev.userDecorations,
      }));
    })();
    return () => { mounted = false; };
  }, []);

  const { state: aiState } = useAIState();
  const activityRef = useRef(state.currentActivity);
  const fatigueRef = useRef(state.fatigue);
  const lastHighLoadRef = useRef(state.lastHighLoadAt);
  const autonomyRef = useRef(state.autonomyDecision);

  // 缓存 aiState 到 ref，避免 effect 因 aiState.currentSentence 等高频字段频繁重建
  const aiStateRef = useRef(aiState);
  aiStateRef.current = aiState;

  // 保持 ref 同步
  useEffect(() => { activityRef.current = state.currentActivity; }, [state.currentActivity]);
  useEffect(() => { fatigueRef.current = state.fatigue; }, [state.fatigue]);
  useEffect(() => { lastHighLoadRef.current = state.lastHighLoadAt; }, [state.lastHighLoadAt]);
  useEffect(() => { autonomyRef.current = state.autonomyDecision; }, [state.autonomyDecision]);

  // ===== 1. 时间节律引擎（每分钟更新）=====
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setState((prev) => {
        const newMode = getScheduleMode(now, DEFAULT_SCHEDULE);
        const newPhase = getDayPhase(now);
        const nextChange = getNextScheduleChange(now, DEFAULT_SCHEDULE);
        return {
          ...prev,
          currentTime: now,
          scheduleMode: newMode,
          dayPhase: newPhase,
          scheduleNextChange: nextChange,
        };
      });
    };
    tick();
    const interval = setInterval(tick, 60000); // 每分钟检查一次
    return () => clearInterval(interval);
  }, []);

  // ===== 2. 从 AI 状态推导当前活动 =====
  // FIX: 依赖数组移除 aiState.currentSentence，该字段流式输出时高频变化导致 effect 过度执行
  // currentSentence 通过 ref 在 setState updater 中读取，保证 thinking 活动的 target 是最新的
  useEffect(() => {
    const { isThinking, emotion, systemPerception } = aiStateRef.current;
    const now = Date.now();

    setState((prev) => {
      let newActivity = prev.currentActivity;
      let newFatigue = prev.fatigue;
      let newLastHighLoad = prev.lastHighLoadAt;

      // 推理当前活动类型
      if (isThinking) {
        newActivity = {
          type: 'thinking',
          target: aiStateRef.current.currentSentence || '深度思考中',
          location: '书房·书桌',
          progress: prev.currentActivity?.type === 'thinking' ? prev.currentActivity.progress : 0,
          since: prev.currentActivity?.type === 'thinking' ? prev.currentActivity.since : now,
        };
      } else if (systemPerception.physicalTasks.length > 0) {
        const task = systemPerception.physicalTasks[0];
        newActivity = {
          type: 'monitoring',
          target: `${task.action} (${task.status})`,
          location: '客厅·控制台',
          progress: 0.5,
          since: prev.currentActivity?.type === 'monitoring' ? prev.currentActivity.since : now,
        };
      } else if (emotion === 'sleepy' || prev.scheduleMode === 'sleep') {
        newActivity = {
          type: 'dreaming',
          target: '记忆整合与梦境处理',
          location: '卧室·床',
          progress: 0,
          since: prev.currentActivity?.type === 'dreaming' ? prev.currentActivity.since : now,
        };
      } else if (prev.scheduleMode === 'work') {
        // 工作模式但没有具体任务 → 监控/待命
        newActivity = {
          type: 'idle',
          target: '等待指令',
          location: '书房·书桌',
          progress: 0,
          since: prev.currentActivity?.since || now,
        };
      } else if (prev.scheduleMode === 'rest' || prev.scheduleMode === 'break') {
        newActivity = {
          type: 'resting',
          target: '放松恢复',
          location: '客厅·沙发',
          progress: 0,
          since: prev.currentActivity?.type === 'resting' ? prev.currentActivity.since : now,
        };
      }

      // 疲劳度计算
      const highLoad = isThinking || systemPerception.taskLoad.totalRecent > 5;
      if (highLoad) {
        // 高负荷时疲劳累积：每分钟 +0.02
        newFatigue = Math.min(1, prev.fatigue + 0.02);
        newLastHighLoad = now;
      } else {
        // 低负荷时疲劳恢复：每分钟 -0.01
        newFatigue = Math.max(0, prev.fatigue - 0.01);
      }

      // 自主决策：疲劳过高时自动休息
      let newAutonomy = prev.autonomyDecision;
      let newAutonomyUntil = prev.autonomyDecisionUntil;
      if (newFatigue > 0.7 && !prev.autonomyDecision && prev.scheduleMode === 'work') {
        newAutonomy = '去沙发小憩一会儿';
        newAutonomyUntil = now + 300000; // 5 分钟
      } else if (prev.autonomyDecisionUntil && now > prev.autonomyDecisionUntil) {
        newAutonomy = null;
        newAutonomyUntil = null;
      }

      return {
        ...prev,
        currentActivity: newActivity,
        fatigue: newFatigue,
        lastHighLoadAt: newLastHighLoad,
        autonomyDecision: newAutonomy,
        autonomyDecisionUntil: newAutonomyUntil,
      };
    });
  }, [aiState.isThinking, aiState.emotion, aiState.systemPerception.physicalTasks.length, aiState.systemPerception.taskLoad.totalRecent]);

  // ===== 3. 从视觉感知推导环境 =====
  useEffect(() => {
    const { systemPerception } = aiState;
    const detectedObjects = systemPerception.detectedObjects || [];
    const userDetected = systemPerception.userDetected;

    // 亮度推断：基于 dayPhase + 是否有用户检测
    let brightness = 0.5;
    switch (state.dayPhase) {
      case 'morning': brightness = 0.7; break;
      case 'afternoon': brightness = 0.9; break;
      case 'evening': brightness = 0.5; break;
      case 'night': brightness = 0.2; break;
    }
    // 如果检测到室内灯光/屏幕，增加亮度
    if (detectedObjects.some(o => o.includes('lamp') || o.includes('screen'))) {
      brightness = Math.min(1, brightness + 0.2);
    }

    // 场景推断
    let scene = state.environment.detectedScene;
    if (detectedObjects.some(o => o.includes('desk') || o.includes('computer') || o.includes('chair'))) {
      scene = 'office';
    } else if (detectedObjects.some(o => o.includes('sofa') || o.includes('tv') || o.includes('bed'))) {
      scene = 'home';
    } else if (userDetected && detectedObjects.length > 3) {
      scene = 'home';
    }

    // 人数
    const peopleCount = userDetected ? Math.max(1, state.environment.peopleCount) : 0;

    // 天气推断
    const weather = inferWeatherFromVision(detectedObjects, brightness);

    setState((prev) => {
      const newObjects = detectedObjects.filter(
        obj => !prev.collectedObjects.some(c => c.name === obj)
      );

      let newCollectibles = prev.collectedObjects;
      if (newObjects.length > 0) {
        // 每次最多收集一个新物体
        const obj = newObjects[0];
        const id = `col_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
        // 根据物体类型决定视觉形态和放置位置
        let visualForm = 'sticker';
        let roomId = 'living_room';
        const name = obj.toLowerCase();
        if (name.includes('plant') || name.includes('flower') || name.includes('植物')) {
          visualForm = 'figurine';
          roomId = 'greenhouse';
        } else if (name.includes('cat') || name.includes('猫')) {
          visualForm = 'sticker';
          roomId = 'living_room';
        } else if (name.includes('coffee') || name.includes('cup') || name.includes('咖啡')) {
          visualForm = 'figurine';
          roomId = 'kitchen';
        } else if (name.includes('book') || name.includes('notebook') || name.includes('书')) {
          visualForm = 'figurine';
          roomId = 'library';
        } else if (name.includes('guitar') || name.includes('instrument') || name.includes('乐器')) {
          visualForm = 'figurine';
          roomId = 'living_room';
        } else if (name.includes('game') || name.includes('console') || name.includes('游戏')) {
          visualForm = 'figurine';
          roomId = 'living_room';
        } else if (name.includes('pillow') || name.includes('plush') || name.includes('玩偶') || name.includes('抱枕')) {
          visualForm = 'figurine';
          roomId = 'bedroom';
        } else if (name.includes('ball') || name.includes('sport') || name.includes('运动') || name.includes('球')) {
          visualForm = 'figurine';
          roomId = 'living_room';
        }
        const position = {
          x: 20 + Math.random() * 80,
          y: visualForm === 'sticker' ? 20 + Math.random() * 60 : 200 + Math.random() * 100,
        };
        newCollectibles = [
          ...prev.collectedObjects,
          {
            id,
            name: obj,
            detectedAt: Date.now(),
            detectedFrom: `摄像头检测到: ${obj}`,
            visualForm,
            placedRoomId: roomId,
            placedPosition: position,
          },
        ].slice(-50); // 上限 50，防止无界增长
      }

      // 认知地图标签生成（AI 自动标注空间功能）
      let newLabels = prev.cognitiveLabels.slice(-30); // 上限 30，防止无界增长
      const labelMap: Record<string, { label: string; type: CognitiveLabel['type'] }> = {
        sofa: { label: '休息区', type: 'rest' },
        bed: { label: '梦境港湾', type: 'rest' },
        desk: { label: '工作区', type: 'work' },
        computer: { label: '指挥中心', type: 'work' },
        coffee: { label: '能量补给站', type: 'energy' },
        plant: { label: '绿意角落', type: 'social' },
        bookshelf: { label: '知识殿堂', type: 'work' },
        console: { label: '指挥中心', type: 'work' },
        fireplace: { label: '温暖 hearth', type: 'rest' },
        guitar: { label: '灵感角落', type: 'social' },
        game: { label: '娱乐空间', type: 'social' },
      };
      for (const obj of detectedObjects) {
        const key = Object.keys(labelMap).find(k => obj.toLowerCase().includes(k));
        if (key && !prev.cognitiveLabels.some(l => l.label === labelMap[key].label)) {
          const cfg = labelMap[key];
          newLabels = [
            ...newLabels,
            {
              x: 50 + Math.random() * 200,
              y: 50 + Math.random() * 150,
              label: cfg.label,
              type: cfg.type,
              confidence: 0.5 + Math.random() * 0.5,
              discoveredAt: Date.now(),
            },
          ];
        }
      }

      return {
        ...prev,
        environment: {
          ...prev.environment,
          brightness,
          weather,
          detectedScene: scene,
          peopleCount,
          keyObjects: detectedObjects.slice(0, 5),
        },
        collectedObjects: newCollectibles,
        cognitiveLabels: newLabels,
      };
    });
  }, [aiState.systemPerception.detectedObjects, aiState.systemPerception.userDetected, state.dayPhase]);

  // ===== Actions =====

  const setScheduleMode = useCallback((mode: ScheduleMode, nextChange?: number) => {
    setState((prev) => ({
      ...prev,
      scheduleMode: mode,
      scheduleNextChange: nextChange || getNextScheduleChange(new Date(), DEFAULT_SCHEDULE),
    }));
  }, []);

  const setEnvironment = useCallback((env: Partial<EnvironmentState>) => {
    setState((prev) => ({
      ...prev,
      environment: { ...prev.environment, ...env },
    }));
  }, []);

  const setCurrentActivity = useCallback((activity: CurrentActivity | null) => {
    setState((prev) => ({ ...prev, currentActivity: activity }));
  }, []);

  const updateActivityProgress = useCallback((progress: number) => {
    setState((prev) => ({
      ...prev,
      currentActivity: prev.currentActivity
        ? { ...prev.currentActivity, progress: Math.max(0, Math.min(1, progress)) }
        : null,
    }));
  }, []);

  const recordHighLoad = useCallback(() => {
    setState((prev) => ({
      ...prev,
      lastHighLoadAt: Date.now(),
      fatigue: Math.min(1, prev.fatigue + 0.1),
    }));
  }, []);

  const makeAutonomyDecision = useCallback((decision: string, durationSeconds = 300) => {
    setState((prev) => ({
      ...prev,
      autonomyDecision: decision,
      autonomyDecisionUntil: Date.now() + durationSeconds * 1000,
    }));
  }, []);

  const clearAutonomyDecision = useCallback(() => {
    setState((prev) => ({
      ...prev,
      autonomyDecision: null,
      autonomyDecisionUntil: null,
    }));
  }, []);

  const addCollectedObject = useCallback((obj: Omit<CollectedObject, 'id'>) => {
    const id = `col_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setState((prev) => ({
      ...prev,
      collectedObjects: [...prev.collectedObjects, { ...obj, id }].slice(-50),
    }));
  }, []);

  const addMemoryAnchor = useCallback((anchor: Omit<MemoryAnchor, 'id'>) => {
    const id = `ma_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setState((prev) => ({
      ...prev,
      memoryAnchors: [...prev.memoryAnchors, { ...anchor, id }].slice(-50),
    }));
  }, []);

  const addReasoningNode = useCallback((chunk: string) => {
    setState((prev) => ({
      ...prev,
      reasoningNodes: [...prev.reasoningNodes, chunk].slice(-20),
    }));
  }, []);

  const clearReasoningNodes = useCallback(() => {
    setState((prev) => ({ ...prev, reasoningNodes: [] }));
  }, []);

  const addSpatialMemory = useCallback((memory: Omit<SpatialMemory, 'id'>) => {
    const id = `sm_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setState((prev) => ({
      ...prev,
      spatialMemory: [...prev.spatialMemory, { ...memory, id }].slice(-100),
    }));
  }, []);

  const addObjectInventory = useCallback((obj: Omit<ObjectInventoryItem, 'id'>) => {
    const id = `oi_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setState((prev) => ({
      ...prev,
      objectInventory: [...prev.objectInventory, { ...obj, id }].slice(-50),
    }));
  }, []);

  const addUserDecoration = useCallback((dec: Omit<UserDecoration, 'id'>) => {
    const id = `ud_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setState((prev) => ({
      ...prev,
      userDecorations: [...prev.userDecorations, { ...dec, id }].slice(-50),
    }));
  }, []);

  const removeUserDecoration = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      userDecorations: prev.userDecorations.filter(d => d.id !== id),
    }));
  }, []);

  const setVisionPerception = useCallback((perception: VisionPerception | null) => {
    setState((prev) => ({ ...prev, visionPerception: perception }));
  }, []);

  // ===== 推荐动作（供 RoomSystem 使用）=====
  const getRecommendedAction = useCallback((): { action: string; reason: string } | null => {
    const s = state;

    // P0: 自主决策优先
    if (s.autonomyDecision) {
      return { action: 'autonomy', reason: s.autonomyDecision };
    }

    // P1: 系统告警
    if (aiState.systemPerception.alertSeverity === 'critical') {
      return { action: 'alert', reason: '系统紧急告警' };
    }

    // P2: 物理任务
    if (aiState.systemPerception.physicalTasks.length > 0) {
      return { action: 'operate', reason: `执行物理任务: ${aiState.systemPerception.physicalTasks[0].action}` };
    }

    // P3: 深度思考
    if (aiState.isThinking) {
      return { action: 'think_deep', reason: s.fatigue > 0.5 ? '疲惫中思考' : '深度思考中' };
    }

    // P4: 梦境模式
    if (s.scheduleMode === 'sleep') {
      return { action: 'sleep', reason: '梦境模式：记忆整合' };
    }

    // P5: 休息模式
    if ((s.scheduleMode === 'rest' || s.scheduleMode === 'break') && s.fatigue > 0.3) {
      return { action: 'rest', reason: s.scheduleMode === 'rest' ? '午间休息' : '傍晚小憩' };
    }

    // P6: 用户在场
    if (aiState.systemPerception.userDetected) {
      return { action: 'commune', reason: '迎接用户' };
    }

    // P7: 工作模式待机
    if (s.scheduleMode === 'work') {
      return { action: 'monitor', reason: '工作模式：监控系统' };
    }

    return null;
  }, [state, aiState.systemPerception, aiState.isThinking]);

  return (
    <SpacetimeContext.Provider
      value={{
        state,
        setScheduleMode,
        setEnvironment,
        setCurrentActivity,
        updateActivityProgress,
        recordHighLoad,
        makeAutonomyDecision,
        clearAutonomyDecision,
        addCollectedObject,
        addMemoryAnchor,
        addReasoningNode,
        clearReasoningNodes,
        addSpatialMemory,
        addObjectInventory,
        addUserDecoration,
        removeUserDecoration,
        setVisionPerception,
        getRecommendedAction,
      }}
    >
      {children}
    </SpacetimeContext.Provider>
  );
}

export function useSpacetime() {
  return useContext(SpacetimeContext);
}
