/**
 * WorldTypes — 2D 世界的核心类型定义
 * 坐标系层级：World → Room Local → Screen（通过 Camera 转换）
 */

// ===== 基础几何 =====
export interface Point {
  x: number;
  y: number;
}

export interface Size {
  w: number;
  h: number;
}

export interface Rect extends Point, Size {}

// ===== 相机 =====
export interface Camera {
  x: number;   // 世界坐标：相机左上角
  y: number;
  zoom: number; // 缩放倍数（0.5 ~ 2.0）
}

// ===== 房间 =====
export interface Room {
  id: string;
  name: string;
  nameZh: string;
  description: string;
  bounds: Rect;        // 世界坐标
  bgColor: string;
  wallColor: string;
  unlocked: boolean;
  unlockCondition?: UnlockCondition;
  furniture: Furniture[];
  artifacts: Artifact[];
  props?: Prop[];
}

export interface UnlockCondition {
  type: 'task_count' | 'task_category' | 'level';
  threshold: number;
  category?: string;
}

// ===== 家具 =====
export interface Furniture {
  id: string;
  type: FurnitureType;
  name: string;
  position: Point;      // 相对于房间左上角
  size: Size;
  color: string;
  strokeColor: string;
  shape: FurnitureShape;
  interactable: boolean;
  functions: FurnitureFunction[];
  avatarAnchor?: Point; // Avatar 使用此家具时的站立位置（相对于房间）
  zIndex: number;       // 渲染层级
}

export type FurnitureType =
  | 'sofa' | 'coffee_table' | 'window' | 'rug' | 'console'
  | 'desk' | 'lamp' | 'bookshelf' | 'globe'
  | 'workbench' | 'tool_rack' | 'blueprint_table'
  | 'reading_chair' | 'fireplace'
  | 'plant_shelf' | 'watering_can'
  | 'bed' | 'nightstand' | 'wardrobe'
  | 'memory_board' | 'emotional_corner';

export type FurnitureShape = 'rect' | 'rounded_rect' | 'ellipse' | 'custom';

export type FurnitureFunction =
  | 'rest'
  | 'work'
  | 'think'
  | 'monitor'
  | 'store'
  | 'display';

// ===== 智慧藏品（任务成果） =====
export interface Artifact {
  id: string;
  name: string;
  taskId: string;
  category: ArtifactCategory;
  position: Point;      // 相对于房间
  visualType: ArtifactVisual;
  createdAt: number;
  rarity: ArtifactRarity;
  description?: string;
}

export type ArtifactCategory = 'code' | 'writing' | 'design' | 'analysis' | 'creative';
export type ArtifactVisual = 'book' | 'crystal' | 'scroll' | 'gear' | 'plant' | 'painting';
export type ArtifactRarity = 'common' | 'rare' | 'epic' | 'legendary';

// ===== 可交互道具（机制一-3） =====
export interface Prop {
  id: string;
  type: PropType;
  name: string;
  roomId: string;
  position: Point;      // 相对于房间左上角
  size: Size;
  state: 'idle' | 'in_use' | 'used' | 'cooldown';  // 交互状态
  lastInteractedAt: number | null;
  interactCount: number;
  color: string;
  zIndex: number;
}

export type PropType = 'coffee_cup' | 'watering_can' | 'wall_clock';

export interface PropInteraction {
  propId: string;
  propType: PropType;
  action: string;
  timestamp: number;
  roomId: string;
}

// ===== Avatar 在世界中的状态 =====
export interface WorldAvatarState {
  roomId: string;
  position: Point;      // 世界坐标
  targetRoomId: string | null;
  targetFurnitureId: string | null;
  currentAction: string;
  facing: number;       // 1 = 右, -1 = 左
  isMoving: boolean;
}

// ===== 世界状态 =====
export interface UserDecoration {
  id: string;
  roomId: string;
  decorationType: string;
  name: string;
  position: Point;
  size: Size;
  color: string;
  createdAt: string;
}

export interface CommunityBuilding {
  id: string;
  name: string;
  nameZh: string;
  type: 'plaza' | 'market' | 'temple' | 'friend_home';
  bounds: Rect;
  bgColor: string;
  accentColor: string;
  icon: string; // emoji or symbol
  description: string;
}

