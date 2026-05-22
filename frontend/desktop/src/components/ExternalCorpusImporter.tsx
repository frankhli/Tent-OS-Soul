/**
 * 外部语料导入组件
 * 支持导入微信聊天记录、邮件、日记等外部语料，
 * 解析后存入记忆库并更新人格画像。
 */

import { useState, useRef, useCallback } from 'react';
import { Upload, FileText, Mail, BookOpen, CheckCircle, AlertCircle, Loader2, X } from 'lucide-react';

interface IngestResult {
 status: string;
 parser_used: string;
 parse_summary: {
 total_messages: number;
 speakers: string[];
 time_range: { earliest: string | null; latest: string | null };
 } | null;
 memory: { inserted: number; skipped: number; failed: number; errors: string[] };
 persona: { extracted: boolean; fields_updated: number };
 profile: { updated: boolean; rebuilt: boolean };
 timing: { duration_seconds: number };
 warnings: string[];
}

const PARSER_OPTIONS = [
 { name: 'wechat', label: '微信聊天记录', icon: MessageSquareIcon, ext: '.txt', desc: '微信导出的 txt 聊天记录' },
 { name: 'email', label: '邮件', icon: MailIcon, ext: '.eml/.mbox', desc: '单封邮件或邮件集合' },
 { name: 'diary', label: '日记/备忘录', icon: BookOpenIcon, ext: '.txt/.md', desc: '带日期标记的文本或 Markdown' },
];

function MessageSquareIcon(props: any) { return <FileText {...props} />; }
function MailIcon(props: any) { return <Mail {...props} />; }
function BookOpenIcon(props: any) { return <BookOpen {...props} />; }

