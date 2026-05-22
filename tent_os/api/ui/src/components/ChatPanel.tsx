import { useState, useRef, useEffect, useCallback, memo } from 'react';
import {
  Send,
  Square,
  Plus,
  Bot,
  Wrench,
  AlertCircle,
  ChevronRight,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Brain,
  ChevronDown,
  ChevronUp,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  ImagePlus,
  FileText,
  X,
  ThumbsUp,
  ThumbsDown,
  PencilLine,
  Tent,
  Truck,
  Eye,
  Sparkles,
  Lightbulb,
  History,
  Edit2,
  RefreshCw,
} from 'lucide-react';
import { useVoice } from '@/hooks/useVoice';
import { useAIState } from '@/contexts/AIStateContext';
import { useSpacetime } from '@/contexts/SpacetimeContext';
import { useIsMobile } from '@/hooks/useMediaQuery';
import { AvatarHomeButton } from './AvatarHomeButton';
import { MarkdownRenderer } from './MarkdownRenderer';
import type { TaskSession, ChatMessage } from '@/types';

interface ChatPanelProps {
  sessions: TaskSession[];
  activeSession: TaskSession | null;
  onSelectSession: (id: string) => void;
  onSendMessage: (text: string, images?: string[]) => void;
  onAbortTask: (id: string) => void;
  onFeedback?: (sessionId: string, messageIndex: number, type: 'like' | 'dislike' | 'correct', correction?: string) => void;
  onEditMessage?: (sessionId: string, messageIndex: number, newContent: string) => void;
  onRegenerateMessage?: (sessionId: string, messageIndex: number) => void;
  connectionStatus: 'connecting' | 'connected' | 'disconnected';
  isStreaming?: boolean;
  emotion?: string;
  persona?: string;
  onViewProfile?: () => void;
  onEnterMemoryScene?: (sessionId: string) => void;
}

function FeedbackBar({
  onLike,
  onDislike,
  onCorrect,
  feedbackState,
}: {
  onLike: () => void;
  onDislike: () => void;
  onCorrect: (text: string) => void;
  feedbackState?: 'like' | 'dislike' | 'correct' | null;
}) {
  const [showCorrect, setShowCorrect] = useState(false);
  const [correctText, setCorrectText] = useState('');

  return (
    <div className="flex items-center gap-1 mt-1.5 ml-10">
      <button
        onClick={onLike}
        className={`p-1 rounded-md transition-colors ${feedbackState === 'like' ? 'bg-green-100 text-green-600' : 'text-gray-400 hover:text-green-500 hover:bg-gray-100'}`}
        title="有用"
      >
        <ThumbsUp className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={onDislike}
        className={`p-1 rounded-md transition-colors ${feedbackState === 'dislike' ? 'bg-red-100 text-red-600' : 'text-gray-400 hover:text-red-500 hover:bg-gray-100'}`}
        title="无用"
      >
        <ThumbsDown className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={() => setShowCorrect(!showCorrect)}
        className={`p-1 rounded-md transition-colors ${feedbackState === 'correct' ? 'bg-blue-100 text-blue-600' : 'text-gray-400 hover:text-blue-500 hover:bg-gray-100'}`}
        title="纠正"
      >
        <PencilLine className="w-3.5 h-3.5" />
      </button>
      {showCorrect && (
        <div className="flex items-center gap-1 ml-1">
          <input
            type="text"
            value={correctText}
            onChange={(e) => setCorrectText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && correctText.trim()) {
                onCorrect(correctText.trim());
                setCorrectText('');
                setShowCorrect(false);
              }
            }}
            placeholder="应该如何回答..."
            className="w-40 px-2 py-0.5 text-xs rounded border border-gray-200 focus:border-tent-400 focus:outline-none"
            autoFocus
          />
          <button
            onClick={() => {
              if (correctText.trim()) {
                onCorrect(correctText.trim());
                setCorrectText('');
                setShowCorrect(false);
              }
            }}
            className="text-xs px-1.5 py-0.5 bg-tent-600 text-white rounded hover:bg-tent-700"
          >
            提交
          </button>
        </div>
      )}
    </div>
  );
}

