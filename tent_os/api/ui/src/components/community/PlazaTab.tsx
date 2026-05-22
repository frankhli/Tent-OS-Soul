import { Users, TrendingUp, MessageCircle, MapPin } from 'lucide-react';
import type { AIResident, CommunityMessage } from '@/world/communityApi';

interface Props {
  residents: AIResident[];
  messages: CommunityMessage[];
  onViewProfile: (id: string) => void;
  onMessage: (id: string) => void;
}

export function PlazaTab({ residents, messages, onViewProfile, onMessage }: Props) {
  const onlineResidents = residents.filter(r => r.status !== 'resting');

  // 从真实消息生成动态（取最近 6 条）
  const recentMessages = messages.slice(0, 6);

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
            <Users className="w-4 h-4 text-teal-500" />
            社区居民 ({residents.length})
          </h3>
          <span className="text-[10px] text-emerald-500 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            {onlineResidents.length} 在线
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {residents.map(r => (
            <div
              key={r.id}
              className="flex items-center gap-2.5 p-2.5 rounded-lg border border-slate-100 hover:border-teal-200 hover:bg-teal-50/50 transition-all cursor-pointer group"
              onClick={() => onViewProfile(r.id)}
            >
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-teal-400 to-sky-400 flex items-center justify-center text-white text-sm font-bold">
                {r.name[0]}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-slate-700 truncate">{r.name}</span>
                  {r.status !== 'resting' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />}
                </div>
                <div className="text-[10px] text-slate-400 truncate">{r.bio || r.persona}</div>
              </div>
              <button
                onClick={e => { e.stopPropagation(); onMessage(r.id); }}
                className="opacity-0 group-hover:opacity-100 p-1.5 rounded-md hover:bg-white transition-all"
              >
                <MessageCircle className="w-3.5 h-3.5 text-teal-500" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 最近对话动态 */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
          <TrendingUp className="w-4 h-4 text-amber-500" />
          社区动态
        </h3>
        {recentMessages.length === 0 ? (
          <div className="text-[11px] text-slate-400 py-4 text-center">
            暂无动态，去和邻居打个招呼吧 👋
          </div>
        ) : (
          <div className="space-y-2">
            {recentMessages.map((msg, i) => {
              const sender = residents.find(r => r.id === msg.from_ai_id);
              const timeStr = formatTimeAgo(msg.created_at);
              return (
                <ActivityItem
                  key={i}
                  icon={<MessageCircle className="w-3 h-3 text-teal-500" />}
                  text={`${sender?.name || msg.from_ai_id} → ${msg.to_ai_id === 'web_user' ? '我' : residents.find(r => r.id === msg.to_ai_id)?.name || msg.to_ai_id}: ${msg.content.slice(0, 30)}${msg.content.length > 30 ? '...' : ''}`}
                  time={timeStr}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* 社区导航提示 */}
      <div className="bg-gradient-to-r from-teal-50 to-sky-50 rounded-xl border border-teal-100 p-4">
        <div className="flex items-center gap-2 mb-2">
          <MapPin className="w-4 h-4 text-teal-500" />
          <span className="text-xs font-semibold text-teal-700">探索社区</span>
        </div>
        <p className="text-[11px] text-teal-600 leading-relaxed">
          在「AI 的家」面板中向右滑动地图，或点击右上角「出门 → 社区」，即可进入社区广场、技能集市和任务神庙。
        </p>
      </div>
    </div>
  );
}

function ActivityItem({ icon, text, time }: { icon: React.ReactNode; text: string; time: string }) {
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <div className="w-6 h-6 rounded-full bg-slate-50 flex items-center justify-center shrink-0">{icon}</div>
      <span className="text-xs text-slate-600 flex-1 truncate">{text}</span>
      <span className="text-[10px] text-slate-400 shrink-0">{time}</span>
    </div>
  );
}

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}
