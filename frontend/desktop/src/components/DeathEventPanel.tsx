import { useState, useEffect, useRef } from 'react';
import { Shield, ShieldAlert, ShieldCheck, AlertTriangle } from 'lucide-react';

export default function DeathEventPanel({ userId }: { userId: string }) {
 const [deathEvent, setDeathEvent] = useState<string | null>(null);
 const [loading, setLoading] = useState(false);
 const [confirming, setConfirming] = useState(false);
 const mountedRef = useRef(true);
 useEffect(() => { return () => { mountedRef.current = false; }; }, []);

 const fetchStatus = async () => {
 try {
 const res = await fetch(`/api/v1/soul/death/${userId}`);
 const data = await res.json();
 if (!mountedRef.current) return;
 if (data.status === 'ok') {
 setDeathEvent(data.death_event);
 }
 } catch (e) {
 console.error('查询死亡事件失败:', e);
 }
 };

 useEffect(() => {
 fetchStatus();
 }, [userId]);

 const handleMark = async () => {
 if (!confirming) {
 setConfirming(true);
 return;
 }
 setLoading(true);
 try {
 const res = await fetch(`/api/v1/soul/death/${userId}`, { method: 'POST' });
 const data = await res.json();
 if (data.status === 'ok') {
 setDeathEvent(data.death_event);
 }
 } catch (e) {
 console.error('标记死亡事件失败:', e);
 } finally {
 if (mountedRef.current) {
 setLoading(false);
 setConfirming(false);
 }
 }
 };

 const handleClear = async () => {
 setLoading(true);
 try {
 const res = await fetch(`/api/v1/soul/death/${userId}`, { method: 'DELETE' });
 const data = await res.json();
 if (data.status === 'ok') {
 setDeathEvent(null);
 }
 } catch (e) {
 console.error('清除死亡事件失败:', e);
 } finally {
 if (mountedRef.current) setLoading(false);
 }
 };

 if (deathEvent) {
 return (
 <div className="space-y-3">
 <div className="flex items-center gap-2 text-amber-400">
 <ShieldAlert className="w-4 h-4" />
 <span className="text-sm font-medium">死亡事件已标记</span>
 </div>
 <div className="text-xs text-content-muted">
 时间: {new Date(deathEvent).toLocaleString('zh-CN')}
 </div>
 <div className="text-xs text-content-muted">
 此后所有对话将不再用于人格画像分析，防止继承人对话污染逝者人格。
 </div>
 <button
 onClick={handleClear}
 disabled={loading}
 className="px-3 py-1.5 text-xs bg-surface-overlay hover:bg-surface-overlay text-content-secondary rounded-lg transition disabled:opacity-50"
 >
 {loading ? '处理中...' : '清除标记（测试用）'}
 </button>
 </div>
 );
 }

 return (
 <div className="space-y-3">
 <div className="flex items-center gap-2 text-content-muted">
 <Shield className="w-4 h-4" />
 <span className="text-sm">死亡事件未标记</span>
 </div>
 <div className="text-xs text-content-muted">
 标记后，所有此后的对话将不再用于人格画像分析。
 这是防止继承人对话污染逝者人格的核心机制。
 </div>
 {confirming ? (
 <div className="space-y-2">
 <div className="flex items-center gap-2 text-amber-400 text-xs">
 <AlertTriangle className="w-4 h-4" />
 <span>此操作不可逆，确认标记死亡事件？</span>
 </div>
 <div className="flex gap-2">
 <button
 onClick={handleMark}
 disabled={loading}
 className="px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition disabled:opacity-50"
 >
 {loading ? '处理中...' : '确认标记'}
 </button>
 <button
 onClick={() => setConfirming(false)}
 className="px-3 py-1.5 text-xs bg-surface-overlay hover:bg-surface-overlay text-content-secondary rounded-lg transition"
 >
 取消
 </button>
 </div>
 </div>
 ) : (
 <button
 onClick={handleMark}
 className="px-3 py-1.5 text-xs bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-600/30 rounded-lg transition"
 >
 标记死亡事件
 </button>
 )}
 </div>
 );
}