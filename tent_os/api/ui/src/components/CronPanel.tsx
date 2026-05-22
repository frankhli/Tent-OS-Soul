import { useState, useEffect, useCallback } from 'react';
import { CalendarClock, Plus, Trash2, Loader2, Play, Pause, Clock, Activity } from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';

interface CronTask {
  task_id: string;
  name: string;
  cron: string;
  command: string;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
  run_count: number;
}

export function CronPanel() {
  const [tasks, setTasks] = useState<CronTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', cron: '', command: '' });
  const { showToast } = useToast();

  const loadTasks = useCallback(async () => {
    try {
      const resp = await fetch('/api/v1/cron');
      const data = await resp.json();
      setTasks(data.tasks || []);
    } catch (e) {
      showToast('加载定时任务失败', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 10000);
    return () => clearInterval(interval);
  }, [loadTasks]);

  const handleCreate = async () => {
    if (!form.name.trim() || !form.cron.trim() || !form.command.trim()) {
      showToast('请填写完整信息', 'warning');
      return;
    }
    setCreating(true);
    try {
      const resp = await fetch('/api/v1/cron', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (resp.ok) {
        showToast('定时任务创建成功', 'success');
        setForm({ name: '', cron: '', command: '' });
        setShowCreate(false);
        await loadTasks();
      } else {
        const data = await resp.json();
        showToast(`创建失败: ${data.detail || '未知错误'}`, 'error');
      }
    } catch (e) {
      showToast('创建请求失败', 'error');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (taskId: string) => {
    if (!confirm('确定删除这个定时任务吗？')) return;
    try {
      const resp = await fetch(`/api/v1/cron/${encodeURIComponent(taskId)}`, { method: 'DELETE' });
      if (resp.ok) {
        showToast('任务已删除', 'success');
        await loadTasks();
      } else {
        showToast('删除失败', 'error');
      }
    } catch (e) {
      showToast('删除请求失败', 'error');
    }
  };

  const handleToggle = async (taskId: string) => {
    try {
      const resp = await fetch(`/api/v1/cron/${encodeURIComponent(taskId)}/toggle`, { method: 'POST' });
      if (resp.ok) {
        const data = await resp.json();
        showToast(data.enabled ? '任务已启用' : '任务已禁用', 'success');
        await loadTasks();
      } else {
        showToast('操作失败', 'error');
      }
    } catch (e) {
      showToast('请求失败', 'error');
    }
  };

  const enabledCount = tasks.filter((t) => t.enabled).length;

  const formatTime = (t: string | null) => {
    if (!t) return '从未';
    try {
      return new Date(t).toLocaleString('zh-CN');
    } catch {
      return t;
    }
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
              <CalendarClock className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">定时任务</h2>
              <p className="text-sm text-gray-500">管理系统的自动化定时任务</p>
            </div>
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-tent-600 hover:bg-tent-700 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            新建任务
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <CalendarClock className="w-4 h-4 text-gray-400" />
              <span className="text-xs text-gray-500">任务总数</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{tasks.length}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Play className="w-4 h-4 text-green-400" />
              <span className="text-xs text-gray-500">已启用</span>
            </div>
            <p className="text-2xl font-bold text-green-600">{enabledCount}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-1">
              <Activity className="w-4 h-4 text-blue-400" />
              <span className="text-xs text-gray-500">总执行次数</span>
            </div>
            <p className="text-2xl font-bold text-blue-600">
              {tasks.reduce((s, t) => s + t.run_count, 0)}
            </p>
          </div>
        </div>

        {/* Create Form */}
        {showCreate && (
          <div className="bg-blue-50 rounded-xl border border-blue-200 p-4 mb-6">
            <h3 className="text-sm font-semibold text-blue-800 mb-3">新建定时任务</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-blue-700 mb-1 block">任务名称</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="例如：每日报告生成"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-blue-200 bg-white focus:border-tent-400 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-blue-700 mb-1 block">CRON 表达式</label>
                <input
                  type="text"
                  value={form.cron}
                  onChange={(e) => setForm((f) => ({ ...f, cron: e.target.value }))}
                  placeholder="例如：0 9 * * *（每天9点）"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-blue-200 bg-white focus:border-tent-400 focus:outline-none"
                />
                <p className="text-[10px] text-blue-500 mt-1">
                  格式：分 时 日 月 周 · 示例：0 */6 * * *（每6小时）· 0 2 * * 1（每周一2点）
                </p>
              </div>
              <div>
                <label className="text-xs text-blue-700 mb-1 block">执行命令/描述</label>
                <input
                  type="text"
                  value={form.command}
                  onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                  placeholder="例如：生成销售日报并发送邮件"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-blue-200 bg-white focus:border-tent-400 focus:outline-none"
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setShowCreate(false)}
                  className="px-3 py-1.5 rounded-lg text-xs text-gray-600 hover:bg-gray-100 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating}
                  className="px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-tent-600 hover:bg-tent-700 transition-colors disabled:opacity-50"
                >
                  {creating ? '创建中...' : '创建'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Task List */}
        <div className="space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              加载中...
            </div>
          ) : tasks.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <CalendarClock className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>暂无定时任务</p>
              <p className="text-xs mt-1">点击&quot;新建任务&quot;创建第一个定时任务</p>
            </div>
          ) : (
            tasks.map((t) => (
              <div
                key={t.task_id}
                className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${
                        t.enabled
                          ? 'bg-green-50 text-green-700 border-green-200'
                          : 'bg-gray-50 text-gray-500 border-gray-200'
                      }`}>
                        {t.enabled ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                        {t.enabled ? '运行中' : '已暂停'}
                      </span>
                      <span className="text-xs text-gray-400 font-mono">{t.task_id.slice(0, 12)}</span>
                    </div>
                    <h3 className="text-sm font-semibold text-gray-900">{t.name}</h3>
                    <p className="text-xs text-gray-500 mt-0.5">{t.command}</p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {t.cron}
                      </span>
                      <span>上次：{formatTime(t.last_run)}</span>
                      <span>下次：{formatTime(t.next_run)}</span>
                      <span>已执行 {t.run_count} 次</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => handleToggle(t.task_id)}
                      className={`p-1.5 rounded-lg transition-colors ${
                        t.enabled
                          ? 'text-amber-600 hover:bg-amber-50'
                          : 'text-green-600 hover:bg-green-50'
                      }`}
                      title={t.enabled ? '暂停' : '启用'}
                    >
                      {t.enabled ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => handleDelete(t.task_id)}
                      className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="删除"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
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
