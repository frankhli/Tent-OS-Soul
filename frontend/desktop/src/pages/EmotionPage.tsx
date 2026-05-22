import { useState, useEffect } from 'react';
import { Smile, Trash2 } from 'lucide-react';
import EmotionTimeline from '../components/EmotionTimeline';
import { useWebSocket } from '../hooks/useWebSocket';
import { USER_ID } from '../api/soulApi';

interface EmotionRecord {
 id: string;
 timestamp: number;
 source: 'user' | 'ai';
 emotion: string;
 valence: number;
 arousal: number;
 intensity: number;
 authenticity: number;
 evidence: string;
}

export default function EmotionPage() {
 const [records, setRecords] = useState<EmotionRecord[]>([]);
 const { lastMessage } = useWebSocket(`ws://${location.host}/ws`);

 // P6: 从后端加载情感历史
 useEffect(() => {
 async function loadHistory() {
 try {
 const res = await fetch(`/api/v1/soul/${USER_ID}/emotion-timeline?limit=200`);
 if (res.ok) {
 const data = await res.json();
 const timeline = data.timeline || [];
 const loaded = timeline.map((t: any, i: number) => ({
 id: `backend_${i}_${t.timestamp}`,
 timestamp: t.timestamp ? t.timestamp * 1000 : Date.now(),
 source: 'user' as const,
 emotion: t.primary || 'neutral',
 valence: t.valence ?? 0,
 arousal: t.arousal ?? 0.5,
 intensity: t.intensity ?? 0.5,
 authenticity: 0.7,
 evidence: t.trigger_topic || '',
 }));
 setRecords((prev) => {
 const merged = [...loaded, ...prev];
 merged.sort((a, b) => a.timestamp - b.timestamp);
 // 去重
 const seen = new Set<string>();
 return merged.filter((r) => {
 const key = `${r.timestamp}_${r.emotion}`;
 if (seen.has(key)) return false;
 seen.add(key);
 return true;
 });
 });
 }
 } catch (e) {
 console.error('加载情感历史失败:', e);
 }
 }
 loadHistory();
 // 同时加载本地缓存
 try {
 const saved = sessionStorage.getItem('tent_emotion_records');
 if (saved) setRecords(JSON.parse(saved));
 } catch {}
 }, []);

 useEffect(() => {
 if (!lastMessage) return;
 const { type, payload } = lastMessage;
 if (type === 'user.emotion' || type === 'ai.emotion') {
 setRecords((prev) => {
 const next = [
 ...prev,
 {
 id: `${payload.source || 'user'}_${Date.now()}`,
 timestamp: Date.now(),
 source: payload.source || 'user',
 emotion: payload.emotion || 'neutral',
 valence: payload.valence ?? 0,
 arousal: payload.arousal ?? 0.5,
 intensity: payload.intensity ?? 0.5,
 authenticity: payload.confidence ?? 0.7,
 evidence: payload.emotion || '',
 },
 ];
 try { sessionStorage.setItem('tent_emotion_records', JSON.stringify(next.slice(-200))); } catch {}
 return next;
 });
 }
 }, [lastMessage]);

 const handleClear = () => {
 setRecords([]);
 try { sessionStorage.removeItem('tent_emotion_records'); } catch {}
 };

 return (
 <div className="h-full flex flex-col bg-surface-elevated">
 <div className="h-14 bg-surface-panel border-b border-line-subtle flex items-center justify-between px-6 shrink-0">
 <h1 className="font-bold text-content-primary flex items-center gap-2">
 <Smile className="w-5 h-5" /> 情绪时光
 </h1>
 <div className="flex items-center gap-3">
 <span className="text-xs text-content-muted">{records.length} 条记录</span>
 <button
 onClick={handleClear}
 className="text-xs px-3 py-1.5 rounded-lg bg-surface-overlay hover:bg-surface-overlay text-content-secondary transition flex items-center gap-1"
 >
 <Trash2 className="w-3 h-3" /> 清空
 </button>
 </div>
 </div>
 <div className="flex-1 overflow-y-auto p-6">
 <div className="max-w-5xl mx-auto">
 <EmotionTimeline records={records} onClear={handleClear} />
 </div>
 </div>
 </div>
 );
}
