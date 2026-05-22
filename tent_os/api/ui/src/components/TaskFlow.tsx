import { useState, useEffect } from 'react';
import {
  GitBranch,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronRight,
  Wrench,
} from 'lucide-react';
import type { TaskSession } from '@/types';

interface TaskFlowProps {
  sessions: TaskSession[];
}

interface TaskDetail {
  status: string;
  result?: unknown;
  steps?: Array<{ step: number; action: string; status: string }>;
}

export function TaskFlow({ sessions }: TaskFlowProps) {
  const [expandedSession, setExpandedSession] = useState<string | null>(null);
  const [allSessions, setAllSessions] = useState<TaskSession[]>([]);
  const [details, setDetails] = useState<Record<string, TaskDetail>>({});
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 合并 WS 实时会话 + REST API 历史会话
  useEffect(() => {
    fetch('/ui/api/tasks?limit=50')
      .then((r) => r.json())
      .then((data) => {
        if (data.tasks) {
          const mapped: TaskSession[] = data.tasks.map((t: Record<string, unknown>) => ({
            sessionId: t.session_id as string,
            status: (t.status as string) || 'unknown',
            task: (t.task as string) || '未命名任务',
            messages: [],
            createdAt: new Date(t.created_at as string).getTime(),
            updatedAt: new Date(t.updated_at as string).getTime(),
          }));
          const wsIds = new Set(sessions.map((s) => s.sessionId));
          const filtered = mapped.filter((m) => !wsIds.has(m.sessionId));
          setAllSessions([...sessions, ...filtered]);
          setError(null);
        }
      })
      .catch((e) => {
        setAllSessions(sessions);
        setError('加载任务列表失败');
        console.warn('TaskFlow加载失败:', e);
      });
  }, [sessions]);

  // 展开时动态获取任务详情
  useEffect(() => {
    if (!expandedSession) return;

    // 如果已有该 session 的 messages（来自 WS 实时数据），不需要额外获取
    const wsSession = sessions.find((s) => s.sessionId === expandedSession);
    if (wsSession && wsSession.messages.length > 0) return;

    setLoadingDetail(expandedSession);
    fetch(`/api/v1/tasks/${encodeURIComponent(expandedSession)}`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.error) {
          setDetails((prev) => ({
            ...prev,
            [expandedSession]: {
              status: data.status,
              result: data.result,
              steps: data.result?.steps || data.result?.plan?.steps,
            },
          }));
        }
      })
      .catch(() => {
        // 静默失败，保持原有展示
      })
      .finally(() => setLoadingDetail(null));
  }, [expandedSession, sessions]);

  const statusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'aborted':
        return <XCircle className="w-4 h-4 text-gray-500" />;
      case 'executing':
      case 'planning':
        return <Loader2 className="w-4 h-4 text-tent-500 animate-spin" />;
      default:
        return <Clock className="w-4 h-4 text-amber-500" />;
    }
  };

  const statusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'border-green-200 bg-green-50';
      case 'failed':
        return 'border-red-200 bg-red-50';
      case 'aborted':
        return 'border-gray-200 bg-gray-50';
      case 'executing':
      case 'planning':
        return 'border-tent-200 bg-tent-50';
      default:
        return 'border-amber-200 bg-amber-50';
    }
  };

  const getStepCount = (session: TaskSession): string => {
    const wsSteps = session.messages.filter((m) => m.role === 'tool').length;
    if (wsSteps > 0) return `${wsSteps} 个步骤`;
    const detail = details[session.sessionId];
    if (detail?.steps && detail.steps.length > 0) return `${detail.steps.length} 个步骤`;
    if (detail?.result) return '有结果';
    return '-';
  };

  const renderExpandedContent = (session: TaskSession) => {
    const wsMessages = session.messages.filter((m) => m.role === 'tool' || m.role === 'system');
    if (wsMessages.length > 0) {
      return (
        <div className="mt-3 space-y-2">
          {wsMessages.map((msg, idx) => (
            <div key={msg.id} className="flex items-start gap-3 p-3 bg-white/60 rounded-lg">
              <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center shrink-0 text-xs font-medium text-gray-500">
                {idx + 1}
              </div>
              <div className="flex-1">
                <p className="text-sm text-gray-700">{msg.content}</p>
                {msg.metadata && (
                  <pre className="mt-1.5 p-2 bg-gray-100 rounded text-xs text-gray-600 overflow-x-auto">
                    {JSON.stringify(msg.metadata, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          ))}
        </div>
      );
    }

    const detail = details[session.sessionId];
    if (loadingDetail === session.sessionId) {
      return (
        <div className="mt-3 flex items-center gap-2 text-sm text-gray-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          加载执行详情...
        </div>
      );
    }

    if (detail?.steps && detail.steps.length > 0) {
      return (
        <div className="mt-3 space-y-2">
          {detail.steps.map((step: any, idx: number) => (
            <div key={idx} className="flex items-start gap-3 p-3 bg-white/60 rounded-lg">
              <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center shrink-0 text-xs font-medium text-gray-500">
                {idx + 1}
              </div>
              <div className="flex-1">
                <p className="text-sm text-gray-700">{step.action || step.description || '执行步骤'}</p>
                <span className="text-[10px] text-gray-400">{step.status || 'completed'}</span>
              </div>
            </div>
          ))}
        </div>
      );
    }

    if (detail?.result) {
      return (
        <div className="mt-3">
          <pre className="p-3 bg-gray-100 rounded text-xs text-gray-600 overflow-x-auto">
            {JSON.stringify(detail.result, null, 2)}
          </pre>
        </div>
      );
    }

    return <p className="mt-3 text-sm text-gray-400 py-2">暂无执行步骤</p>;
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-tent-100 flex items-center justify-center">
              <GitBranch className="w-5 h-5 text-tent-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">任务流</h2>
              <p className="text-sm text-gray-500">
                {allSessions.length} 个会话 · {allSessions.filter((s) => s.status === 'completed').length} 完成 ·{' '}
                {allSessions.filter((s) => s.status === 'failed').length} 失败
              </p>
            </div>
          </div>
          {error && (
            <span className="text-xs text-red-500 bg-red-50 px-2 py-1 rounded border border-red-200">
              {error}
            </span>
          )}
        </div>

        <div className="space-y-3">
          {allSessions.map((session) => (
            <div
              key={session.sessionId}
              className={`rounded-xl border ${statusColor(session.status)} overflow-hidden transition-all`}
            >
              <button
                onClick={() =>
                  setExpandedSession(expandedSession === session.sessionId ? null : session.sessionId)
                }
                className="w-full px-5 py-4 flex items-center gap-4 text-left"
              >
                {expandedSession === session.sessionId ? (
                  <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                )}
                {statusIcon(session.status)}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{session.task}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {session.sessionId.slice(0, 8)}... · {new Date(session.createdAt).toLocaleString('zh-CN')}
                  </p>
                </div>
                <span className="text-xs text-gray-400 shrink-0 flex items-center gap-1">
                  <Wrench className="w-3 h-3" />
                  {getStepCount(session)}
                </span>
              </button>

              {expandedSession === session.sessionId && (
                <div className="px-5 pb-4 border-t border-black/5">
                  {renderExpandedContent(session)}
                </div>
              )}
            </div>
          ))}

          {allSessions.length === 0 && (
            <div className="text-center py-16 text-gray-400">
              <Clock className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>暂无任务记录</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
