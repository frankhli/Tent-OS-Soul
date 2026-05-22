/**
 * SystemEventBridge — 系统事件桥接
 * 将前端系统事件（tab切换、任务状态、代码错误等）转换为 Avatar 可理解的事件
 */

export type SystemEvent =
  | { type: 'tab_changed'; tab: string }
  | { type: 'user_typing_start' }
  | { type: 'user_idle'; seconds: number }
  | { type: 'task_started'; taskId: string }
  | { type: 'task_step'; step: number; total: number }
  | { type: 'task_success'; taskId: string }
  | { type: 'task_fail'; taskId: string; error: string }
  | { type: 'code_error'; message: string }
  | { type: 'code_success' }
  | { type: 'memory_praise'; content: string }
  | { type: 'memory_criticism'; content: string }
  // P0: 新增系统感知事件
  | { type: 'system_queue_overload'; depth: number }
  | { type: 'system_executor_offline'; count: number }
  | { type: 'system_error_spike'; rate: number }
  | { type: 'system_disk_full'; usage: number }
  | { type: 'system_all_clear' }
  | { type: 'physical_task_assigned'; taskId: string; provider: string; action: string; targetLocation: string }
  | { type: 'physical_task_executing'; taskId: string }
  | { type: 'physical_task_completed'; taskId: string }
  | { type: 'physical_fallback_triggered'; from: string; to: string }
  | { type: 'physical_circuit_open'; provider: string }
  | { type: 'vision_user_detected'; confidence: number }
  | { type: 'vision_user_emotion'; emotion: string; confidence: number }
  | { type: 'vision_object_detected'; objects: string[] }
  | { type: 'avatar_system_state'; health: unknown; physicalTasks: unknown[]; taskLoad: unknown };

export interface SystemEventState {
  events: SystemEvent[];
  lastEventTime: number;
  taskInProgress: boolean;
  currentTaskId: string | null;
  currentStep: number;
  totalSteps: number;
  // P0: 系统感知状态缓存
  systemHealth: 'healthy' | 'warning' | 'critical';
  activePhysicalTasks: number;
  lastPhysicalEvent: string | null;
  userDetected: boolean;
  userEmotion: string | null;
}

export function createSystemEventState(): SystemEventState {
  return {
    events: [],
    lastEventTime: 0,
    taskInProgress: false,
    currentTaskId: null,
    currentStep: 0,
    totalSteps: 0,
    systemHealth: 'healthy',
    activePhysicalTasks: 0,
    lastPhysicalEvent: null,
    userDetected: false,
    userEmotion: null,
  };
}

/** 添加系统事件 */
export function emitEvent(state: SystemEventState, event: SystemEvent): void {
  state.events.push(event);
  state.lastEventTime = performance.now();

  // 更新任务追踪
  if (event.type === 'task_started') {
    state.taskInProgress = true;
    state.currentTaskId = event.taskId;
    state.currentStep = 0;
    state.totalSteps = 0;
  }
  if (event.type === 'task_step') {
    state.currentStep = event.step;
    state.totalSteps = event.total;
  }
  if (event.type === 'task_success' || event.type === 'task_fail') {
    state.taskInProgress = false;
  }

  // P0: 更新系统感知状态
  if (event.type === 'system_queue_overload' || event.type === 'system_executor_offline' ||
      event.type === 'system_error_spike' || event.type === 'system_disk_full') {
    state.systemHealth = 'critical';
  }
  if (event.type === 'system_all_clear') {
    state.systemHealth = 'healthy';
  }
  if (event.type === 'physical_task_assigned' || event.type === 'physical_task_executing') {
    state.activePhysicalTasks++;
    state.lastPhysicalEvent = event.type;
  }
  if (event.type === 'physical_task_completed') {
    state.activePhysicalTasks = Math.max(0, state.activePhysicalTasks - 1);
    state.lastPhysicalEvent = event.type;
  }
  if (event.type === 'physical_fallback_triggered') {
    state.lastPhysicalEvent = 'fallback';
  }
  if (event.type === 'vision_user_detected') {
    state.userDetected = true;
  }
  if (event.type === 'vision_user_emotion') {
    state.userEmotion = event.emotion;
  }

  // 限制事件队列长度
  if (state.events.length > 20) {
    state.events.shift();
  }
}

/** 消费下一个事件 */
export function consumeNextEvent(state: SystemEventState): SystemEvent | null {
  return state.events.shift() || null;
}

/** 是否有未处理事件 */
export function hasPendingEvents(state: SystemEventState): boolean {
  return state.events.length > 0;
}

