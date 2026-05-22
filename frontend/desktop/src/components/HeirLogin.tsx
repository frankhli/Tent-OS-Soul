import { useState, useEffect } from 'react';
import { Flame } from 'lucide-react';

interface Props {
 onAccess: (userId: string, heirName: string, token: string) => void;
}

interface EternalStatus {
 user_id: string;
 user_name: string;
 is_active: boolean;
 activation_condition: string;
 heirs: { name: string; relationship: string }[];
 farewell_letter?: string;
 has_access_code?: boolean;
 soul_completeness: Record<string, number>;
}

export default function HeirLogin({ onAccess }: Props) {
 const [userId, setUserId] = useState('web_user');
 const [heirName, setHeirName] = useState('');
 const [accessCode, setAccessCode] = useState('');
 const [status, setStatus] = useState<EternalStatus | null>(null);
 const [loading, setLoading] = useState(false);
 const [error, setError] = useState('');
 const [checking, setChecking] = useState(false);

 // 自动检查状态
 useEffect(() => {
 if (!userId) return;
 const timer = setTimeout(() => checkStatus(userId), 500);
 return () => clearTimeout(timer);
 }, [userId]);

 const checkStatus = async (uid: string) => {
 setChecking(true);
 try {
 const res = await fetch(`/api/v1/soul/eternal/status/${uid}`);
 if (res.ok) {
 const data = await res.json();
 setStatus(data);
 }
 } catch {
 setStatus(null);
 } finally {
 setChecking(false);
 }
 };

 const handleLogin = async () => {
 if (!heirName.trim()) {
 setError('请输入你的姓名');
 return;
 }
 setLoading(true);
 setError('');
 try {
 const res = await fetch(`/api/v1/soul/eternal/access/${userId}`, {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ heir_name: heirName.trim(), access_code: accessCode }),
 });
 const data = await res.json();
 if (!res.ok) {
 setError(data.detail || '验证失败');
 return;
 }
 onAccess(userId, data.heir_name, data.token);
 } catch (e: any) {
 setError('网络错误，请稍后重试');
 } finally {
 setLoading(false);
 }
 };

 return (
 <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-6">
 <div className="w-full max-w-md">
 {/* Header */}
 <div className="text-center mb-10">
 <div className="mb-4 flex justify-center"><Flame className="w-12 h-12 text-violet-300" /></div>
 <h1 className="text-2xl font-bold text-white mb-2">灵魂对讲机</h1>
 <p className="text-content-muted text-sm">
 当记忆成为桥梁，爱便跨越了时间
 </p>
 </div>

 {/* Status Card */}
 {status && (
 <div className="mb-6 p-4 rounded-xl bg-surface-panel/60 border border-line-subtle/50">
 {checking ? (
 <div className="text-center text-content-muted text-sm">查询中...</div>
 ) : (
 <>
 <div className="flex items-center justify-between mb-2">
 <span className="text-sm text-content-secondary">
 {status.user_name || status.user_id}
 </span>
 <span className={`text-xs px-2 py-0.5 rounded-full ${
 status.is_active
 ? 'bg-emerald-500/100/20 text-emerald-300 border border-emerald-500/30'
 : 'bg-amber-500/100/20 text-amber-300 border border-amber-500/30'
 }`}>
 {status.is_active ? '已激活' : '未激活'}
 </span>
 </div>
 {status.is_active && status.soul_completeness && (
 <div className="mt-3">
 <div className="text-xs text-content-muted mb-1.5">灵魂完整度</div>
 <div className="h-1.5 bg-surface-overlay rounded-full overflow-hidden">
 <div
 className="h-full bg-accent-subtle rounded-full transition-all"
 style={{ width: `${(status.soul_completeness.overall || 0) * 100}%` }}
 />
 </div>
 <div className="text-[10px] text-content-muted mt-1">
 {Math.round((status.soul_completeness.overall || 0) * 100)}%
 </div>
 </div>
 )}
 {!status.is_active && (
 <p className="text-xs text-amber-400/80 mt-2">
 遗嘱尚未激活。当激活条件满足后，继承人即可访问。
 </p>
 )}
 </>
 )}
 </div>
 )}

 {/* Login Form */}
 <div className="space-y-4">
 <div>
 <label className="text-sm text-content-muted block mb-1.5">逝者标识</label>
 <input
 type="text"
 value={userId}
 onChange={(e) => setUserId(e.target.value)}
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2.5 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500"
 placeholder="输入逝者标识..."
 />
 </div>

 <div>
 <label className="text-sm text-content-muted block mb-1.5">你的姓名</label>
 <input
 type="text"
 value={heirName}
 onChange={(e) => setHeirName(e.target.value)}
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2.5 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500"
 placeholder="输入你在遗嘱中登记的姓名..."
 />
 {status && status.heirs.length > 0 && (
 <div className="mt-2 flex flex-wrap gap-1.5">
 <span className="text-[10px] text-content-muted">登记的继承人：</span>
 {status.heirs.map((h, i) => (
 <button
 key={i}
 onClick={() => setHeirName(h.name)}
 className="text-[10px] px-2 py-0.5 rounded-full bg-surface-overlay text-content-secondary hover:bg-surface-overlay transition"
 >
 {h.name}（{h.relationship}）
 </button>
 ))}
 </div>
 )}
 </div>

 {status?.has_access_code && (
 <div>
 <label className="text-sm text-content-muted block mb-1.5">
 访问验证码 <span className="text-amber-400">*</span>
 </label>
 <input
 type="password"
 value={accessCode}
 onChange={(e) => setAccessCode(e.target.value)}
 className="w-full bg-surface-panel border border-line-subtle rounded-lg px-3 py-2.5 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500"
 placeholder="请输入遗嘱中设置的验证码"
 />
 <p className="text-[10px] text-content-muted mt-1">此验证码由逝者生前设置，用于保护数字灵魂不被未授权访问。</p>
 </div>
 )}

 {error && (
 <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
 {error}
 </div>
 )}

 <button
 onClick={handleLogin}
 disabled={loading || !status?.is_active}
 className="w-full py-3 bg-violet-600 hover:bg-violet-700 disabled:bg-surface-overlay disabled:text-content-muted text-white rounded-xl text-sm font-medium transition"
 >
 {loading ? '验证中...' : !status?.is_active ? '遗嘱尚未激活' : '进入永恒对话'}
 </button>

 <p className="text-center text-xs text-content-muted mt-4">
 所有访问记录均被加密存储，仅限授权继承人查看
 </p>
 </div>
 </div>
 </div>
 );
}
