import { useState, useEffect, useCallback, useRef } from 'react';
import { PanelRightOpen, PanelRightClose, PanelLeftOpen, PanelLeftClose, X, CheckSquare, BookOpen } from 'lucide-react';
import ChatInterface from '../components/ChatInterface';
import SessionSidebar from '../components/SessionSidebar';
import TodoPanel from '../components/TodoPanel';
import KnowledgePanel from '../components/KnowledgePanel';
import * as api from '../api/soulApi';

export default function ChatPage() {
  const mountedRef = useRef(true);
  useEffect(() => { return () => { mountedRef.current = false; }; }, []);
  const [leftOpen, setLeftOpen] = useState(() => {
    try {
      const saved = localStorage.getItem('tent_sidebar_open');
      if (saved !== null) return saved === 'true';
      return window.innerWidth >= 1024;
    } catch { return true; }
  });
  const [sideOpen, setSideOpen] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [rightTab, setRightTab] = useState<'todo' | 'knowledge'>('todo');
  const [sessions, setSessions] = useState<any[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  // FIX: 恢复上次活跃会话（刷新页面后保持上下文）
  useEffect(() => {
    try {
      const saved = localStorage.getItem('tent_current_session');
      if (saved) {
        setCurrentSessionId(saved);
      }
    } catch {}
  }, []);

  // Persist sidebar state
  useEffect(() => {
    try { localStorage.setItem('tent_sidebar_open', String(leftOpen)); } catch {}
  }, [leftOpen]);

  // Auto-collapse on small screens
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth < 1024) {
        setLeftOpen(false);
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/chat/sessions?user_id=${api.USER_ID}`);
      if (res.ok) {
        const data = await res.json();
        const newSessions = data.sessions || [];
        setSessions((prev) => {
          if (JSON.stringify(prev) === JSON.stringify(newSessions)) return prev;
          return newSessions;
        });
        // FIX: 如果恢复的会话不在列表中（已被删除），重置为新建会话
        try {
          const saved = localStorage.getItem('tent_current_session');
          if (saved && !newSessions.some((s: any) => s.session_id === saved)) {
            localStorage.removeItem('tent_current_session');
            setCurrentSessionId(null);
          }
        } catch {}
      }
    } catch {}
  }, []);

  useEffect(() => {
    loadSessions();
    const iv = setInterval(loadSessions, 30000);
    return () => clearInterval(iv);
  }, [loadSessions]);

  const handleNewSession = () => {
    setCurrentSessionId(null);
    try { localStorage.removeItem('tent_current_session'); } catch {}
  };

  const handleSelectSession = (sessionId: string) => {
    setCurrentSessionId(sessionId);
    try { localStorage.setItem('tent_current_session', sessionId); } catch {}
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await fetch(`/api/v1/chat/sessions/${sessionId}?user_id=${api.USER_ID}`, { method: 'DELETE' });
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        try { localStorage.removeItem('tent_current_session'); } catch {}
      }
      loadSessions();
    } catch {}
  };

  return (
    <div className="h-full flex bg-surface-base">
      {/* Left Sidebar — Session History (desktop) */}
      {leftOpen && (
        <div className="hidden md:block w-64 shrink-0">
          <SessionSidebar
            sessions={sessions}
            currentSessionId={currentSessionId}
            onSelectSession={handleSelectSession}
            onDeleteSession={handleDeleteSession}
          />
        </div>
      )}

      {/* Left Side Panel Toggle (desktop) */}
      <button
        onClick={() => setLeftOpen((v) => !v)}
        className="hidden md:flex shrink-0 w-8 items-center justify-center border-r border-line-subtle hover:bg-surface-overlay transition-colors"
        title={leftOpen ? '收起历史' : '展开历史'}
      >
        {leftOpen ? (
          <PanelLeftClose className="w-4 h-4 text-content-muted" />
        ) : (
          <PanelLeftOpen className="w-4 h-4 text-content-muted" />
        )}
      </button>

      {/* Mobile Drawer — Session History */}
      {mobileDrawerOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/30 z-40 md:hidden"
            onClick={() => setMobileDrawerOpen(false)}
          />
          {/* Drawer */}
          <div className="fixed left-0 top-0 bottom-0 w-72 z-50 bg-surface-elevated shadow-2xl transform transition-transform duration-200 ease-out md:hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-line-subtle">
              <span className="text-sm font-medium text-content-primary">历史会话</span>
              <button
                onClick={() => setMobileDrawerOpen(false)}
                className="p-1 rounded-lg hover:bg-surface-overlay text-content-muted"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <SessionSidebar
                sessions={sessions}
                currentSessionId={currentSessionId}
                onSelectSession={(id) => {
                  handleSelectSession(id);
                  setMobileDrawerOpen(false);
                }}
                onDeleteSession={handleDeleteSession}
              />
            </div>
          </div>
        </>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <ChatInterface
          sessionId={currentSessionId}
          onSessionCreated={(sid) => {
            setCurrentSessionId(sid);
            try { localStorage.setItem('tent_current_session', sid); } catch {}
            loadSessions();
          }}
          onNewSession={handleNewSession}
          onOpenHistory={() => setMobileDrawerOpen(true)}
        />
      </div>

      {/* Right Side Panel Toggle */}
      <button
        onClick={() => setSideOpen((v) => !v)}
        className="shrink-0 w-8 flex items-center justify-center border-l border-line-subtle hover:bg-surface-overlay transition-colors"
        title={sideOpen ? '收起侧边栏' : '展开侧边栏'}
      >
        {sideOpen ? (
          <PanelRightClose className="w-4 h-4 text-content-muted" />
        ) : (
          <PanelRightOpen className="w-4 h-4 text-content-muted" />
        )}
      </button>

      {/* Right Side Panel */}
      {sideOpen && (
        <div className="hidden lg:block shrink-0 w-80 border-l border-line-subtle bg-surface-elevated flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-line-subtle">
            <button
              onClick={() => setRightTab('todo')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium transition ${
                rightTab === 'todo'
                  ? 'text-accent border-b-2 border-accent bg-accent-subtle/30'
                  : 'text-content-muted hover:text-content-secondary hover:bg-surface-overlay'
              }`}
            >
              <CheckSquare className="w-3.5 h-3.5" /> 任务
            </button>
            <button
              onClick={() => setRightTab('knowledge')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium transition ${
                rightTab === 'knowledge'
                  ? 'text-accent border-b-2 border-accent bg-accent-subtle/30'
                  : 'text-content-muted hover:text-content-secondary hover:bg-surface-overlay'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" /> 知识
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-auto">
            {rightTab === 'todo' ? <TodoPanel /> : <KnowledgePanel />}
          </div>
        </div>
      )}
    </div>
  );
}
