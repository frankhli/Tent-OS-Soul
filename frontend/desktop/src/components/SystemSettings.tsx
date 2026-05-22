import { useState, useEffect } from 'react';
import { Check, Volume2, Brain, Monitor, Moon, Sun, Mic, Shield, AlertTriangle } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

interface Settings {
 tts_enabled: boolean;
 tts_auto_play: boolean;
 tts_voice: string;
 show_reasoning: boolean;
 compact_mode: boolean;
 command_block_enabled: boolean;
 approval_required: boolean;
}

const DEFAULT_SETTINGS: Settings = {
 tts_enabled: true,
 tts_auto_play: false,
 tts_voice: 'xiaoxiao',
 show_reasoning: false,
 compact_mode: false,
 command_block_enabled: true,
 approval_required: false,
};

export function useSystemSettings() {
 const [settings, setSettings] = useState<Settings>(() => {
 try {
 const saved = localStorage.getItem('tent_os_settings');
 return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
 } catch {
 return DEFAULT_SETTINGS;
 }
 });

 // 启动时从后端加载用户设置，覆盖本地缓存
 useEffect(() => {
 fetch('/api/v1/settings')
 .then((res) => (res.ok ? res.json() : null))
 .then((data) => {
 if (data?.settings) {
 setSettings((prev) => ({
 ...prev,
 ...(data.settings.show_reasoning !== undefined ? { show_reasoning: data.settings.show_reasoning } : {}),
 ...(data.settings.compact_mode !== undefined ? { compact_mode: data.settings.compact_mode } : {}),
 ...(data.settings.tts_voice ? { tts_voice: data.settings.tts_voice } : {}),
 ...(data.settings.tts_enabled !== undefined ? { tts_enabled: data.settings.tts_enabled } : {}),
 ...(data.settings.tts_auto_play !== undefined ? { tts_auto_play: data.settings.tts_auto_play } : {}),
 ...(data.settings.command_block_enabled !== undefined ? { command_block_enabled: data.settings.command_block_enabled } : {}),
 ...(data.settings.approval_required !== undefined ? { approval_required: data.settings.approval_required } : {}),
 }));
 }
 })
 .catch(() => {});
 }, []);

 useEffect(() => {
 localStorage.setItem('tent_os_settings', JSON.stringify(settings));
 }, [settings]);

 const updateSetting = <K extends keyof Settings>(key: K, value: Settings[K]) => {
 setSettings((prev) => ({ ...prev, [key]: value }));
 };

 return { settings, updateSetting };
}

interface Props {
 onClose?: () => void;
 standalone?: boolean;
}

