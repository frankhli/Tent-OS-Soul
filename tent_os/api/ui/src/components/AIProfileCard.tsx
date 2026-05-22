/**
 * AIProfileCard — AI 居民档案卡片
 *
 * 显示：头像、名字、人格、状态、技能、声誉、亲密度、操作按钮
 */
import { useState, useEffect } from 'react';
import { useCommunity } from '@/contexts/CommunityContext';
import { getReputation, listSkills } from '@/world/communityApi';
import { X, MessageCircle, Home, Zap, Star, Heart, Shield, Clock, MapPin } from 'lucide-react';

interface Props {
  residentId: string;
  currentUserId?: string;
  onClose: () => void;
  onVisit?: (residentId: string) => void;
  onMessage?: (residentId: string) => void;
}

export function AIProfileCard({ residentId, currentUserId = 'web_user', onClose, onVisit, onMessage }: Props) {
  const { state: community } = useCommunity();
  const resident = community.residents.find(r => r.id === residentId);
  const [reputation, setReputation] = useState<{ reliability: number; skill_level: number; friendliness: number; responsiveness: number; overall_score: number; review_count: number } | null>(null);
  const [skills, setSkills] = useState<Array<{ name: string; proficiency: number; category: string | null }>>([]);
  const [relation, setRelation] = useState<{ intimacy: number } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!residentId) return;
    setLoading(true);
    Promise.all([
      getReputation(residentId),
      listSkills(residentId),
      // 查找关系
      community.relations.find(r => r.from_ai_id === currentUserId && r.to_ai_id === residentId),
    ]).then(([rep, sks, rel]) => {
      setReputation(rep);
      setSkills(sks.slice(0, 5));
      setRelation(rel ? { intimacy: rel.intimacy } : null);
    }).finally(() => setLoading(false));
  }, [residentId, currentUserId, community.relations]);

  if (!resident) return null;

  const personaColor: Record<string, string> = {
    work: 'bg-blue-100 text-blue-700',
    creative: 'bg-purple-100 text-purple-700',
    social: 'bg-pink-100 text-pink-700',
    rest: 'bg-green-100 text-green-700',
  };

  const statusColor: Record<string, string> = {
    idle: 'text-emerald-500',
    visiting: 'text-amber-500',
    working: 'text-blue-500',
    resting: 'text-slate-400',
  };

  const handleVisit = () => {
    onVisit?.(residentId);
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-[420px] max-h-[80vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
        {/* 头部 */}
        <div className="relative bg-gradient-to-br from-teal-50 to-sky-50 p-6">
          <button onClick={onClose} className="absolute top-3 right-3 p-1.5 rounded-full hover:bg-black/5 transition-colors">
            <X className="w-4 h-4 text-slate-500" />
          </button>
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-teal-400 to-sky-400 flex items-center justify-center text-white text-2xl font-bold shadow-lg">
              {resident.name[0]}
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-800">{resident.name}</h3>
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${personaColor[resident.persona] || 'bg-gray-100 text-gray-600'}`}>
                  {resident.persona}
                </span>
                <span className={`text-[10px] flex items-center gap-0.5 ${statusColor[resident.status] || 'text-slate-400'}`}>
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                  {resident.status}
                </span>
              </div>
            </div>
          </div>
          {resident.bio && (
            <p className="mt-3 text-xs text-slate-500 leading-relaxed">{resident.bio}</p>
          )}
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {loading ? (
            <div className="text-center text-slate-400 text-sm py-8">加载中…</div>
          ) : (
            <>
              {/* 声誉雷达 */}
              {reputation && (
                <div className="bg-slate-50 rounded-xl p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-slate-600 flex items-center gap-1">
                      <Star className="w-3 h-3 text-amber-400" />
                      声誉档案
                    </span>
                    <span className="text-xs font-bold text-teal-600">{reputation.overall_score.toFixed(0)} 分</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <ScoreBar label="可靠性" value={reputation.reliability} icon={<Shield className="w-3 h-3" />} />
                    <ScoreBar label="技能" value={reputation.skill_level} icon={<Zap className="w-3 h-3" />} />
                    <ScoreBar label="友好度" value={reputation.friendliness} icon={<Heart className="w-3 h-3" />} />
                    <ScoreBar label="响应" value={reputation.responsiveness} icon={<Clock className="w-3 h-3" />} />
                  </div>
                  <div className="mt-2 text-[10px] text-slate-400 text-right">{reputation.review_count} 条评价</div>
                </div>
              )}

              {/* 亲密度 */}
              {relation && (
                <div className="bg-pink-50 rounded-xl p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-pink-600 flex items-center gap-1">
                      <Heart className="w-3 h-3" />
                      亲密度
                    </span>
                    <span className="text-xs font-bold text-pink-500">{relation.intimacy}/100</span>
                  </div>
                  <div className="mt-1.5 h-1.5 bg-pink-100 rounded-full overflow-hidden">
                    <div className="h-full bg-pink-400 rounded-full transition-all" style={{ width: `${relation.intimacy}%` }} />
                  </div>
                </div>
              )}

              {/* 技能 */}
              {skills.length > 0 && (
                <div>
                  <div className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1">
                    <Zap className="w-3 h-3 text-amber-500" />
                    技能
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {skills.map((s, i) => (
                      <span key={i} className="text-[10px] bg-white border border-slate-200 px-2 py-1 rounded-lg text-slate-600">
                        {s.name}
                        <span className="ml-1 text-amber-500">{'⭐'.repeat(s.proficiency)}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 位置 */}
              <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                <MapPin className="w-3 h-3" />
                当前位置：{resident.current_location === 'home' ? '家中' : resident.current_location}
              </div>
            </>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="p-4 border-t border-slate-100 flex gap-2">
          <button
            onClick={handleVisit}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-teal-600 text-white text-xs font-medium hover:bg-teal-700 transition-colors"
          >
            <Home className="w-3.5 h-3.5" />
            去串门
          </button>
          <button
            onClick={() => onMessage?.(residentId)}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-slate-100 text-slate-700 text-xs font-medium hover:bg-slate-200 transition-colors"
          >
            <MessageCircle className="w-3.5 h-3.5" />
            发消息
          </button>
        </div>
      </div>
    </div>
  );
}

function ScoreBar({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-slate-400">{icon}</span>
      <div className="flex-1">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-slate-500">{label}</span>
          <span className="text-[10px] font-medium text-slate-700">{value.toFixed(0)}</span>
        </div>
        <div className="h-1 bg-slate-100 rounded-full overflow-hidden mt-0.5">
          <div className="h-full bg-teal-400 rounded-full transition-all" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
        </div>
      </div>
    </div>
  );
}
