import { useState, useEffect, useCallback } from 'react';
import { Brain, Search, Layers, Clock, Database, RefreshCw, ChevronDown } from 'lucide-react';
import type { MemoryItem } from '@/types';

const PAGE_SIZE = 50;

export function MemoryPanel() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [stats, setStats] = useState({ total: 0, working: 0, shortTerm: 0, longTerm: 0 });
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(PAGE_SIZE);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadData = useCallback(async (limit: number, isMore: boolean = false) => {
    if (!isMore) setLoading(true);
    else setLoadingMore(true);
    try {
      const [memData, statData] = await Promise.all([
        fetch(`/ui/api/memory?limit=${limit}`).then((r) => r.json()),
        fetch('/ui/api/memory/stats').then((r) => r.json()),
      ]);
      setMemories(memData.memories || []);
      setStats(statData.stats || { total: 0, working: 0, shortTerm: 0, longTerm: 0 });
      setLastUpdated(new Date());
    } catch (e) {
      console.warn('Memory加载失败:', e);
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

  const filtered = memories.filter((m) =>
    m.content.toLowerCase().includes(search.toLowerCase()) ||
    m.source.toLowerCase().includes(search.toLowerCase())
  );

  const hasMore = !search && memories.length < stats.total;
  const showingCount = search ? filtered.length : memories.length;

  const tierBadge = (tier: string) => {
    const colors: Record<string, string> = {
      working: 'bg-purple-50 text-purple-700 border-purple-200',
      short_term: 'bg-blue-50 text-blue-700 border-blue-200',
      long_term: 'bg-amber-50 text-amber-700 border-amber-200',
    };
    const labels: Record<string, string> = {
      working: '工作记忆',
      short_term: '短期记忆',
      long_term: '长期记忆',
    };
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full border ${colors[tier] || colors.working}`}>
        {labels[tier] || tier}
      </span>
    );
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-100 flex items-center justify-center">
              <Brain className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">记忆库</h2>
              <p className="text-sm text-gray-500">检索与浏览系统记忆</p>
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

        {/* Stats */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Database className="w-4 h-4 text-gray-400" />
              <span className="text-xs text-gray-500">总计</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{stats.total}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Layers className="w-4 h-4 text-purple-400" />
              <span className="text-xs text-gray-500">工作记忆</span>
            </div>
            <p className="text-2xl font-bold text-purple-600">{stats.working}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="w-4 h-4 text-blue-400" />
              <span className="text-xs text-gray-500">短期记忆</span>
            </div>
            <p className="text-2xl font-bold text-blue-600">{stats.shortTerm}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Database className="w-4 h-4 text-amber-400" />
              <span className="text-xs text-gray-500">长期记忆</span>
            </div>
            <p className="text-2xl font-bold text-amber-600">{stats.longTerm}</p>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索记忆内容或来源..."
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 bg-white text-sm focus:border-tent-400 focus:outline-none focus:ring-2 focus:ring-tent-100"
          />
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-400">
            {search ? `${filtered.length} 条匹配` : `显示 ${showingCount} / ${stats.total} 条`}
          </span>
        </div>

        {/* Memory List */}
        <div className="space-y-2">
          {loading ? (
            <div className="text-center py-12 text-gray-400">加载中...</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <Brain className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>{search ? '没有匹配的记忆' : '暂无记忆记录'}</p>
            </div>
          ) : (
            filtered.map((m) => (
              <div
                key={m.id}
                className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {tierBadge(m.tier)}
                    <span className="text-xs text-gray-400">{m.source}</span>
                  </div>
                  <span className="text-xs text-gray-400">
                    {new Date(m.timestamp).toLocaleString('zh-CN')}
                  </span>
                </div>
                <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{m.content}</p>
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