const MessageBubble = memo(function MessageBubble({
  msg,
  index,
  sessionId,
  onFeedback,
  onEditMessage,
  onRegenerateMessage,
}: {
  msg: ChatMessage;
  index: number;
  sessionId?: string;
  onFeedback?: (sessionId: string, messageIndex: number, type: 'like' | 'dislike' | 'correct', correction?: string) => void;
  onEditMessage?: (sessionId: string, messageIndex: number, newContent: string) => void;
  onRegenerateMessage?: (sessionId: string, messageIndex: number) => void;
}) {
  const [feedbackState, setFeedbackState] = useState<'like' | 'dislike' | 'correct' | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(msg.content);
  const [showActions, setShowActions] = useState(false);

  const formatTime = (ts: number) => {
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  if (msg.role === 'user') {
    return (
      <div
        className="flex justify-end mb-4 group"
        onMouseEnter={() => setShowActions(true)}
        onMouseLeave={() => setShowActions(false)}
      >
        <div className="chat-message-user max-w-[92%] md:max-w-[85%] relative">
          {msg.images && msg.images.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {msg.images.map((img, i) => (
                <img
                  key={i}
                  src={img.startsWith('data:') ? img : `data:image/jpeg;base64,${img}`}
                  alt="uploaded"
                  className="max-w-[120px] max-h-[120px] rounded-lg object-cover border border-white/30"
                />
              ))}
            </div>
          )}
          {isEditing ? (
            <div className="flex flex-col gap-2">
              <textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                className="w-full min-w-[200px] px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white focus:border-tent-400 focus:outline-none resize-none"
                rows={3}
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => { setIsEditing(false); setEditText(msg.content); }}
                  className="px-2 py-1 text-xs rounded bg-gray-100 text-gray-600 hover:bg-gray-200"
                >
                  取消
                </button>
                <button
                  onClick={() => {
                    if (editText.trim() && sessionId && onEditMessage) {
                      onEditMessage(sessionId, index, editText.trim());
                      setIsEditing(false);
                    }
                  }}
                  className="px-2 py-1 text-xs rounded bg-tent-600 text-white hover:bg-tent-700"
                >
                  保存
                </button>
              </div>
            </div>
          ) : (
            <>
              {msg.content && <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>}
              {showActions && sessionId && onEditMessage && (
                <div className="absolute -left-7 bottom-0 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => setIsEditing(true)}
                    className="p-1 rounded bg-white/80 text-gray-400 hover:text-blue-500 hover:bg-white shadow-sm border border-gray-100"
                    title="编辑"
                  >
                    <Edit2 className="w-3 h-3" />
                  </button>
                </div>
              )}
            </>
          )}
          <span className="text-[10px] text-white/50 mt-1 block text-right">{formatTime(msg.timestamp)}</span>
        </div>
      </div>
    );
  }

  if (msg.role === 'tool') {
    return (
      <div className="flex justify-start mb-3">
        <div className="tool-card flex items-start gap-2">
          <Wrench className="w-4 h-4 text-gray-400 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{msg.content}</p>
            {msg.metadata?.toolResult !== undefined && (
              <pre className="mt-2 p-2 bg-white/60 rounded text-xs text-gray-600 overflow-x-auto">
                {JSON.stringify(msg.metadata.toolResult, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (msg.role === 'system') {
    return (
      <div className="flex justify-center mb-3">
        <div className="chat-message-system flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span className="text-sm">{msg.content}</span>
        </div>
      </div>
    );
  }

  if (msg.role === 'monologue') {
    return (
      <div className="flex justify-start mb-3">
        <div className="flex gap-3 max-w-[85%]">
          <div className="shrink-0 mt-0.5">
            <div className="w-9 h-9 rounded-full bg-purple-50 border border-purple-200 flex items-center justify-center">
              <span className="text-xs">💭</span>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="bg-purple-50/60 border border-purple-100 rounded-xl rounded-bl-sm px-4 py-2.5">
              <p className="text-xs italic text-purple-800/70 leading-relaxed whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (msg.role === 'proactive') {
    return (
      <div className="flex justify-start mb-4">
        <div className="flex gap-3 max-w-[85%]">
          <div className="shrink-0 mt-0.5">
            <div className="w-9 h-9 rounded-full bg-amber-50 border border-amber-200 flex items-center justify-center">
              <Lightbulb className="w-4 h-4 text-amber-500" />
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="bg-amber-50/60 border border-amber-200 rounded-xl rounded-bl-sm px-4 py-3">
              <p className="text-sm text-amber-900 leading-relaxed whitespace-pre-wrap">{msg.content}</p>
              <span className="text-[10px] text-amber-500/60 mt-1 block">主动关怀</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="flex justify-start mb-4 group">
      <div className="flex gap-3 max-w-[85%]">
        <div className="shrink-0 mt-0.5 w-9 h-9 rounded-full bg-teal-100 border border-teal-200 flex items-center justify-center text-lg select-none" title="AI 助手">
          🤖
        </div>
        <div className="flex-1 min-w-0">
          {msg.reasoning && (
            <ReasoningBlock reasoning={msg.reasoning} />
          )}
          <div className="chat-message-assistant">
            <MarkdownRenderer content={msg.content} />
          </div>
          {msg.explanation && (
            <ExplainChip explanation={msg.explanation} />
          )}
          <div className="flex items-center gap-2 mt-1">
            {onFeedback && sessionId && (
              <FeedbackBar
                feedbackState={feedbackState}
                onLike={() => {
                  setFeedbackState('like');
                  onFeedback(sessionId, index, 'like');
                }}
                onDislike={() => {
                  setFeedbackState('dislike');
                  onFeedback(sessionId, index, 'dislike');
                }}
                onCorrect={(text) => {
                  setFeedbackState('correct');
                  onFeedback(sessionId, index, 'correct', text);
                }}
              />
            )}
            {sessionId && onRegenerateMessage && (
              <button
                onClick={() => onRegenerateMessage(sessionId, index)}
                className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] text-gray-400 hover:text-tent-600 hover:bg-tent-50 transition-colors opacity-0 group-hover:opacity-100"
                title="重新生成"
              >
                <RefreshCw className="w-3 h-3" />
                重新生成
              </button>
            )}
          </div>
          <span className="text-[10px] text-gray-300 mt-0.5 block">{formatTime(msg.timestamp)}</span>
        </div>
      </div>
    </div>
  );
});

function ReasoningBlock({ reasoning }: { reasoning: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = reasoning.length > 80;
  const displayText = expanded || !isLong ? reasoning : reasoning.slice(0, 80) + '...';

  return (
    <div className="mb-2 bg-amber-50/80 border border-amber-200 rounded-lg px-3 py-2">
      <button
        onClick={() => isLong && setExpanded(!expanded)}
        className={`flex items-center gap-1.5 text-xs text-amber-700 mb-1 ${isLong ? 'cursor-pointer hover:text-amber-800' : ''}`}
      >
        <Brain className="w-3 h-3" />
        <span className="font-medium">思考过程</span>
        {isLong && (
          expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
        )}
      </button>
      <p className="text-xs text-amber-800/70 leading-relaxed whitespace-pre-wrap">{displayText}</p>
    </div>
  );
}

function ExplainChip({ explanation }: { explanation: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <button
      onClick={() => setExpanded(!expanded)}
      className="mt-2 flex items-center gap-1.5 text-xs text-blue-600 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-full px-3 py-1 transition-colors"
    >
      <Lightbulb className="w-3 h-3" />
      <span>{expanded ? explanation : '🤔 为什么这样回答？'}</span>
    </button>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="flex gap-3">
        <div className="shrink-0 mt-0.5">
          <AvatarHomeButton source="chat" size={36} />
        </div>
        <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
          <div className="flex gap-1.5">
            <span className="w-2 h-2 rounded-full bg-gray-400 typing-dot" />
            <span className="w-2 h-2 rounded-full bg-gray-400 typing-dot" />
            <span className="w-2 h-2 rounded-full bg-gray-400 typing-dot" />
          </div>
        </div>
      </div>
    </div>
  );
}

function SessionStatus({ status }: { status: string }) {
  const configs: Record<string, { icon: React.ElementType; text: string; color: string }> = {
    pending: { icon: Clock, text: '等待中', color: 'text-amber-600 bg-amber-50 border-amber-200' },
    planning: { icon: Loader2, text: '规划中', color: 'text-blue-600 bg-blue-50 border-blue-200' },
    executing: { icon: Loader2, text: '执行中', color: 'text-tent-600 bg-tent-50 border-tent-200' },
    completed: { icon: CheckCircle2, text: '已完成', color: 'text-green-600 bg-green-50 border-green-200' },
    failed: { icon: XCircle, text: '失败', color: 'text-red-600 bg-red-50 border-red-200' },
    aborted: { icon: Square, text: '已中止', color: 'text-gray-600 bg-gray-50 border-gray-200' },
  };
  const cfg = configs[status] || configs.pending;
  const Icon = cfg.icon;
  const isSpinning = status === 'planning' || status === 'executing';

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${cfg.color}`}>
      <Icon className={`w-3.5 h-3.5 ${isSpinning ? 'animate-spin' : ''}`} />
      {cfg.text}
    </span>
  );
}

interface SessionContextData {
  permission_mode: string;
  security_assessment?: {
    safety_level: string;
    reasoning: string;
    mode_changed: boolean;
  } | null;
  activated_skills: string[];
  available_tools_count: number;
  file_memories_recalled: number;
  procedural_rules_injected: number;
  llm_calls: number;
  total_tokens: number;
  avg_latency_ms: number;
  brain_v2_enabled: boolean;
}

function PermissionModeBadge({ mode }: { mode: string }) {
  const configs: Record<string, { label: string; color: string; desc: string }> = {
    strict: { label: '严格', color: 'bg-orange-100 text-orange-700 border-orange-200', desc: '只读' },
    standard: { label: '标准', color: 'bg-blue-100 text-blue-700 border-blue-200', desc: '常规' },
    auto: { label: '自动', color: 'bg-purple-100 text-purple-700 border-purple-200', desc: '动态' },
    unrestricted: { label: '无限制', color: 'bg-red-100 text-red-700 border-red-200', desc: '全开' },
  };
  const cfg = configs[mode] || configs.standard;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${cfg.color}`} title={`权限模式: ${cfg.desc}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {cfg.label}
    </span>
  );
}

function SessionContextBar({ sessionId }: { sessionId: string }) {
  const [context, setContext] = useState<SessionContextData | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchContext = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const resp = await fetch(`/ui/api/session/${encodeURIComponent(sessionId)}/context`);
      if (resp.ok) {
        const data = await resp.json();
        if (!data.error) {
          setContext(data);
        }
      }
    } catch (e) {
      console.warn('获取会话上下文失败:', e);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchContext();
    // 每 3 秒轮询一次（对话进行中时状态变化快）
    const interval = setInterval(fetchContext, 30000);
    return () => clearInterval(interval);
  }, [fetchContext]);

  if (!context && !loading) return null;

  return (
    <div className="bg-gray-50 border-b border-gray-200">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-5 py-2 flex items-center justify-between hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-3">
          {context && (
            <>
              <PermissionModeBadge mode={context.permission_mode} />
              {context.activated_skills.length > 0 && (
                <div className="flex items-center gap-1">
                  {context.activated_skills.map((skill) => (
                    <span key={skill} className="px-1.5 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700 border border-emerald-200">
                      {skill}
                    </span>
                  ))}
                </div>
              )}
              {context.llm_calls > 0 && (
                <span className="text-xs text-gray-500">
                  {context.llm_calls} 次调用 · {context.total_tokens} tokens
                </span>
              )}
            </>
          )}
          {loading && <span className="text-xs text-gray-400">加载中...</span>}
        </div>
        {context && (
          <span className="text-xs text-gray-400">
            {expanded ? '收起' : '详情'}
          </span>
        )}
      </button>
      
      {expanded && context && (
        <div className="px-5 py-3 border-t border-gray-200 grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-white rounded-lg p-2.5 border border-gray-100">
            <p className="text-xs text-gray-400 mb-1">安全评估</p>
            <p className="text-sm font-medium text-gray-700">
              {context.security_assessment?.safety_level === 'safe' ? '安全' :
               context.security_assessment?.safety_level === 'cautious' ? '谨慎' :
               context.security_assessment?.safety_level === 'dangerous' ? '危险' :
               context.security_assessment?.safety_level === 'critical' ? '高危' : '未知'}
            </p>
            {context.security_assessment?.reasoning && (
              <p className="text-xs text-gray-500 mt-0.5 truncate">{context.security_assessment.reasoning}</p>
            )}
          </div>
          <div className="bg-white rounded-lg p-2.5 border border-gray-100">
            <p className="text-xs text-gray-400 mb-1">可用工具</p>
            <p className="text-sm font-medium text-gray-700">{context.available_tools_count} 个</p>
          </div>
          <div className="bg-white rounded-lg p-2.5 border border-gray-100">
            <p className="text-xs text-gray-400 mb-1">记忆召回</p>
            <p className="text-sm font-medium text-gray-700">
              文件 {context.file_memories_recalled} · 规则 {context.procedural_rules_injected}
            </p>
          </div>
          <div className="bg-white rounded-lg p-2.5 border border-gray-100">
            <p className="text-xs text-gray-400 mb-1">平均延迟</p>
            <p className="text-sm font-medium text-gray-700">{context.avg_latency_ms > 0 ? `${context.avg_latency_ms.toFixed(0)}ms` : '-'}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ===== AI 状态气泡条 =====
function AIStatusBar() {
  const { state: spacetime } = useSpacetime();
  const { state: aiState } = useAIState();

  const activity = spacetime.currentActivity;
  const location = activity?.location || '未知';
  const target = activity?.target || '待机中';

  // 疲劳度颜色
  const fatigueColor =
    spacetime.fatigue > 0.7 ? 'text-red-500' :
    spacetime.fatigue > 0.4 ? 'text-amber-500' :
    'text-green-500';

  // 活动图标
  const activityIcon =
    activity?.type === 'coding' ? '💻' :
    activity?.type === 'thinking' ? '🧠' :
    activity?.type === 'monitoring' ? '📊' :
    activity?.type === 'dreaming' ? '🌙' :
    activity?.type === 'resting' ? '☕' :
    activity?.type === 'chatting' ? '💬' :
    '⏳';

  // 时间表图标
  const scheduleIcon =
    spacetime.scheduleMode === 'work' ? '💼' :
    spacetime.scheduleMode === 'rest' ? '☕' :
    spacetime.scheduleMode === 'sleep' ? '🌙' :
    spacetime.scheduleMode === 'break' ? '😌' :
    '⏰';

  return (
    <div className="sticky top-0 z-10 bg-white/90 backdrop-blur-sm border-b border-gray-200">
      <div className="px-5 py-2 flex items-center gap-3 flex-wrap">
        {/* 状态指示灯 */}
        <div className="flex items-center gap-1.5">
          <span className="relative flex h-2.5 w-2.5">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${aiState.isThinking ? 'bg-amber-400' : 'bg-green-400'}`} />
            <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${aiState.isThinking ? 'bg-amber-500' : 'bg-green-500'}`} />
          </span>
          <span className="text-xs font-medium text-gray-700">
            {aiState.isThinking ? '思考中' : '在线'}
          </span>
        </div>

        <span className="text-gray-300">|</span>

        {/* 位置 */}
        <div className="flex items-center gap-1 text-xs text-gray-600">
          <span>🏠</span>
          <span className="font-medium">{location}</span>
        </div>

        <span className="text-gray-300">|</span>

        {/* 当前活动 */}
        <div className="flex items-center gap-1 text-xs text-gray-600">
          <span>{activityIcon}</span>
          <span className="truncate max-w-[200px]" title={target}>{target}</span>
        </div>

        <span className="text-gray-300">|</span>

        {/* 疲劳度 */}
        <div className="flex items-center gap-1 text-xs">
          <span className="text-gray-500">疲劳</span>
          <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                spacetime.fatigue > 0.7 ? 'bg-red-400' :
                spacetime.fatigue > 0.4 ? 'bg-amber-400' :
                'bg-green-400'
              }`}
              style={{ width: `${spacetime.fatigue * 100}%` }}
            />
          </div>
          <span className={`text-[10px] ${fatigueColor}`}>
            {Math.round(spacetime.fatigue * 100)}%
          </span>
        </div>

        <span className="text-gray-300">|</span>

        {/* 时间表模式 */}
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <span>{scheduleIcon}</span>
          <span>
            {spacetime.scheduleMode === 'work' && '工作时间'}
            {spacetime.scheduleMode === 'rest' && '休息时间'}
            {spacetime.scheduleMode === 'sleep' && '梦境模式'}
            {spacetime.scheduleMode === 'break' && '小憩中'}
          </span>
        </div>

        {/* 自主决策提示 */}
        {spacetime.autonomyDecision && (
          <>
            <span className="text-gray-300">|</span>
            <div className="flex items-center gap-1 px-2 py-0.5 bg-amber-50 border border-amber-200 rounded-full">
              <span className="text-[10px] text-amber-700">
                💭 {spacetime.autonomyDecision}
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export const ChatPanel = memo(function ChatPanel({
  sessions,
  activeSession,
  onSelectSession,
  onSendMessage,
  onAbortTask,
  onFeedback,
  onEditMessage,
  onRegenerateMessage,
  connectionStatus,
  isStreaming,
  emotion: _emotion = 'listening',
  persona: _persona = 'work',
  onViewProfile,
  onEnterMemoryScene,
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  const [sessionSearch, setSessionSearch] = useState('');
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [pendingFileNames, setPendingFileNames] = useState<string[]>([]);
  const [isComposing, setIsComposing] = useState(false);
  const [describeLoading, setDescribeLoading] = useState(false);
  const [fileUploading, setFileUploading] = useState(false);
  const isMobile = useIsMobile();
  const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);
  const [personaModes] = useState<{mode: string; label: string; desc: string}[]>([
    { mode: 'work', label: '工作', desc: '专业、高效、主动' },
    { mode: 'casual', label: '休闲', desc: '轻松、随和、有温度' },
    { mode: 'emergency', label: '紧急', desc: '快速、直接、结果导向' },
    { mode: 'learning', label: '学习', desc: '耐心、详细、教学式' },
    { mode: 'creative', label: '创意', desc: '发散、灵感、脑洞大' },
  ]);
  // FIX: 移除本地 currentPersona state，完全使用 persona prop，避免双轨分裂
  // 人格切换通过 WebSocket persona.changed 广播更新到 App.tsx，再作为 prop 传入
  const [, setLevelInfo] = useState<{ level: number; title: string; xp: number; nextThreshold: number }>({ level: 1, title: '新手', xp: 0, nextThreshold: 100 });
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const describeInputRef = useRef<HTMLInputElement>(null);
  // AI 口型同步（预留）
  const {
    isListening,
    transcript,
    voiceCommand,
    clearVoiceCommand,
    ttsEnabled,
    isSpeaking: _isSpeaking,
    isSupported: voiceSupported,
    isTtsSupported,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
    toggleTts,
  } = useVoice();

  // A5: 输入状态持久化 — 切换 session 时恢复草稿
  const draftKey = `tent_chat_draft_${activeSession?.sessionId || 'default'}`;
  useEffect(() => {
    try {
      const saved = localStorage.getItem(draftKey);
      if (saved) {
        const draft = JSON.parse(saved);
        if (draft.input) setInput(draft.input);
        if (draft.pendingImages) setPendingImages(draft.pendingImages);
        if (draft.pendingFileNames) setPendingFileNames(draft.pendingFileNames);
      }
    } catch {
      // ignore parse error
    }
  }, [draftKey]);

  // A5: 输入变化时自动保存草稿
  useEffect(() => {
    try {
      if (input || pendingImages.length || pendingFileNames.length) {
        localStorage.setItem(draftKey, JSON.stringify({ input, pendingImages, pendingFileNames }));
      } else {
        localStorage.removeItem(draftKey);
      }
    } catch {
      // ignore storage error
    }
  }, [input, pendingImages, pendingFileNames, draftKey]);

  // 语音识别结束后自动发送
  useEffect(() => {
    if (!isListening && transcript) {
      setInput(transcript);
      // 延迟一点让 setInput 生效
      setTimeout(() => {
        if (transcript.trim() && connectionStatus === 'connected') {
          onSendMessage(transcript.trim());
          setInput('');
          setPendingImages([]);
        }
      }, 200);
    }
  }, [isListening, transcript, connectionStatus, onSendMessage]);

  // AI 回复完成后自动朗读（情感 TTS + 句子级分段）
  useEffect(() => {
    if (activeSession?.status === 'completed' && ttsEnabled) {
      const lastMsg = activeSession.messages[activeSession.messages.length - 1];
      if (lastMsg?.role === 'assistant' && lastMsg.content) {
        speak(lastMsg.content, {
          emotion: _emotion,
        });
      }
    }
  }, [activeSession?.status, activeSession?.messages, ttsEnabled, speak, _emotion]);

  // 加载 AI 等级数据
  useEffect(() => {
    const loadLevel = async () => {
      try {
        const res = await fetch('/ui/api/six-axis').then((r) => r.json());
        if (res.radar) {
          const scores = Object.values(res.radar as Record<string, { score: number }>).map((d) => d.score);
          const avg = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
          const thresholds = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
          let level = 1;
          for (let i = 1; i < thresholds.length; i++) { if (avg >= thresholds[i]) level = i + 1; else break; }
          const nextThreshold = thresholds[level] || 100;
          // 使用后端返回的 title，保持一致
          setLevelInfo({ level, title: res.title || '新手', xp: Math.round(res.total_exp || 0), nextThreshold });
        }
      } catch {
        // ignore
      }
    };
    loadLevel();
    const interval = setInterval(loadLevel, 300000);
    return () => clearInterval(interval);
  }, []);

  // Auto-scroll to bottom (only when user is near bottom)
  useEffect(() => {
    if (scrollRef.current) {
      const el = scrollRef.current;
      const threshold = 100; // px
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight;
      }
    }
  }, [activeSession?.messages.length, activeSession?.status]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if ((!trimmed && !pendingImages.length) || connectionStatus !== 'connected') return;
    onSendMessage(trimmed, pendingImages.length > 0 ? pendingImages : undefined);
    setInput('');
    setPendingImages([]);
    setPendingFileNames([]);
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  }, [input, pendingImages, connectionStatus, onSendMessage]);

  // C1: 语音指令处理
  useEffect(() => {
    if (!voiceCommand) return;
    switch (voiceCommand) {
      case 'stop_speaking':
        stopSpeaking();
        break;
      case 'clear_input':
        setInput('');
        setPendingImages([]);
        setPendingFileNames([]);
        break;
      case 'send_message':
        if (input.trim() || pendingImages.length) {
          handleSend();
        }
        break;
    }
    clearVoiceCommand();
  }, [voiceCommand, stopSpeaking, clearVoiceCommand, input, pendingImages, handleSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend, isComposing]
  );

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (const file of Array.from(files)) {
      if (file.type.startsWith('image/')) {
        // 图片：直接 base64
        const reader = new FileReader();
        reader.onload = (ev) => {
          const result = ev.target?.result as string;
          if (result) {
            setPendingImages((prev) => [...prev, result]);
          }
        };
        reader.readAsDataURL(file);
      } else {
        // 文档：上传到后端提取内容
        setFileUploading(true);
        try {
          const formData = new FormData();
          formData.append('file', file);
          const resp = await fetch('/ui/api/files/upload', {
            method: 'POST',
            body: formData,
          });
          if (resp.ok) {
            const data = await resp.json();
            const fileHeader = `📎 **${data.filename}** (${(data.size / 1024).toFixed(1)} KB)\n\n`;
            const extractedText = data.text || '[无法提取文本内容]';
            setInput((prev) => {
              const sep = prev && !prev.endsWith('\n') ? '\n\n' : '';
              return prev + sep + fileHeader + extractedText + '\n\n';
            });
            setPendingFileNames((prev) => [...prev, data.filename]);
          } else {
            console.warn('文件上传失败:', resp.statusText);
          }
        } catch (err) {
          console.warn('文件上传请求失败:', err);
        } finally {
          setFileUploading(false);
        }
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  // 智能描述：图片 → VLM → 任务描述
  const handleSmartDescribe = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    setDescribeLoading(true);
    try {
      const reader = new FileReader();
      reader.onload = async (ev) => {
        const imageData = ev.target?.result as string;
        if (!imageData) return;
        try {
          const resp = await fetch('/ui/api/vision/describe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_data: imageData }),
          });
          const result = await resp.json();
          if (result.description || result.details) {
            const text = result.details || result.description;
            setInput(text);
            // 自动调整textarea高度
            setTimeout(() => {
              if (inputRef.current) {
                inputRef.current.style.height = 'auto';
                inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`;
              }
            }, 10);
          } else if (result.error) {
            console.warn('智能描述失败:', result.error);
          }
        } catch (err) {
          console.warn('智能描述请求失败:', err);
        } finally {
          setDescribeLoading(false);
        }
      };
      reader.readAsDataURL(file);
    } catch {
      setDescribeLoading(false);
    }
    if (describeInputRef.current) describeInputRef.current.value = '';
  }, []);

  const removePendingImage = useCallback((idx: number) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const removePendingFile = useCallback((idx: number) => {
    setPendingFileNames((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const handleInput = useCallback((e: React.FormEvent<HTMLTextAreaElement>) => {
    const el = e.currentTarget;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const isRunning = activeSession?.status === 'pending' || activeSession?.status === 'planning' || activeSession?.status === 'executing';
  const isAborting = activeSession?.status === 'aborted';

  return (
    <div className="flex h-full">
      {/* Session List */}
      <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="px-3 py-3 border-b border-gray-100">
          <button
            onClick={() => onSelectSession('')}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm font-medium text-tent-700 bg-tent-50 hover:bg-tent-100 transition-colors"
          >
            <Plus className="w-4 h-4" />
            新对话
          </button>
        </div>
        <div className="px-3 py-2 border-b border-gray-100">
          <div className="relative">
            <input
              type="text"
              value={sessionSearch}
              onChange={(e) => setSessionSearch(e.target.value)}
              placeholder="搜索会话..."
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-gray-50 focus:border-tent-400 focus:bg-white focus:outline-none transition-all"
            />
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions
            .filter((s) => {
              const q = sessionSearch.trim().toLowerCase();
              if (!q) return true;
              return (
                s.task.toLowerCase().includes(q) ||
                s.messages.some((m) => m.content.toLowerCase().includes(q))
              );
            })
            .map((s) => (
            <button
              key={s.sessionId}
              onClick={() => onSelectSession(s.sessionId)}
              className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors ${
                activeSession?.sessionId === s.sessionId
                  ? 'bg-tent-50 border border-tent-200'
                  : 'hover:bg-gray-50 border border-transparent'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-gray-700 truncate pr-2">
                  {s.task.slice(0, 30)}{s.task.length > 30 ? '...' : ''}
                </span>
                <ChevronRight className="w-3.5 h-3.5 text-gray-300 shrink-0" />
              </div>
              <div className="flex items-center justify-between">
                <SessionStatus status={s.status} />
                <span className="text-xs text-gray-400">
                  {new Date(s.updatedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            </button>
          ))}
          {sessions.length === 0 && (
            <div className="text-center py-8 text-gray-400 text-sm">
              暂无对话
            </div>
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col bg-gray-50">
        {/* Header */}
        <div className="px-5 py-3 bg-white border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {activeSession ? (
              <>
                <div className="w-8 h-8 rounded-full bg-tent-100 flex items-center justify-center">
                  <Bot className="w-4 h-4 text-tent-600" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-gray-900">
                    {activeSession.task.slice(0, 40)}
                    {activeSession.task.length > 40 ? '...' : ''}
                  </h2>
                  <div className="flex items-center gap-2 mt-0.5">
                    <SessionStatus status={activeSession.status} />
                    <span className="text-xs text-gray-400">
                      {activeSession.messages.length} 条消息
                    </span>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center">
                  <Bot className="w-4 h-4 text-gray-400" />
                </div>
                <span className="text-sm text-gray-500">开始一个新对话</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* 回忆空间入口 */}
            {activeSession && onEnterMemoryScene && (
              <button
                onClick={() => onEnterMemoryScene(activeSession.sessionId)}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium border bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100 transition-colors"
                title="进入回忆空间"
              >
                <History className="w-3 h-3" />
                <span className="hidden sm:inline">回忆</span>
              </button>
            )}
            {/* TTS */}
            {isTtsSupported && (
              <button
                onClick={toggleTts}
                className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  ttsEnabled
                    ? 'bg-tent-50 text-tent-700 border-tent-200'
                    : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                }`}
                title={ttsEnabled ? '关闭朗读' : '开启朗读'}
              >
                {ttsEnabled ? <Volume2 className="w-3 h-3" /> : <VolumeX className="w-3 h-3" />}
                {ttsEnabled ? '朗读开' : '朗读关'}
              </button>
            )}
            {isRunning && (
              <button
                onClick={() => activeSession && onAbortTask(activeSession.sessionId)}
                disabled={isAborting}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  isAborting
                    ? 'text-amber-600 bg-amber-50 border-amber-200 cursor-wait'
                    : 'text-red-600 bg-red-50 hover:bg-red-100 border-red-200'
                }`}
              >
                {isAborting ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" />
                    中止中...
                  </>
                ) : (
                  <>
                    <Square className="w-3 h-3 fill-current" />
                    中止
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Session Context Bar */}
        {activeSession && <SessionContextBar sessionId={activeSession.sessionId} />}

        {/* AI 状态气泡条 */}
        <AIStatusBar />

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
          {activeSession ? (
            <>
              {activeSession.messages.map((msg, idx) => (
                <MessageBubble
                  key={msg.id}
                  msg={msg}
                  index={idx}
                  sessionId={activeSession.sessionId}
                  onFeedback={onFeedback}
                  onEditMessage={onEditMessage}
                  onRegenerateMessage={onRegenerateMessage}
                />
              ))}
              {isRunning && !isStreaming && <TypingIndicator />}
              {isStreaming && (
                <div className="flex justify-start mb-4">
                  <div className="flex gap-3">
                    <div className="shrink-0 mt-0.5">
                      <AvatarHomeButton source="chat" size={36} />
                    </div>
                    <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
                      <div className="flex gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-tent-400 animate-pulse" />
                        <span className="w-1.5 h-1.5 rounded-full bg-tent-400 animate-pulse delay-100" />
                        <span className="w-1.5 h-1.5 rounded-full bg-tent-400 animate-pulse delay-200" />
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <div className="w-16 h-16 rounded-2xl bg-tent-100 flex items-center justify-center mb-4 animate-bounce">
                <Tent className="w-8 h-8 text-tent-400" />
              </div>
              <h3 className="text-lg font-medium text-gray-600 mb-1">Tent OS</h3>
              <p className="text-sm text-gray-400 mb-4">输入任务描述，AI 将为你规划并执行</p>
              {/* 快捷操作 */}
              <div className="flex flex-wrap gap-2 justify-center max-w-md">
                <QuickAction
                  icon={<Truck className="w-3.5 h-3.5" />}
                  label="帮我取快递"
                  onClick={() => onSendMessage('帮我取一下前台快递')}
                />
                <QuickAction
                  icon={<Eye className="w-3.5 h-3.5" />}
                  label="看看周围有什么"
                  onClick={() => onSendMessage('描述一下当前摄像头看到的场景')}
                />
                <QuickAction
                  icon={<Sparkles className="w-3.5 h-3.5" />}
                  label="讲个笑话"
                  onClick={() => onSendMessage('给我讲个程序员笑话')}
                />
                <QuickAction
                  icon={<Bot className="w-3.5 h-3.5" />}
                  label="今天有什么安排"
                  onClick={() => onSendMessage('查看今天的定时任务和安排')}
                />
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="px-5 py-3 bg-white border-t border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-400">
              {isListening ? (
                <span className="text-red-500 font-medium">🎙️ 正在录音，请说话...</span>
              ) : voiceSupported ? (
                <span>点击麦克风按钮语音输入</span>
              ) : (
                <span>当前浏览器不支持语音识别</span>
              )}
            </span>
          </div>
          {/* Pending image previews */}
          {pendingImages.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {pendingImages.map((img, i) => (
                <div key={i} className="relative group">
                  <img
                    src={img}
                    alt="preview"
                    className="w-16 h-16 rounded-lg object-cover border border-gray-200"
                  />
                  <button
                    onClick={() => removePendingImage(i)}
                    className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
          {/* Pending file names */}
          {pendingFileNames.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {pendingFileNames.map((name, i) => (
                <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs border border-blue-100">
                  <FileText className="w-3 h-3" />
                  {name}
                  <button
                    onClick={() => removePendingFile(i)}
                    className="ml-0.5 text-blue-400 hover:text-blue-600"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-end gap-3">
            <div className="shrink-0 mb-1 relative">
              <AvatarHomeButton
                source="chat"
                size={80}
                showLevelRing={true}
                showParticles={true}
                onClick={() => setAvatarMenuOpen(!avatarMenuOpen)}
              />
              {/* 角色快捷菜单 */}
              {avatarMenuOpen && (
                <div className="absolute bottom-full left-0 mb-2 w-56 bg-white rounded-xl shadow-lg border border-gray-200 py-2 z-50 animate-in fade-in slide-in-from-bottom-2 duration-200">
                  <div className="px-3 py-2 border-b border-gray-100">
                    <p className="text-xs font-semibold text-gray-700">🤖 小腾的状态</p>
                    <p className="text-[10px] text-gray-400 mt-0.5">当前情绪: {_emotion || '聆听中'}</p>
                  </div>
                  <div className="px-3 py-2">
                    <p className="text-[10px] font-medium text-gray-500 mb-1.5">切换人格模式</p>
                    <div className="grid grid-cols-3 gap-1">
                      {personaModes.map((p) => (
                        <button
                          key={p.mode}
                          onClick={async () => {
                            try {
                              await fetch('/ui/api/persona/mode', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ mode: p.mode }),
                              });
                              // FIX: 不再本地 setState，等待 WebSocket persona.changed 广播更新 prop
                              setAvatarMenuOpen(false);
                            } catch {}
                          }}
                          className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                            _persona === p.mode
                              ? 'bg-tent-100 text-tent-700 border border-tent-200'
                              : 'bg-gray-50 text-gray-600 border border-gray-100 hover:bg-gray-100'
                          }`}
                        >
                          {p.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="px-3 py-1.5 border-t border-gray-100">
                    <button
                      onClick={() => { setAvatarMenuOpen(false); onViewProfile?.(); }}
                      className="w-full text-left px-2 py-1.5 rounded text-xs text-gray-600 hover:bg-gray-50 transition-colors"
                    >
                      📋 查看完整档案
                    </button>
                  </div>
                </div>
              )}
            </div>
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onCompositionStart={() => setIsComposing(true)}
                onCompositionEnd={() => setIsComposing(false)}
                onInput={handleInput}
                placeholder={
                  connectionStatus === 'connected'
                    ? '输入任务描述，按 Enter 发送，Shift+Enter 换行...'
                    : '等待连接...'
                }
                disabled={connectionStatus !== 'connected'}
                rows={1}
                className={`w-full resize-none rounded-xl border border-gray-200 bg-gray-50 text-sm text-gray-900 placeholder-gray-400 focus:border-tent-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-tent-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed ${isMobile ? 'px-3 py-2 pr-10' : 'px-4 py-3 pr-12'}`}
              />
              <div className="absolute right-3 bottom-3 text-xs text-gray-400">
                {input.length > 0 && `${input.length} 字`}
              </div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,.pdf,.docx,.xlsx,.txt,.md,.csv,.json,.py,.js,.ts,.html,.css,.yaml,.yml"
              multiple
              onChange={handleFileSelect}
              className="hidden"
            />
            <input
              ref={describeInputRef}
              type="file"
              accept="image/*"
              onChange={handleSmartDescribe}
              className="hidden"
            />
            <button
              onClick={() => describeInputRef.current?.click()}
              disabled={connectionStatus !== 'connected' || describeLoading}
              className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-colors shadow-sm ${
                describeLoading
                  ? 'bg-amber-100 text-amber-600 animate-pulse'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              } disabled:opacity-40 disabled:cursor-not-allowed`}
              title="拍照描述需求（智能识别图片内容生成任务）"
            >
              {describeLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Tent className="w-4 h-4" />}
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={connectionStatus !== 'connected' || fileUploading}
              className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-colors shadow-sm ${
                fileUploading
                  ? 'bg-blue-100 text-blue-600 animate-pulse'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              } disabled:opacity-40 disabled:cursor-not-allowed`}
              title="上传文件（图片、PDF、DOCX、Excel、代码文件等）"
            >
              {fileUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ImagePlus className="w-4 h-4" />}
            </button>
            {voiceSupported && (
              <button
                onClick={isListening ? stopListening : startListening}
                disabled={connectionStatus !== 'connected'}
                className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-colors shadow-sm ${
                  isListening
                    ? 'bg-red-500 text-white animate-pulse'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                } disabled:opacity-40 disabled:cursor-not-allowed`}
                title={isListening ? '停止录音' : '语音输入'}
              >
                {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>
            )}
            <button
              onClick={handleSend}
              disabled={(!input.trim() && !pendingImages.length) || connectionStatus !== 'connected'}
              className="shrink-0 w-10 h-10 rounded-xl bg-tent-600 text-white flex items-center justify-center hover:bg-tent-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <div className="mt-1.5 flex items-center justify-between text-xs text-gray-400">
            <span>Tent OS 可能产生错误信息，请验证重要结果</span>
            {connectionStatus !== 'connected' && (
              <span className="text-amber-500">WebSocket {connectionStatus === 'connecting' ? '连接中...' : '已断开'}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

function QuickAction({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-600 bg-white border border-gray-200 hover:border-tent-300 hover:text-tent-600 hover:bg-tent-50 transition-all shadow-sm"
    >
      {icon}
      {label}
    </button>
  );
}
