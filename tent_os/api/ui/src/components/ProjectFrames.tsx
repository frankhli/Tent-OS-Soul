/**
 * ProjectFrames — AI 庄园的画框墙
 * 每完成一个项目，自动生成一幅"项目画像"挂在墙上
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Frame, Clock, CheckCircle2, Sparkles, X,
} from 'lucide-react';

interface Project {
  session_id: string;
  task: string;
  created_at: string;
  updated_at: string;
  duration_min: number;
  result_preview: string;
}

interface ProjectsData {
  projects: Project[];
  count: number;
  total_completed: number;
}

// 画框风格模板
const FRAME_STYLES = [
  { border: '#8D6E63', bg: '#FFF8F0', accent: '#5D4037', name: '胡桃木' },
  { border: '#546E7A', bg: '#F0F5FF', accent: '#37474F', name: '钢铁灰' },
  { border: '#7E57C2', bg: '#F3E5F5', accent: '#512DA8', name: '紫罗兰' },
  { border: '#43A047', bg: '#E8F5E9', accent: '#2E7D32', name: '翡翠绿' },
  { border: '#E53935', bg: '#FFEBEE', accent: '#C62828', name: '朱砂红' },
  { border: '#FB8C00', bg: '#FFF3E0', accent: '#EF6C00', name: '琥珀橙' },
];

// 根据任务内容生成简单图标/图案描述
function generateProjectArt(task: string): { icon: string; pattern: string } {
  const t = task.toLowerCase();
  if (t.includes('代码') || t.includes('script') || t.includes('程序') || t.includes('开发')) {
    return { icon: '💻', pattern: '代码雨' };
  }
  if (t.includes('分析') || t.includes('数据') || t.includes('报表')) {
    return { icon: '📊', pattern: '数据流' };
  }
  if (t.includes('写') || t.includes('文档') || t.includes('报告') || t.includes('邮件')) {
    return { icon: '📝', pattern: '文字云' };
  }
  if (t.includes('设计') || t.includes('图') || t.includes('ui') || t.includes('画')) {
    return { icon: '🎨', pattern: '色彩块' };
  }
  if (t.includes('搜索') || t.includes('查') || t.includes('找')) {
    return { icon: '🔍', pattern: '网络图' };
  }
  if (t.includes('修复') || t.includes('bug') || t.includes('调试')) {
    return { icon: '🐛', pattern: '修复链' };
  }
  if (t.includes('部署') || t.includes('发布') || t.includes('上线')) {
    return { icon: '🚀', pattern: '发射轨' };
  }
  return { icon: '✨', pattern: '星光点' };
}

export function ProjectFrames() {
  const [data, setData] = useState<ProjectsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/ui/api/world/projects?limit=50');
      if (res.ok) {
        const d = await res.json();
        setData(d);
      }
    } catch (e) {
      console.error('[ProjectFrames] fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const formatDate = (s: string) => {
    try {
      return new Date(s).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    } catch {
      return s;
    }
  };

  return (
    <div className="h-full flex flex-col bg-gradient-to-b from-stone-100 to-amber-50">
      {/* 头部 — 画廊标题 */}
      <div className="px-5 py-4 bg-white border-b border-stone-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Frame className="w-5 h-5 text-stone-600" />
          <div>
            <h2 className="text-sm font-bold text-gray-800">项目画廊</h2>
            <p className="text-[10px] text-gray-400">
              {data?.total_completed ?? 0} 幅完成的项目画像
            </p>
          </div>
        </div>
        <button
          onClick={fetchProjects}
          className="p-1.5 rounded-lg hover:bg-stone-100 text-gray-400 transition-colors"
          title="刷新"
        >
          <Sparkles className="w-4 h-4" />
        </button>
      </div>

      {/* 画框墙 */}
      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <div className="h-full flex items-center justify-center text-gray-400 text-sm">
            <Sparkles className="w-5 h-5 animate-spin mr-2" />
            加载画廊...
          </div>
        ) : !data || data.projects.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Frame className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">墙上还没有画像</p>
            <p className="text-xs mt-1">完成项目后，它们会自动出现在这里</p>
          </div>
        ) : (
          <div className="max-w-5xl mx-auto">
            {/* 画框网格 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {data.projects.map((project, idx) => {
                const style = FRAME_STYLES[idx % FRAME_STYLES.length];
                const art = generateProjectArt(project.task);
                const rotation = ((idx * 7) % 5) - 2; // -2 到 +2 度微旋转

                return (
                  <button
                    key={project.session_id}
                    onClick={() => setSelectedProject(project)}
                    className="group text-left transition-transform hover:scale-[1.02]"
                    style={{ transform: `rotate(${rotation}deg)` }}
                  >
                    {/* 画框外框 */}
                    <div
                      className="rounded-lg p-3 shadow-sm hover:shadow-lg transition-shadow"
                      style={{
                        background: `linear-gradient(135deg, ${style.border}20, ${style.border}10)`,
                        border: `3px solid ${style.border}`,
                      }}
                    >
                      {/* 内框（画布） */}
                      <div
                        className="rounded-md p-4 min-h-[140px] flex flex-col items-center justify-center gap-2 relative overflow-hidden"
                        style={{ backgroundColor: style.bg }}
                      >
                        {/* 装饰性背景图案 */}
                        <div className="absolute inset-0 opacity-5">
                          {Array.from({ length: 6 }).map((_, i) => (
                            <div
                              key={i}
                              className="absolute rounded-full"
                              style={{
                                width: `${20 + i * 15}px`,
                                height: `${20 + i * 15}px`,
                                left: `${10 + i * 12}%`,
                                top: `${10 + (i % 3) * 25}%`,
                                backgroundColor: style.accent,
                              }}
                            />
                          ))}
                        </div>

                        {/* 中心图标 */}
                        <span className="text-4xl relative z-10">{art.icon}</span>

                        {/* 图案名称 */}
                        <span
                          className="text-[10px] font-medium relative z-10"
                          style={{ color: style.accent }}
                        >
                          {art.pattern}
                        </span>

                        {/* 完成标记 */}
                        <div className="absolute top-2 right-2">
                          <CheckCircle2 className="w-4 h-4 text-green-500" />
                        </div>
                      </div>

                      {/* 画框铭牌 */}
                      <div className="mt-2 px-1">
                        <p className="text-xs font-medium text-gray-700 truncate">
                          {project.task || '未命名项目'}
                        </p>
                        <div className="flex items-center justify-between mt-1">
                          <span className="text-[10px] text-gray-400">
                            {formatDate(project.updated_at)}
                          </span>
                          <span className="text-[10px] text-gray-400 flex items-center gap-0.5">
                            <Clock className="w-3 h-3" />
                            {project.duration_min}分钟
                          </span>
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 项目详情弹窗 */}
      {selectedProject && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-800">项目详情</h3>
              <button
                onClick={() => setSelectedProject(null)}
                className="p-1 rounded-lg hover:bg-gray-100 text-gray-400"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{generateProjectArt(selectedProject.task).icon}</span>
                <div>
                  <p className="text-sm font-medium text-gray-800">{selectedProject.task}</p>
                  <p className="text-[10px] text-gray-400">{selectedProject.session_id}</p>
                </div>
              </div>
              <div className="flex items-center gap-4 text-[10px] text-gray-500">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  耗时 {selectedProject.duration_min} 分钟
                </span>
                <span className="flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3 text-green-500" />
                  已完成
                </span>
              </div>
              {selectedProject.result_preview && (
                <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-600 leading-relaxed">
                  <p className="font-medium text-gray-500 mb-1">结果预览：</p>
                  {selectedProject.result_preview}
                </div>
              )}
              <div className="text-[10px] text-gray-400">
                完成于 {new Date(selectedProject.updated_at).toLocaleString('zh-CN')}
              </div>
            </div>
            <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 flex justify-end">
              <button
                onClick={() => setSelectedProject(null)}
                className="px-4 py-2 rounded-lg text-xs font-medium bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
