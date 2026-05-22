import { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  MessageSquare,
  GitBranch,
  Brain,
  Activity,
  Settings,
  Wifi,
  WifiOff,
  Loader2,
  ScrollText,
  Puzzle,
  Bot,
  PanelLeftClose,
  PanelLeftOpen,
  Moon,
  ShieldCheck,
  CalendarClock,
  Bot as BotIcon,
  Heart,
  Home,
  Users,
  TreePine,
} from 'lucide-react';
import type { ViewTab, SystemHealth } from '@/types';
import { AvatarHomeButton } from './AvatarHomeButton';

interface SidebarProps {
  activeTab: ViewTab;
  onTabChange: (tab: ViewTab) => void;
  health: SystemHealth | null;
  connectionStatus: 'connecting' | 'connected' | 'disconnected';
  collapsed: boolean;
  onToggleCollapse: () => void;
  emotion?: string;
  persona?: string;
}

interface NavGroup {
  label: string;
  items: { tab: ViewTab; label: string; icon: React.ElementType }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: '核心',
    items: [
      { tab: 'dashboard', label: '概览', icon: LayoutDashboard },
      { tab: 'chat', label: '聊天', icon: MessageSquare },
      { tab: 'assistant', label: '角色档案', icon: Bot },
    ],
  },
  {
    label: '认知',
    items: [
      { tab: 'tasks', label: '任务流', icon: GitBranch },
      { tab: 'memory', label: '记忆', icon: Brain },
      { tab: 'skills', label: 'Skills', icon: Puzzle },
    ],
  },
  {
    label: '情绪',
    items: [
      { tab: 'emotion', label: '情绪时间线', icon: Heart },
    ],
  },
  {
    label: '物理世界',
    items: [
      { tab: 'physical', label: '物理控制', icon: BotIcon },
    ],
  },
  {
    label: 'AI空间',
    items: [
      { tab: 'estate', label: '家园概览', icon: Home },
      { tab: 'world', label: 'AI 的家', icon: TreePine },
      { tab: 'community', label: 'AI 社区', icon: Users },
    ],
  },
  {
    label: '监控',
    items: [
      { tab: 'slo', label: '系统监控', icon: Activity },
      { tab: 'approvals', label: '审批', icon: ShieldCheck },
      { tab: 'logs', label: '日志', icon: ScrollText },
    ],
  },
  {
    label: '系统',
    items: [
      { tab: 'dreaming', label: '梦境', icon: Moon },
      { tab: 'cron', label: '定时任务', icon: CalendarClock },
      { tab: 'config', label: '配置', icon: Settings },
    ],
  },
];