export interface NeighborAvatar {
  id: string;
  name: string;
  position: Point;
  targetPosition: Point | null;
  emotion: string;
  isMoving: boolean;
  speed: number;
}

export interface VisualMemoryProp {
  id: string;
  name: string;
  visualType: ArtifactVisual;
  roomId: string;
  position: Point;
  description?: string;
  createdAt: number;
}

export interface WorldState {
  rooms: Room[];
  avatar: WorldAvatarState;
  camera: Camera;
  selectedRoomId: string | null;
  hoveredFurnitureId: string | null;
  hoveredArtifactId: string | null;
  hoveredPropId: string | null;
  hoveredBuildingId: string | null;
  timeOfDay: TimeOfDay;
  isDragging: boolean;
  dragStart: Point | null;
  cameraDragStart: Point | null;
  props: Prop[];
  userDecorations: UserDecoration[];
  communityBuildings: CommunityBuilding[];
  neighborAvatars: NeighborAvatar[];
  visualMemoryProps: VisualMemoryProp[];
  dreamEntries: string[];
  avatarTravelState: 'home' | 'travelling' | 'visiting' | 'returning' | null;
  avatarTravelTarget: string | null; // building id or resident id
  avatarTravelProgress: number; // 0-1
}

export type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night';

function createOfficeRoom(): Room {
  return {
    id: 'office',
    name: 'Office',
    nameZh: '办公室',
    description: '效率与协作的现代空间',
    bounds: { x: 1650, y: 560, w: 400, h: 400 },
    bgColor: '#F0F4F8',
    wallColor: '#E2E8F0',
    unlocked: true,
    furniture: [
      {
        id: 'office_desk',
        type: 'desk',
        name: '办公桌',
        position: { x: 80, y: 60 },
        size: { w: 240, h: 100 },
        color: '#607D8B',
        strokeColor: '#455A64',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['work', 'think'],
        avatarAnchor: { x: 200, y: 180 },
        zIndex: 10,
      },
      {
        id: 'office_lamp',
        type: 'lamp',
        name: '护眼台灯',
        position: { x: 90, y: 30 },
        size: { w: 30, h: 40 },
        color: '#CFD8DC',
        strokeColor: '#90A4AE',
        shape: 'custom',
        interactable: false,
        functions: [],
        zIndex: 15,
      },
      {
        id: 'filing_cabinet',
        type: 'bookshelf',
        name: '文件柜',
        position: { x: 320, y: 180 },
        size: { w: 60, h: 140 },
        color: '#78909C',
        strokeColor: '#546E7A',
        shape: 'rect',
        interactable: true,
        functions: ['store'],
        zIndex: 8,
      },
      {
        id: 'meeting_sofa',
        type: 'sofa',
        name: '会客沙发',
        position: { x: 40, y: 260 },
        size: { w: 160, h: 70 },
        color: '#90A4AE',
        strokeColor: '#78909C',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['rest', 'think'],
        avatarAnchor: { x: 120, y: 340 },
        zIndex: 10,
      },
      {
        id: 'office_window',
        type: 'window',
        name: '落地窗',
        position: { x: 180, y: 20 },
        size: { w: 140, h: 90 },
        color: '#B3E5FC',
        strokeColor: '#78909C',
        shape: 'rect',
        interactable: false,
        functions: [],
        zIndex: 1,
      },
      {
        id: 'office_plant',
        type: 'plant_shelf',
        name: '办公桌绿植',
        position: { x: 340, y: 60 },
        size: { w: 40, h: 50 },
        color: '#66BB6A',
        strokeColor: '#43A047',
        shape: 'rect',
        interactable: false,
        functions: ['display'],
        zIndex: 12,
      },
    ],
    artifacts: [],
  };
}

// ===== 系统状态 → 家具/动作映射 =====
export interface SystemActionMapping {
  action: string;
  targetFurnitureType: FurnitureType;
  emotion: string;
}

// ===== 常量 =====
export const WORLD_SIZE: Size = { w: 3200, h: 1100 };
export const HOME_SIZE: Size = { w: 1920, h: 1200 };
export const AVATAR_WORLD_SIZE = 60; // Avatar 在世界中的高度（像素）
export const ROOM_GAP = 40;
export const ROOM_RADIUS = 16;

