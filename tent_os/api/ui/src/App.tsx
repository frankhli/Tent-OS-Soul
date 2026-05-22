import { useState, useCallback, useEffect, useRef } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useToast } from '@/contexts/ToastContext';
import { useVision } from '@/hooks/useVision';
// import { useVoiceProsody } from '@/hooks/useVoiceProsody';
import { AIStateProvider, useAIState } from '@/contexts/AIStateContext';
import { SpacetimeProvider, useSpacetime } from '@/contexts/SpacetimeContext';
import { CommunityProvider, useCommunity } from '@/contexts/CommunityContext';
import { CommunityPanel } from '@/components/CommunityPanel';
import { Sidebar } from '@/components/Sidebar';

import { ChatPanel } from '@/components/ChatPanel';
import { TaskFlow } from '@/components/TaskFlow';
import { MemoryPanel } from '@/components/MemoryPanel';
import { RulesPanel } from '@/components/RulesPanel';
import { SLOPanel } from '@/components/SLOPanel';
import { DreamPanel } from '@/components/DreamPanel';
import { ConfigPanel } from '@/components/ConfigPanel';
import { LogsPanel } from '@/components/LogsPanel';
import { SkillsPanel } from '@/components/SkillsPanel';
import { AIAssistantPanel } from '@/components/AIAssistantPanel';
import { ApprovalPanel } from '@/components/ApprovalPanel';
import { CronPanel } from '@/components/CronPanel';
import { ApprovalDialog } from '@/components/ApprovalDialog';
import { VisionFloatingPanel } from '@/components/VisionFloatingPanel';
import { PhysicalWorldPanel } from '@/components/PhysicalWorldPanel';
import { EmotionTimelinePanel } from '@/components/EmotionTimelinePanel';
import { MemoryScenePanel } from '@/components/MemoryScenePanel';
import { Dashboard } from '@/components/Dashboard';
import { EstateDashboard } from '@/components/EstateDashboard';
import { WorldMapPanel } from '@/world/WorldMapPanel';
import { MiniWorldView } from '@/world/MiniWorldView';
import { GlobalAvatarFree } from '@/components/GlobalAvatarFree';
import { AvatarHomeProvider } from '@/contexts/AvatarHomeContext';
import { MessageSquare, LayoutDashboard, Bot, Home, MoreHorizontal, MapIcon, PanelRightClose } from 'lucide-react';
import { useIsMobile } from '@/hooks/useMediaQuery';
import type { ViewTab, TaskSession, WSMessage, WSMessageType, SystemHealth, ChatMessage } from '@/types';

const WS_URL = (() => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
})();

const LS_KEY = 'tent_os_sessions';
const LS_SIDEBAR = 'tent_os_sidebar_collapsed';
const LS_WORLD_PANEL = 'tent_os_world_panel_open';

function loadSessionsFromStorage(): Map<string, TaskSession> {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return new Map();
    const arr = JSON.parse(raw) as TaskSession[];
    return new Map(arr.map((s) => [s.sessionId, s]));
  } catch {
    return new Map();
  }
}

function saveSessionsToStorage(sessions: Map<string, TaskSession>) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(Array.from(sessions.values())));
  } catch {
    // ignore
  }
}

