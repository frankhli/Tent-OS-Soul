import { Users } from 'lucide-react';
import RelationGalaxy from '../components/RelationGalaxy';

export default function RelationPage() {
 return (
 <div className="h-full flex flex-col bg-surface-elevated">
 {/* Header */}
 <div className="h-14 bg-surface-panel border-b border-line-subtle flex items-center justify-between px-6 shrink-0">
 <h1 className="font-bold text-content-primary flex items-center gap-2">
 <Users className="w-5 h-5" /> 关系星系
 </h1>
 <p className="text-xs text-content-muted">从对话中自动提取的人物关系网络</p>
 </div>

 {/* Full-screen galaxy */}
 <div className="flex-1 p-6">
 <div className="w-full h-full rounded-2xl bg-surface-panel border border-line-subtle overflow-hidden shadow-sm">
 <RelationGalaxy />
 </div>
 </div>
 </div>
 );
}