// ===== 默认房间配置 =====
export function createDefaultRooms(): Room[] {
  return [
    createLivingRoom(),
    createStudyRoom(),
    createBedroomRoom(),
    createWorkshopRoom(),
    createLibraryRoom(),
    createGreenhouseRoom(),
    createOfficeRoom(),
  ];
}

function createLivingRoom(): Room {
  return {
    id: 'living_room',
    name: 'Living Room',
    nameZh: '客厅',
    description: 'AI 的客厅，温暖的起点',
    bounds: { x: 100, y: 100, w: 500, h: 400 },
    bgColor: '#F5F0EB',
    wallColor: '#EDE6DE',
    unlocked: true,
    furniture: [
      {
        id: 'sofa',
        type: 'sofa',
        name: '舒适沙发',
        position: { x: 50, y: 240 },
        size: { w: 200, h: 80 },
        color: '#E07A5F',
        strokeColor: '#C05640',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['rest', 'think'],
        avatarAnchor: { x: 150, y: 330 },
        zIndex: 10,
      },
      {
        id: 'coffee_table',
        type: 'coffee_table',
        name: '茶几',
        position: { x: 100, y: 160 },
        size: { w: 100, h: 60 },
        color: '#D4A574',
        strokeColor: '#B08A5E',
        shape: 'ellipse',
        interactable: true,
        functions: ['display'],
        zIndex: 5,
      },
      {
        id: 'window',
        type: 'window',
        name: '大窗户',
        position: { x: 200, y: 30 },
        size: { w: 120, h: 80 },
        color: '#BFDBFE',
        strokeColor: '#8B7355',
        shape: 'rect',
        interactable: false,
        functions: [],
        zIndex: 1,
      },
      {
        id: 'rug',
        type: 'rug',
        name: '地毯',
        position: { x: 80, y: 200 },
        size: { w: 260, h: 160 },
        color: '#E8DDD0',
        strokeColor: '#D4C4B0',
        shape: 'rounded_rect',
        interactable: false,
        functions: [],
        zIndex: 2,
      },
      {
        id: 'console',
        type: 'console',
        name: '系统控制台',
        position: { x: 320, y: 50 },
        size: { w: 140, h: 70 },
        color: '#374151',
        strokeColor: '#1F2937',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['monitor', 'work'],
        avatarAnchor: { x: 390, y: 140 },
        zIndex: 10,
      },
      // PRD D2.0: 家园中的可交互物品 — 实体化为家具
      {
        id: 'fridge_board',
        type: 'memory_board',
        name: '冰箱贴墙',
        position: { x: 10, y: 80 },
        size: { w: 55, h: 130 },
        color: '#F5F5F5',
        strokeColor: '#E0E0E0',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['display'],
        zIndex: 5,
      },
      {
        id: 'calendar_wall',
        type: 'memory_board',
        name: '日历墙',
        position: { x: 435, y: 80 },
        size: { w: 55, h: 130 },
        color: '#FFF8E1',
        strokeColor: '#FFD54F',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['display'],
        zIndex: 5,
      },
      {
        id: 'project_frame',
        type: 'memory_board',
        name: '项目画框',
        position: { x: 170, y: 15 },
        size: { w: 110, h: 75 },
        color: '#FFF3E0',
        strokeColor: '#FFB74D',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['display'],
        zIndex: 5,
      },
      {
        id: 'letter_rack',
        type: 'memory_board',
        name: '信件架',
        position: { x: 10, y: 270 },
        size: { w: 50, h: 80 },
        color: '#E8F5E9',
        strokeColor: '#A5D6A7',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['display'],
        zIndex: 5,
      },
    ],
    artifacts: [],
  };
}

