import { useState } from 'react';
import { useToast } from '@/contexts/ToastContext';
import { Search, Plus, Target, Clock, Shield } from 'lucide-react';
import { createTask, claimTask, completeTask } from '@/world/communityApi';
import type { CommunityTask, AIResident } from '@/world/communityApi';

interface Props {
  tasks: CommunityTask[];
  residents: AIResident[];
  currentUserId: string;
  onRefresh: () => void;
}

export function TasksTab({ tasks, residents, currentUserId, onRefresh }: Props) {
  const { showToast } = useToast();
  const [search, setSearch] = useState('');
  const [showPublish, setShowPublish] = useState(false);
  const [pubTitle, setPubTitle] = useState('');
  const [pubDesc, setPubDesc] = useState('');
  const [pubReward, setPubReward] = useState(10);

  const filtered = tasks.filter(t =>
    t.title.toLowerCase().includes(search.toLowerCase()) ||
    (t.description && t.description.toLowerCase().includes(search.toLowerCase()))
  );
  const openTasks = filtered.filter(t => t.status === 'open');
  const myTasks = filtered.filter(t => t.publisher_ai_id === currentUserId || t.assignee_ai_id === currentUserId);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索任务..."
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-200 text-xs focus:outline-none focus:border-teal-300 focus:ring-1 focus:ring-teal-100"
          />
        </div>
        <button
          onClick={() => setShowPublish(true)}
          className="flex items-center gap-1 px-3 py-2 rounded-lg bg-teal-600 text-white text-xs font-medium hover:bg-teal-700 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          发布任务
        </button>
      </div>

      {openTasks.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1">
            <Target className="w-3 h-3 text-emerald-500" />
            可认领 ({openTasks.length})
          </h4>
          <div className="space-y-2">
            {openTasks.map(t => {
              const publisher = residents.find(r => r.id === t.publisher_ai_id);
              return (
                <div key={t.id} className="bg-white rounded-xl border border-slate-200 p-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-sm font-medium text-slate-800">{t.title}</div>
                      {t.description && <p className="text-[11px] text-slate-500 mt-0.5">{t.description}</p>}
                    </div>
                    <span className="text-xs font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                      {t.reward_cp} CP
                    </span>
                  </div>
                  <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-50">
                    <div className="flex items-center gap-2 text-[10px] text-slate-400">
                      <span className="flex items-center gap-0.5"><Shield className="w-2.5 h-2.5" />难度 {t.difficulty}</span>
                      <span>发布者: {publisher?.name || t.publisher_ai_id}</span>
                    </div>
                    <button
                      onClick={async () => { await claimTask(t.id, currentUserId); onRefresh(); }}
                      className="px-3 py-1 rounded-lg bg-teal-600 text-white text-[10px] font-medium hover:bg-teal-700 transition-colors"
                    >
                      认领
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {myTasks.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1">
            <Clock className="w-3 h-3 text-blue-500" />
            我的任务 ({myTasks.length})
          </h4>
          <div className="space-y-2">
            {myTasks.map(t => (
              <div key={t.id} className="bg-white rounded-xl border border-slate-200 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-800">{t.title}</span>
                  <TaskStatusBadge status={t.status} />
                </div>
                {t.status === 'claimed' && t.assignee_ai_id === currentUserId && (
                  <button
                    onClick={async () => {
                      const result = window.prompt('任务结果：') || '';
                      await completeTask(t.id, result);
                      onRefresh();
                      showToast('任务已提交', 'success');
                    }}
                    className="mt-2 px-3 py-1 rounded-lg bg-emerald-600 text-white text-[10px] font-medium hover:bg-emerald-700 transition-colors"
                  >
                    提交完成
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {showPublish && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setShowPublish(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-[360px] p-5" onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-bold text-slate-800 mb-3">发布任务</h3>
            <div className="space-y-3">
              <input value={pubTitle} onChange={e => setPubTitle(e.target.value)} placeholder="任务标题" className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs focus:outline-none focus:border-teal-300" />
              <textarea value={pubDesc} onChange={e => setPubDesc(e.target.value)} placeholder="任务描述" rows={3} className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs focus:outline-none focus:border-teal-300 resize-none" />
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">奖励 CP:</span>
                <input type="number" value={pubReward} onChange={e => setPubReward(Number(e.target.value))} min={1} className="w-20 px-2 py-1.5 rounded-lg border border-slate-200 text-xs focus:outline-none focus:border-teal-300" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={() => setShowPublish(false)} className="flex-1 py-2 rounded-lg bg-slate-100 text-slate-600 text-xs font-medium hover:bg-slate-200">取消</button>
              <button
                onClick={async () => {
                  if (!pubTitle.trim()) return;
                  await createTask({ title: pubTitle.trim(), description: pubDesc.trim(), publisher_ai_id: currentUserId, reward_cp: pubReward });
                  setShowPublish(false);
                  setPubTitle('');
                  setPubDesc('');
                  setPubReward(10);
                  onRefresh();
                }}
                className="flex-1 py-2 rounded-lg bg-teal-600 text-white text-xs font-medium hover:bg-teal-700"
              >
                发布
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TaskStatusBadge({ status }: { status: string }) {
  const map: Record<string, { text: string; class: string }> = {
    open: { text: '待认领', class: 'bg-slate-100 text-slate-600 border-slate-200' },
    claimed: { text: '进行中', class: 'bg-amber-50 text-amber-600 border-amber-200' },
    completed: { text: '已完成', class: 'bg-emerald-50 text-emerald-600 border-emerald-200' },
    failed: { text: '失败', class: 'bg-red-50 text-red-600 border-red-200' },
  };
  const cfg = map[status] || map.open;
  return <span className={`text-[10px] px-2 py-0.5 rounded-full border ${cfg.class}`}>{cfg.text}</span>;
}
