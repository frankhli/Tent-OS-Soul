import type { CognitiveLabel } from './Decorations';

export interface WorldRenderEffects {
  emotion?: string;
  alertSeverity?: string | null;
  isThinking?: boolean;
  userDetected?: boolean;
  levelUpFlash?: number; // 0-1，升级闪光强度
  roomUnlockFlash?: { roomId: string; intensity: number } | null;
  environment?: {
    brightness: number;
    weather: string | null;
  };
  currentActivity?: {
    type: string;
    target: string;
    progress: number;
  } | null;
  collectedObjects?: Array<{
    name: string;
    visualForm: string;
    placedRoomId: string;
    placedPosition: { x: number; y: number };
  }>;
  cognitiveLabels?: CognitiveLabel[];
  reasoningNodes?: string[];
  spatialMemory?: Array<{
    roomId: string;
    x: number;
    y: number;
    label: string;
    memoryType: string;
    emotionalTag: string | null;
  }>;
  userDecorations?: Array<{
    roomId: string;
    position: { x: number; y: number };
    size: { w: number; h: number };
    color: string;
    decorationType: string;
  }>;
}