export default function SystemSettings({ onClose, standalone }: Props) {
 const { settings, updateSetting } = useSystemSettings();
 const { isDark, toggleTheme } = useTheme();
 const [saved, setSaved] = useState(false);

 const handleSave = async () => {
 localStorage.setItem('tent_os_settings', JSON.stringify(settings));
 // 同步所有设置到后端
 try {
 const res = await fetch('/api/v1/settings', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({
 show_reasoning: settings.show_reasoning,
 compact_mode: settings.compact_mode,
 tts_voice: settings.tts_voice,
 tts_enabled: settings.tts_enabled,
 tts_auto_play: settings.tts_auto_play,
 command_block_enabled: settings.command_block_enabled,
 approval_required: settings.approval_required,
 }),
 });
 if (!res.ok) {
 throw new Error(`后端保存失败: ${res.status}`);
 }
 setSaved(true);
 setTimeout(() => setSaved(false), 2000);
 } catch (e) {
 console.warn('同步设置到后端失败:', e);
 }
 };

 const Toggle = ({ label, desc, value, onChange }: { label: string; desc: string; value: boolean; onChange: (v: boolean) => void }) => (
 <div className="flex items-center justify-between">
 <div>
 <div className="text-sm font-medium text-content-primary">{label}</div>
 <div className="text-xs text-content-muted mt-0.5">{desc}</div>
 </div>
 <button
 onClick={() => onChange(!value)}
 className={`w-11 h-6 rounded-full transition relative shrink-0 ${value ? 'bg-accent-subtle' : 'bg-slate-300 bg-slate-600'}`}
 >
 <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-surface-elevated shadow transition-transform ${value ? 'translate-x-6' : 'translate-x-0.5'}`} />
 </button>
 </div>
 );

 const inner = (
 <>
 {!standalone && (
 <div className="p-5 border-b border-line-subtle flex items-center justify-between">
 <h3 className="text-lg font-bold text-content-primary flex items-center gap-2">
 <Monitor className="w-5 h-5" /> 偏好设置
 </h3>
 {onClose && (
 <button onClick={onClose} className="text-content-muted hover:text-content-secondary text-xl transition">
 &times;
 </button>
 )}
 </div>
 )}

 <div className="p-5 space-y-6 max-h-[60vh] overflow-y-auto">
 <div className="space-y-5">
 <Toggle
 label="语音合成 (TTS)"
 desc="在 AI 回复旁显示朗读按钮"
 value={settings.tts_enabled}
 onChange={(v) => updateSetting('tts_enabled', v)}
 />
 <Toggle
 label="自动朗读"
 desc="AI 回复完成后自动播放语音"
 value={settings.tts_auto_play}
 onChange={(v) => updateSetting('tts_auto_play', v)}
 />

 {/* Voice Selection */}
 <div className="pt-2">
 <div className="flex items-center gap-2 mb-2">
 <Mic className="w-3.5 h-3.5 text-content-muted" />
 <span className="text-sm font-medium text-content-primary">声音选择</span>
 </div>
 <p className="text-xs text-content-muted mb-2">当前使用 edge-tts（微软免费语音）。录制更多语音样本后，未来可切换至你的克隆声音。</p>
 <select
 value={settings.tts_voice}
 onChange={(e) => updateSetting('tts_voice', e.target.value)}
 className="w-full bg-surface-overlay border border-line-active rounded-lg px-3 py-2 text-sm text-content-primary focus:outline-none focus:border-violet-400"
 >
 <optgroup label="女声">
 <option value="xiaoxiao">晓晓 — 通用自然</option>
 <option value="xiaoyi">小艺 — 温柔舒缓</option>
 <option value="xiaohan">晓涵 — 成熟稳重</option>
 <option value="xiaomeng">晓梦 — 甜美活泼</option>
 <option value="xiaorui">晓睿 — 知性专业</option>
 </optgroup>
 <optgroup label="男声">
 <option value="yunxi">云希 — 年轻自然</option>
 <option value="yunjian">云健 — 新闻播报</option>
 <option value="yunxia">云夏 — 活泼阳光</option>
 </optgroup>
 </select>
 </div>
 <Toggle
 label="显示思考过程"
 desc="默认展开 AI 的思考推理链"
 value={settings.show_reasoning}
 onChange={(v) => updateSetting('show_reasoning', v)}
 />
 <Toggle
 label="紧凑模式"
 desc="缩小间距，显示更多内容"
 value={settings.compact_mode}
 onChange={(v) => updateSetting('compact_mode', v)}
 />
 </div>

 <div className="border-t border-line-subtle pt-5">
 <div className="text-sm font-medium text-content-primary mb-3">外观</div>
 <div className="flex items-center gap-3">
 <button
 onClick={toggleTheme}
 className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition ${
 isDark
 ? 'bg-accent-subtle text-accent border border-accent-border'
 : 'bg-surface-overlay text-content-muted border border-line-active'
 }`}
 >
 {isDark ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
 {isDark ? '夜间模式' : '日间模式'}
 </button>
 </div>
 </div>

 {/* 安全设置 */}
 <div className="border-t border-line-subtle pt-5">
 <div className="flex items-center gap-2 mb-3">
 <Shield className="w-4 h-4 text-content-muted" />
 <span className="text-sm font-medium text-content-primary">安全与权限</span>
 </div>
 <div className="space-y-4">
 <Toggle
 label="拦截危险命令"
 desc="阻止 rm -rf、sudo、mkfs 等高风险操作（推荐开启）"
 value={settings.command_block_enabled}
 onChange={(v) => updateSetting('command_block_enabled', v)}
 />
 <Toggle
 label="操作前审批"
 desc="每次执行工具前弹出确认框（默认关闭，开启后响应变慢）"
 value={settings.approval_required}
 onChange={(v) => updateSetting('approval_required', v)}
 />
 <div className="p-2.5 rounded-lg bg-amber-500/100/10 bg-amber-500/10 border border-amber-300/50">
 <div className="flex items-start gap-2">
 <AlertTriangle className="w-3.5 h-3.5 text-amber-500 mt-0.5 shrink-0" />
 <p className="text-[11px] text-amber-600 leading-relaxed">
 关闭危险命令拦截后，AI 可以执行任何 shell 命令（包括 sudo）。请确保你信任 AI 的操作。审批流程目前仅在专家模式下生效。
 </p>
 </div>
 </div>
 </div>
 </div>

 <div className="p-3 rounded-xl bg-surface-panel/50 border border-line-subtle">
 <div className="text-xs text-content-muted leading-relaxed">
 <span className="font-medium text-content-secondary">数据说明：</span>
 基础设置已同步到服务端，换设备登录可恢复。安全设置（拦截/审批）同时保存在服务端。
 </div>
 </div>
 </div>

 <div className="p-5 border-t border-line-subtle flex items-center justify-between">
 <span className={`text-sm transition flex items-center gap-1 ${saved ? 'text-emerald-500' : 'text-content-muted'}`}>
 {saved && <Check className="w-3.5 h-3.5" />}
 {saved ? '已保存' : '设置存储在浏览器本地'}
 </span>
 <div className="flex gap-2">
 {onClose && !standalone && (
 <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-content-secondary hover:bg-surface-overlay transition">
 关闭
 </button>
 )}
 <button onClick={handleSave} className="px-4 py-2 rounded-lg text-sm bg-violet-600 text-white hover:bg-violet-700 transition">
 保存
 </button>
 </div>
 </div>
 </>
 );

 if (standalone) {
 return (
 <div className="bg-surface-panel rounded-2xl shadow-sm border border-line-subtle overflow-hidden">
 {inner}
 </div>
 );
 }

 return (
 <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
 <div className="w-full max-w-lg bg-surface-panel rounded-2xl shadow-2xl overflow-hidden">
 {inner}
 </div>
 </div>
 );
}
