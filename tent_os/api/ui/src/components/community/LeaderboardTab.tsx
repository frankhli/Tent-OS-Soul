import { useState, useEffect } from 'react';
import { Trophy, Gem, Shield, Zap } from 'lucide-react';
import { getLeaderboard } from '@/world/communityApi';

export function LeaderboardTab() {
  const [category, setCategory] = useState<'overall' | 'wealth' | 'reliable' | 'skilled'>('overall');
  const [data, setData] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    getLeaderboard(category).then(r => setData(r.leaderboard));
  }, [category]);

  const categories = [
    { key: 'overall' as const, label: '综合', icon: <Trophy className="w-3.5 h-3.5" /> },
    { key: 'wealth' as const, label: '财富', icon: <Gem className="w-3.5 h-3.5" /> },
    { key: 'reliable' as const, label: '可靠', icon: <Shield className="w-3.5 h-3.5" /> },
    { key: 'skilled' as const, label: '技能', icon: <Zap className="w-3.5 h-3.5" /> },
  ];

  return (
    <div className="space-y-4">
      <div className="flex gap-1">
        {categories.map(c => (
          <button
            key={c.key}
            onClick={() => setCategory(c.key)}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              category === c.key ? 'bg-teal-600 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {c.icon}
            {c.label}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {data.map((item, i) => {
          const name = (item.resident_name || item.ai_id) as string;
          const score = (item.overall_score || item.balance || item.reliability || item.skill_level || 0) as number;
          const isTop3 = i < 3;
          return (
            <div key={i} className={`flex items-center gap-3 px-4 py-3 ${i !== data.length - 1 ? 'border-b border-slate-50' : ''}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                isTop3 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'
              }`}>
                {i + 1}
              </div>
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-teal-400 to-sky-400 flex items-center justify-center text-white text-xs font-bold">
                {name[0]}
              </div>
              <div className="flex-1">
                <div className="text-xs font-medium text-slate-700">{name}</div>
              </div>
              <div className="text-xs font-bold text-teal-600">{typeof score === 'number' ? score.toFixed(0) : score}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
