import { useState, useEffect, useMemo } from 'react';
import {
  Heart, TrendingUp, TrendingDown, Minus, Activity, Brain,
  AlertTriangle, CheckCircle, Clock, Zap, Eye, Mic, MessageSquare,
  ChevronDown, ChevronUp, BarChart3,
} from 'lucide-react';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, BarChart, Bar, Cell,
} from 'recharts';

interface EmotionRecord {
  timestamp: number;
  primary: string;
  intensity: number;
  valence: number;
  arousal: number;
  mixed: Record<string, number>;
  trend: string;
  authenticity: number;
  trigger: string;
}

interface EmotionInsights {
  dominant: string;
  avg_intensity: number;
  authenticity_avg: number;
  diversity: number;
  trend_direction: string;
  record_count: number;
  summary: string;
}

export function EmotionTimelinePanel() {
  const [history, setHistory] = useState<EmotionRecord[]>([]);
  const [insights, setInsights] = useState<EmotionInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [windowHours, setWindowHours] = useState(24);
  const [expandedRecord, setExpandedRecord] = useState<number | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [histRes, insightRes] = await Promise.all([
          fetch(`/ui/api/emotion/fusion/history?user_id=web_user&hours=${windowHours}&limit=200`).then(r => r.json()).catch(() => ({ records: [] })),
          fetch(`/ui/api/emotion/fusion/insights?user_id=web_user&window_hours=${windowHours}`).then(r => r.json()).catch(() => null),
        ]);
        setHistory(histRes.records || []);
        setInsights(insightRes);
      } catch {
        setHistory([]);
        setInsights(null);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [windowHours]);

  const chartData = useMemo(() => {
    return [...history].reverse().map((r) => ({
      time: new Date(r.timestamp * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      valence: r.valence,
      arousal: r.arousal,
      intensity: r.intensity,
      primary: r.primary,
    }));
  }, [history]);

  const emotionDistribution = useMemo(() => {
    const counts: Record<string, number> = {};
    history.forEach((r) => {
      counts[r.primary] = (counts[r.primary] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([emotion, count]) => ({ emotion, count, pct: count / history.length }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);
  }, [history]);

  const emotionColor = (emotion: string) => {
    const map: Record<string, string> = {
      happy: '#22c55e', joy: '#22c55e', excited: '#f59e0b',
      sad: '#3b82f6', sadness: '#3b82f6', tired: '#6b7280',
      angry: '#ef4444', anger: '#ef4444', frustrated: '#f97316',
      fear: '#a855f7', fearful: '#a855f7', anxious: '#a855f7',
      neutral: '#9ca3af', surprise: '#fbbf24', disgust: '#84cc16',
      sleepy: '#6366f1', thinking: '#14b8a6', listening: '#10b981',
    };
    return map[emotion] || '#9ca3af';
  };

  const trendIcon = (trend: string) => {
    switch (trend) {
      case 'escalating': return <TrendingUp className="w-3.5 h-3.5 text-red-500" />;
      case 'de-escalating': return <TrendingDown className="w-3.5 h-3.5 text-green-500" />;
      default: return <Minus className="w-3.5 h-3.5 text-gray-400" />;
    }
  };

  const authenticityBadge = (auth: number) => {
    if (auth >= 0.7) return { icon: <CheckCircle className="w-3 h-3 text-green-500" />, text: '真实', color: 'bg-green-50 text-green-700 border-green-200' };
    if (auth >= 0.4) return { icon: <Activity className="w-3 h-3 text-amber-500" />, text: '存疑', color: 'bg-amber-50 text-amber-700 border-amber-200' };
    return { icon: <AlertTriangle className="w-3 h-3 text-red-500" />, text: '强撑', color: 'bg-red-50 text-red-700 border-red-200' };
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-gray-400">加载情绪数据中...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Heart className="w-5 h-5 text-pink-500" />
            <h2 className="text-lg font-bold text-gray-900">情绪记忆时间线</h2>
            <span className="text-xs text-gray-400">多模态融合 · 文本 + 视觉 + 语音</span>
          </div>
          <div className="flex items-center gap-2">
            {([1, 6, 24, 72, 168] as const).map((h) => (
              <button
                key={h}
                onClick={() => setWindowHours(h)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  windowHours === h
                    ? 'bg-pink-50 text-pink-700 border border-pink-200'
                    : 'bg-white text-gray-500 border border-gray-200 hover:bg-gray-50'
                }`}
              >
                {h >= 24 ? `${h / 24}天` : `${h}小时`}
              </button>
            ))}
          </div>
        </div>

        {/* Insights Cards */}
        {insights && (
          <div className="grid grid-cols-5 gap-3 mb-6">
            <InsightCard
              icon={<Heart className="w-4 h-4 text-pink-500" />}
              label="主导情绪"
              value={insights.dominant}
              sub={`${insights.record_count} 条记录`}
              accent="pink"
            />
            <InsightCard
              icon={<Zap className="w-4 h-4 text-amber-500" />}
              label="平均强度"
              value={`${(insights.avg_intensity * 100).toFixed(0)}%`}
              sub={`多样性: ${insights.diversity}`}
              accent="amber"
            />
            <InsightCard
              icon={<CheckCircle className="w-4 h-4 text-green-500" />}
              label="真实性"
              value={`${(insights.authenticity_avg * 100).toFixed(0)}%`}
              sub={insights.authenticity_avg < 0.5 ? '可能存在掩饰' : '表达真实'}
              accent="green"
            />
            <InsightCard
              icon={insights.trend_direction === 'improving' ? <TrendingUp className="w-4 h-4 text-green-500" /> : insights.trend_direction === 'declining' ? <TrendingDown className="w-4 h-4 text-red-500" /> : <Minus className="w-4 h-4 text-gray-400" />}
              label="情绪趋势"
              value={insights.trend_direction === 'improving' ? '上升' : insights.trend_direction === 'declining' ? '下降' : '平稳'}
              sub="基于 Valence 变化"
              accent={insights.trend_direction === 'improving' ? 'green' : insights.trend_direction === 'declining' ? 'red' : 'gray'}
            />
            <InsightCard
              icon={<Brain className="w-4 h-4 text-purple-500" />}
              label="情绪类型"
              value={`${insights.diversity} 种`}
              sub="检测到的情绪种类"
              accent="purple"
            />
          </div>
        )}

        {/* Charts Row */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          {/* VA Timeline */}
          <div className="col-span-2 bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="w-4 h-4 text-pink-500" />
              <h3 className="text-sm font-semibold text-gray-800">情绪心电图（Valence · Arousal）</h3>
            </div>
            {chartData.length > 0 ? (
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="valenceGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ec4899" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#ec4899" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="arousalGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                    <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#9ca3af' }} interval="preserveStartEnd" />
                    <YAxis domain={[-1, 1]} tick={{ fontSize: 10, fill: '#9ca3af' }} ticks={[-1, -0.5, 0, 0.5, 1]} />
                    <RechartsTooltip
                      content={({ active, payload }) => {
                        if (!active || !payload || !payload.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs">
                            <div className="font-medium text-gray-800 mb-1">{d.time}</div>
                            <div className="flex items-center gap-3">
                              <span className="text-pink-600">Valence: {d.valence.toFixed(2)}</span>
                              <span className="text-purple-600">Arousal: {d.arousal.toFixed(2)}</span>
                            </div>
                            <div className="text-gray-500 mt-0.5">{d.primary}</div>
                          </div>
                        );
                      }}
                    />
                    <Area type="monotone" dataKey="valence" stroke="#ec4899" strokeWidth={2} fill="url(#valenceGrad)" dot={false} />
                    <Area type="monotone" dataKey="arousal" stroke="#8b5cf6" strokeWidth={2} fill="url(#arousalGrad)" dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-52 flex items-center justify-center">
                <p className="text-xs text-gray-400">暂无情绪数据</p>
              </div>
            )}
            <div className="flex items-center gap-4 mt-3 text-[10px] text-gray-400">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-pink-500" />Valence（愉悦度）</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-500" />Arousal（唤醒度）</span>
            </div>
          </div>

          {/* Distribution */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="w-4 h-4 text-purple-500" />
              <h3 className="text-sm font-semibold text-gray-800">情绪分布</h3>
            </div>
            {emotionDistribution.length > 0 ? (
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={emotionDistribution} layout="vertical" margin={{ top: 0, right: 20, left: 0, bottom: 0 }}>
                    <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                    <YAxis type="category" dataKey="emotion" tick={{ fontSize: 10, fill: '#6b7280' }} width={60} />
                    <RechartsTooltip
                      content={({ active, payload }) => {
                        if (!active || !payload || !payload.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs">
                            <div className="font-medium text-gray-800">{d.emotion}</div>
                            <div className="text-gray-500">{d.count} 次 · {(d.pct * 100).toFixed(1)}%</div>
                          </div>
                        );
                      }}
                    />
                    <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
                      {emotionDistribution.map((entry, index) => (
                        <Cell key={index} fill={emotionColor(entry.emotion)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-52 flex items-center justify-center">
                <p className="text-xs text-gray-400">暂无数据</p>
              </div>
            )}
          </div>
        </div>

        {/* Recent Records */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-4 h-4 text-gray-500" />
            <h3 className="text-sm font-semibold text-gray-800">最近记录</h3>
            <span className="text-[10px] text-gray-400 ml-auto">显示最近 {Math.min(history.length, 50)} 条</span>
          </div>
          {history.length === 0 ? (
            <p className="text-xs text-gray-400 text-center py-8">暂无情绪记录。开始对话后，系统将自动记录多模态融合情绪。</p>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {history.slice(0, 50).map((record, idx) => {
                const auth = authenticityBadge(record.authenticity);
                const isExpanded = expandedRecord === idx;
                const hasMixed = Object.keys(record.mixed || {}).length > 0;
                return (
                  <div
                    key={idx}
                    className="border border-gray-100 rounded-lg hover:border-gray-200 transition-colors"
                  >
                    <button
                      onClick={() => setExpandedRecord(isExpanded ? null : idx)}
                      className="w-full flex items-center gap-3 px-3 py-2.5 text-left"
                    >
                      <div
                        className="w-2.5 h-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: emotionColor(record.primary) }}
                      />
                      <span className="text-xs font-medium text-gray-700 w-16 capitalize">{record.primary}</span>
                      <div className="flex-1 flex items-center gap-2">
                        <div className="relative h-1.5 bg-gray-100 rounded-full overflow-hidden flex-1 max-w-[120px]">
                          <div
                            className="absolute top-0 left-0 h-full rounded-full transition-all"
                            style={{ width: `${record.intensity * 100}%`, backgroundColor: emotionColor(record.primary) }}
                          />
                        </div>
                        <span className="text-[10px] text-gray-400 w-8">{(record.intensity * 100).toFixed(0)}%</span>
                      </div>
                      <div className="flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium shrink-0" style={{ borderColor: auth.color.split(' ')[2].replace('border-', ''), backgroundColor: auth.color.includes('green') ? '#f0fdf4' : auth.color.includes('amber') ? '#fffbeb' : '#fef2f2' }}>
                        {auth.icon}
                        <span className={auth.color.split(' ')[1]}>{auth.text}</span>
                      </div>
                      <div className="flex items-center gap-1 text-gray-400 shrink-0">
                        {trendIcon(record.trend)}
                        <span className="text-[10px] capitalize">{record.trend}</span>
                      </div>
                      <span className="text-[10px] text-gray-400 shrink-0 w-14 text-right">
                        {new Date(record.timestamp * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      {hasMixed ? (
                        isExpanded ? <ChevronUp className="w-3 h-3 text-gray-400" /> : <ChevronDown className="w-3 h-3 text-gray-400" />
                      ) : (
                        <div className="w-3" />
                      )}
                    </button>
                    {isExpanded && (
                      <div className="px-3 pb-3 pt-0 border-t border-gray-50">
                        <div className="grid grid-cols-3 gap-3 mt-2">
                          <MiniMetric label="Valence" value={record.valence.toFixed(2)} desc="愉悦度" />
                          <MiniMetric label="Arousal" value={record.arousal.toFixed(2)} desc="唤醒度" />
                          <MiniMetric label="真实性" value={`${(record.authenticity * 100).toFixed(0)}%`} desc="Authenticity" />
                        </div>
                        {hasMixed && (
                          <div className="mt-2">
                            <span className="text-[10px] text-gray-400">混合情绪:</span>
                            <div className="flex flex-wrap gap-1.5 mt-1">
                              {Object.entries(record.mixed).map(([k, v]) => (
                                <span key={k} className="px-2 py-0.5 rounded-full text-[10px] bg-gray-50 border border-gray-200 text-gray-600">
                                  {k} ({(v as number).toFixed(1)})
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {record.trigger && (
                          <div className="mt-1.5 text-[10px] text-gray-400">
                            触发: {record.trigger}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="mt-4 text-[10px] text-gray-400 flex items-center gap-4">
          <span className="flex items-center gap-1"><MessageSquare className="w-3 h-3" /> 文本情绪</span>
          <span className="flex items-center gap-1"><Eye className="w-3 h-3" /> 视觉察言观色</span>
          <span className="flex items-center gap-1"><Mic className="w-3 h-3" /> 语音韵律分析</span>
          <span className="ml-auto">数据来源: tent_scheduler.db / emotion_history</span>
        </div>
      </div>
    </div>
  );
}

function InsightCard({ icon, label, value, sub, accent }: { icon: React.ReactNode; label: string; value: string; sub: string; accent: string }) {
  const accentMap: Record<string, string> = {
    pink: 'from-pink-50 to-white border-pink-100',
    amber: 'from-amber-50 to-white border-amber-100',
    green: 'from-green-50 to-white border-green-100',
    red: 'from-red-50 to-white border-red-100',
    purple: 'from-purple-50 to-white border-purple-100',
    gray: 'from-gray-50 to-white border-gray-100',
  };
  return (
    <div className={`bg-gradient-to-br ${accentMap[accent] || accentMap.gray} rounded-xl border p-4`}>
      <div className="flex items-center gap-2 mb-2">{icon}<span className="text-xs text-gray-500">{label}</span></div>
      <div className="text-lg font-bold text-gray-900">{value}</div>
      <div className="text-[10px] text-gray-400 mt-1">{sub}</div>
    </div>
  );
}

function MiniMetric({ label, value, desc }: { label: string; value: string; desc: string }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-gray-400">{label}</span>
        <span className="text-[10px] text-gray-300">{desc}</span>
      </div>
      <div className="text-sm font-semibold text-gray-700 mt-0.5">{value}</div>
    </div>
  );
}
