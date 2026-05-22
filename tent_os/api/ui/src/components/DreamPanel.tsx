import { useState, useEffect, useCallback, useMemo } from 'react';
import { Moon, Sparkles, Zap, BookOpen, Clock, ToggleLeft, ToggleRight, Loader2 } from 'lucide-react';
import { AvatarHomeButton } from './AvatarHomeButton';

interface DreamEntry {
  phase: string;
  description: string;
  detail: string;
  timestamp: string;
}

interface DreamRecord {
  id: string;
  started_at: string;
  ended_at: string;
  status: string;
  depth: number;
  entries: DreamEntry[];
  insights: string[];
  summary: string;
  memories_processed: number;
  rules_extracted: number;
  contradictions_found: number;
}

interface DreamStatus {
  enabled: boolean;
  is_dreaming: boolean;
  current_dream_id: string | null;
  schedule: string;
  depth: number;
  stats: {
    total_dreams: number;
    total_memories_processed: number;
    total_rules_extracted: number;
    total_contradictions_found: number;
  };
}

interface DreamPanelProps {
  emotion?: string;
  persona?: string;
}

// 星空背景组件
function Starfield() {
  const stars = useMemo(() => {
    return Array.from({ length: 60 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() * 2 + 0.5,
      opacity: Math.random() * 0.5 + 0.2,
      twinkleSpeed: Math.random() * 3 + 2,
    }));
  }, []);
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {stars.map((s) => (
        <div
          key={s.id}
          className="absolute rounded-full bg-white"
          style={{
            left: `${s.x}%`,
            top: `${s.y}%`,
            width: s.size,
            height: s.size,
            opacity: s.opacity,
            animation: `twinkle ${s.twinkleSpeed}s ease-in-out infinite alternate`,
          }}
        />
      ))}
      <style>{`
        @keyframes twinkle {
          0% { opacity: 0.2; transform: scale(1); }
          100% { opacity: 0.8; transform: scale(1.5); }
        }
      `}</style>
    </div>
  );
}

