/**
 * FridgeNotes — AI 庄园的冰箱贴便签墙
 * 用户可以给 AI 留言，AI 也可以把想法写成便签贴在冰箱上
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  StickyNote, Plus, X, Send, User, Bot, Sparkles,
} from 'lucide-react';

interface FridgeNote {
  id: string;
  content: string;
  color: string;
  author: 'user' | 'ai';
  created_at: string;
}

const NOTE_COLORS = [
  { bg: '#FFD54F', border: '#FFA000', name: '黄色' },
  { bg: '#81D4FA', border: '#0288D1', name: '蓝色' },
  { bg: '#A5D6A7', border: '#388E3C', name: '绿色' },
  { bg: '#F48FB1', border: '#C2185B', name: '粉色' },
  { bg: '#CE93D8', border: '#7B1FA2', name: '紫色' },
  { bg: '#FFAB91', border: '#D84315', name: '橙色' },
];

const AI_NOTE_TEMPLATES = [
  '今天完成了 3 个任务，效率不错！',
  '记得检查一下明天的日程安排',
  '用户似乎很疲惫，要不要提醒他休息？',
  '刚刚学到了一个新技能，想试试',
  '窗外的天气很好，适合出去走走',
];

export function FridgeNotes() {
  const [notes, setNotes] = useState<FridgeNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState('');
  const [selectedColor, setSelectedColor] = useState(NOTE_COLORS[0].bg);
  const [isAdding, setIsAdding] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const fetchNotes = useCallback(async () => {
    try {
      const res = await fetch('/ui/api/world/fridge-notes');
      if (res.ok) {
        const data = await res.json();
        setNotes(data.notes || []);
      }
    } catch (e) {
      console.error('[FridgeNotes] fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotes();
  }, [fetchNotes]);

  const addNote = async () => {
    if (!newContent.trim()) return;
    try {
      const res = await fetch('/ui/api/world/fridge-notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: newContent.trim(),
          color: selectedColor,
          author: 'user',
        }),
      });
      if (res.ok) {
        setNewContent('');
        setIsAdding(false);
        fetchNotes();
      }
    } catch (e) {
      console.error('[FridgeNotes] add failed:', e);
    }
  };

  const deleteNote = async (id: string) => {
    try {
      const res = await fetch(`/ui/api/world/fridge-notes/${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        fetchNotes();
      }
    } catch (e) {
      console.error('[FridgeNotes] delete failed:', e);
    }
  };

  const addAiNote = async () => {
    const template = AI_NOTE_TEMPLATES[Math.floor(Math.random() * AI_NOTE_TEMPLATES.length)];
    const color = NOTE_COLORS[Math.floor(Math.random() * NOTE_COLORS.length)].bg;
    try {
      await fetch('/ui/api/world/fridge-notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: template, color, author: 'ai' }),
      });
      fetchNotes();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-slate-100 to-gray-200">
      {/* 头部 — 冰箱门样式 */}
      <div className="px-5 py-4 bg-white border-b border-gray-300 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-100 to-gray-200 border border-gray-300 flex items-center justify-center shadow-sm">
            <StickyNote className="w-5 h-5 text-gray-600" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-gray-800">冰箱贴便签墙</h2>
            <p className="text-[10px] text-gray-400">
              {notes.length} 张便签 · 给 AI 留言，或看看 AI 在想什么
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={addAiNote}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-purple-50 text-purple-600 border border-purple-200 hover:bg-purple-100 transition-colors"
            title="模拟 AI 贴一张便签"
          >
            <Bot className="w-3 h-3" />
            <span>AI 贴便签</span>
          </button>
          <button
            onClick={() => {
              setIsAdding(true);
              setTimeout(() => inputRef.current?.focus(), 100);
            }}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 transition-colors"
          >
            <Plus className="w-3 h-3" />
            <span>写便签</span>
          </button>
        </div>
      </div>

      {/* 冰箱门背景 + 便签墙 */}
      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <div className="h-full flex items-center justify-center text-gray-400 text-sm">
            <Sparkles className="w-5 h-5 animate-spin mr-2" />
            加载便签...
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            {/* 新建便签输入区 */}
            {isAdding && (
              <div className="mb-5 bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-gray-500">写一张新便签</span>
                  <button
                    onClick={() => setIsAdding(false)}
                    className="p-1 rounded hover:bg-gray-100 text-gray-400"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
                <textarea
                  ref={inputRef}
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  placeholder="想对 AI 说什么..."
                  className="w-full h-20 p-2.5 rounded-lg border border-gray-200 bg-gray-50 text-xs text-gray-700 resize-none focus:outline-none focus:ring-2 focus:ring-amber-200 focus:border-amber-300"
                />
                <div className="flex items-center justify-between mt-2">
                  <div className="flex items-center gap-1.5">
                    {NOTE_COLORS.map((c) => (
                      <button
                        key={c.bg}
                        onClick={() => setSelectedColor(c.bg)}
                        className={`w-5 h-5 rounded-full border-2 transition-all ${
                          selectedColor === c.bg ? 'border-gray-600 scale-110' : 'border-transparent hover:scale-105'
                        }`}
                        style={{ backgroundColor: c.bg }}
                        title={c.name}
                      />
                    ))}
                  </div>
                  <button
                    onClick={addNote}
                    disabled={!newContent.trim()}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <Send className="w-3 h-3" />
                    贴上
                  </button>
                </div>
              </div>
            )}

            {/* 便签网格 — 模拟贴在冰箱上的效果 */}
            {notes.length === 0 ? (
              <div className="text-center py-16 text-gray-400">
                <StickyNote className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="text-sm">冰箱上还没有便签</p>
                <p className="text-xs mt-1">写一张便签，AI 会看到它</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                {notes.map((note) => {
                  const colorCfg = NOTE_COLORS.find((c) => c.bg === note.color) || NOTE_COLORS[0];
                  const rotation = ((note.id.charCodeAt(note.id.length - 1) % 7) - 3) * 1.5; // 随机微旋转

                  return (
                    <div
                      key={note.id}
                      className="relative group"
                      style={{ transform: `rotate(${rotation}deg)` }}
                    >
                      {/* 胶带效果 */}
                      <div className="absolute -top-2 left-1/2 -translate-x-1/2 w-8 h-3 bg-white/40 rounded-sm backdrop-blur-sm border border-white/30 z-10" />

                      <div
                        className="rounded-lg p-3 pt-4 min-h-[100px] flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                        style={{
                          backgroundColor: note.color,
                          border: `1px solid ${colorCfg.border}30`,
                        }}
                      >
                        <p className="text-xs text-gray-800 leading-relaxed whitespace-pre-wrap">
                          {note.content}
                        </p>
                        <div className="flex items-center justify-between mt-2 pt-2 border-t border-black/5">
                          <div className="flex items-center gap-1">
                            {note.author === 'ai' ? (
                              <Bot className="w-3 h-3 text-gray-600" />
                            ) : (
                              <User className="w-3 h-3 text-gray-600" />
                            )}
                            <span className="text-[10px] text-gray-600">
                              {note.author === 'ai' ? 'AI' : '我'}
                            </span>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteNote(note.id);
                            }}
                            className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-black/10 text-gray-600 transition-opacity"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