function AppInner() {
  const [activeTab, setActiveTab] = useState<ViewTab>('chat');
  const [sessions, setSessions] = useState<Map<string, TaskSession>>(loadSessionsFromStorage);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [streamingSessionId, setStreamingSessionId] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<{ session_id: string; plan: unknown } | null>(null);
  const [memorySceneSessionId, setMemorySceneSessionId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(LS_SIDEBAR) === 'true'; } catch { return false; }
  });
  const [worldPanelOpen, setWorldPanelOpen] = useState(() => {
    try {
      const saved = localStorage.getItem(LS_WORLD_PANEL);
      return saved === null ? true : saved === 'true';
    } catch { return true; }
  });
  const isMobile = useIsMobile();
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);
  const { showToast } = useToast();
  const { state: aiState, setEmotion, setPersona, setThinking, setUserEmotion, setFusedEmotion, setVitals, setCurrentSentence, setIsBeingPetted, setSystemPerception, setSendWs } = useAIState();
  const { setCurrentActivity, clearAutonomyDecision, addReasoningNode, clearReasoningNodes, makeAutonomyDecision, setVisionPerception } = useSpacetime();
  const { addMessage, addTask } = useCommunity();

  // FIX: 用 ref 缓存 aiState，避免 handleMessage 闭包捕获旧值导致 stale closure
  const aiStateRef = useRef(aiState);
  aiStateRef.current = aiState;

  // FIX: 初始加载时从后端持久化存储读取真实人格，避免硬编码 'work'
  useEffect(() => {
    const loadPersona = async () => {
      try {
        const res = await fetch('/ui/api/persona/mode');
        if (res.ok) {
          const data = await res.json();
          if (data.mode) {
            setPersona(data.mode);
          }
        }
      } catch {
        // ignore: fallback to default 'work'
      }
    };
    loadPersona();
  }, [setPersona]);

  // 持久化到 localStorage（5 秒防抖，避免每收到 WS 消息都序列化）
  useEffect(() => {
    const timer = setTimeout(() => {
      saveSessionsToStorage(sessions);
    }, 5000);
    return () => clearTimeout(timer);
  }, [sessions]);

  useEffect(() => {
    localStorage.setItem(LS_SIDEBAR, String(collapsed));
  }, [collapsed]);

  useEffect(() => {
    localStorage.setItem(LS_WORLD_PANEL, String(worldPanelOpen));
  }, [worldPanelOpen]);

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'system.health': {
        setHealth(msg.payload as SystemHealth);
        break;
      }

      case 'chat.session.list': {
        const { sessions: list } = msg.payload as { sessions: Array<{ session_id: string; title: string; updated_at: string; message_count: number }> };
        setSessions((prev) => {
          let changed = false;
          const next = new Map(prev);
          for (const item of list) {
            if (!next.has(item.session_id)) {
              changed = true;
              next.set(item.session_id, {
                sessionId: item.session_id,
                status: 'completed',
                task: item.title,
                messages: [],
                createdAt: Date.now(),
                updatedAt: Date.now(),
              });
            }
          }
          return changed ? next : prev;
        });
        break;
      }

      case 'chat.history': {
        const { session_id, messages: history } = msg.payload as {
          session_id: string;
          messages: Array<{ role: string; content: string; timestamp: string }>;
        };
        setSessions((prev) => {
          const s = prev.get(session_id);
          if (!s) return prev;
          const next = new Map(prev);
          next.set(session_id, {
            ...s,
            messages: history.map((m, i) => ({
              id: `hist-${session_id}-${i}`,
              role: m.role as ChatMessage['role'],
              content: m.content,
              images: (m as any).images,
              timestamp: new Date(m.timestamp).getTime() || Date.now(),
            })),
            updatedAt: Date.now(),
          });
          return next;
        });
        break;
      }

      case 'chat.message_accepted': {
        const { session_id } = msg.payload as { session_id: string };
        setStreamingSessionId(session_id);
        setThinking(true);
        setSessions((prev) => {
          const s = prev.get(session_id);
          if (!s || s.status === 'planning') return prev;
          const next = new Map(prev);
          next.set(session_id, {
            ...s,
            status: 'planning',
            updatedAt: Date.now(),
          });
          return next;
        });
        break;
      }

      case 'chat.stream_chunk': {
        const { session_id, chunk } = msg.payload as { session_id: string; chunk: string };
        setStreamingSessionId(session_id);
        setThinking(true);
        setCurrentActivity({
          type: 'chatting',
          target: '正在回复中...',
          location: '书房·书桌',
          progress: 0.5,
          since: Date.now(),
          sessionId: session_id,
        });
        setSessions((prev) => {
          const s = prev.get(session_id);
          if (!s) return prev;
          const next = new Map(prev);
          const lastMsg = s.messages[s.messages.length - 1];
          let newMessages;
          if (lastMsg && lastMsg.role === 'assistant' && lastMsg.id.startsWith('stream-')) {
            newMessages = s.messages.map((m, idx) =>
              idx === s.messages.length - 1 ? { ...m, content: m.content + chunk } : m
            );
          } else {
            newMessages = [
              ...s.messages,
              {
                id: `stream-${session_id}-${Date.now()}`,
                role: 'assistant' as ChatMessage['role'],
                content: chunk,
                timestamp: Date.now(),
              },
            ];
          }
          next.set(session_id, {
            ...s,
            messages: newMessages,
            status: 'executing',
            updatedAt: Date.now(),
          });
          return next;
        });
        break;
      }

      case 'chat.stream_reasoning': {
        const { session_id, chunk } = msg.payload as { session_id: string; chunk: string };
        if (chunk && chunk.trim()) {
          addReasoningNode(chunk.trim());
        }
        setStreamingSessionId(session_id);
        setSessions((prev) => {
          const s = prev.get(session_id);
          if (!s) return prev;
          const next = new Map(prev);
          const lastMsg = s.messages[s.messages.length - 1];
          let newMessages;
          if (lastMsg && lastMsg.role === 'assistant' && lastMsg.id.startsWith('stream-')) {
            newMessages = s.messages.map((m, idx) =>
              idx === s.messages.length - 1
                ? { ...m, reasoning: (m.reasoning || '') + chunk }
                : m
            );
          } else {
            newMessages = [
              ...s.messages,
              {
                id: `stream-${session_id}-${Date.now()}`,
                role: 'assistant' as ChatMessage['role'],
                content: '',
                reasoning: chunk,
                timestamp: Date.now(),
              },
            ];
          }
          next.set(session_id, {
            ...s,
            messages: newMessages,
            status: 'planning',
            updatedAt: Date.now(),
          });
          return next;
        });
        break;
      }

      case 'ai.monologue': {
        const payload = msg.payload as { session_id?: string; chunk?: string; done?: boolean };
        const sid = payload.session_id || 'default';
        setSessions((prev) => {
          const s = prev.get(sid);
          if (!s) return prev;
          const next = new Map(prev);
          const lastMsg = s.messages[s.messages.length - 1];
          let newMessages;
          if (lastMsg && lastMsg.role === 'monologue' && lastMsg.id.startsWith('mono-')) {
            newMessages = s.messages.map((m, idx) =>
              idx === s.messages.length - 1
                ? { ...m, content: m.content + (payload.chunk || '') }
                : m
            );
          } else {
            newMessages = [
              ...s.messages,
              {
                id: `mono-${sid}-${Date.now()}`,
                role: 'monologue' as ChatMessage['role'],
                content: payload.chunk || '',
                timestamp: Date.now(),
              },
            ];
          }
          next.set(sid, { ...s, messages: newMessages, updatedAt: Date.now() });
          return next;
        });
        break;
      }

      case 'chat.completed':
      case 'task.completed': {
        clearReasoningNodes();
        const payload = msg.payload as {
          session_id: string;
          content?: string;
          result?: string;
          source?: string;
          proactive_type?: string;
          explanation?: string;
        };
        const { session_id, content, result, source, explanation } = payload;
        const text = content || result || '';
        const isProactive = source === 'proactive';
        setStreamingSessionId(null);
        setThinking(false);
        // 回复完成后，保持 chatting 状态 3 秒，然后清除
        setCurrentActivity({
          type: 'chatting',
          target: '回复完成',
          location: '书房·书桌',
          progress: 1,
          since: Date.now(),
          sessionId: session_id,
        });
        setTimeout(() => {
          setCurrentActivity(null);
        }, 3000);
        setSessions((prev) => {
          const next = new Map(prev);
          const s = next.get(session_id);
          if (s) {
            const lastMsg = s.messages[s.messages.length - 1];
            let newMessages;
            if (lastMsg && (lastMsg.role === 'assistant' || lastMsg.role === 'proactive') && lastMsg.id.startsWith('stream-')) {
              newMessages = s.messages.map((m, idx) =>
                idx === s.messages.length - 1
                  ? {
                      ...m,
                      id: `final-${session_id}-${Date.now()}`,
                      content: text || m.content || '',
                      role: (isProactive ? 'proactive' : m.role) as ChatMessage['role'],
                      explanation: explanation || m.explanation,
                    }
                  : m
              );
            } else {
              newMessages = [
                ...s.messages,
                {
                  id: `final-${session_id}-${Date.now()}`,
                  role: (isProactive ? 'proactive' : 'assistant') as ChatMessage['role'],
                  content: text || '',
                  explanation: explanation,
                  timestamp: Date.now(),
                },
              ];
            }
            next.set(session_id, {
              ...s,
              messages: newMessages,
              status: 'completed',
              updatedAt: Date.now(),
            });
          }
          return next;
        });
        // 信件架：任务完成信件
        fetch('/ui/api/world/letter-rack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            type: 'task_completed',
            title: '任务完成',
            content: `任务「${text.slice(0, 60)}」已完成`,
          }),
        }).catch(() => {});
        break;
      }

      case 'task.aborted': {
        const { session_id } = msg.payload as { session_id: string };
        setStreamingSessionId(null);
        setThinking(false);
        setSessions((prev) => {
          const s = prev.get(session_id);
          if (!s) return prev;
          const next = new Map(prev);
          next.set(session_id, {
            ...s,
            status: 'aborted',
            messages: [
              ...s.messages,
              {
                id: `aborted-${Date.now()}`,
                role: 'system',
                content: '任务已中止',
                timestamp: Date.now(),
              },
            ],
            updatedAt: Date.now(),
          });
          return next;
        });
        break;
      }

      case 'task.plan': {
        const { session_id, plan } = msg.payload as { session_id: string; plan: unknown };
        setSessions((prev) => {
          const s = prev.get(session_id);
          if (!s) return prev;
          const next = new Map(prev);
          next.set(session_id, {
            ...s,
            status: 'executing',
            messages: [
              ...s.messages,
              {
                id: `plan-${Date.now()}`,
                role: 'system',
                content: `正在执行计划...`,
                timestamp: Date.now(),
                metadata: { plan: plan as never },
              },
            ],
            updatedAt: Date.now(),
          });
          return next;
        });
        break;
      }

      case 'task.step': {
        const { session_id, step, action, status } = msg.payload as {
          session_id: string;
          step: number;
          action: string;
          status: string;
        };
        setSessions((prev) => {
          const s = prev.get(session_id);
          if (!s) return prev;
          const next = new Map(prev);
          next.set(session_id, {
            ...s,
            messages: [
              ...s.messages,
              {
                id: `step-${Date.now()}`,
                role: 'tool',
                content: `Step ${step}: ${action} (${status})`,
                timestamp: Date.now(),
              },
            ],
            updatedAt: Date.now(),
          });
          return next;
        });
        break;
      }

      case 'task.failed': {
        clearReasoningNodes();
        const { session_id, error } = msg.payload as { session_id: string; error: string };
        setStreamingSessionId(null);
        setThinking(false);
        setSessions((prev) => {
          const s = prev.get(session_id);
          if (!s) return prev;
          const next = new Map(prev);
          next.set(session_id, {
            ...s,
            status: 'failed',
            messages: [
              ...s.messages,
              {
                id: `error-${Date.now()}`,
                role: 'system',
                content: `Error: ${error}`,
                timestamp: Date.now(),
              },
            ],
            updatedAt: Date.now(),
          });
          return next;
        });
        // 信件架：任务失败信件
        fetch('/ui/api/world/letter-rack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            type: 'task_failed',
            title: '任务失败',
            content: `任务失败: ${error?.slice(0, 120) || '未知错误'}`,
          }),
        }).catch(() => {});
        break;
      }

      case 'approval.request': {
        const { session_id, plan } = msg.payload as { session_id: string; plan: unknown };
        setPendingApproval({ session_id, plan });
        break;
      }

      case 'spacetime.autonomy': {
        const payload = msg.payload as { decision: string; reason: string; suggested_action: string };
        if (payload.decision) {
          makeAutonomyDecision(payload.decision, 300);
        }
        break;
      }

      case 'ai.emotion':
      case 'emotion.update': {
        const payload = msg.payload as { emotion?: string; score?: number; confidence?: number; persona?: string; user_emotion?: string };
        if (payload.emotion) {
          setEmotion(payload.emotion);
        }
        if (payload.persona) {
          setPersona(payload.persona);
        }
        if (payload.user_emotion) {
          setUserEmotion(payload.user_emotion);
        }
        break;
      }

      case 'emotion.fused': {
        const payload = msg.payload as {
          primary?: string;
          intensity?: number;
          valence?: number;
          arousal?: number;
          mixed?: Record<string, number>;
          trend?: string;
          authenticity?: number;
        };
        if (payload.primary) {
          setFusedEmotion({
            primary: payload.primary,
            intensity: payload.intensity ?? 0,
            valence: payload.valence ?? 0,
            mixed: payload.mixed ?? {},
            trend: payload.trend ?? 'stable',
            authenticity: payload.authenticity ?? 0.5,
          });
          // 同时更新用户情绪显示
          setUserEmotion(payload.primary);
          // Phase 3: 计算生命体征
          const arousal = payload.arousal ?? 0.3;
          const intensity = payload.intensity ?? 0;
          setVitals({
            heartRate: Math.round(60 + arousal * 60 + intensity * 20),
            breathRate: Math.round(12 + arousal * 12 + intensity * 8),
            intensity: intensity,
          });
        }
        break;
      }

      case 'ai.speech.segment': {
        const payload = msg.payload as { sentence?: string; index?: number };
        if (payload.sentence) {
          setCurrentSentence(payload.sentence);
        }
        break;
      }

      case 'avatar.pet': {
        setIsBeingPetted(true);
        setEmotion('happy');
        setTimeout(() => setIsBeingPetted(false), 3000);
        break;
      }

      case 'persona.changed': {
        const payload = msg.payload as { mode?: string };
        if (payload.mode) {
          setPersona(payload.mode);
        }
        break;
      }

      // P0: 系统健康告警
      case 'system.health_alert': {
        const payload = msg.payload as { alert_type?: string; severity?: string; metric?: string; value?: number; message?: string };
        const latestPerception = aiStateRef.current.systemPerception;
        setSystemPerception({
          ...latestPerception,
          lastAlert: payload.alert_type || payload.metric || null,
          alertSeverity: payload.severity === 'critical' ? 'critical' : 'warning',
        });
        // 信件架：系统告警信件
        fetch('/ui/api/world/letter-rack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            type: 'system_alert',
            title: `系统告警: ${payload.alert_type || payload.metric || '未知'}`,
            content: payload.message || `严重程度: ${payload.severity || 'warning'}`,
          }),
        }).catch(() => {});
        break;
      }

      // P0: 物理执行状态变化
      case 'physical.status_change': {
        const payload = msg.payload as {
          task_id?: string; status?: string; provider?: string; action?: string;
          target_location?: string; event?: string; fallback_from?: string; fallback_to?: string;
        };
        const latestPerception2 = aiStateRef.current.systemPerception;
        const currentTasks = latestPerception2.physicalTasks;
        let newTasks = [...currentTasks];
        if (payload.event === 'task_assigned') {
          newTasks.push({
            taskId: payload.task_id || '',
            status: payload.status || 'assigned',
            provider: payload.provider || '',
            action: payload.action || '',
            targetLocation: payload.target_location || '',
          });
        } else if (payload.event === 'task_completed' || payload.event === 'task_failed') {
          newTasks = newTasks.filter(t => t.taskId !== payload.task_id);
        }
        setSystemPerception({
          ...latestPerception2,
          physicalTasks: newTasks,
        });
        break;
      }

      // P0: 社区消息实时推送
      case 'community.message': {
        const payload = msg.payload as { id?: number; sender_id?: string; sender_name?: string; avatar?: string; content?: string; channel?: string; created_at?: string; from_ai_id?: string; to_ai_id?: string; message_type?: string; timestamp?: string; auto_generated?: boolean };
        if (payload.content) {
          // 添加到 CommunityContext
          addMessage({
            id: payload.id || Date.now(),
            from_ai_id: payload.sender_id || payload.from_ai_id || 'unknown',
            to_ai_id: payload.channel || 'plaza',
            content: payload.content,
            message_type: payload.message_type || 'chat',
            created_at: payload.created_at || payload.timestamp || new Date().toISOString(),
          });
          // 如果消息是发给当前用户的，显示 toast 通知
          const fromName = payload.sender_name || payload.from_ai_id || '未知';
          if (payload.to_ai_id === 'web_user' || payload.to_ai_id === 'frank') {
            showToast(`💬 ${fromName}: ${payload.content.slice(0, 40)}${payload.content.length > 40 ? '...' : ''}`, 'info');
          }
        }
        break;
      }

      // P0: 社区任务更新实时推送
      case 'community.task_update': {
        const payload = msg.payload as { task_id?: string; status?: string; progress?: number; agent_id?: string; agent_name?: string; message?: string };
        const agentName = payload.agent_name || payload.agent_id || 'AI Agent';
        const progress = payload.progress ?? 0;
        const progressBar = progress > 0 ? ` [${'█'.repeat(Math.round(progress / 10))}${'░'.repeat(10 - Math.round(progress / 10))}] ${Math.round(progress)}%` : '';
        showToast(
          `📋 ${agentName}: ${payload.message || `任务 ${payload.status}`}${progressBar}`,
          payload.status === 'completed' ? 'success' : payload.status === 'failed' ? 'error' : 'info'
        );
        if (payload.task_id) {
          addTask({
            id: parseInt(payload.task_id, 10) || Date.now(),
            title: payload.message || payload.task_id || '未命名任务',
            description: null,
            publisher_ai_id: payload.agent_id || '',
            assignee_ai_id: payload.agent_id || null,
            status: payload.status || 'pending',
            reward_cp: 0,
            deadline: null,
            difficulty: 1,
            result: null,
            created_at: new Date().toISOString(),
            completed_at: payload.status === 'completed' ? new Date().toISOString() : null,
          } as any);
        }
        break;
      }

      // P0: 视觉感知（FaceLandmarker 实时检测）
      case 'vision.perception': {
        const payload = msg.payload as {
          event_type?: string; user_detected?: boolean; user_emotion?: string;
          detected_objects?: string[]; confidence?: number;
          room_id?: string; scene_type?: string; scene_description?: string;
          objects?: Array<{name: string; location: string; confidence: number}>;
          people_count?: number; lighting?: string; mood?: string; timestamp?: string;
        };
        // 1. 更新 systemPerception（实时情绪/在场检测）
        if (payload.user_detected !== undefined || payload.detected_objects !== undefined) {
          const latestSp = aiStateRef.current.systemPerception;
          setSystemPerception({
            ...latestSp,
            userDetected: payload.user_detected || false,
            userEmotion: payload.user_emotion || null,
            detectedObjects: payload.detected_objects || [],
          });
        }
        // 2. 更新 visionPerception（VLM 场景分析）
        if (payload.scene_type !== undefined || payload.scene_description !== undefined) {
          setVisionPerception({
            roomId: payload.room_id || 'unknown',
            sceneType: payload.scene_type || 'unknown',
            sceneDescription: payload.scene_description || '',
            objects: payload.objects || [],
            peopleCount: payload.people_count ?? 0,
            lighting: payload.lighting || 'unknown',
            mood: payload.mood || 'neutral',
            timestamp: payload.timestamp || new Date().toISOString(),
          });
        }
        break;
      }

      // P0: Avatar 系统状态定期广播
      case 'avatar.system_state': {
        const payload = msg.payload as {
          health?: SystemHealth; physical_tasks?: unknown[]; task_load?: { total_recent?: number; completed_recent?: number; failed_recent?: number };
        };
        setHealth(payload.health || null);
        setSystemPerception({
          ...aiState.systemPerception,
          health: payload.health || aiState.systemPerception.health,
          physicalTasks: (payload.physical_tasks as any[])?.map(t => ({
            taskId: t.task_id || '',
            status: t.status || '',
            provider: t.provider || '',
            action: t.action || '',
            targetLocation: t.target_location || '',
          })) || aiState.systemPerception.physicalTasks,
          taskLoad: {
            totalRecent: payload.task_load?.total_recent || 0,
            completedRecent: payload.task_load?.completed_recent || 0,
            failedRecent: payload.task_load?.failed_recent || 0,
          },
        });
        break;
      }

      // Phase 1.5: 家园事件实时推送
      case 'house.event': {
        const payload = msg.payload as { event?: string; item_type?: string; item_id?: string; data?: unknown; source?: string };
        // 家园事件通过 Toast 通知用户
        if (payload.event) {
          const eventLabels: Record<string, string> = {
            'fridge_note_added': '📝 新冰箱贴',
            'calendar_event_added': '📅 新日程',
            'letter_received': '✉️ 新信件',
            'project_frame_added': '🎨 新项目画像',
            'weather_changed': '🌤️ 天气变化',
            'visitor_arrived': '🏠 有访客',
          };
          const label = eventLabels[payload.event] || '🏠 家园更新';
          const detail = payload.data && typeof payload.data === 'object' && 'content' in payload.data
            ? String((payload.data as any).content).slice(0, 40)
            : '';
          showToast(`${label}${detail ? ': ' + detail : ''}`, 'info');
        }
        break;
      }

      case 'social.friend_request': {
        const payload = msg.payload as { from_ai_id?: string; to_ai_id?: string; timestamp?: string };
        if (payload.from_ai_id) {
          showToast(`🤝 收到好友申请：${payload.from_ai_id}`, 'info');
        }
        break;
      }

      case 'social.friend_accepted': {
        const payload = msg.payload as { from_ai_id?: string; to_ai_id?: string; friendship_id?: number; timestamp?: string };
        if (payload.from_ai_id) {
          showToast(`✅ ${payload.from_ai_id} 接受了你的好友申请！`, 'success');
        }
        break;
      }

      case 'social.visit.request': {
        const payload = msg.payload as { from_ai_id?: string; to_ai_id?: string; timestamp?: string };
        if (payload.from_ai_id) {
          showToast(`🏠 ${payload.from_ai_id} 想串门拜访你！`, 'info');
        }
        break;
      }

      case 'social.visit.accepted': {
        const payload = msg.payload as { visit_id?: string; to_ai_id?: string; timestamp?: string };
        if (payload.to_ai_id) {
          showToast(`🚪 串门请求已被接受！`, 'success');
        }
        break;
      }

      case 'social.visit.rejected': {
        const payload = msg.payload as { visit_id?: string; to_ai_id?: string; timestamp?: string };
        if (payload.to_ai_id) {
          showToast(`🚫 串门请求被拒绝`, 'info');
        }
        break;
      }

      case 'pong': {
        break;
      }

      default:
        break;
    }
  }, []);

  const { send } = useWebSocket({
    url: WS_URL,
    onMessage: handleMessage,
    onOpen: () => {
      setConnectionStatus('connected');
      send('chat.session.list', { user_id: 'web_user' });
    },
    onClose: () => setConnectionStatus('disconnected'),
  });

  // 将 send 函数注入全局状态，供 useVoice 等使用
  useEffect(() => {
    setSendWs(send as (type: string, payload: unknown) => void);
  }, [send, setSendWs]);

  // Vision: camera + face detection + YOLO (app-level so it's visible across all tabs)
  const vision = useVision(
    (type: string, payload: unknown) => send(type as WSMessageType, payload),
    'web_user'
  );

  // Phase 1: 语音韵律分析 — 已禁用（零用户可见价值，持续占用麦克风和 CPU）
  // const { start: startProsody, stop: stopProsody } = useVoiceProsody();
  // useEffect(() => {
  //   if (connectionStatus === 'connected') { startProsody(); } else { stopProsody(); }
  //   return () => { stopProsody(); };
  // }, [connectionStatus, startProsody, stopProsody]);

  const handleSendMessage = useCallback((text: string, images?: string[]) => {
    if ((!text.trim() && !images?.length) || connectionStatus !== 'connected') return;

    // 用户发送消息 → Avatar 进入交流状态
    setCurrentActivity({
      type: 'chatting',
      target: text.slice(0, 20) || '图片消息',
      location: '书房·书桌',
      progress: 0,
      since: Date.now(),
    });
    clearAutonomyDecision();

    let targetSessionId = activeSessionId;
    if (!targetSessionId) {
      targetSessionId = `ws_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      const newSession: TaskSession = {
        sessionId: targetSessionId,
        status: 'pending',
        task: text || '图片消息',
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };
      setSessions((prev) => {
        const next = new Map(prev);
        next.set(targetSessionId!, newSession);
        return next;
      });
      setActiveSessionId(targetSessionId);
    }

    setSessions((prev) => {
      const s = prev.get(targetSessionId!);
      if (!s) return prev;
      const next = new Map(prev);
      next.set(targetSessionId!, {
        ...s,
        messages: [
          ...s.messages,
          {
            id: `user-${Date.now()}`,
            role: 'user',
            content: text,
            images: images,
            timestamp: Date.now(),
          },
        ],
        task: text || '图片消息',
        updatedAt: Date.now(),
      });
      return next;
    });

    const payload: Record<string, unknown> = {
      session_id: targetSessionId,
      content: text,
      user_id: 'web_user',
    };
    if (images && images.length > 0) {
      payload.images = images;
    }
    send('chat.message', payload);
  }, [activeSessionId, connectionStatus, send]);

  const handleSelectSession = useCallback((id: string) => {
    if (!id) {
      setActiveSessionId(null);
      return;
    }
    setActiveSessionId(id);
    send('chat.history', { session_id: id });
  }, [send]);

  const handleAbortTask = useCallback((sessionId: string) => {
    try {
      send('task.abort' as never, { session_id: sessionId });
      setSessions((prev) => {
        const s = prev.get(sessionId);
        if (!s) return prev;
        const next = new Map(prev);
        next.set(sessionId, {
          ...s,
          status: 'aborted',
          messages: [
            ...s.messages,
            {
              id: `aborting-${Date.now()}`,
              role: 'system',
              content: '⏳ 正在中止任务...',
              timestamp: Date.now(),
            },
          ],
          updatedAt: Date.now(),
        });
        return next;
      });
    } catch (e) {
      showToast('中止任务失败，请检查连接', 'error');
    }
  }, [send, showToast]);

  const handleFeedback = useCallback(async (
    sessionId: string,
    _messageIndex: number,
    type: 'like' | 'dislike' | 'correct',
    correction?: string
  ) => {
    try {
      const resp = await fetch(`/api/v1/sessions/${sessionId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, correction }),
      });
      if (resp.ok) {
        showToast('反馈已提交，感谢！', 'success');
      } else {
        const err = await resp.json().catch(() => ({}));
        showToast(err.detail || '反馈提交失败', 'error');
      }
    } catch (e) {
      showToast('反馈提交失败，请检查网络', 'error');
    }
  }, [showToast]);

  const handleEditMessage = useCallback((sessionId: string, messageIndex: number, newContent: string) => {
    setSessions((prev) => {
      const s = prev.get(sessionId);
      if (!s) return prev;
      const next = new Map(prev);
      const keptMessages = s.messages.slice(0, messageIndex);
      const editedMsg: ChatMessage = {
        ...s.messages[messageIndex],
        content: newContent,
        timestamp: Date.now(),
      };
      keptMessages.push(editedMsg);
      next.set(sessionId, {
        ...s,
        messages: keptMessages,
        updatedAt: Date.now(),
      });
      return next;
    });
    send('chat.message', {
      session_id: sessionId,
      content: newContent,
      user_id: 'web_user',
      regenerate: true,
    });
    setStreamingSessionId(sessionId);
    setThinking(true);
  }, [send]);

  const handleRegenerateMessage = useCallback((sessionId: string, messageIndex: number) => {
    setSessions((prev) => {
      const s = prev.get(sessionId);
      if (!s) return prev;
      const next = new Map(prev);
      const keptMessages = s.messages.slice(0, messageIndex);
      let lastUserMsg = '';
      for (let i = keptMessages.length - 1; i >= 0; i--) {
        if (keptMessages[i].role === 'user') {
          lastUserMsg = keptMessages[i].content;
          break;
        }
      }
      next.set(sessionId, {
        ...s,
        messages: keptMessages,
        updatedAt: Date.now(),
      });
      if (lastUserMsg) {
        setTimeout(() => {
          send('chat.message', {
            session_id: sessionId,
            user_id: 'web_user',
            content: lastUserMsg,
            regenerate: true,
          });
        }, 0);
      }
      return next;
    });
    setStreamingSessionId(sessionId);
    setThinking(true);
  }, [send]);

  const handleApproval = useCallback(async (sessionId: string, approved: boolean) => {
    try {
      const resp = await fetch(`/api/v1/approvals/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      });
      if (resp.ok) {
        setPendingApproval(null);
        setSessions((prev) => {
          const s = prev.get(sessionId);
          if (!s) return prev;
          const next = new Map(prev);
          next.set(sessionId, {
            ...s,
            status: approved ? 'executing' : 'completed',
            messages: [
              ...s.messages,
              {
                id: `approval-${Date.now()}`,
                role: 'system',
                content: approved ? '✅ 任务已获批准，正在执行...' : '❌ 任务已被拒绝。',
                timestamp: Date.now(),
              },
            ],
            updatedAt: Date.now(),
          });
          return next;
        });
        showToast(approved ? '任务已批准' : '任务已拒绝', 'success');
      } else {
        const err = await resp.json().catch(() => ({}));
        showToast(err.detail || '审批提交失败', 'error');
      }
    } catch (e) {
      showToast('审批提交失败，请检查网络', 'error');
    }
  }, [showToast]);

  const activeSession = activeSessionId ? sessions.get(activeSessionId) ?? null : null;

  const renderPanel = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <Dashboard
            sessions={Array.from(sessions.values())}
            onSelectSession={handleSelectSession}
            onTabChange={setActiveTab}
            emotion={aiState.emotion}
            persona={aiState.persona}
          />
        );
      case 'estate':
        return <EstateDashboard />;
      case 'chat':
        return (
          <div className="flex h-full">
            <div className="flex-1 min-w-0 relative">
              <ChatPanel
                sessions={Array.from(sessions.values())}
                activeSession={activeSession}
                onSelectSession={handleSelectSession}
                onSendMessage={handleSendMessage}
                onAbortTask={handleAbortTask}
                onFeedback={handleFeedback}
                onEditMessage={handleEditMessage}
                onRegenerateMessage={handleRegenerateMessage}
                connectionStatus={connectionStatus}
                isStreaming={streamingSessionId === activeSessionId}
                emotion={aiState.emotion}
                persona={aiState.persona}
                onViewProfile={() => setActiveTab('assistant')}
                onEnterMemoryScene={(sid) => {
                  setMemorySceneSessionId(sid);
                  setActiveTab('memory_scene');
                }}
              />
              {/* 世界窗折叠/展开切换按钮（悬浮在聊天区右上角） */}
              <button
                onClick={() => setWorldPanelOpen(!worldPanelOpen)}
                className={`absolute top-3 z-20 flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs font-medium border transition-all shadow-sm hover:shadow-md ${
                  worldPanelOpen
                    ? 'right-3 bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                    : 'right-3 bg-teal-50 text-teal-700 border-teal-200 hover:bg-teal-100'
                }`}
                title={worldPanelOpen ? '收起 AI 世界' : '展开 AI 世界'}
              >
                {worldPanelOpen ? (
                  <>
                    <PanelRightClose className="w-3.5 h-3.5" />
                    <span className="hidden xl:inline">收起</span>
                  </>
                ) : (
                  <>
                    <MapIcon className="w-3.5 h-3.5" />
                    <span className="hidden xl:inline">AI 世界</span>
                  </>
                )}
              </button>
            </div>
            {/* 右侧可折叠 AI 世界缩略视图 */}
            <div
              className={`hidden lg:flex flex-col border-l border-gray-200 bg-gray-50 transition-all duration-300 ease-in-out overflow-hidden ${
                worldPanelOpen ? 'w-80 opacity-100' : 'w-0 opacity-0 border-l-0'
              }`}
            >
              {/* FIX: 始终渲染，避免卸载/重挂载导致 Canvas 白屏 */}
              <div className={`h-full ${worldPanelOpen ? '' : 'invisible'}`}>
                <MiniWorldView onExpand={() => setActiveTab('world')} />
              </div>
            </div>
          </div>
        );
      case 'assistant':
        return <AIAssistantPanel emotion={aiState.emotion} persona={aiState.persona} />;
      case 'tasks':
        return <TaskFlow sessions={Array.from(sessions.values())} />;
      case 'memory':
        return <MemoryPanel />;
      case 'rules':
        return <RulesPanel />;
      case 'slo':
        return <SLOPanel />;
      case 'dreaming':
        return <DreamPanel emotion={aiState.emotion} persona={aiState.persona} />;
      case 'config':
        return <ConfigPanel />;
      case 'logs':
        return <LogsPanel />;
      case 'skills':
        return <SkillsPanel />;
      case 'approvals':
        return <ApprovalPanel />;
      case 'cron':
        return <CronPanel />;
      case 'physical':
        return <PhysicalWorldPanel />;
      case 'emotion':
        return <EmotionTimelinePanel />;
      case 'world':
        return <WorldMapPanel />;
      case 'memory_scene':
        return (
          <MemoryScenePanel
            sessionId={memorySceneSessionId || undefined}
            onBack={() => {
              setActiveTab('chat');
              setMemorySceneSessionId(null);
            }}
            onContinueChat={(sid) => {
              setActiveTab('chat');
              setMemorySceneSessionId(null);
              handleSelectSession(sid);
            }}
          />
        );
      case 'community':
        return <CommunityPanel />;
      default:
        return null;
    }
  };

  return (
    <div className="flex h-screen w-screen bg-gray-50">
      {/* C2: 桌面端 Sidebar / 移动端隐藏 */}
      {!isMobile && (
        <Sidebar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          health={health}
          connectionStatus={connectionStatus}
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed((c) => !c)}
          emotion={aiState.emotion}
          persona={aiState.persona}
        />
      )}
      <main className={`flex-1 overflow-hidden relative ${isMobile ? 'pb-16' : ''}`}>
        {renderPanel()}
        {pendingApproval && (
          <ApprovalDialog
            sessionId={pendingApproval.session_id}
            plan={pendingApproval.plan}
            onApprove={() => handleApproval(pendingApproval.session_id, true)}
            onReject={() => handleApproval(pendingApproval.session_id, false)}
          />
        )}
        {/* ===== Avatar 家园系统：自由态覆盖层 ===== */}
        {/* 在 world tab 下隐藏全局 Avatar，让世界内的 Avatar 成为主角 */}
        {/* ===== Avatar 家园系统：自由态覆盖层 ===== */}
        {/* 在 world tab 下隐藏全局 Avatar，让世界内的 Avatar 成为主角 */}
        {activeTab !== 'world' && <GlobalAvatarFree />}
        {/* Floating Vision Panel — visible across all tabs */}
        {!isMobile && (
          <VisionFloatingPanel
            videoRef={vision.videoRef}
            detectedObjects={vision.detectedObjects}
            lastEmotion={vision.lastEmotion}
            emotionConfidence={vision.emotionConfidence}
            cameraActive={vision.isActive}
            cameraMirror={vision.mirror}
            devices={vision.devices}
            selectedDeviceId={vision.selectedDeviceId}
            onStart={vision.startCamera}
            onStop={vision.stopCamera}
            onToggleMirror={vision.toggleMirror}
            onSwitchCamera={vision.switchCamera}
            onCapture={() => {
              // 截图后可以选择发送到 AI 分析
              console.log('[Vision] 截图已保存');
            }}
          />
        )}
      </main>

      {/* C2: 移动端底部导航栏 */}
      {isMobile && (
        <>
          <nav className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 safe-area-bottom">
            <div className="flex items-center justify-around h-14">
              {[
                { tab: 'chat' as ViewTab, label: '聊天', icon: MessageSquare },
                { tab: 'dashboard' as ViewTab, label: '概览', icon: LayoutDashboard },
                { tab: 'estate' as ViewTab, label: '概览', icon: Home },
                { tab: 'assistant' as ViewTab, label: '角色', icon: Bot },
              ].map((item) => (
                <button
                  key={item.tab}
                  onClick={() => setActiveTab(item.tab)}
                  className={`flex flex-col items-center justify-center gap-0.5 w-16 h-14 transition-colors ${
                    activeTab === item.tab
                      ? 'text-tent-600'
                      : 'text-gray-400'
                  }`}
                >
                  <item.icon className="w-5 h-5" />
                  <span className="text-[10px]">{item.label}</span>
                </button>
              ))}
              <button
                onClick={() => setMobileMoreOpen(!mobileMoreOpen)}
                className={`flex flex-col items-center justify-center gap-0.5 w-16 h-14 transition-colors ${
                  mobileMoreOpen ? 'text-tent-600' : 'text-gray-400'
                }`}
              >
                <MoreHorizontal className="w-5 h-5" />
                <span className="text-[10px]">更多</span>
              </button>
            </div>
          </nav>
          {/* 更多菜单弹层 */}
          {mobileMoreOpen && (
            <div className="fixed bottom-16 left-2 right-2 z-50 bg-white rounded-xl shadow-lg border border-gray-200 p-2 animate-in fade-in slide-in-from-bottom-2">
              <div className="grid grid-cols-4 gap-1">
                {[
                  { tab: 'tasks' as ViewTab, label: '任务' },
                  { tab: 'memory' as ViewTab, label: '记忆' },
                  { tab: 'rules' as ViewTab, label: '规则' },
                  { tab: 'skills' as ViewTab, label: '技能' },
                  { tab: 'community' as ViewTab, label: '社区' },
                  { tab: 'world' as ViewTab, label: '世界' },
                  { tab: 'dreaming' as ViewTab, label: '梦境' },
                ].map((item) => (
                  <button
                    key={item.tab}
                    onClick={() => { setActiveTab(item.tab); setMobileMoreOpen(false); }}
                    className={`px-2 py-2 rounded-lg text-xs font-medium transition-colors ${
                      activeTab === item.tab
                        ? 'bg-tent-50 text-tent-700'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {/* 点击外部关闭更多菜单 */}
          {mobileMoreOpen && (
            <div
              className="fixed inset-0 z-40"
              onClick={() => setMobileMoreOpen(false)}
            />
          )}
        </>
      )}
    </div>
  );
}

export default function App() {
  return (
    <AIStateProvider>
      <SpacetimeProvider>
        <CommunityProvider>
          <AvatarHomeProvider>
            <AppInner />
          </AvatarHomeProvider>
        </CommunityProvider>
      </SpacetimeProvider>
    </AIStateProvider>
  );
}
