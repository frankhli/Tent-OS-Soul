/**
 * LetterRack — AI 庄园的信件架
 * 系统通知、任务完成、升级提示等以信封形式陈列
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Mail, MailOpen, Trash2, Sparkles, Bell, AlertTriangle,
  CheckCircle2, Trophy, Package, X,
} from 'lucide-react';

interface Letter {
  id: string;
  type: string;
  title: string;
  content: string;
  read: boolean;
  created_at: string;
}

const LETTER_ICONS: Record<string, React.ElementType> = {
  task_completed: CheckCircle2,
  task_failed: AlertTriangle,
  system_alert: Bell,
  level_up: Trophy,
  artifact: Package,
  default: Mail,
};

const LETTER_COLORS: Record<string, { bg: string; border: string; icon: string }> = {
  task_completed: { bg: '#E8F5E9', border: '#81C784', icon: '#2E7D32' },
  task_failed: { bg: '#FFEBEE', border: '#EF5350', icon: '#C62828' },
  system_alert: { bg: '#FFF3E0', border: '#FFB74D', icon: '#EF6C00' },
  level_up: { bg: '#F3E5F5', border: '#BA68C8', icon: '#7B1FA2' },
  artifact: { bg: '#FFF8E1', border: '#FFD54F', icon: '#F57F17' },
  default: { bg: '#E3F2FD', border: '#64B5F6', icon: '#1565C0' },
};

export function LetterRack() {
  const [letters, setLetters] = useState<Letter[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedLetter, setSelectedLetter] = useState<Letter | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);

  const fetchLetters = useCallback(async () => {
    try {
      const res = await fetch('/ui/api/world/letter-rack');
      if (res.ok) {
        const data = await res.json();
        setLetters(data.letters || []);
        setUnreadCount(data.unread_count || 0);
      }
    } catch (e) {
      console.error('[LetterRack] fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLetters();
  }, [fetchLetters]);

  const markRead = async (id: string) => {
    try {
      await fetch(`/ui/api/world/letter-rack/${id}/read`, { method: 'POST' });
      fetchLetters();
    } catch (e) {
      console.error(e);
    }
  };

  const deleteLetter = async (id: string) => {
    try {
      await fetch(`/ui/api/world/letter-rack/${id}`, { method: 'DELETE' });
      setSelectedLetter(null);
      fetchLetters();
    } catch (e) {
      console.error(e);
    }
  };

  const openLetter = (letter: Letter) => {
    setSelectedLetter(letter);
    if (!letter.read) {
      markRead(letter.id);
    }
  };

  const formatTime = (s: string) => {
    try {
      return new Date(s).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return s;
    }
  };

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-amber-50 to-orange-50">
      {/* 头部 — 信件架 */}
      <div className="px-5 py-4 bg-white border-b border-amber-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative">
            <Mail className="w-5 h-5 text-amber-600" />
            {unreadCount > 0 && (
              <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </div>
          <div>
            <h2 className="text-sm font-bold text-gray-800">信件架</h2>
            <p className="text-[10px] text-gray-400">
              {letters.length} 封信 · {unreadCount} 封未读
            </p>
          </div>
        </div>
        <button
          onClick={fetchLetters}
          className="p-1.5 rounded-lg hover:bg-amber-100 text-gray-400 transition-colors"
        >
          <Sparkles className="w-4 h-4" />
        </button>
      </div>

      {/* 信件列表 */}
      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <div className="h-full flex items-center justify-center text-gray-400 text-sm">
            <Sparkles className="w-5 h-5 animate-spin mr-2" />
            加载信件...
          </div>
        ) : letters.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Mail className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">信件架是空的</p>
            <p className="text-xs mt-1">系统通知和任务完成时会自动放入这里</p>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto space-y-3">
            {letters.map((letter) => {
              const colors = LETTER_COLORS[letter.type] || LETTER_COLORS.default;
              const Icon = LETTER_ICONS[letter.type] || LETTER_ICONS.default;

              return (
                <button
                  key={letter.id}
                  onClick={() => openLetter(letter)}
                  className={`w-full text-left rounded-xl border p-3 flex items-center gap-3 transition-all hover:shadow-md ${
                    letter.read
                      ? 'bg-white border-gray-200 opacity-70'
                      : 'bg-white border-amber-200 shadow-sm'
                  }`}
                >
                  {/* 信封图标 */}
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                    style={{ backgroundColor: colors.bg, border: `1px solid ${colors.border}` }}
                  >
                    <Icon className="w-5 h-5" style={{ color: colors.icon }} />
                  </div>

                  {/* 内容 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className={`text-xs truncate ${letter.read ? 'text-gray-500 font-normal' : 'text-gray-800 font-semibold'}`}>
                        {letter.title}
                      </p>
                      {!letter.read && (
                        <span className="w-2 h-2 rounded-full bg-red-400 shrink-0" />
                      )}
                    </div>
                    {letter.content && (
                      <p className="text-[10px] text-gray-400 truncate mt-0.5">{letter.content}</p>
                    )}
                    <p className="text-[10px] text-gray-300 mt-0.5">{formatTime(letter.created_at)}</p>
                  </div>

                  {/* 右侧箭头 */}
                  {letter.read ? (
                    <MailOpen className="w-4 h-4 text-gray-300 shrink-0" />
                  ) : (
                    <Mail className="w-4 h-4 text-amber-400 shrink-0" />
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* 信件详情弹窗 */}
      {selectedLetter && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                {(() => {
                  const colors = LETTER_COLORS[selectedLetter.type] || LETTER_COLORS.default;
                  const Icon = LETTER_ICONS[selectedLetter.type] || LETTER_ICONS.default;
                  return (
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: colors.bg }}
                    >
                      <Icon className="w-4 h-4" style={{ color: colors.icon }} />
                    </div>
                  );
                })()}
                <h3 className="text-sm font-bold text-gray-800">{selectedLetter.title}</h3>
              </div>
              <button
                onClick={() => setSelectedLetter(null)}
                className="p-1 rounded-lg hover:bg-gray-100 text-gray-400"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5">
              {selectedLetter.content && (
                <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">
                  {selectedLetter.content}
                </p>
              )}
              <p className="text-[10px] text-gray-400 mt-4">
                收到于 {formatTime(selectedLetter.created_at)}
              </p>
            </div>
            <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 flex justify-between">
              <button
                onClick={() => deleteLetter(selectedLetter.id)}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs text-red-500 hover:bg-red-50 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                删除
              </button>
              <button
                onClick={() => setSelectedLetter(null)}
                className="px-4 py-2 rounded-lg text-xs font-medium bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
