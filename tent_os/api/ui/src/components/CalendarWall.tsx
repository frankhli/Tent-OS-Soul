/**
 * CalendarWall — AI 庄园的日历墙
 * 挂在书房墙上的实体日历，显示每日任务完成情况
 */

import { useState, useEffect, useCallback } from 'react';
import { Calendar, ChevronLeft, ChevronRight, CheckCircle2, XCircle, Clock, Sparkles } from 'lucide-react';

interface CalendarTask {
  session_id: string;
  status: string;
  task: string;
  created_at: string;
}

interface CalendarDay {
  date: string;
  day: number;
  tasks: CalendarTask[];
  has_completed: boolean;
  has_failed: boolean;
  has_pending: boolean;
}

interface CalendarData {
  month: string;
  year: number;
  mon: number;
  days_in_month: number;
  first_weekday: number;
  grid: (CalendarDay | null)[];
  total_tasks: number;
}

interface CalendarWallProps {
  onClose?: () => void;
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];
const MONTH_NAMES = [
  '一月', '二月', '三月', '四月', '五月', '六月',
  '七月', '八月', '九月', '十月', '十一月', '十二月',
];

export function CalendarWall({ onClose }: CalendarWallProps) {
  const [data, setData] = useState<CalendarData | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentMonth, setCurrentMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [selectedDay, setSelectedDay] = useState<CalendarDay | null>(null);

  const fetchCalendar = useCallback(async (month: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/ui/api/world/calendar?month=${month}`);
      if (res.ok) {
        const d = await res.json();
        setData(d);
      }
    } catch (e) {
      console.error('[CalendarWall] fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCalendar(currentMonth);
  }, [currentMonth, fetchCalendar]);

  const goPrevMonth = () => {
    const [y, m] = currentMonth.split('-').map(Number);
    const prev = m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`;
    setCurrentMonth(prev);
    setSelectedDay(null);
  };

  const goNextMonth = () => {
    const [y, m] = currentMonth.split('-').map(Number);
    const next = m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`;
    setCurrentMonth(next);
    setSelectedDay(null);
  };

  const todayStr = new Date().toISOString().slice(0, 10);

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-amber-50 to-orange-50">
      {/* 头部 — 日历标题栏 */}
      <div className="px-5 py-4 bg-white border-b border-amber-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Calendar className="w-5 h-5 text-amber-600" />
          <div>
            <h2 className="text-sm font-bold text-gray-800">
              {data ? `${data.year}年 ${MONTH_NAMES[data.mon - 1]}` : '日历墙'}
            </h2>
            <p className="text-[10px] text-gray-400">
              {data?.total_tasks ?? 0} 个任务记录
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={goPrevMonth}
            className="p-1.5 rounded-lg hover:bg-amber-100 text-gray-500 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs font-medium text-gray-600 w-16 text-center">
            {currentMonth}
          </span>
          <button
            onClick={goNextMonth}
            className="p-1.5 rounded-lg hover:bg-amber-100 text-gray-500 transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="ml-2 px-3 py-1 rounded-lg text-xs bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
            >
              关闭
            </button>
          )}
        </div>
      </div>

      {/* 日历网格 */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {loading ? (
          <div className="h-full flex items-center justify-center text-gray-400 text-sm">
            <Sparkles className="w-5 h-5 animate-spin mr-2" />
            加载日历...
          </div>
        ) : (
          <>
            {/* 星期标题 */}
            <div className="grid grid-cols-7 gap-1 mb-2">
              {WEEKDAYS.map((w) => (
                <div key={w} className="text-center text-[10px] font-medium text-gray-400 py-1">
                  {w}
                </div>
              ))}
            </div>

            {/* 日期网格 */}
            <div className="grid grid-cols-7 gap-1">
              {data?.grid.map((day, idx) => {
                if (!day) {
                  return <div key={`empty-${idx}`} className="aspect-square" />;
                }
                const isToday = day.date === todayStr;
                const isSelected = selectedDay?.date === day.date;
                const hasAny = day.tasks.length > 0;

                return (
                  <button
                    key={day.date}
                    onClick={() => setSelectedDay(isSelected ? null : day)}
                    className={`aspect-square rounded-xl border text-xs flex flex-col items-center justify-center gap-0.5 transition-all ${
                      isSelected
                        ? 'bg-amber-500 text-white border-amber-500 shadow-md'
                        : isToday
                        ? 'bg-amber-100 border-amber-300 text-amber-800'
                        : hasAny
                        ? 'bg-white border-amber-200 hover:border-amber-400 text-gray-700'
                        : 'bg-white/50 border-transparent text-gray-400 hover:bg-white hover:border-gray-200'
                    }`}
                  >
                    <span className={`font-semibold ${isSelected ? 'text-white' : ''}`}>
                      {day.day}
                    </span>
                    {hasAny && (
                      <div className="flex gap-0.5">
                        {day.has_completed && (
                          <div className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-white' : 'bg-green-400'}`} />
                        )}
                        {day.has_failed && (
                          <div className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-white' : 'bg-red-400'}`} />
                        )}
                        {day.has_pending && (
                          <div className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-white' : 'bg-amber-400'}`} />
                        )}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>

            {/* 选中日期详情 */}
            {selectedDay && (
              <div className="mt-4 bg-white rounded-xl border border-amber-200 p-3">
                <h3 className="text-xs font-semibold text-gray-700 mb-2">
                  {selectedDay.date} 的任务
                </h3>
                <div className="space-y-1.5">
                  {selectedDay.tasks.map((t, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-gray-50 text-xs"
                    >
                      {t.status === 'completed' ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
                      ) : t.status === 'failed' ? (
                        <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />
                      ) : (
                        <Clock className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                      )}
                      <span className="text-gray-700 truncate flex-1">{t.task || '未命名任务'}</span>
                      <span className={`text-[10px] shrink-0 ${
                        t.status === 'completed' ? 'text-green-600' :
                        t.status === 'failed' ? 'text-red-600' :
                        'text-amber-600'
                      }`}>
                        {t.status === 'completed' ? '已完成' :
                         t.status === 'failed' ? '失败' :
                         t.status === 'executing' ? '执行中' : '进行中'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 图例 */}
            <div className="mt-4 flex items-center gap-4 text-[10px] text-gray-400">
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-green-400" />
                <span>已完成</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-amber-400" />
                <span>进行中</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-red-400" />
                <span>失败</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
