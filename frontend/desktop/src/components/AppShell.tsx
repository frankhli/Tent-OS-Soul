import { NavLink, useLocation } from 'react-router-dom';
import { ReactNode, useState } from 'react';
import { MessageCircle, BookOpen, Users, FlaskConical, Settings, Sun, Moon, Wrench } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

const NAV_ITEMS = [
  { path: '/', label: '对话', icon: MessageCircle },
  { path: '/memory', label: '记忆', icon: BookOpen },
  { path: '/soul', label: '灵魂', icon: FlaskConical },
  { path: '/agents', label: 'Agent', icon: Users },
  { path: '/tools', label: '工具', icon: Wrench },
  { path: '/settings', label: '设置', icon: Settings },
];

interface Props {
  children: ReactNode;
}

export default function AppShell({ children }: Props) {
  const location = useLocation();
  const { isDark, toggleTheme } = useTheme();
  const isEternal = location.pathname.startsWith('/eternal');
  const [tooltip, setTooltip] = useState<string | null>(null);

  if (isEternal) {
    return <>{children}</>;
  }

  return (
    <div className="h-screen flex bg-surface-base">
      {/* Left Navigation */}
      <nav className="w-20 border-r border-line-subtle flex flex-col items-center py-4 shrink-0 z-30 bg-surface-elevated">
        {/* Logo */}
        <div className="w-10 h-10 rounded-xl soul-gradient flex items-center justify-center text-white font-bold text-sm mb-6 shadow-elevation-1 dark:shadow-elevation-1-dark">
          T
        </div>

        {/* Nav Items */}
        <div className="flex-1 flex flex-col gap-2 w-full px-2 overflow-y-auto scrollbar-thin">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `relative flex flex-col items-center gap-1 py-2.5 rounded-xl text-[10px] font-medium transition ${
                    isActive
                      ? 'bg-accent-subtle text-accent border border-accent-border'
                      : 'text-content-muted hover:text-content-secondary hover:bg-surface-overlay'
                  }`
                }
                onMouseEnter={() => setTooltip(item.label)}
                onMouseLeave={() => setTooltip(null)}
              >
                <Icon className="w-5 h-5" />
                <span className="truncate w-full text-center px-0.5">{item.label}</span>
              </NavLink>
            );
          })}
        </div>

        {/* Bottom: Theme toggle */}
        <div className="w-full px-2 pb-2">
          <button
            onClick={toggleTheme}
            className="w-full py-2 rounded-lg text-xs transition flex items-center justify-center gap-1.5 bg-surface-overlay text-content-muted hover:text-content-secondary"
            title={isDark ? '切换日间模式' : '切换夜间模式'}
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            <span className="text-[10px]">{isDark ? '日间' : '夜间'}</span>
          </button>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {children}
      </main>
    </div>
  );
}