export function Sidebar({ activeTab, onTabChange, health, connectionStatus, collapsed, onToggleCollapse, emotion = 'listening', persona: _persona = 'work' }: SidebarProps) {
  const [pendingCount, setPendingCount] = useState(0);
  const [levelInfo, setLevelInfo] = useState<{ level: number; title: string }>({ level: 1, title: '新手' });

  // 监听 EstateDashboard 的导航事件
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail) onTabChange(detail as ViewTab);
    };
    window.addEventListener('tent-os-navigate', handler);
    return () => window.removeEventListener('tent-os-navigate', handler);
  }, [onTabChange]);

  useEffect(() => {
    const fetchPending = async () => {
      try {
        const resp = await fetch('/ui/api/approvals/history?limit=1');
        const data = await resp.json();
        const pending = data.pending_count ?? 0;
        setPendingCount(pending);
      } catch {
        // ignore
      }
    };
    const fetchLevel = async () => {
      try {
        const resp = await fetch('/ui/api/six-axis');
        const data = await resp.json();
        if (data.title) {
          const thresholds = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
          const avg = data.avg_score || 0;
          let level = 1;
          for (let i = 1; i < thresholds.length; i++) { if (avg >= thresholds[i]) level = i + 1; else break; }
          setLevelInfo({ level, title: data.title });
        }
      } catch {
        // ignore
      }
    };
    fetchPending();
    fetchLevel();
    const interval = setInterval(() => { fetchPending(); fetchLevel(); }, 60000);
    return () => clearInterval(interval);
  }, []);
  const statusIcon =
    connectionStatus === 'connected' ? (
      <Wifi className="w-3.5 h-3.5 text-green-500" />
    ) : connectionStatus === 'connecting' ? (
      <Loader2 className="w-3.5 h-3.5 text-amber-500 animate-spin" />
    ) : (
      <WifiOff className="w-3.5 h-3.5 text-red-500" />
    );

  const statusText =
    connectionStatus === 'connected'
      ? '已连接'
      : connectionStatus === 'connecting'
      ? '连接中...'
      : '已断开';

  if (collapsed) {
    return (
      <aside className="w-14 bg-white border-r border-gray-200 flex flex-col items-center py-3">
        {/* Logo — 小型角色头像（可拖拽召唤） */}
        <div className="mb-4">
          <AvatarHomeButton
            source="sidebar"
            size={36}
            showLevelRing={false}
            showParticles={false}
            onClick={() => onTabChange('assistant')}
            title="查看角色档案 · 拖拽解放我"
          />
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto space-y-1 w-full px-1">
          {NAV_GROUPS.flatMap((g) => g.items).map((item) => {
            const isActive = activeTab === item.tab;
            return (
              <button
                key={item.tab}
                onClick={() => onTabChange(item.tab)}
                title={item.label}
                className={`relative w-full flex items-center justify-center py-2 rounded-md transition-colors ${
                  isActive
                    ? 'bg-tent-50 text-tent-700'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
              >
                <item.icon className={`w-4 h-4 ${isActive ? 'text-tent-600' : 'text-gray-400'}`} />
                {item.tab === 'approvals' && pendingCount > 0 && (
                  <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
                )}
              </button>
            );
          })}
        </nav>

        {/* Toggle & Status */}
        <div className="mt-auto pt-3 border-t border-gray-100 w-full px-1 space-y-1">
          <button
            onClick={onToggleCollapse}
            className="w-full flex items-center justify-center py-2 rounded-md text-gray-400 hover:bg-gray-50 hover:text-gray-600 transition-colors"
            title="展开侧边栏"
          >
            <PanelLeftOpen className="w-4 h-4" />
          </button>
          <div className="flex items-center justify-center py-1">
            {statusIcon}
          </div>
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
      {/* Logo — 角色化 */}
      <div className="px-4 py-4 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <AvatarHomeButton
            source="sidebar"
            size={36}
            showLevelRing={false}
            showParticles={false}
            onClick={() => onTabChange('assistant')}
            title="查看角色档案 · 拖拽解放我"
          />
          <div>
            <div className="flex items-center gap-1.5">
              <h1 className="text-sm font-bold text-gray-900 leading-tight">Tent OS</h1>
              <span className="text-[9px] font-medium px-1 py-0 bg-tent-100 text-tent-600 rounded">Lv.{levelInfo.level}</span>
            </div>
            <p className="text-[10px] text-gray-400">{levelInfo.title}</p>
          </div>
        </div>
        <button
          onClick={onToggleCollapse}
          className="p-1 rounded text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          title="收起侧边栏"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="px-2 mb-1 text-[10px] font-medium text-gray-400 uppercase tracking-wider">
              {group.label}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const isActive = activeTab === item.tab;
                return (
                  <button
                    key={item.tab}
                    onClick={() => onTabChange(item.tab)}
                    className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-xs transition-colors ${
                      isActive
                        ? 'bg-tent-50 text-tent-700 font-medium'
                        : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                    }`}
                  >
                    <item.icon className={`w-4 h-4 ${isActive ? 'text-tent-600' : 'text-gray-400'}`} />
                    <span className="flex-1 text-left">{item.label}</span>
                    {item.tab === 'approvals' && pendingCount > 0 && (
                      <span className="px-1.5 py-0.5 text-[10px] font-bold text-white bg-red-500 rounded-full min-w-[18px] text-center">
                        {pendingCount > 99 ? '99+' : pendingCount}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Status */}
      <div className="px-3 py-3 border-t border-gray-100">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            {statusIcon}
            <span className="text-[11px] text-gray-500">{statusText}</span>
          </div>
          {health && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                health.status === 'ok'
                  ? 'bg-green-50 text-green-600'
                  : health.status === 'degraded'
                  ? 'bg-amber-50 text-amber-600'
                  : 'bg-red-50 text-red-600'
              }`}
            >
              {health.status === 'ok' ? '正常' : health.status === 'degraded' ? '降级' : '故障'}
            </span>
          )}
        </div>
        {/* 情绪状态 pill */}
        {emotion && emotion !== 'listening' && (
          <div className="flex items-center gap-1.5 px-2 py-1 bg-amber-50 border border-amber-200 rounded-lg">
            <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-[10px] text-amber-600 font-medium capitalize">{emotion}</span>
          </div>
        )}
      </div>
    </aside>
  );
}
