// Tent OS Control UI 类型定义

export type ViewTab = 'dashboard' | 'chat' | 'tasks' | 'memory' | 'rules' | 'slo' | 'dreaming' | 'config' | 'logs' | 'skills' | 'assistant' | 'approvals' | 'cron' | 'physical' | 'emotion' | 'world' | 'memory_scene' | 'estate' | 'community';

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool' | 'monologue' | 'proactive';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  reasoning?: string;  // 思考过程（可折叠显示）
  explanation?: string; // 解释：为什么这样回应
  images?: string[];   // 多模态图片（base64 data URL）
  metadata?: {
    toolName?: string;
    toolParams?: Record<string, unknown>;
    toolResult?: unknown;
    plan?: PlanData;
  };
}

export interface PlanData {
  analysis: string;
  steps: PlanStep[];
}

export interface PlanStep {
  step: number;
  action: string;
  executor: string;
  status?: 'pending' | 'running' | 'completed' | 'failed';
  result?: unknown;
}

export interface TaskSession {
  sessionId: string;
  status: 'pending' | 'planning' | 'executing' | 'completed' | 'failed' | 'aborted';
  task: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export interface SystemHealth {
  status: 'ok' | 'degraded' | 'down';
  natsConnected: boolean;
  redisConnected: boolean;
  workers: {
    memory: boolean;
    governance: boolean;
    scheduler: boolean;
  };
  version: string;
}

export interface TaskSummary {
  session_id: string;
  status: string;
  task: string;
  created_at: string;
  updated_at: string;
}

export interface MemoryItem {
  id: string;
  content: string;
  source: string;
  timestamp: string;
  tier: 'working' | 'short_term' | 'long_term';
}

export interface ProceduralRule {
  id: number;
  pattern: string;
  action: string;
  category: string;
  confidence: number;
  verification_count: number;
  source: string;
  created_at: string;
}

export interface SLIData {
  metric_name: string;
  target: number;
  actual: number;
  status: 'ok' | 'warning' | 'breached';
  window_hours: number;
}

export interface ConfigItem {
  key: string;
  value: unknown;
  section: string;
}

// WebSocket 消息协议
export interface WSMessage {
  type: WSMessageType;
  payload: unknown;
  timestamp: number;
}

export type WSMessageType =
  | 'task.submit'
  | 'task.plan'
  | 'task.step'
  | 'task.result'
  | 'task.completed'
  | 'task.failed'
  | 'task.aborted'
  | 'task.abort'
  | 'chat.message'
  | 'chat.message_accepted'
  | 'chat.stream_chunk'
  | 'chat.stream_reasoning'
  | 'chat.completed'
  | 'chat.history'
  | 'chat.session.list'
  | 'chat.session.created'
  | 'approval.request'
  | 'system.health'
  | 'system.health_alert'
  | 'physical.status_change'
  | 'vision.perception'
  | 'vision.emotion_detected'
  | 'vision.blendshapes'
  | 'avatar.system_state'
  | 'ai.emotion'
  | 'ai.motion'
  | 'ai.speech'
  | 'emotion.update'
  | 'emotion.fused'
  | 'spacetime.autonomy'
  | 'community.message'
  | 'community.task_update'
  | 'voice.prosody'
  | 'ai.speech.segment'
  | 'ai.monologue'
  | 'avatar.pet'
  | 'persona.changed'
  | 'house.event'
  | 'avatar.state'
  | 'social.friend_request'
  | 'social.friend_accepted'
  | 'social.visit.request'
  | 'social.visit.accepted'
  | 'social.visit.rejected'
  | 'ping'
  | 'pong'
  | 'error';