/** 事件 → Avatar 情绪/行为映射 */
export function eventToAvatarReaction(event: SystemEvent): {
  emotion: string;
  intensity: number;
  action: string;
  message: string;
} {
  switch (event.type) {
    case 'tab_changed':
      return { emotion: 'curious', intensity: 0.4, action: 'watch', message: '切换到新页面了？' };
    case 'user_typing_start':
      return { emotion: 'listening', intensity: 0.3, action: 'attention', message: '用户在输入...' };
    case 'user_idle':
      if (event.seconds > 300) {
        return { emotion: 'worried', intensity: 0.3, action: 'check', message: '还在吗？' };
      }
      return { emotion: 'calm', intensity: 0.2, action: 'idle', message: '' };
    case 'task_started':
      return { emotion: 'focused', intensity: 0.5, action: 'ready', message: '开始干活了！' };
    case 'task_step':
      return { emotion: 'focused', intensity: 0.3, action: 'watch', message: `进度 ${event.step}/${event.total}` };
    case 'task_success':
      return { emotion: 'happy', intensity: 0.8, action: 'celebrate', message: '任务完成！' };
    case 'task_fail':
      return { emotion: 'sad', intensity: 0.6, action: 'comfort', message: '没关系，再试一次' };
    case 'code_error':
      return { emotion: 'worried', intensity: 0.5, action: 'alert', message: '代码出错了...' };
    case 'code_success':
      return { emotion: 'happy', intensity: 0.5, action: 'thumbs_up', message: '代码跑通了！' };
    case 'memory_praise':
      return { emotion: 'happy', intensity: 0.7, action: 'blush', message: '被夸奖了~' };
    case 'memory_criticism':
      return { emotion: 'sad', intensity: 0.5, action: 'apologize', message: '我会改进的...' };
    // P0: 系统感知事件映射
    case 'system_queue_overload':
      return { emotion: 'worried', intensity: 0.8, action: 'alert', message: '任务队列堆积了！' };
    case 'system_executor_offline':
      return { emotion: 'worried', intensity: 0.9, action: 'alert', message: '执行者离线了！' };
    case 'system_error_spike':
      return { emotion: 'sad', intensity: 0.7, action: 'alert', message: '错误率飙升...' };
    case 'system_disk_full':
      return { emotion: 'worried', intensity: 0.6, action: 'alert', message: '磁盘满了' };
    case 'system_all_clear':
      return { emotion: 'happy', intensity: 0.5, action: 'thumbs_up', message: '系统恢复正常' };
    case 'physical_task_assigned':
      return { emotion: 'focused', intensity: 0.6, action: 'operate', message: '调度物理任务' };
    case 'physical_task_executing':
      return { emotion: 'focused', intensity: 0.5, action: 'operate', message: '执行中...' };
    case 'physical_task_completed':
      return { emotion: 'happy', intensity: 0.7, action: 'celebrate', message: '物理任务完成！' };
    case 'physical_fallback_triggered':
      return { emotion: 'confused', intensity: 0.6, action: 'alert', message: '自动降级中...' };
    case 'physical_circuit_open':
      return { emotion: 'sad', intensity: 0.7, action: 'alert', message: '熔断器打开了' };
    case 'vision_user_detected':
      return { emotion: 'curious', intensity: 0.4, action: 'watch', message: '看到你了' };
    case 'vision_user_emotion':
      return { emotion: 'listening', intensity: 0.3, action: 'attention', message: '察觉到你的情绪' };
    case 'vision_object_detected':
      return { emotion: 'curious', intensity: 0.3, action: 'watch', message: '发现了新东西' };
    default:
      return { emotion: 'neutral', intensity: 0, action: 'idle', message: '' };
  }
}

/** 从 WS 消息解析系统事件 */
export function parseWsMessage(msg: { type: string; payload?: unknown }): SystemEvent | null {
  const p = msg.payload as any;
  switch (msg.type) {
    case 'task.completed':
      return { type: 'task_success', taskId: p?.session_id || '' };
    case 'task.failed':
      return { type: 'task_fail', taskId: p?.session_id || '', error: p?.error || '' };
    case 'task.step':
      return { type: 'task_step', step: p?.step || 0, total: p?.total || 0 };
    case 'chat.message_accepted':
      return { type: 'task_started', taskId: p?.session_id || '' };
    // P0: 新增系统事件解析
    case 'system.health_alert':
      if (p?.metric === 'queue_depth') return { type: 'system_queue_overload', depth: p?.value || 0 };
      if (p?.metric === 'offline_executors') return { type: 'system_executor_offline', count: p?.value || 0 };
      if (p?.metric === 'error_rate') return { type: 'system_error_spike', rate: p?.value || 0 };
      if (p?.metric === 'disk_usage') return { type: 'system_disk_full', usage: p?.value || 0 };
      return { type: 'system_all_clear' };
    case 'physical.status_change':
      if (p?.event === 'task_assigned') return { type: 'physical_task_assigned', taskId: p?.task_id || '', provider: p?.provider || '', action: p?.action || '', targetLocation: p?.target_location || '' };
      if (p?.event === 'task_executing') return { type: 'physical_task_executing', taskId: p?.task_id || '' };
      if (p?.event === 'task_completed') return { type: 'physical_task_completed', taskId: p?.task_id || '' };
      if (p?.event === 'fallback_triggered') return { type: 'physical_fallback_triggered', from: p?.fallback_from || '', to: p?.fallback_to || '' };
      if (p?.event === 'circuit_open') return { type: 'physical_circuit_open', provider: p?.provider || '' };
      return null;
    case 'vision.perception':
      if (p?.event_type === 'user_emotion_detected') return { type: 'vision_user_emotion', emotion: p?.user_emotion || 'neutral', confidence: p?.confidence || 0 };
      if (p?.user_detected) return { type: 'vision_user_detected', confidence: p?.confidence || 0 };
      if (p?.detected_objects?.length > 0) return { type: 'vision_object_detected', objects: p?.detected_objects || [] };
      return null;
    case 'avatar.system_state':
      return { type: 'avatar_system_state', health: p?.health, physicalTasks: p?.physical_tasks || [], taskLoad: p?.task_load };
    default:
      return null;
  }
}
