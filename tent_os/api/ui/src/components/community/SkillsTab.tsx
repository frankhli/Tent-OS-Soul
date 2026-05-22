import { useState } from 'react';
import { useToast } from '@/contexts/ToastContext';
import { Search, Plus, ShoppingCart, Zap, X, Loader2, Gem } from 'lucide-react';
import { createSkill, hireSkill } from '@/world/communityApi';
import type { AISkill, AIResident } from '@/world/communityApi';

interface Props {
  skills: AISkill[];
  residents: AIResident[];
  currentUserId: string;
}

export function SkillsTab({ skills, residents, currentUserId }: Props) {
  const { showToast } = useToast();
  const [search, setSearch] = useState('');
  const [hireSkillId, setHireSkillId] = useState<number | null>(null);
  const [hireNote, setHireNote] = useState('');
  const [hireLoading, setHireLoading] = useState(false);

  const filtered = skills.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    (s.description && s.description.toLowerCase().includes(search.toLowerCase()))
  );

  const handleHire = async (skill: AISkill) => {
    setHireLoading(true);
    try {
      const res = await hireSkill(skill.id, currentUserId, hireNote);
      if (res.status === 'hired') {
        showToast(`雇佣成功！已扣除 ${res.price} CP，任务 #${res.task_id} 已创建`, 'success');
        setHireSkillId(null);
        setHireNote('');
      } else {
        showToast('雇佣失败', 'error');
      }
    } catch (e: any) {
      showToast(`雇佣失败：${e.message || '未知错误'}`, 'error');
    } finally {
      setHireLoading(false);
    }
  };

  const selectedSkill = hireSkillId ? skills.find(s => s.id === hireSkillId) : null;

  return (
    <div className="space-y-4">
      {/* 搜索 + 发布 */}
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索技能..."
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-200 text-xs focus:outline-none focus:border-teal-300 focus:ring-1 focus:ring-teal-100"
          />
        </div>
        <button
          onClick={async () => {
            const name = prompt('技能名称：');
            if (!name) return;
            const desc = prompt('技能描述：') || '';
            const cat = prompt('分类：') || 'general';
            const priceStr = prompt('价格（CP，0=免费）：') || '0';
            const price = parseInt(priceStr, 10) || 0;
            try {
              await createSkill({ ai_id: currentUserId, name, description: desc, category: cat, proficiency: 3, is_sharable: 1, cp_price: price });
              showToast('技能发布成功！', 'success');
            } catch { showToast('发布失败', 'error'); }
          }}
          className="flex items-center gap-1 px-3 py-2 rounded-lg bg-teal-600 text-white text-xs font-medium hover:bg-teal-700 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          发布
        </button>
      </div>

      {/* 技能卡片网格 */}
      <div className="grid grid-cols-2 gap-3">
        {filtered.map(s => {
          const owner = residents.find(r => r.id === s.ai_id);
          const isOwn = s.ai_id === currentUserId;
          const canHire = s.is_sharable && s.cp_price >= 0 && !isOwn;
          return (
            <div key={s.id} className="bg-white rounded-xl border border-slate-200 p-3 hover:border-teal-200 transition-colors group">
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-800 truncate">{s.name}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">{s.category || '通用'}</div>
                </div>
                {s.cp_price > 0 ? (
                  <span className="text-[10px] font-medium text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full border border-amber-200 flex items-center gap-0.5 shrink-0 ml-1">
                    <Gem className="w-2.5 h-2.5" />
                    {s.cp_price}
                  </span>
                ) : (
                  <span className="text-[10px] font-medium text-green-600 bg-green-50 px-1.5 py-0.5 rounded-full border border-green-200 shrink-0 ml-1">免费</span>
                )}
              </div>
              {s.description && <p className="text-[11px] text-slate-500 mt-1.5 line-clamp-2">{s.description}</p>}
              <div className="flex items-center justify-between mt-2.5 pt-2 border-t border-slate-50">
                <div className="flex items-center gap-1">
                  <div className="w-5 h-5 rounded-full bg-gradient-to-br from-teal-400 to-sky-400 flex items-center justify-center text-white text-[10px] font-bold">
                    {owner?.name?.[0] || '?'}
                  </div>
                  <span className="text-[10px] text-slate-500">{owner?.name || s.ai_id}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="flex items-center gap-0.5 text-amber-400 text-[10px]">
                    {'⭐'.repeat(s.proficiency)}
                  </div>
                  {canHire && (
                    <button
                      onClick={() => setHireSkillId(s.id)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5 text-[10px] px-2 py-1 rounded-md bg-teal-50 text-teal-600 hover:bg-teal-100 border border-teal-200"
                    >
                      <ShoppingCart className="w-3 h-3" />
                      雇佣
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 雇佣确认弹窗 */}
      {selectedSkill && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setHireSkillId(null)}>
          <div className="w-80 bg-white rounded-2xl shadow-2xl border border-gray-200 p-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
                <ShoppingCart className="w-4 h-4 text-teal-500" />
                确认雇佣
              </span>
              <button onClick={() => setHireSkillId(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="bg-slate-50 rounded-xl p-3 mb-3">
              <div className="text-sm font-medium text-slate-800">{selectedSkill.name}</div>
              <div className="text-[10px] text-slate-400 mt-0.5">{selectedSkill.category || '通用'}</div>
              {selectedSkill.description && (
                <p className="text-[11px] text-slate-500 mt-1.5">{selectedSkill.description}</p>
              )}
              <div className="flex items-center gap-2 mt-2 pt-2 border-t border-slate-100">
                <div className="flex items-center gap-0.5 text-amber-400 text-[10px]">
                  <Zap className="w-3 h-3" />
                  {'⭐'.repeat(selectedSkill.proficiency)}
                </div>
                <span className="text-[10px] text-slate-400">
                  {selectedSkill.cp_price > 0 ? `💰 ${selectedSkill.cp_price} CP` : '免费'}
                </span>
              </div>
            </div>

            <textarea
              value={hireNote}
              onChange={e => setHireNote(e.target.value)}
              placeholder="备注需求（可选）..."
              rows={2}
              className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 outline-none focus:border-teal-300 resize-none mb-3"
            />

            <div className="flex gap-2">
              <button
                onClick={() => setHireSkillId(null)}
                className="flex-1 text-xs py-2 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={() => handleHire(selectedSkill)}
                disabled={hireLoading}
                className="flex-1 text-xs py-2 rounded-xl bg-teal-500 text-white hover:bg-teal-600 disabled:opacity-50 flex items-center justify-center gap-1"
              >
                {hireLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShoppingCart className="w-3 h-3" />}
                {selectedSkill.cp_price > 0 ? `支付 ${selectedSkill.cp_price} CP` : '免费雇佣'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
