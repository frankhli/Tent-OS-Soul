import { X, Send } from 'lucide-react';

interface Props {
  toId: string;
  toName: string;
  onClose: () => void;
  onSend: () => void;
  text: string;
  onChangeText: (s: string) => void;
}

export function MessageDialog({ toName, onClose, onSend, text, onChangeText }: Props) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-[360px] p-5" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-800">发给 {toName}</h3>
          <button onClick={onClose} className="p-1 rounded-full hover:bg-slate-100"><X className="w-4 h-4 text-slate-400" /></button>
        </div>
        <textarea
          value={text}
          onChange={e => onChangeText(e.target.value)}
          placeholder="输入消息..."
          rows={4}
          className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs focus:outline-none focus:border-teal-300 resize-none"
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); } }}
        />
        <button
          onClick={onSend}
          disabled={!text.trim()}
          className="mt-3 w-full py-2 rounded-lg bg-teal-600 text-white text-xs font-medium hover:bg-teal-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1"
        >
          <Send className="w-3.5 h-3.5" />
          发送
        </button>
      </div>
    </div>
  );
}
