import { useState, useEffect } from 'react';
import { Settings, Save, RotateCcw, HardDrive } from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';

interface SettingField {
  key: string;
  label: string;
  description: string;
  type: 'toggle' | 'number' | 'select';
  min?: number;
  max?: number;
  unit?: string;
  options?: string[];
  scope: string;
}

const SETTING_FIELDS: SettingField[] = [
  {
    key: 'auto_approve',
    label: '自动确认危险操作',
    description: '覆盖文件、删除、移动等高风险操作自动通过，无需手动确认',
    type: 'toggle',
    scope: '安全',
  },
  {
    key: 'cognitive_budget_seconds',
    label: '前台汇报周期',
    description: '系统运行多久后向您发送一次进度更新。任务不会停止，只是换个方式继续',
    type: 'number',
    min: 30,
    max: 86400,
    unit: '秒',
    scope: '性能',
  },
  {
    key: 'brain_v2_enabled',
    label: '深度思考模式',
    description: '启用工作记忆、情绪感知和自主学习能力，让助手更懂你',
    type: 'toggle',
    scope: '功能',
  },
  {
    key: 'default_persona',
    label: '助手风格',
    description: 'AI助理的性格倾向，影响回复语气和思考方式',
    type: 'select',
    options: ['work', 'casual', 'emergency', 'learning', 'creative'],
    scope: '功能',
  },
  {
    key: 'stream_block_size',
    label: '回复流畅度',
    description: '控制回复输出的速度和平滑度，数值越小回复越快',
    type: 'number',
    min: 10,
    max: 500,
    unit: '字符',
    scope: '性能',
  },
];

export function ConfigPanel() {
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [original, setOriginal] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [persisting, setPersisting] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    fetch('/ui/api/settings')
      .then((r) => r.json())
      .then((data) => {
        const s = data.settings || {};
        setSettings(s);
        setOriginal({ ...s });
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const updateValue = (key: string, value: unknown) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const resp = await fetch('/ui/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      const data = await resp.json();
      if (data.errors?.length > 0) {
        showToast(`保存失败: ${data.errors.join(', ')}`, 'error');
      } else {
        // 如果人格模式发生变化，同时调用人格切换 API
        const newPersona = settings.default_persona;
        const oldPersona = original.default_persona;
        if (newPersona && newPersona !== oldPersona) {
          try {
            await fetch('/ui/api/persona/mode', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ mode: newPersona }),
            });
          } catch {
            // 人格切换失败不影响设置保存
          }
        }
        setOriginal({ ...settings });
        showToast('设置已保存（内存生效）', 'success');
      }
    } catch (e) {
      showToast('保存出错', 'error');
    } finally {
      setSaving(false);
    }
  };

  const resetSettings = () => {
    setSettings({ ...original });
    showToast('已恢复原始设置', 'info');
  };

  const persistSettings = async () => {
    setPersisting(true);
    try {
      const resp = await fetch('/ui/api/settings/persist', { method: 'POST' });
      const data = await resp.json();
      if (data.success) {
        showToast('已保存到配置文件，重启后配置保留', 'success');
      } else {
        showToast(`持久化失败: ${data.error}`, 'error');
      }
    } catch (e) {
      showToast('持久化请求失败', 'error');
    } finally {
      setPersisting(false);
    }
  };

  const hasChanges = JSON.stringify(settings) !== JSON.stringify(original);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-sm text-gray-400">加载中...</div>
      </div>
    );
  }

  const groups = Array.from(new Set(SETTING_FIELDS.map((f) => f.scope)));

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
              <Settings className="w-5 h-5 text-gray-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">系统配置</h2>
              <p className="text-sm text-gray-500">热更新设置（无需重启）</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {hasChanges && (
              <button
                onClick={resetSettings}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-md transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                恢复
              </button>
            )}
            <button
              onClick={saveSettings}
              disabled={!hasChanges || saving}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md transition-colors ${
                hasChanges
                  ? 'bg-tent-600 text-white hover:bg-tent-700'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              }`}
            >
              <Save className="w-3.5 h-3.5" />
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              onClick={persistSettings}
              disabled={persisting}
              title="将当前配置写入配置文件，重启后依然生效"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-md transition-colors disabled:opacity-50"
            >
              <HardDrive className="w-3.5 h-3.5" />
              {persisting ? '写入中...' : '持久化'}
            </button>
          </div>
        </div>

        {groups.map((group) => (
          <div key={group} className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
            <h3 className="text-sm font-semibold text-gray-800 mb-3">{group}</h3>
            <div className="space-y-4">
              {SETTING_FIELDS.filter((f) => f.scope === group).map((field) => (
                <div key={field.key} className="flex items-start justify-between">
                  <div className="flex-1 min-w-0 pr-4">
                    <div className="text-xs font-medium text-gray-700">{field.label}</div>
                    <div className="text-[10px] text-gray-400">{field.description}</div>
                  </div>
                  <div className="flex-shrink-0">
                    {field.type === 'toggle' && (
                      <button
                        onClick={() => updateValue(field.key, !settings[field.key])}
                        className="transition-colors"
                      >
                        {settings[field.key] ? (
                          <ToggleOn />
                        ) : (
                          <ToggleOff />
                        )}
                      </button>
                    )}
                    {field.type === 'number' && (
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          min={field.min}
                          max={field.max}
                          value={String(settings[field.key] ?? '')}
                          onChange={(e) => updateValue(field.key, Number(e.target.value))}
                          className="w-20 px-2 py-1 text-xs border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-tent-500"
                        />
                        <span className="text-[10px] text-gray-400">{field.unit || ''}</span>
                      </div>
                    )}
                    {field.type === 'select' && field.options && (
                      <select
                        value={String(settings[field.key] ?? '')}
                        onChange={(e) => updateValue(field.key, e.target.value)}
                        className="px-2 py-1 text-xs border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-tent-500"
                      >
                        {field.options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {/* 只读配置展示 */}
        <div className="bg-gray-50 rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-500 mb-2">完整配置（只读）</h3>
          <p className="text-[10px] text-gray-400 mb-2">以下配置需修改配置文件后重启生效</p>
          <ConfigReadOnly />
        </div>
      </div>
    </div>
  );
}

function ToggleOn() {
  return (
    <div className="w-10 h-6 bg-tent-500 rounded-full relative transition-colors">
      <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow-sm" />
    </div>
  );
}

function ToggleOff() {
  return (
    <div className="w-10 h-6 bg-gray-300 rounded-full relative transition-colors">
      <div className="absolute left-1 top-1 w-4 h-4 bg-white rounded-full shadow-sm" />
    </div>
  );
}

function ConfigReadOnly() {
  const [config, setConfig] = useState<Record<string, unknown>>({});

  useEffect(() => {
    fetch('/ui/api/config')
      .then((r) => r.json())
      .then((data) => setConfig(data.config || {}))
      .catch(() => {});
  }, []);

  return (
    <div className="max-h-48 overflow-y-auto">
      <pre className="text-[10px] text-gray-500 whitespace-pre-wrap">
        {JSON.stringify(config, null, 2)}
      </pre>
    </div>
  );
}