function createStudyRoom(): Room {
  return {
    id: 'study',
    name: 'Study',
    nameZh: '书房',
    description: '知识的殿堂，思考的静所',
    bounds: { x: 660, y: 100, w: 400, h: 400 },
    bgColor: '#E8F0F5',
    wallColor: '#D8E5ED',
    unlocked: true,
    furniture: [
      {
        id: 'desk',
        type: 'desk',
        name: '实木书桌',
        position: { x: 100, y: 80 },
        size: { w: 220, h: 100 },
        color: '#5D4037',
        strokeColor: '#3E2723',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['work', 'think'],
        avatarAnchor: { x: 210, y: 200 },
        zIndex: 10,
      },
      {
        id: 'lamp',
        type: 'lamp',
        name: '阅读台灯',
        position: { x: 110, y: 50 },
        size: { w: 30, h: 40 },
        color: '#F59E0B',
        strokeColor: '#4B5563',
        shape: 'custom',
        interactable: false,
        functions: [],
        zIndex: 15,
      },
      {
        id: 'bookshelf',
        type: 'bookshelf',
        name: '书架',
        position: { x: 40, y: 200 },
        size: { w: 80, h: 180 },
        color: '#8B6F47',
        strokeColor: '#6B5337',
        shape: 'rect',
        interactable: true,
        functions: ['store'],
        zIndex: 8,
      },
      {
        id: 'globe',
        type: 'globe',
        name: '地球仪',
        position: { x: 200, y: 50 },
        size: { w: 35, h: 45 },
        color: '#3B82F6',
        strokeColor: '#1E40AF',
        shape: 'custom',
        interactable: false,
        functions: [],
        zIndex: 12,
      },
    ],
    artifacts: [],
  };
}

function createWorkshopRoom(): Room {
  return {
    id: 'workshop',
    name: 'Workshop',
    nameZh: '工坊',
    description: '创造与构建的空间',
    bounds: { x: 100, y: 560, w: 450, h: 400 },
    bgColor: '#ECECEC',
    wallColor: '#E0E0E0',
    unlocked: true,
    furniture: [
      {
        id: 'workbench',
        type: 'workbench',
        name: '工作台',
        position: { x: 80, y: 100 },
        size: { w: 250, h: 100 },
        color: '#78909C',
        strokeColor: '#546E7A',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['work'],
        avatarAnchor: { x: 205, y: 220 },
        zIndex: 10,
      },
      {
        id: 'tool_rack',
        type: 'tool_rack',
        name: '工具架',
        position: { x: 40, y: 240 },
        size: { w: 60, h: 120 },
        color: '#A1887F',
        strokeColor: '#8D6E63',
        shape: 'rect',
        interactable: true,
        functions: ['store'],
        zIndex: 8,
      },
    ],
    artifacts: [],
  };
}

function createLibraryRoom(): Room {
  return {
    id: 'library',
    name: 'Library',
    nameZh: '图书馆',
    description: '智慧的海洋',
    bounds: { x: 600, y: 560, w: 500, h: 450 },
    bgColor: '#F5F0E0',
    wallColor: '#EDE6D0',
    unlocked: true,
    furniture: [
      {
        id: 'reading_chair',
        type: 'reading_chair',
        name: '阅读椅',
        position: { x: 150, y: 200 },
        size: { w: 80, h: 90 },
        color: '#8D6E63',
        strokeColor: '#6D4C41',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['rest', 'think'],
        avatarAnchor: { x: 190, y: 310 },
        zIndex: 10,
      },
      {
        id: 'fireplace',
        type: 'fireplace',
        name: '壁炉',
        position: { x: 350, y: 40 },
        size: { w: 100, h: 80 },
        color: '#5D4037',
        strokeColor: '#3E2723',
        shape: 'rect',
        interactable: false,
        functions: [],
        zIndex: 5,
      },
    ],
    artifacts: [],
  };
}

