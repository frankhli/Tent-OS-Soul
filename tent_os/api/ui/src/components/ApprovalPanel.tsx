import { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, CheckCircle2, XCircle, Clock, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react';

interface ApprovalRecord {
  id: string;
  session_id: string;
  plan_summary?: string;
  approved: boolean | null;
  reason?: string;
  created_at: string;
  responded_at?: string;
  plan?: unknown;
}

interface ApprovalStats {
  total: number;
  approved: number;
  rejected: number;
  pending: number;
}

export function ApprovalPanel() {
  const [records, setRecords] = useState<ApprovalRecord[]>([]);
  const [stats, setStats] = useState<ApprovalStats>({ total: 0, approved: 0, rejected: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadData = useCallback(async () => {
    try {
      const resp = await fetch('/ui/api/approvals/history?limit=100');
      const data = await resp.json();
      const list: ApprovalRecord[] = data.approvals || [];
      setRecords(list);
      setStats({
        total: list.length,
        approved: list.filter((r) => r.approved === true).length,
        rejected: list.filter((r) => r.approved === false).length,
        pending: list.filter((r) => r.approved === null).length,
      });
      setLastUpdated(new Date());
    } catch (e) {
      console.warn('审批历史加载失败:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  const statusBadge = (record: ApprovalRecord) => {
    if (record.approved === true) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
          <CheckCircle2 className="w-3 h-3" />
          已通过
        </span>
      );
    }
    if (record.approved === false) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200">
          <XCircle className="w-3 h-3" />
          已拒绝
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
        <Clock className="w-3 h-3" />
        待审批
      </span>
    );
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-green-100 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">审批记录</h2>
              <p className="text-sm text-gray-500">危险操作的人工审批历史</p>
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

        {/* Stats */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <ShieldCheck className="w-4 h-4 text-gray-400" />
              <span className="text-xs text-gray-500">总计</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{stats.total}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle2 className="w-4 h-4 text-green-400" />
              <span className="text-xs text-gray-500">已通过</span>
            </div>
            <p className="text-2xl font-bold text-green-600">{stats.approved}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <XCircle className="w-4 h-4 text-red-400" />
              <span className="text-xs text-gray-500">已拒绝</span>
            </div>
            <p className="text-2xl font-bold text-red-600">{stats.rejected}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="w-4 h-4 text-amber-400" />
              <span className="text-xs text-gray-500">待审批</span>
            </div>
            <p className="text-2xl font-bold text-amber-600">{stats.pending}</p>
          </div>
        </div>

        {/* List */}
        <div className="space-y-2">
          {loading ? (
            <div className="text-center py-12 text-gray-400">加载中...</div>
          ) : records.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <ShieldCheck className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>暂无审批记录</p>
              <p className="text-xs mt-1">危险操作将在这里等待您的确认</p>
            </div>
          ) : (
            records.map((record) => (
              <div
                key={record.id}
                className={`bg-white rounded-xl border overflow-hidden transition-all ${
                  expandedId === record.id ? 'border-gray-300 shadow-sm' : 'border-gray-200 hover:shadow-sm'
                }`}
              >
                <button
                  onClick={() => setExpandedId(expandedId === record.id ? null : record.id)}
                  className="w-full px-5 py-4 flex items-center gap-4 text-left"
                >
                  {expandedId === record.id ? (
                    <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                  )}
                  {statusBadge(record)}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {record.plan_summary || '未命名任务'}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {record.session_id.slice(0, 16)}... ·{' '}
                      {new Date(record.created_at).toLocaleString('zh-CN')}
                    </p>
                  </div>
                </button>

                {expandedId === record.id && !!record.plan && (
                  <div className="px-5 pb-4 border-t border-gray-100">
                    <div className="mt-3">
                      <p className="text-xs font-medium text-gray-500 mb-2">执行计划</p>
                      <pre className="p-3 bg-gray-50 rounded-lg text-xs text-gray-700 overflow-x-auto">
                        {JSON.stringify(record.plan, null, 2)}
                      </pre>
                    </div>
                    {record.reason && (
                      <div className="mt-2">
                        <p className="text-xs font-medium text-gray-500 mb-1">原因</p>
                        <p className="text-sm text-gray-700">{record.reason}</p>
                      </div>
                    )}
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
