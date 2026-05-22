import { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, Clock, CheckCircle2, XCircle, Loader2, AlertCircle } from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';

interface ApprovalRecord {
  session_id: string;
  plan_summary: string;
  approved: number | null;
  approved_by: string;
  created_at: string;
  decided_at: string | null;
}

export function ApprovalHistoryPanel() {
  const [records, setRecords] = useState<ApprovalRecord[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('all');
  const { showToast } = useToast();

  const loadData = useCallback(async () => {
    try {
      const resp = await fetch('/ui/api/approvals/history?limit=100');
      const data = await resp.json();
      setRecords(data.history || []);
      setPendingCount(data.pending_count || 0);
    } catch (e) {
      showToast('加载审批历史失败', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const filtered = records.filter((r) => {
    if (filter === 'pending') return r.approved === null;
    if (filter === 'approved') return r.approved === 1;
    if (filter === 'rejected') return r.approved === 0;
    return true;
  });

  const stats = {
    total: records.length,
    pending: records.filter((r) => r.approved === null).length,
    approved: records.filter((r) => r.approved === 1).length,
    rejected: records.filter((r) => r.approved === 0).length,
  };

  const statusBadge = (record: ApprovalRecord) => {
    if (record.approved === null) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
          <Clock className="w-3 h-3" />
          待审批
        </span>
      );
    }
    if (record.approved === 1) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
          <CheckCircle2 className="w-3 h-3" />
          已通过
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200">
        <XCircle className="w-3 h-3" />
        已拒绝
      </span>
    );
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">审批历史</h2>
              <p className="text-sm text-gray-500">查看任务计划的审批记录</p>
            </div>
          </div>
          {pendingCount > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 text-xs font-medium">
              <AlertCircle className="w-4 h-4" />
              {pendingCount} 个待审批
            </div>
          )}
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
              <Clock className="w-4 h-4 text-amber-400" />
              <span className="text-xs text-gray-500">待审批</span>
            </div>
            <p className="text-2xl font-bold text-amber-600">{stats.pending}</p>
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
        </div>

        {/* Filter */}
        <div className="flex items-center gap-2 mb-4">
          {([
            { key: 'all', label: '全部' },
            { key: 'pending', label: '待审批' },
            { key: 'approved', label: '已通过' },
            { key: 'rejected', label: '已拒绝' },
          ] as const).map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === f.key
                  ? 'bg-tent-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-200'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              加载中...
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <ShieldCheck className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>暂无审批记录</p>
            </div>
          ) : (
            filtered.map((r) => (
              <div
                key={`${r.session_id}-${r.created_at}`}
                className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      {statusBadge(r)}
                      <span className="text-xs text-gray-400 font-mono">{r.session_id.slice(0, 16)}...</span>
                    </div>
                    <p className="text-sm text-gray-700 leading-relaxed">{r.plan_summary || '无描述'}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs text-gray-400">
                      {r.created_at ? new Date(r.created_at).toLocaleString('zh-CN') : '-'}
                    </p>
                    {r.decided_at && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        决策于 {new Date(r.decided_at).toLocaleString('zh-CN')}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
