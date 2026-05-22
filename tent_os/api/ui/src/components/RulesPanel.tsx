import { useState, useEffect, useCallback } from 'react';
import { BookOpen, TrendingUp, Shield, Zap, Search, RefreshCw, ChevronDown } from 'lucide-react';
import type { ProceduralRule } from '@/types';

const PAGE_SIZE = 50;

export function RulesPanel() {
  const [rules, setRules] = useState<ProceduralRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(PAGE_SIZE);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadData = useCallback(async (limit: number, isMore: boolean = false) => {
    if (!isMore) setLoading(true);
    else setLoadingMore(true);
    try {
      const data = await fetch(`/ui/api/procedural?limit=${limit}`).then((r) => r.json());
      setRules(data.rules || []);
      setLastUpdated(new Date());
    } catch (e) {
      console.warn('Rules加载失败:', e);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    loadData(PAGE_SIZE);
    const interval = setInterval(() => loadData(PAGE_SIZE), 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleLoadMore = () => {
    const next = displayLimit + PAGE_SIZE;
    setDisplayLimit(next);
    loadData(next, true);
  };

  const handleRefresh = () => {
    setDisplayLimit(PAGE_SIZE);
    loadData(PAGE_SIZE);
  };

  const categories = Array.from(new Set(rules.map((r) => r.category)));

  const filtered = rules.filter((r) => {
    const matchesSearch =
      !search ||
      r.pattern.toLowerCase().includes(search.toLowerCase()) ||
      r.action.toLowerCase().includes(search.toLowerCase()) ||
      r.source.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = categoryFilter === 'all' || r.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  const hasMore = !search && categoryFilter === 'all' && rules.length >= displayLimit;
  const showingCount = search || categoryFilter !== 'all' ? filtered.length : rules.length;

  const confidenceColor = (c: number) => {
    if (c >= 0.8) return 'text-green-600 bg-green-50 border-green-200';
    if (c >= 0.5) return 'text-amber-600 bg-amber-50 border-amber-200';
    return 'text-red-600 bg-red-50 border-red-200';
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center">
              <BookOpen className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">程序记忆</h2>
              <p className="text-sm text-gray-500">AI 从经验中提取的行为规则</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {lastUpdated && (
              <span className="text-[10px] text-gray-400">
                更新于 {lastUpdated.toLocaleTimeString('zh-CN')}
              </span>
            )}
            <button
              onClick={handleRefresh}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              title="立即刷新"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Summary */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Zap className="w-4 h-4 text-tent-500" />
              <span className="text-xs text-gray-500">规则总数</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{rules.length}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="w-4 h-4 text-green-500" />
              <span className="text-xs text-gray-500">高置信度</span>
            </div>
            <p className="text-2xl font-bold text-green-600">
              {rules.filter((r) => r.confidence >= 0.8).length}
            </p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Shield className="w-4 h-4 text-blue-500" />
              <span className="text-xs text-gray-500">平均验证</span>
            </div>
            <p className="text-2xl font-bold text-blue-600">
              {rules.length > 0
                ? (rules.reduce((s, r) => s + r.verification_count, 0) / rules.length).toFixed(1)
                : '0'}
            </p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <BookOpen className="w-4 h-4 text-purple-500" />
              <span className="text-xs text-gray-500">分类数</span>
            </div>
            <p className="text-2xl font-bold text-purple-600">{categories.length}</p>
          </div>
        </div>

        {/* Search & Filter */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索规则模式、动作或来源..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 bg-white text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-400">
              {search || categoryFilter !== 'all' ? `${filtered.length} 条匹配` : `显示 ${showingCount} 条`}
            </span>
          </div>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-3 py-2.5 rounded-xl border border-gray-200 bg-white text-sm focus:border-tent-400 focus:outline-none"
          >
            <option value="all">全部分类</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {/* Rules List */}
        <div className="space-y-2">
          {loading ? (
            <div className="text-center py-12 text-gray-400">加载中...</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <BookOpen className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>{search || categoryFilter !== 'all' ? '没有匹配的规则' : '暂无程序记忆规则'}</p>
              <p className="text-xs mt-1">AI 在执行任务时会自动从经验中学习</p>
            </div>
          ) : (
            filtered.map((r) => (
              <div
                key={r.id}
                className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {r.category}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${confidenceColor(r.confidence)}`}>
                        置信度 {(r.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-sm font-medium text-gray-900 mb-1">{r.pattern}</p>
                    <p className="text-sm text-gray-500">→ {r.action}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-xs text-gray-400">验证 {r.verification_count} 次</p>
                    <p className="text-xs text-gray-400 mt-0.5">来源: {r.source}</p>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Load More */}
        {hasMore && (
          <div className="flex justify-center mt-4">
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-50"
            >
              {loadingMore ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
              {loadingMore ? '加载中...' : '加载更多'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