export default function ExternalCorpusImporter({ userId, onImportSuccess }: { userId: string; onImportSuccess?: () => void }) {
 const [isDragging, setIsDragging] = useState(false);
 const [isUploading, setIsUploading] = useState(false);
 const [result, setResult] = useState<IngestResult | null>(null);
 const [error, setError] = useState<string | null>(null);
 const [selectedParser, setSelectedParser] = useState<string | null>(null);
 const [targetSpeaker, setTargetSpeaker] = useState('');
 const fileInputRef = useRef<HTMLInputElement>(null);

 const handleDragOver = useCallback((e: React.DragEvent) => {
 e.preventDefault();
 setIsDragging(true);
 }, []);

 const handleDragLeave = useCallback((e: React.DragEvent) => {
 e.preventDefault();
 setIsDragging(false);
 }, []);

 const handleDrop = useCallback((e: React.DragEvent) => {
 e.preventDefault();
 setIsDragging(false);
 const files = e.dataTransfer.files;
 if (files.length > 0) {
 uploadFile(files[0]);
 }
 }, [userId, selectedParser, targetSpeaker]);

 const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
 const file = e.target.files?.[0];
 if (file) uploadFile(file);
 };

 const uploadFile = async (file: File) => {
 setIsUploading(true);
 setResult(null);
 setError(null);

 const formData = new FormData();
 formData.append('file', file);

 const params = new URLSearchParams();
 if (selectedParser) params.append('source_type', selectedParser);
 if (targetSpeaker.trim()) params.append('target_speaker', targetSpeaker.trim());

 try {
 const res = await fetch(`/api/v1/soul/ingest/${userId}?${params.toString()}`, {
 method: 'POST',
 body: formData,
 });

 const data = await res.json();

 if (!res.ok) {
 setError(data.detail || `导入失败: ${res.status}`);
 } else {
 setResult(data.result);
 }
 } catch (e: any) {
 setError(e.message || '网络错误');
 } finally {
 setIsUploading(false);
 if (fileInputRef.current) fileInputRef.current.value = '';
 }
 };

 return (
 <div className="space-y-4">
 {/* 解析器选择 */}
 <div className="grid grid-cols-3 gap-2">
 {PARSER_OPTIONS.map((parser) => {
 const Icon = parser.icon;
 const isSelected = selectedParser === parser.name;
 return (
 <button
 key={parser.name}
 onClick={() => setSelectedParser(isSelected ? null : parser.name)}
 className={`p-3 rounded-xl border text-left transition ${
 isSelected
 ? 'bg-violet-600/20 border-violet-500/50 text-white'
 : 'bg-surface-panel/40 border-line-subtle/50 text-content-secondary hover:bg-surface-panel/60'
 }`}
 >
 <Icon className={`w-4 h-4 mb-1.5 ${isSelected ? 'text-accent' : 'text-content-muted'}`} />
 <div className="text-xs font-medium">{parser.label}</div>
 <div className="text-[10px] text-content-muted mt-0.5">{parser.ext}</div>
 </button>
 );
 })}
 </div>

 {/* 说话者过滤 */}
 <div>
 <label className="text-xs text-content-muted mb-1 block">只保留该说话者的消息（可选，用于聚焦逝者本人）</label>
 <input
 type="text"
 value={targetSpeaker}
 onChange={(e) => setTargetSpeaker(e.target.value)}
 placeholder="例如：张三"
 className="w-full bg-surface-panel/60 border border-line-subtle/50 rounded-lg px-3 py-2 text-sm text-content-primary placeholder-content-muted focus:outline-none focus:border-violet-500"
 />
 </div>

 {/* 拖拽上传区 */}
 <div
 onDragOver={handleDragOver}
 onDragLeave={handleDragLeave}
 onDrop={handleDrop}
 onClick={() => fileInputRef.current?.click()}
 className={`relative border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition ${
 isDragging
 ? 'border-violet-500 bg-violet-600/10'
 : 'border-line-subtle/50 bg-surface-panel/30 hover:bg-surface-panel/50'
 }`}
 >
 <input
 ref={fileInputRef}
 type="file"
 className="hidden"
 onChange={handleFileSelect}
 accept=".txt,.md,.markdown,.eml,.mbox,.html,.htm"
 />
 {isUploading ? (
 <div className="flex flex-col items-center">
 <Loader2 className="w-8 h-8 text-accent animate-spin mb-2" />
 <span className="text-sm text-content-secondary">正在解析和导入...</span>
 <span className="text-xs text-content-muted mt-1">这可能需要几分钟</span>
 </div>
 ) : (
 <div className="flex flex-col items-center">
 <Upload className={`w-8 h-8 mb-2 ${isDragging ? 'text-accent' : 'text-content-muted'}`} />
 <span className="text-sm text-content-secondary">拖拽文件到此处，或点击上传</span>
 <span className="text-xs text-content-muted mt-1">支持 txt, md, eml, mbox, html</span>
 </div>
 )}
 </div>

 {/* 结果展示 */}
 {error && (
 <div className="p-3 rounded-xl bg-red-900/20 border border-red-700/30 flex items-start gap-2">
 <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
 <div className="text-sm text-red-300">{error}</div>
 </div>
 )}

 {result && (
 <div className="p-4 rounded-xl bg-surface-panel/60 border border-line-subtle/50 space-y-3">
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-2">
 <CheckCircle className="w-4 h-4 text-emerald-400" />
 <span className="text-sm font-medium text-white">
 {result.status === 'success' ? '导入成功' : '部分成功'}
 </span>
 </div>
 <button onClick={() => setResult(null)} className="text-content-muted hover:text-content-primary">
 <X className="w-4 h-4" />
 </button>
 </div>

 {/* 解析摘要 */}
 {result.parse_summary && (
 <div className="text-xs text-content-muted space-y-1">
 <div>解析器: <span className="text-content-secondary">{result.parser_used}</span></div>
 <div>提取消息: <span className="text-content-secondary">{result.parse_summary.total_messages} 条</span></div>
 {result.parse_summary.speakers.length > 0 && (
 <div>说话者: <span className="text-content-secondary">{result.parse_summary.speakers.join('、')}</span></div>
 )}
 </div>
 )}

 {/* 记忆导入 */}
 <div className="flex gap-3 text-xs">
 <div className="px-2 py-1 rounded bg-emerald-900/20 text-emerald-400">
 记忆入库: {result.memory.inserted}
 </div>
 <div className="px-2 py-1 rounded bg-surface-overlay/30 text-content-muted">
 跳过: {result.memory.skipped}
 </div>
 {result.memory.failed > 0 && (
 <div className="px-2 py-1 rounded bg-red-900/20 text-red-400">
 失败: {result.memory.failed}
 </div>
 )}
 </div>

 {/* 人格提取 */}
 {result.persona.extracted && (
 <div className="text-xs text-content-muted">
 人格画像: <span className="text-accent">已更新 {result.persona.fields_updated} 个维度</span>
 {result.profile.rebuilt && <span className="text-amber-400 ml-2">(全量重建)</span>}
 </div>
 )}

 {/* 导入后引导 */}
 <div className="p-3 rounded-lg bg-accent-subtle/10 border border-violet-500/20">
 <p className="text-xs text-violet-300 mb-2">
 语料已导入记忆库。建议重新分析人格画像，让系统从导入的内容中提取你的人格特征。
 </p>
 <button
 onClick={() => onImportSuccess?.()}
 className="text-xs px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg transition"
 >
 立即重新分析人格画像
 </button>
 </div>

 {/* 警告 */}
 {result.warnings.length > 0 && (
 <div className="space-y-1">
 {result.warnings.map((w, i) => (
 <div key={i} className="text-xs text-amber-400/80 flex items-start gap-1">
 <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
 {w}
 </div>
 ))}
 </div>
 )}

 <div className="text-[10px] text-content-secondary">
 耗时: {result.timing.duration_seconds}s
 </div>
 </div>
 )}
 </div>
 );
}