function createBedroomRoom(): Room {
  return {
    id: 'bedroom',
    name: 'Bedroom',
    nameZh: '卧室',
    description: '梦境与休憩的港湾',
    bounds: { x: 1150, y: 560, w: 450, h: 400 },
    bgColor: '#EDE8F0',
    wallColor: '#E0DAE8',
    unlocked: true,
    furniture: [
      {
        id: 'bed',
        type: 'bed',
        name: '舒适大床',
        position: { x: 150, y: 80 },
        size: { w: 180, h: 220 },
        color: '#9FA8DA',
        strokeColor: '#7986CB',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['rest'],
        avatarAnchor: { x: 240, y: 200 },
        zIndex: 5,
      },
      {
        id: 'nightstand',
        type: 'nightstand',
        name: '床头柜',
        position: { x: 340, y: 120 },
        size: { w: 50, h: 50 },
        color: '#D7CCC8',
        strokeColor: '#A1887F',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['display'],
        zIndex: 8,
      },
      {
        id: 'window_bedroom',
        type: 'window',
        name: '卧室窗户',
        position: { x: 50, y: 20 },
        size: { w: 100, h: 70 },
        color: '#BFDBFE',
        strokeColor: '#8B7355',
        shape: 'rect',
        interactable: false,
        functions: [],
        zIndex: 1,
      },
      {
        id: 'wardrobe',
        type: 'wardrobe',
        name: '衣柜',
        position: { x: 30, y: 280 },
        size: { w: 100, h: 100 },
        color: '#8D6E63',
        strokeColor: '#6D4C41',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['store'],
        zIndex: 10,
      },
      {
        id: 'memory_board',
        type: 'memory_board',
        name: '记忆墙',
        position: { x: 200, y: 20 },
        size: { w: 200, h: 120 },
        color: '#F5F0E0',
        strokeColor: '#D4C4B0',
        shape: 'rect',
        interactable: true,
        functions: ['display'],
        zIndex: 5,
      },
      {
        id: 'emotional_corner',
        type: 'emotional_corner',
        name: '情绪角落',
        position: { x: 350, y: 250 },
        size: { w: 80, h: 80 },
        color: '#E8D5E0',
        strokeColor: '#C8A5C0',
        shape: 'rounded_rect',
        interactable: true,
        functions: ['rest'],
        zIndex: 5,
      },
    ],
    artifacts: [],
  };
}

function createGreenhouseRoom(): Room {
  return {
    id: 'greenhouse',
    name: 'Greenhouse',
    nameZh: '温室',
    description: '创意与灵感的花园',
    bounds: { x: 1150, y: 100, w: 400, h: 400 },
    bgColor: '#E8F5E9',
    wallColor: '#C8E6C9',
    unlocked: true,
    furniture: [
      {
        id: 'plant_shelf',
        type: 'plant_shelf',
        name: '植物架',
        position: { x: 50, y: 150 },
        size: { w: 120, h: 180 },
        color: '#66BB6A',
        strokeColor: '#43A047',
        shape: 'rect',
        interactable: true,
        functions: ['display', 'store'],
        zIndex: 8,
      },
      {
        id: 'watering_can',
        type: 'watering_can',
        name: '浇水壶',
        position: { x: 200, y: 280 },
        size: { w: 40, h: 35 },
        color: '#90A4AE',
        strokeColor: '#78909C',
        shape: 'custom',
        interactable: false,
        functions: [],
        zIndex: 12,
      },
    ],
    artifacts: [],
  };
}

// ===== 系统状态 → 家具/动作映射 =====
export const PROP_ACTION_MAP: Record<PropType, { action: string; emotion: string; duration: number }> = {
  coffee_cup: { action: 'drink_coffee', emotion: 'happy', duration: 5 },
  watering_can: { action: 'water_plant', emotion: 'calm', duration: 4 },
  wall_clock: { action: 'check_time', emotion: 'waiting', duration: 2 },
};

export const SYSTEM_ACTION_MAP: Record<string, { furnitureType: FurnitureType; action: string; emotion: string }> = {
  alert: { furnitureType: 'console', action: 'alert', emotion: 'worried' },
  operate: { furnitureType: 'desk', action: 'operate', emotion: 'focused' },
  think_deep: { furnitureType: 'sofa', action: 'think_deep', emotion: 'thinking' },
  monitor: { furnitureType: 'console', action: 'monitor', emotion: 'calm' },
  commune: { furnitureType: 'sofa', action: 'commune', emotion: 'happy' },
  celebrate: { furnitureType: 'rug', action: 'celebrate', emotion: 'excited' },
  sleep: { furnitureType: 'bed', action: 'sleep', emotion: 'sleepy' },
  dreaming: { furnitureType: 'bed', action: 'dreaming', emotion: 'sleepy' },
  idle: { furnitureType: 'rug', action: 'idle', emotion: 'neutral' },
};
