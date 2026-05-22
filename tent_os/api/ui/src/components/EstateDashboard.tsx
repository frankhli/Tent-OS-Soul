/**
 * EstateDashboard — 家园概览
 * 综合展示：今日任务、最近便签、项目统计、未读信件
 * 注意：不再包含重复导航，2D家园入口统一在侧边栏「AI 的家」
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Home, Calendar, StickyNote, Frame, Mail,
  CheckCircle2, Sparkles, TreePine,
} from 'lucide-react';

interface EstateData {
  today_tasks: number;
  completed_today: number;
  recent_notes: { id: string; content: string; author: string; created_at: string }[];
  recent_projects: { task: string; updated_at: string }[];
  unread_letters: number;
  total_letters: number;
}

export function EstateDashboard() {
  const [data, setData] = useState<EstateData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [calendarRes, notesRes, projectsRes, lettersRes] = await Promise.all([
        fetch('/ui/api/world/calendar').then((r) => r.json()).catch(() => ({ grid: [], total_tasks: 0 })),
        fetch('/ui/api/world/fridge-notes').then((r) => r.json()).catch(() => ({ notes: [] })),
        fetch('/ui/api/world/projects?limit=5').then((r) => r.json()).catch(() => ({ projects: [] })),
        fetch('/ui/api/world/letter-rack').then((r) => r.json()).catch(() => ({ unread_count: 0, count: 0 })),
      ]);

      // 统计今日任务
      const todayStr = new Date().toISOString().slice(0, 10);
      const todayTasks = (calendarRes.grid || []).filter(
        (d: { date: string; tasks: unknown[] }) => d && d.date === todayStr
      );
      const todayTaskCount = todayTasks.reduce(
        (sum: number, d: { tasks: unknown[] }) => sum + (d.tasks?.length || 0), 0
      );
      const completedToday = todayTasks.reduce(
        (sum: number, d: { has_completed: boolean; tasks: { status: string }[] }) =>
          sum + (d.tasks?.filter((t: { status: string }) => t.status === 'completed').length || 0),
        0
      );

      setData({
        today_tasks: todayTaskCount,
        completed_today: completedToday,
        recent_notes: (notesRes.notes || []).slice(0, 4),
        recent_projects: (projectsRes.projects || []).slice(0, 4),
        unread_letters: lettersRes.unread_count || 0,
        total_letters: lettersRes.count || 0,
      });
    } catch (e) {
      console.error('[EstateDashboard] fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const formatTime = (s: string) => {
    try {
      return new Date(s).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    } catch {
      return s;
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-b from-gray-50 to-stone-100">
      <div className="max-w-4xl mx-auto px-6 py-6">
        {/* 头部 */}
        <div className="flex items-center gap-3 mb-6">
          <Home className="w-6 h-6 text-teal-600" />
          <div>
            <h2 className="text-lg font-bold text-gray-900">家园概览</h2>
            <p className="text-xs text-gray-400">AI 之家的每日快照</p>
          </div>
        </div>

        {loading ? (
          <div className="h-64 flex items-center justify-center text-gray-400">
            <Sparkles className="w-5 h-5 animate-spin mr-2" />
            加载庄园...
          </div>
        ) : (
          <div className="space-y-5">
            {/* 今日概览卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard
                icon={Calendar}
                label="今日任务"
                value={data?.today_tasks ?? 0}
                color="text-amber-600"
                bg="bg-amber-50"
              />
              <StatCard
                icon={CheckCircle2}
                label="已完成"
                value={data?.completed_today ?? 0}
                color="text-green-600"
                bg="bg-green-50"
              />
              <StatCard
                icon={Frame}
                label="项目画像"
                value={data?.recent_projects?.length ?? 0}
                color="text-purple-600"
                bg="bg-purple-50"
              />
              <StatCard
                icon={Mail}
                label="未读信件"
                value={data?.unread_letters ?? 0}
                color="text-red-600"
                bg="bg-red-50"
              />
            </div>

            {/* 两列布局 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* 最近便签 */}
              <SectionCard
                icon={StickyNote}
                title="冰箱贴"
              >
                {data?.recent_notes && data.recent_notes.length > 0 ? (
                  <div className="grid grid-cols-2 gap-2">
                    {data.recent_notes.map((note) => (
                      <div
                        key={note.id}
                        className="rounded-lg p-2.5 text-xs"
                        style={{
                          backgroundColor: note.author === 'ai' ? '#F3E5F5' : '#FFF8E1',
                          border: `1px solid ${note.author === 'ai' ? '#CE93D8' : '#FFD54F'}40`,
                        }}
                      >
                        <p className="text-gray-700 line-clamp-3">{note.content}</p>
                        <span className="text-[10px] text-gray-400 mt-1 block">
                          {note.author === 'ai' ? '🤖 AI' : '👤 我'}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState text="冰箱上还没有便签" />
                )}
              </SectionCard>

              {/* 最近完成的项目 */}
              <SectionCard
                icon={Frame}
                title="最近完成"
              >
                {data?.recent_projects && data.recent_projects.length > 0 ? (
                  <div className="space-y-2">
                    {data.recent_projects.map((p, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white border border-gray-100"
                      >
                        <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                        <span className="text-xs text-gray-700 truncate flex-1">{p.task}</span>
                        <span className="text-[10px] text-gray-400 shrink-0">{formatTime(p.updated_at)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState text="还没有完成的项目" />
                )}
              </SectionCard>
            </div>

            {/* 提示：进入 2D 家园 */}
            <div className="bg-teal-50 rounded-xl border border-teal-200 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <TreePine className="w-4 h-4 text-teal-600" />
                  <span className="text-sm text-teal-700 font-medium">想与 AI 互动？进入 2D 家园</span>
                </div>
                <button
                  onClick={() => window.dispatchEvent(new CustomEvent('tent-os-navigate', { detail: 'world' }))}
                  className="px-3 py-1.5 rounded-lg text-xs bg-teal-600 text-white hover:bg-teal-700 transition-colors"
                >
                  进入 AI 的家
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ===== 子组件 =====

function StatCard({
  icon: Icon,
  label,
  value,
  color,
  bg,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  color: string;
  bg: string;
}) {
  return (
    <div className={`${bg} rounded-xl border border-gray-100 p-3`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-4 h-4 ${color}`} />
        <span className="text-[10px] text-gray-500">{label}</span>
      </div>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

function SectionCard({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
          <Icon className="w-4 h-4 text-gray-400" />
          {title}
        </h3>
      </div>
      {children}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="text-center py-6 text-gray-400 text-xs">{text}</div>
  );
}