export function DreamPanel({ emotion: _emotion = 'listening', persona: _persona = 'work' }: DreamPanelProps) {
  const [status, setStatus] = useState<DreamStatus | null>(null);
  const [dreams, setDreams] = useState<DreamRecord[]>([]);
  const [selectedDream, setSelectedDream] = useState<DreamRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [levelInfo, setLevelInfo] = useState<{ level: number; title: string }>({ level: 1, title: '新手' });

  const loadData = useCallback(async () => {
    try {
      const [statusRes, diaryRes] = await Promise.all([
        fetch('/ui/api/dreaming/status'),
        fetch('/ui/api/dreaming/diary'),
      ]);
      const s = await statusRes.json();
      const d = await diaryRes.json();
      setStatus(s);
      setDreams(d.dreams || []);
      // 加载等级
      try {
        const sixRes = await fetch('/ui/api/six-axis').then((r) => r.json());
        if (sixRes.title) {
          const thresholds = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
          const avg = sixRes.avg_score || 0;
          let level = 1;
          for (let i = 1; i < thresholds.length; i++) { if (avg >= thresholds[i]) level = i + 1; else break; }
          setLevelInfo({ level, title: sixRes.title });
        }
      } catch {}
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const toggleDreaming = async () => {
    if (!status) return;
    const newEnabled = !status.enabled;
    await fetch('/ui/api/dreaming/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: newEnabled }),
    });
    setStatus({ ...status, enabled: newEnabled });
  };

  const triggerDream = async () => {
    setTriggering(true);
    try {
      await fetch('/ui/api/dreaming/trigger', { method: 'POST' });
      await loadData();
    } finally {
      setTriggering(false);
    }
  };

  const phaseIcon = (phase: string) => {
    switch (phase) {
      case 'compress': return <Zap className="w-4 h-4 text-purple-500" />;
      case 'associate': return <Sparkles className="w-4 h-4 text-blue-500" />;
      case 'contradict': return <BookOpen className="w-4 h-4 text-amber-500" />;
      case 'insight': return <Moon className="w-4 h-4 text-tent-500" />;
      default: return <Moon className="w-4 h-4 text-gray-400" />;
    }
  };

  const phaseLabel = (phase: string) => {
    switch (phase) {
      case 'compress': return '记忆压缩';
      case 'associate': return '关联构建';
      case 'contradict': return '矛盾检测';
      case 'insight': return '模式发现';
      default: return phase;
    }
  };

  return (
    <div className="h-full overflow-y-auto relative bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">
      <Starfield />
      <div className="relative z-10 max-w-4xl mx-auto px-6 py-5">
        {/* Header — 角色化梦境入口 */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="relative">
              <AvatarHomeButton source="dream" size={100} showLevelRing={false} showParticles={false} />
              {/* Zzz 飘浮动画 */}
              <div className="absolute -top-2 -right-2 text-indigo-300 text-sm font-bold animate-bounce" style={{ animationDuration: '2s' }}>Z</div>
              <div className="absolute -top-4 right-2 text-indigo-400 text-xs font-bold animate-bounce" style={{ animationDuration: '2.5s', animationDelay: '0.5s' }}>z</div>
              <div className="absolute top-0 -right-4 text-indigo-500 text-[10px] font-bold animate-bounce" style={{ animationDuration: '3s', animationDelay: '1s' }}>z</div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-100">梦境模式</h2>
                <span className="text-[10px] font-medium px-2 py-0.5 bg-indigo-900/50 text-indigo-300 rounded-full border border-indigo-700/40">
                  Lv.{levelInfo.level} {levelInfo.title}
                </span>
              </div>
              <p className="text-sm text-slate-400">系统空闲时自动整理记忆</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {status && (
              <button
                onClick={toggleDreaming}
                title={status.enabled ? '点击禁用' : '点击启用梦境模式'}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  status.enabled
                    ? 'bg-indigo-900/50 text-indigo-300 hover:bg-indigo-800/50 border border-indigo-700/40'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-slate-700/50'
                }`}
              >
                {status.enabled ? <ToggleRight className="w-5 h-5" /> : <ToggleLeft className="w-5 h-5" />}
                {status.enabled ? '已启用' : '未启用'}
              </button>
            )}
            <button
              onClick={triggerDream}
              disabled={triggering || !status?.enabled}
              title={status?.enabled ? '手动触发一次梦境' : '梦境模式未启用'}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600/80 text-white hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors border border-indigo-500/40"
            >
              {triggering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              立即做梦
            </button>
          </div>
        </div>

        {/* Status Card */}
        {status && (
          <div className={`rounded-xl border p-5 mb-6 ${
            status.is_dreaming
              ? 'bg-indigo-900/30 border-indigo-500/40'
              : 'bg-slate-800/60 border-slate-700/60'
          }`}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Moon className={`w-5 h-5 ${status.is_dreaming ? 'text-indigo-400 animate-pulse' : 'text-slate-500'}`} />
                <span className="font-semibold text-slate-200">
                  {status.is_dreaming ? '正在梦境中...' : status.enabled ? '等待入梦' : '梦境已关闭'}
                </span>
              </div>
              {status.is_dreaming && status.current_dream_id && (
                <span className="text-xs text-indigo-400 font-mono">{status.current_dream_id}</span>
              )}
            </div>

            <div className="grid grid-cols-4 gap-3">
              <div className="bg-slate-800/80 rounded-lg border border-slate-700/50 p-3">
                <p className="text-xs text-slate-400 mb-1">总梦境次数</p>
                <p className="text-xl font-bold text-slate-100">{status.stats.total_dreams}</p>
              </div>
              <div className="bg-slate-800/80 rounded-lg border border-slate-700/50 p-3">
                <p className="text-xs text-slate-400 mb-1">整理记忆</p>
                <p className="text-xl font-bold text-purple-400">{status.stats.total_memories_processed}</p>
              </div>
              <div className="bg-slate-800/80 rounded-lg border border-slate-700/50 p-3">
                <p className="text-xs text-slate-400 mb-1">提取规则</p>
                <p className="text-xl font-bold text-tent-400">{status.stats.total_rules_extracted}</p>
              </div>
              <div className="bg-slate-800/80 rounded-lg border border-slate-700/50 p-3">
                <p className="text-xs text-slate-400 mb-1">发现矛盾</p>
                <p className="text-xl font-bold text-amber-400">{status.stats.total_contradictions_found}</p>
              </div>
            </div>

            <div className="mt-3 flex items-center gap-4 text-xs text-slate-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                计划: {status.schedule}
              </span>
              <span>深度: {status.depth}/5</span>
            </div>
          </div>
        )}

        {/* Dream Diary */}
        <h3 className="text-sm font-semibold text-slate-200 mb-3">梦境日记</h3>
        <div className="space-y-2">
          {loading ? (
            <div className="text-center py-12 text-slate-500">加载中...</div>
          ) : dreams.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <Moon className="w-12 h-12 mx-auto mb-3 text-slate-600" />
              <p>暂无梦境记录</p>
              <p className="text-xs mt-1 text-slate-600">系统将在空闲时自动进入梦境</p>
            </div>
          ) : (
            dreams.map((dream) => (
              <div
                key={dream.id}
                className={`bg-slate-800/60 rounded-xl border overflow-hidden transition-all ${
                  selectedDream?.id === dream.id ? 'border-indigo-500/40 shadow-sm' : 'border-slate-700/50 hover:border-slate-600/50'
                }`}
              >
                <button
                  onClick={() => setSelectedDream(selectedDream?.id === dream.id ? null : dream)}
                  className="w-full px-5 py-4 flex items-center gap-4 text-left"
                >
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                    dream.status === 'completed' ? 'bg-indigo-900/50' : 'bg-slate-700/50'
                  }`}>
                    <Moon className={`w-5 h-5 ${dream.status === 'completed' ? 'text-indigo-400' : 'text-slate-500'}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-slate-200">{dream.id}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        dream.status === 'completed'
                          ? 'bg-green-900/40 text-green-400 border border-green-700/40'
                          : 'bg-indigo-900/40 text-indigo-400 border border-indigo-700/40'
                      }`}>
                        {dream.status === 'completed' ? '已完成' : '进行中'}
                      </span>
                    </div>
                    <p className="text-sm text-slate-400 truncate">{dream.summary || '无摘要'}</p>
                  </div>
                  <div className="text-right shrink-0 text-xs text-slate-500">
                    <p>{new Date(dream.started_at).toLocaleString('zh-CN')}</p>
                    <p className="mt-0.5">深度 {dream.depth}</p>
                  </div>
                </button>

                {selectedDream?.id === dream.id && (
                  <div className="px-5 pb-4 border-t border-slate-700/50">
                    {/* Entries */}
                    <div className="mt-3 space-y-2">
                      {dream.entries.map((entry, idx) => (
                        <div key={idx} className="flex items-start gap-3 p-3 bg-slate-800/80 rounded-lg">
                          {phaseIcon(entry.phase)}
                          <div className="flex-1">
                            <p className="text-sm font-medium text-slate-300">{phaseLabel(entry.phase)}</p>
                            <p className="text-sm text-slate-400">{entry.description}</p>
                            {entry.detail && (
                              <p className="text-xs text-slate-500 mt-1">{entry.detail}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Insights */}
                    {dream.insights && dream.insights.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-slate-500 mb-2">洞察</p>
                        <div className="space-y-1">
                          {dream.insights.map((insight, idx) => (
                            <div key={idx} className="flex items-start gap-2 p-2 bg-indigo-900/20 rounded-lg">
                              <Sparkles className="w-3.5 h-3.5 text-indigo-400 mt-0.5 shrink-0" />
                              <p className="text-sm text-slate-300">{insight}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Stats */}
                    <div className="mt-3 flex items-center gap-4 text-xs text-slate-500">
                      <span>记忆 {dream.memories_processed}</span>
                      <span>规则 {dream.rules_extracted}</span>
                      <span>矛盾 {dream.contradictions_found}</span>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
