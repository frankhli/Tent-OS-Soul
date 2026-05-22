import { Settings } from 'lucide-react';
import SystemSettings from '../components/SystemSettings';

export default function SettingsPage() {
 return (
 <div className="h-full flex flex-col bg-surface-elevated">
 {/* Header */}
 <div className="h-14 bg-surface-panel border-b border-line-subtle flex items-center px-6 shrink-0">
 <h1 className="font-bold text-content-primary flex items-center gap-2">
 <Settings className="w-5 h-5" /> 设置
 </h1>
 </div>

 {/* Settings content */}
 <div className="flex-1 overflow-y-auto p-6">
 <div className="max-w-2xl mx-auto">
 <SystemSettings standalone />
 </div>
 </div>
 </div>
 );
}
