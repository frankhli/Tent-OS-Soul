import { useState, useEffect, useCallback } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Brain, Shield, Zap, Database, RefreshCw } from 'lucide-react';
import type { SLIData } from '@/types';

interface TelemetryData {
  llm: { total_calls: number; total_tokens: number; avg_latency_ms: number; active_sessions: number };
  memory: { sqlite: number; files: number; graph_nodes: number };
  rules: { total: number; high_confidence: number };
  security: { mode_changes: number; assessments: number };
}

export function SLOPanel() {
  const [slis, setSlis] = useState<SLIData[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [sloData, telData] = await Promise.all([
        fetch('/ui/api/slo').then((r) => r.json()),
        fetch('/ui/api/telemetry').then((r) => r.json()),
      ]);
      setSlis(sloData.slis || []);
      setTelemetry(telData);
      setLastUpdated(new Date());
    } catch (e) {
      console.warn('SLO加载失败:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const statusIcon = (status: string) => {
    switch (status) {
      case 'ok':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />;
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      case 'breached':
        return <AlertTriangle className="w-5 h-5 text-red-500" />;
      default:
        return <Activity className="w-5 h-5 text-gray-400" />;
    }
  };

  const progressColor = (actual: number, target: number) => {
    const ratio = actual / target;
    if (ratio >= 1) return 'bg-green-500';
    if (ratio >= 0.9) return 'bg-amber-500';
    return 'bg-red-500';
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
              <Activity className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">系统监控</h2>
              <p className="text-sm text-gray-500">实时指标与服务质量目标</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {lastUpdated && (
              <span className="text-[10px] text-gray-400">
                更新于 {lastUpdated.toLocaleTimeString('zh-CN')}
              </span>
            )}
            <button
              onClick={loadData}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              title="立即刷新"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Telemetry Cards */}
        {telemetry && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="w-4 h-4 text-tent-500" />
                <span className="text-xs text-gray-500">LLM 调用</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{telemetry.llm.total_calls}</p>
              <p className="text-xs text-gray-400 mt-1">{telemetry.llm.total_tokens} tokens</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Brain className="w-4 h-4 text-purple-500" />
                <span className="text-xs text-gray-500">记忆</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{telemetry.memory.files + telemetry.memory.graph_nodes}</p>
              <p className="text-xs text-gray-400 mt-1">文件 {telemetry.memory.files} · 图谱 {telemetry.memory.graph_nodes}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Database className="w-4 h-4 text-amber-500" />
                <span className="text-xs text-gray-500">程序规则</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{telemetry.rules.total}</p>
              <p className="text-xs text-gray-400 mt-1">高置信度 {telemetry.rules.high_confidence}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Shield className="w-4 h-4 text-green-500" />
                <span className="text-xs text-gray-500">安全评估</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{telemetry.security.assessments}</p>
              <p className="text-xs text-gray-400 mt-1">模式切换 {telemetry.security.mode_changes}</p>
            </div>
          </div>
        )}

        {/* SLI Cards */}
        <div className="space-y-3">
          {loading ? (
            <div className="text-center py-12 text-gray-400">加载中...</div>
          ) : slis.length === 0 ? (
            <div className="text-center py-8 text-gray-400 bg-white rounded-xl border border-gray-200">
              <Activity className="w-10 h-10 mx-auto mb-2 text-gray-300" />
              <p className="text-sm">暂无 SLO 历史数据</p>
              <p className="text-xs mt-1">上方实时指标已展示系统当前状态</p>
            </div>
          ) : (
            slis.map((sli) => (
              <div
                key={sli.metric_name}
                className="bg-white rounded-xl border border-gray-200 p-5"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    {statusIcon(sli.status)}
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900">{sli.metric_name}</h3>
                      <p className="text-xs text-gray-500">{sli.window_hours} 小时窗口</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`text-2xl font-bold ${
                      sli.status === 'ok' ? 'text-green-600' :
                      sli.status === 'warning' ? 'text-amber-600' : 'text-red-600'
                    }`}>
                      {(sli.actual * 100).toFixed(2)}%
                    </p>
                    <p className="text-xs text-gray-400">目标 {(sli.target * 100).toFixed(0)}%</p>
                  </div>
                </div>

                <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`absolute left-0 top-0 h-full rounded-full transition-all ${progressColor(sli.actual, sli.target)}`}
                    style={{ width: `${Math.min((sli.actual / sli.target) * 100, 100)}%` }}
                  />
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
