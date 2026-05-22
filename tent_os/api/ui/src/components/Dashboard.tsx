import { useState, useEffect } from 'react';
import {
  Zap,
  Activity,
  ChevronRight,
  ToggleLeft,
  ToggleRight,
  Cpu,
  Shield,
} from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';
import type { TaskSession } from '@/types';

interface DashboardProps {
  sessions: TaskSession[];
  onSelectSession: (id: string) => void;
  onTabChange: (tab: 'chat') => void;
  emotion?: string;
  persona?: string;
}

interface SystemStats {
  auto_approve: boolean;
  executor_mode: string;
  cognitive_budget: number;
  brain_v2: boolean;
  total_tokens: number;
  total_calls: number;
  today_tokens: number;
  today_calls: number;
  avg_latency_ms: number;
  active_sessions: number;
  graph_nodes: number;
  rules_total: number;
  memory_files: number;
}

export function Dashboard({ sessions, onSelectSession, onTabChange, emotion = 'listening' }: DashboardProps) {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [compressing, setCompressing] = useState(false);
  const [physicalStatus, setPhysicalStatus] = useState<{enabled: boolean; providers: Array<{name: string; enabled: boolean}>; active_tasks: number} | null>(null);
  const { showToast } = useToast();

  useEffect(() => {
    const load = async () => {
      try {
        const [settingsRes, telemetryRes, modeRes] = await Promise.all([
          fetch('/ui/api/settings').then((r) => r.json()),
          fetch('/ui/api/telemetry').then((r) => r.json()),
          fetch('/ui/api/executor/mode').then((r) => r.json()).catch(() => ({ mode: 'local' })),
        ]);

        setStats({
          auto_approve: settingsRes.settings?.auto_approve ?? true,
          executor_mode: modeRes.mode ?? 'local',
          cognitive_budget: settingsRes.settings?.cognitive_budget_seconds ?? 300,
          brain_v2: settingsRes.settings?.brain_v2_enabled ?? true,
          total_tokens: telemetryRes.llm?.total_tokens ?? 0,
          total_calls: telemetryRes.llm?.total_calls ?? 0,
          today_tokens: telemetryRes.llm?.today_tokens ?? 0,
          today_calls: telemetryRes.llm?.today_calls ?? 0,
          avg_latency_ms: telemetryRes.llm?.avg_latency_ms ?? 0,
          active_sessions: telemetryRes.llm?.active_sessions ?? 0,
          graph_nodes: telemetryRes.memory?.graph_nodes ?? 0,
          rules_total: telemetryRes.rules?.total ?? 0,
          memory_files: telemetryRes.memory?.files ?? 0,
        });
      } catch (e) {
        showToast('Dashboard 加载失败，请检查网络连接', 'error');
      } finally {
        setLoading(false);
      }
    };
    const loadPhysical = async () => {
      try {
        const resp = await fetch('/ui/api/physical/status');
        const data = await resp.json();
        setPhysicalStatus(data);
      } catch {
        setPhysicalStatus(null);
      }
    };
    load();
    loadPhysical();
    const interval = setInterval(load, 30000);
    const physInterval = setInterval(loadPhysical, 60000);
    return () => {
      clearInterval(interval);
      clearInterval(physInterval);
    };
  }, []);

  const toggleSetting = async (key: string, value: boolean | number) => {
    setUpdating(key);
    const previousValue = stats ? (key === 'brain_v2_enabled' ? stats.brain_v2 : (stats as unknown as Record<string, unknown>)[key]) : undefined;
    try {
      const resp = await fetch('/ui/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });
      if (resp.ok) {
        await resp.json();
        // 键名映射：后端设置键名 vs 前端 state 键名
        const stateKeyMap: Record<string, string> = {
          brain_v2_enabled: 'brain_v2',
        };
        const stateKey = stateKeyMap[key] || key;
        setStats((prev) => (prev ? { ...prev, [stateKey]: value } : null));
        showToast('设置已更新', 'success');
      } else {
        const err = await resp.json().catch(() => ({}));
        showToast(err.detail || '设置更新失败', 'error');
        // 回滚
        if (previousValue !== undefined) {
          setStats((prev) => (prev ? { ...prev, [key === 'brain_v2_enabled' ? 'brain_v2' : key]: previousValue } : null));
        }
      }
    } catch (e) {
      showToast('设置更新失败，请检查网络', 'error');
      // 回滚
      if (previousValue !== undefined) {
        setStats((prev) => (prev ? { ...prev, [key === 'brain_v2_enabled' ? 'brain_v2' : key]: previousValue } : null));
      }
    } finally {
      setUpdating(null);
    }
  };

  const setExecutorMode = async (mode: string) => {
    setUpdating('executor_mode');
    const previousMode = stats?.executor_mode ?? 'local';
    // 乐观更新 UI
    setStats((prev) => (prev ? { ...prev, executor_mode: mode } : null));
    try {
      const resp = await fetch('/ui/api/executor/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      if (resp.ok) {
        await resp.json();
        showToast(`执行模式已切换为 ${mode}`, 'success');
      } else {
        const err = await resp.json().catch(() => ({}));
        showToast(err.detail || '模式切换失败', 'error');
        // 回滚
        setStats((prev) => (prev ? { ...prev, executor_mode: previousMode } : null));
      }
    } catch (e) {
      showToast('模式切换失败，请检查网络', 'error');
      // 回滚
      setStats((prev) => (prev ? { ...prev, executor_mode: previousMode } : null));
    } finally {
      setUpdating(null);
    }
  };

  const triggerMemoryCompress = async () => {
    setCompressing(true);
    try {
      const resp = await fetch('/ui/api/memory/compress', { method: 'POST' });
      const data = await resp.json();
      if (data.error) {
        showToast(`压缩失败: ${data.error}`, 'error');
      } else {
        showToast(`记忆压缩完成: ${data.compressed_count || 0} 条 L0→L1`, 'success');
      }
    } catch (e) {
      showToast('记忆压缩请求失败', 'error');
    } finally {
      setCompressing(false);
    }
  };

  const setCognitiveBudget = async (seconds: number) => {
    const clamped = Math.max(30, Math.min(86400, seconds));
    setUpdating('cognitive_budget');
    const previousBudget = stats?.cognitive_budget ?? 86400;
    setStats((prev) => (prev ? { ...prev, cognitive_budget: clamped } : null));
    try {
      const resp = await fetch('/ui/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cognitive_budget_seconds: clamped }),
      });
      if (resp.ok) {
        await resp.json();
        showToast('认知预算已更新', 'success');
      } else {
        const err = await resp.json().catch(() => ({}));
        showToast(err.detail || '认知预算更新失败', 'error');
        setStats((prev) => (prev ? { ...prev, cognitive_budget: previousBudget } : null));
      }
    } catch (e) {
      showToast('认知预算更新失败，请检查网络', 'error');
      setStats((prev) => (prev ? { ...prev, cognitive_budget: previousBudget } : null));
    } finally {
      setUpdating(null);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-gray-400">加载中...</div>
      </div>
    );
  }

  const recentSessions = sessions
    .filter((s) => s.messages.length > 0)
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, 5);

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-gray-900">系统概览</h2>
            {emotion && emotion !== 'listening' && (
              <span className="flex items-center gap-1.5 px-2 py-0.5 bg-amber-50 text-amber-600 border border-amber-200 rounded-full text-[10px] font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                AI 情绪: {emotion}
              </span>
            )}
          </div>
          {stats && (
            <span className="text-xs text-gray-400">
              延迟 {stats.avg_latency_ms > 0 ? `${stats.avg_latency_ms.toFixed(0)}ms` : '--'}
            </span>
          )}
        </div>

        {/* 统计卡片 */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={<Zap className="w-4 h-4 text-amber-500" />}
            label="Token消耗"
            value={stats ? `${(stats.today_tokens / 1000).toFixed(1)}k` : '--'}
            sub={`今日 ${stats?.today_calls ?? 0} 次 · 累计 ${((stats?.total_tokens ?? 0) / 1000).toFixed(1)}k`}
            trend={stats ? (stats.today_tokens > 5000 ? 'high' : stats.today_tokens > 1000 ? 'normal' : 'low') : undefined}
          />
          <StatCard
            icon={<Cpu className="w-4 h-4 text-purple-500" />}
            label="认知图谱"
            value={stats ? String(stats.graph_nodes) : '--'}
            sub="记忆节点"
          />
          <StatCard
            icon={<Shield className="w-4 h-4 text-green-500" />}
            label="程序规则"
            value={stats ? String(stats.rules_total) : '--'}
            sub="经验沉淀"
          />
          <StatCard
            icon={<Activity className="w-4 h-4 text-blue-500" />}
            label="活跃会话"
            value={stats ? String(stats.active_sessions) : '--'}
            sub={`文件记忆 ${stats?.memory_files ?? 0}`}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mb-6">
          {/* 系统状态 */}
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-gray-800 mb-3">系统状态</h3>
            <div className="space-y-3">
              <StatusRow
                label="自动确认危险操作"
                status={stats?.auto_approve ? 'on' : 'off'}
                statusText={stats?.auto_approve ? '已开启' : '已关闭'}
              />
              <ModeSelectorRow
                label="执行模式"
                modes={[
                  { value: 'local', label: '本地' },
                  { value: 'sandbox', label: '沙箱' },
                  { value: 'auto', label: '自动' },
                ]}
                current={stats?.executor_mode ?? 'local'}
                onSelect={setExecutorMode}
                updating={updating === 'executor_mode'}
              />
              <NumberAdjustRow
                label="前台汇报周期"
                value={stats?.cognitive_budget ?? 86400}
                min={30}
                max={86400}
                step={300}
                unit="秒"
                onChange={setCognitiveBudget}
                updating={updating === 'cognitive_budget'}
              />
              <StatusRow
                label="深度思考"
                status={stats?.brain_v2 ? 'on' : 'off'}
                statusText={stats?.brain_v2 ? '已启用' : '已禁用'}
              />
            </div>
          </div>

          {/* 快速开关 */}
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-gray-800 mb-3">快速开关</h3>
            <div className="space-y-3">
              <ToggleRow
                label="自动确认危险操作"
                description="覆盖文件、rm、mv等操作自动通过"
                enabled={stats?.auto_approve ?? true}
                onToggle={() => toggleSetting('auto_approve', !(stats?.auto_approve ?? true))}
                updating={updating === 'auto_approve'}
              />
              <ToggleRow
                label="深度思考模式"
                description="启用工作记忆、人格演化、情绪感知"
                enabled={stats?.brain_v2 ?? true}
                onToggle={() => toggleSetting('brain_v2_enabled', !(stats?.brain_v2 ?? true))}
                updating={updating === 'brain_v2_enabled'}
              />
            </div>
          </div>
        </div>

        {/* 物理执行器状态 */}
        {physicalStatus && physicalStatus.enabled && (
          <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
            <h3 className="text-sm font-semibold text-gray-800 mb-3">物理执行器</h3>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                {physicalStatus.providers.map((p) => (
                  <div key={p.name} className={`text-xs px-2 py-1 rounded-full border ${p.enabled ? 'bg-green-50 text-green-700 border-green-200' : 'bg-gray-50 text-gray-400 border-gray-200'}`}>
                    {p.name} {p.enabled ? '在线' : '离线'}
                  </div>
                ))}
              </div>
              {physicalStatus.active_tasks > 0 ? (
                <span className="text-xs text-amber-600 font-medium">{physicalStatus.active_tasks} 个任务执行中</span>
              ) : (
                <span className="text-xs text-gray-400">空闲</span>
              )}
            </div>
            <button
              onClick={async () => {
                if (!confirm('确定要紧急停止所有物理任务吗？')) return;
                try {
                  const resp = await fetch('/ui/api/physical/emergency_stop', { method: 'POST' });
                  if (resp.ok) showToast('紧急停止已发送', 'success');
                  else showToast('紧急停止失败', 'error');
                } catch {
                  showToast('紧急停止请求失败', 'error');
                }
              }}
              className="w-full mt-2 px-3 py-1.5 rounded-lg text-xs font-medium text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors"
            >
              🛑 紧急停止所有物理任务
            </button>
          </div>
        )}

        {/* 记忆维护 */}
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-3">记忆维护</h3>
          <div className="flex items-center justify-between">
            <div className="text-xs text-gray-500">
              <p>手动触发 L0→L1 压缩，减少记忆冗余</p>
              <p className="text-gray-400 mt-0.5">上次: 自动 (每天凌晨 3 点)</p>
            </div>
            <button
              onClick={triggerMemoryCompress}
              disabled={compressing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 border border-purple-200 transition-colors disabled:opacity-50"
            >
              <Cpu className={`w-3.5 h-3.5 ${compressing ? 'animate-spin' : ''}`} />
              {compressing ? '压缩中...' : '立即压缩'}
            </button>
          </div>
        </div>

        {/* 最近会话 */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-3">最近会话</h3>
          {recentSessions.length === 0 ? (
            <p className="text-sm text-gray-400">暂无会话</p>
          ) : (
            <div className="space-y-1">
              {recentSessions.map((s) => (
                <button
                  key={s.sessionId}
                  onClick={() => {
                    onSelectSession(s.sessionId);
                    onTabChange('chat');
                  }}
                  className="w-full flex items-center justify-between px-3 py-2 rounded-md hover:bg-gray-50 text-left group"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-gray-700 truncate">
                      {s.task || '未命名会话'}
                    </p>
                    <p className="text-[10px] text-gray-400">
                      {s.messages.length} 条消息 · {formatTime(s.updatedAt)}
                    </p>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-gray-300 group-hover:text-gray-500" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sub, trend }: { icon: React.ReactNode; label: string; value: string; sub?: string; trend?: 'high' | 'normal' | 'low' }) {
  const trendColor = trend === 'high' ? 'bg-red-100 text-red-600' : trend === 'normal' ? 'bg-amber-100 text-amber-600' : 'bg-green-100 text-green-600';
  const trendLabel = trend === 'high' ? '高' : trend === 'normal' ? '中' : '低';
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs text-gray-500">{label}</span>
        </div>
        {trend && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${trendColor}`}>
            {trendLabel}
          </span>
        )}
      </div>
      <div className="text-xl font-bold text-gray-900">{value}</div>
      {sub && <div className="text-[10px] text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

function StatusRow({
  label,
  status,
  statusText,
}: {
  label: string;
  status: 'on' | 'off' | 'info';
  statusText: string;
}) {
  const statusClass =
    status === 'on'
      ? 'text-green-600 bg-green-50'
      : status === 'off'
      ? 'text-gray-500 bg-gray-100'
      : 'text-blue-600 bg-blue-50';

  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-gray-600">{label}</span>
      <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${statusClass}`}>{statusText}</span>
    </div>
  );
}

function ToggleRow({
  label,
  description,
  enabled,
  onToggle,
  updating,
}: {
  label: string;
  description: string;
  enabled: boolean;
  onToggle: () => void;
  updating: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <div className="text-xs font-medium text-gray-700">{label}</div>
        <div className="text-[10px] text-gray-400">{description}</div>
      </div>
      <button
        onClick={onToggle}
        disabled={updating}
        className={`transition-opacity ${updating ? 'opacity-50' : ''}`}
      >
        {enabled ? (
          <ToggleRight className="w-8 h-8 text-tent-500" />
        ) : (
          <ToggleLeft className="w-8 h-8 text-gray-300" />
        )}
      </button>
    </div>
  );
}

function ModeSelectorRow({
  label,
  modes,
  current,
  onSelect,
  updating,
}: {
  label: string;
  modes: { value: string; label: string }[];
  current: string;
  onSelect: (value: string) => void;
  updating: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-gray-600">{label}</span>
      <div className={`flex items-center gap-1 bg-gray-100 rounded-lg p-0.5 ${updating ? 'opacity-50' : ''}`}>
        {modes.map((m) => (
          <button
            key={m.value}
            onClick={() => onSelect(m.value)}
            disabled={updating}
            className={`px-2.5 py-1 rounded-md text-[10px] font-medium transition-colors ${
              current === m.value
                ? 'bg-white text-tent-700 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function NumberAdjustRow({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
  updating,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  onChange: (v: number) => void;
  updating: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState(String(value));

  const commit = () => {
    const n = parseInt(input, 10);
    if (!isNaN(n)) onChange(n);
    setEditing(false);
  };

  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-gray-600">{label}</span>
      <div className={`flex items-center gap-1 ${updating ? 'opacity-50' : ''}`}>
        <button
          onClick={() => onChange(value - step)}
          disabled={updating || value <= min}
          className="w-5 h-5 flex items-center justify-center rounded bg-gray-100 text-gray-500 text-xs hover:bg-gray-200 disabled:opacity-30"
        >
          −
        </button>
        {editing ? (
          <input
            type="number"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => { if (e.key === 'Enter') commit(); }}
            min={min}
            max={max}
            className="w-14 text-center text-xs border border-gray-200 rounded py-0.5"
            autoFocus
          />
        ) : (
          <button
            onClick={() => { setInput(String(value)); setEditing(true); }}
            className="w-14 text-center text-xs font-medium text-gray-700 hover:text-tent-600"
          >
            {value}{unit}
          </button>
        )}
        <button
          onClick={() => onChange(value + step)}
          disabled={updating || value >= max}
          className="w-5 h-5 flex items-center justify-center rounded bg-gray-100 text-gray-500 text-xs hover:bg-gray-200 disabled:opacity-30"
        >
          +
        </button>
      </div>
    </div>
  );
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
