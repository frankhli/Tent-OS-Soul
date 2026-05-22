import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { MessageSquare, Trash2, X, Check, Search } from 'lucide-react';

interface Session {
  session_id: string;
  title: string;
  updated_at: string;
}

interface Props {
  sessions: Session[];
  currentSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

function getTimeGroup(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yday = new Date(today.getTime() - 86400000);
    const weekAgo = new Date(today.getTime() - 7 * 86400000);

    const dDate = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    if (dDate.getTime() === today.getTime()) return '今天';
    if (dDate.getTime() === yday.getTime()) return '昨天';
    if (dDate.getTime() > weekAgo.getTime()) return '本周';
    return '更早';
  } catch {
    return '更早';
  }
}

function formatTime(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export default function SessionSidebar({
  sessions,
  currentSessionId,
  onSelectSession,
  onDeleteSession,
}: Props) {
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const confirmRef = useRef<string | null>(null);

  useEffect(() => {
    confirmRef.current = confirmDelete;
  }, [confirmDelete]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (confirmRef.current) {
        const target = e.target as HTMLElement;
        const confirmEl = document.querySelector(`[data-delete-confirm="${confirmRef.current}"]`);
        if (confirmEl && !confirmEl.contains(target)) {
          setConfirmDelete(null);
        }
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!confirmDelete) return;
    const timer = setTimeout(() => setConfirmDelete(null), 5000);
    return () => clearTimeout(timer);
  }, [confirmDelete]);

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const q = searchQuery.toLowerCase();
    return sessions.filter((s) => s.title.toLowerCase().includes(q));
  }, [sessions, searchQuery]);

  const grouped = useMemo(() => {
    const groups: Record<string, Session[]> = {};
    filtered.forEach((s) => {
      const g = getTimeGroup(s.updated_at);
      if (!groups[g]) groups[g] = [];
      groups[g].push(s);
    });
    const order = ['今天', '昨天', '本周', '更早'];
    return order.map((label) => ({ label, sessions: groups[label] || [] })).filter((g) => g.sessions.length > 0);
  }, [filtered]);

  const handleDeleteClick = useCallback((e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (confirmDelete === sessionId) {
      onDeleteSession(sessionId);
      setConfirmDelete(null);
    } else {
      setConfirmDelete(sessionId);
    }
  }, [confirmDelete, onDeleteSession]);

  const handleCancelDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirmDelete(null);
  }, []);

  return (
    <div className="h-full flex flex-col bg-surface-elevated border-r border-line-subtle">
      {/* Search */}
      <div className="p-3 border-b border-line-subtle">
        <div className="flex items-center gap-2 bg-surface-panel border border-line-subtle rounded-lg px-2.5 py-1.5">
          <Search className="w-3.5 h-3.5 text-content-muted shrink-0" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索会话..."
            className="flex-1 text-xs bg-transparent border-none outline-none text-content-primary placeholder-content-muted"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="text-content-muted hover:text-content-secondary">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto scrollbar-thin p-2 space-y-3">
        {sessions.length === 0 && (
          <div className="text-center py-8">
            <MessageSquare className="w-8 h-8 text-line-active mx-auto mb-2" />
            <div className="text-xs text-content-muted">还没有对话</div>
            <div className="text-[10px] text-content-disabled mt-1">点击上方开始新对话</div>
          </div>
        )}
        {sessions.length > 0 && filtered.length === 0 && (
          <div className="text-center py-8">
            <Search className="w-6 h-6 text-line-active mx-auto mb-2" />
            <div className="text-xs text-content-muted">未找到匹配的会话</div>
          </div>
        )}
        {grouped.map((group) => (
          <div key={group.label}>
            <div className="text-[10px] text-content-muted font-medium px-2 mb-1 uppercase tracking-wider">
              {group.label}
            </div>
            <div className="space-y-1">
              {group.sessions.map((s) => {
                const isActive = currentSessionId === s.session_id;
                const isConfirming = confirmDelete === s.session_id;
                return (
                  <div
                    key={s.session_id}
                    onClick={() => onSelectSession(s.session_id)}
                    className={`group relative px-3 py-2.5 rounded-xl cursor-pointer transition ${
                      isActive
                        ? 'bg-accent-subtle border border-accent-border'
                        : 'hover:bg-surface-overlay border border-transparent'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <MessageSquare className={`w-4 h-4 shrink-0 mt-0.5 ${isActive ? 'text-accent' : 'text-content-muted'}`} />
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm truncate ${isActive ? 'text-accent font-medium' : 'text-content-secondary'}`}>
                          {s.title || '新对话'}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] text-content-muted">{formatTime(s.updated_at)}</span>
                        </div>
                      </div>
                      {isConfirming ? (
                        <div
                          data-delete-confirm={s.session_id}
                          className="shrink-0 flex items-center gap-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={(e) => handleDeleteClick(e, s.session_id)}
                            className="p-1 rounded bg-red-500 text-white hover:bg-red-600 transition"
                            title="确认删除"
                          >
                            <Check className="w-3 h-3" />
                          </button>
                          <button
                            onClick={handleCancelDelete}
                            className="p-1 rounded bg-surface-overlay text-content-muted hover:text-content-secondary transition"
                            title="取消"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={(e) => handleDeleteClick(e, s.session_id)}
                          className="shrink-0 p-1 rounded transition opacity-0 group-hover:opacity-100 text-content-muted hover:text-red-500"
                          title="删除会话"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
