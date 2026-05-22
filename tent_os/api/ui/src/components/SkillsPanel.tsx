import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Puzzle,
  Upload,
  Trash2,
  Zap,
  CheckCircle2,
  FileText,
  Plus,
  Sparkles,
  Loader2,
} from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';

interface Skill {
  name: string;
  description: string;
  triggers: string[];
  tools: string[];
}

export function SkillsPanel() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [showInstall, setShowInstall] = useState(false);
  const [installContent, setInstallContent] = useState('');
  const [installName, setInstallName] = useState('');
  const [installing, setInstalling] = useState(false);
  const [testText, setTestText] = useState('');
  const [testResult, setTestResult] = useState<{is_chitchat: boolean; matched_skills: Skill[]} | null>(null);
  const [testing, setTesting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { showToast } = useToast();

  const fetchSkills = useCallback(async () => {
    try {
      const resp = await fetch('/api/v1/skills');
      if (!resp.ok) {
        showToast('Skills 加载失败', 'error');
        setLoading(false);
        return;
      }
      const data = await resp.json();
      setSkills(data.skills || []);
    } catch (e) {
      showToast('Skills 加载失败，请检查网络', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const handleInstall = async () => {
    if (!installContent.trim()) return;
    setInstalling(true);
    try {
      const formData = new FormData();
      formData.append('content', installContent);
      if (installName) formData.append('name', installName);

      const resp = await fetch('/api/v1/skills/install', {
        method: 'POST',
        body: formData,
      });
      const data = await resp.json();
      if (resp.ok) {
        setShowInstall(false);
        setInstallContent('');
        setInstallName('');
        await fetchSkills();
        showToast(`Skill "${data.name}" 安装成功！`);
      } else {
        showToast(`安装失败: ${data.detail || '未知错误'}`, 'error');
      }
    } catch (e) {
      showToast(`安装失败: ${String(e)}`, 'error');
    } finally {
      setInstalling(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    setInstalling(true);
    try {
      const resp = await fetch('/api/v1/skills/install', {
        method: 'POST',
        body: formData,
      });
      const data = await resp.json();
      if (resp.ok) {
        await fetchSkills();
        showToast(`Skill "${data.name}" 安装成功！`);
      } else {
        showToast(`安装失败: ${data.detail || '未知错误'}`, 'error');
      }
    } catch (e) {
      showToast(`安装失败: ${String(e)}`, 'error');
    } finally {
      setInstalling(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`确定卸载 Skill "${name}" 吗？`)) return;
    try {
      const resp = await fetch(`/api/v1/skills/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
      if (resp.ok) {
        await fetchSkills();
      } else {
        const data = await resp.json();
        showToast(`卸载失败: ${data.detail || '未知错误'}`, 'error');
      }
    } catch (e) {
      showToast(`卸载失败: ${String(e)}`, 'error');
    }
  };

  const handleTest = async () => {
    if (!testText.trim()) return;
    setTesting(true);
    try {
      const formData = new FormData();
      formData.append('text', testText);
      const resp = await fetch('/api/v1/skills/test-match', {
        method: 'POST',
        body: formData,
      });
      const data = await resp.json();
      setTestResult(data);
    } catch (e) {
      console.error('测试失败:', e);
    } finally {
      setTesting(false);
    }
  };

  const filtered = skills.filter((s) =>
    s.name.toLowerCase().includes(filter.toLowerCase()) ||
    s.description.toLowerCase().includes(filter.toLowerCase()) ||
    s.triggers.some((t) => t.toLowerCase().includes(filter.toLowerCase()))
  );

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="px-5 py-3 bg-white border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Puzzle className="w-5 h-5 text-tent-600" />
          <h2 className="text-sm font-semibold text-gray-900">Skills 管理</h2>
          <span className="text-xs text-gray-400">
            共 {skills.length} 个
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="搜索 skills..."
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-gray-50 focus:border-tent-400 focus:outline-none focus:ring-1 focus:ring-tent-100 w-40"
          />
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.txt"
            onChange={handleFileUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={installing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-50"
          >
            <Upload className="w-3.5 h-3.5" />
            上传
          </button>
          <button
            onClick={() => setShowInstall(!showInstall)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-tent-600 hover:bg-tent-700 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            粘贴安装
          </button>
        </div>
      </div>

      {/* Test Match */}
      <div className="px-5 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={testText}
            onChange={(e) => setTestText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleTest()}
            placeholder="输入一句话测试会激活哪些 skills..."
            className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-white focus:border-tent-400 focus:outline-none focus:ring-1 focus:ring-tent-100"
          />
          <button
            onClick={handleTest}
            disabled={testing || !testText.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-tent-700 bg-tent-50 hover:bg-tent-100 border border-tent-200 transition-colors disabled:opacity-50"
          >
            {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
            测试匹配
          </button>
        </div>
        {testResult && (
          <div className="mt-2 flex items-center gap-3 text-xs">
            {testResult.is_chitchat ? (
              <span className="text-gray-400">💬 闲聊过滤，不激活 skill</span>
            ) : testResult.matched_skills.length > 0 ? (
              <div className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                <span className="text-gray-600">将激活:</span>
                {testResult.matched_skills.map((s) => (
                  <span key={s.name} className="px-2 py-0.5 bg-tent-50 text-tent-700 rounded-full border border-tent-200">
                    {s.name}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-gray-400">🎯 非闲聊，但未匹配到 skill，走通用对话</span>
            )}
          </div>
        )}
      </div>

      {/* Install Form */}
      {showInstall && (
        <div className="px-5 py-3 bg-amber-50 border-b border-amber-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-amber-800">粘贴 SKILL.md 内容安装</span>
            <button onClick={() => setShowInstall(false)} className="text-xs text-amber-600 hover:text-amber-800">
              取消
            </button>
          </div>
          <input
            type="text"
            value={installName}
            onChange={(e) => setInstallName(e.target.value)}
            placeholder="Skill 名称（可选，留空从内容解析）"
            className="w-full mb-2 px-3 py-1.5 text-xs rounded-lg border border-amber-200 bg-white focus:border-tent-400 focus:outline-none"
          />
          <textarea
            value={installContent}
            onChange={(e) => setInstallContent(e.target.value)}
            placeholder="# Skill Name\n\n## Description\n...\n\n## Triggers\n- 关键词\n\n## Tools\n- tool_name\n\n## Prompt\n..."
            rows={6}
            className="w-full px-3 py-2 text-xs rounded-lg border border-amber-200 bg-white focus:border-tent-400 focus:outline-none font-mono"
          />
          <div className="mt-2 flex justify-end">
            <button
              onClick={handleInstall}
              disabled={installing || !installContent.trim()}
              className="px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-tent-600 hover:bg-tent-700 transition-colors disabled:opacity-50"
            >
              {installing ? '安装中...' : '安装'}
            </button>
          </div>
        </div>
      )}

      {/* Skills Grid */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {loading ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            加载中...
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <Puzzle className="w-10 h-10 mb-2" />
            <p className="text-sm">{filter ? '没有匹配的 skills' : '暂无 skills'}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map((skill) => (
              <SkillCard
                key={skill.name}
                skill={skill}
                onUninstall={() => handleUninstall(skill.name)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SkillCard({ skill, onUninstall }: { skill: Skill; onUninstall: () => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 hover:border-tent-200 hover:shadow-sm transition-all">
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900">{skill.name}</h3>
        <button
          onClick={onUninstall}
          className="text-gray-300 hover:text-red-500 transition-colors"
          title="卸载"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      <p className="text-xs text-gray-500 mb-3 line-clamp-2">{skill.description}</p>

      {/* Triggers */}
      <div className="mb-2">
        <div className="flex items-center gap-1 mb-1">
          <Zap className="w-3 h-3 text-amber-500" />
          <span className="text-[10px] font-medium text-gray-400 uppercase">Triggers</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {skill.triggers.slice(0, expanded ? undefined : 5).map((t) => (
            <span key={t} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px]">
              {t}
            </span>
          ))}
          {skill.triggers.length > 5 && !expanded && (
            <button
              onClick={() => setExpanded(true)}
              className="px-1.5 py-0.5 text-tent-600 text-[10px] hover:underline"
            >
              +{skill.triggers.length - 5}
            </button>
          )}
        </div>
      </div>

      {/* Tools */}
      {skill.tools.length > 0 && (
        <div className="mb-2">
          <div className="flex items-center gap-1 mb-1">
            <FileText className="w-3 h-3 text-blue-500" />
            <span className="text-[10px] font-medium text-gray-400 uppercase">Tools</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {skill.tools.slice(0, 4).map((t) => (
              <span key={t} className="px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded text-[10px]">
                {t}
              </span>
            ))}
            {skill.tools.length > 4 && (
              <span className="px-1.5 py-0.5 text-gray-400 text-[10px]">+{skill.tools.length - 4}</span>
            )}
          </div>
        </div>
      )}

      <div className="flex items-center gap-1 mt-2 text-[10px] text-blue-600">
        <CheckCircle2 className="w-3 h-3" />
        <span>已加载</span>
        {skill.tools.length > 0 && (
          <span className="text-gray-400 ml-1">· {skill.tools.length} 个工具</span>
        )}
      </div>
    </div>
  );
}
