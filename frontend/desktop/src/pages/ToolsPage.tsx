import { useState, useEffect, useRef } from 'react';
import { Wrench, Plus, Trash2, Plug, Unplug, Play, Loader2, Server, Box, AlertCircle } from 'lucide-react';
import { USER_ID } from '../api/soulApi';

interface MCPServer {
 name: string;
 command: string;
 args: string[];
 env: Record<string, string>;
 enabled: boolean;
 connected?: boolean;
}

interface MCPTool {
 name: string;
 description: string;
 server: string;
 schema: any;
}

export default function ToolsPage() {
 const mountedRef = useRef(true);
 useEffect(() => { return () => { mountedRef.current = false; }; }, []);
 const [servers, setServers] = useState<MCPServer[]>([]);
 const [tools, setTools] = useState<MCPTool[]>([]);
 const [loading, setLoading] = useState(true);
 const [showAdd, setShowAdd] = useState(false);
 const [newServer, setNewServer] = useState({ name: '', command: '', args: '', enabled: true });
 const [connecting, setConnecting] = useState<string | null>(null);
 const [callResult, setCallResult] = useState<any>(null);
 const [callingTool, setCallingTool] = useState<string | null>(null);
 const [testArgs, setTestArgs] = useState('{}');

 useEffect(() => {
 loadAll();
 const iv = setInterval(loadAll, 10000);
 return () => clearInterval(iv);
 }, []);

 const loadAll = async () => {
 await Promise.all([loadServers(), loadTools()]);
 setLoading(false);
 };

 const loadServers = async () => {
 try {
 const res = await fetch('/api/v1/mcp/servers');
 if (res.ok) {
 const data = await res.json();
 setServers(data.servers || []);
 }
 } catch {}
 };

 const loadTools = async () => {
 try {
 const res = await fetch('/api/v1/mcp/tools');
 if (res.ok) {
 const data = await res.json();
 setTools(data.tools || []);
 }
 } catch {}
 };

 const addServer = async () => {
 if (!newServer.name.trim() || !newServer.command.trim()) return;
 try {
 const res = await fetch('/api/v1/mcp/servers', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({
 name: newServer.name.trim(),
 command: newServer.command.trim(),
 args: newServer.args.split(/\s+/).filter(Boolean),
 enabled: newServer.enabled,
 }),
 });
 if (res.ok) {
 setNewServer({ name: '', command: '', args: '', enabled: true });
 setShowAdd(false);
 loadServers();
 }
 } catch {}
 };

 const removeServer = async (name: string) => {
 if (!confirm(`确定删除 MCP Server "${name}"？`)) return;
 try {
 await fetch(`/api/v1/mcp/servers/${name}`, { method: 'DELETE' });
 loadServers();
 loadTools();
 } catch {}
 };

 const connectServer = async (name: string) => {
 setConnecting(name);
 try {
 const res = await fetch(`/api/v1/mcp/servers/${name}/connect`, { method: 'POST' });
 if (res.ok) {
 await loadServers();
 await loadTools();
 }
 } catch {}
 setConnecting(null);
 };

 const disconnectServer = async (name: string) => {
 try {
 await fetch(`/api/v1/mcp/servers/${name}/disconnect`, { method: 'POST' });
 loadServers();
 loadTools();
 } catch {}
 };

 const callTool = async (toolName: string, serverName: string) => {
 setCallingTool(toolName);
 try {
 let args = {};
 try { args = JSON.parse(testArgs); } catch {}
 const res = await fetch('/api/v1/mcp/tools/call', {
 method: 'POST',
 headers: { 'Content-Type': 'application/json' },
 body: JSON.stringify({ tool: toolName, server: serverName, arguments: args }),
 });
 const data = await res.json();
 setCallResult(data);
 } catch (e) {
 setCallResult({ error: String(e) });
 }
 setCallingTool(null);
 };

 return (
 <div className="h-full flex flex-col bg-surface-base">
 {/* Header */}
 <div className="h-14 flex items-center justify-between px-6 border-b border-line-subtle shrink-0">
 <div className="flex items-center gap-3">
 <Wrench className="w-5 h-5 text-emerald-400" />
 <h1 className="font-bold text-content-primary">外部工具</h1>
 <span className="text-xs text-content-muted bg-surface-panel px-2 py-0.5 rounded-full">
 MCP {tools.length}
 </span>
 </div>
 <button
 onClick={() => setShowAdd(true)}
 className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition"
 >
 <Plus className="w-4 h-4" /> 添加 MCP Server
 </button>
 </div>

 <div className="flex-1 overflow-y-auto p-6">
 {/* MCP Servers */}
 <div className="mb-8">
 <h2 className="text-sm font-semibold text-content-secondary mb-3 flex items-center gap-2">
 <Server className="w-4 h-4 text-content-muted" /> MCP Servers
 </h2>
 {servers.length === 0 ? (
 <div className="p-6 rounded-xl bg-surface-elevated border border-line-subtle text-center">
 <Box className="w-8 h-8 text-content-secondary mx-auto mb-2" />
 <p className="text-sm text-content-muted">暂无 MCP Server</p>
 <p className="text-xs text-content-secondary mt-1">添加外部 MCP Server 以扩展 Agent 能力</p>
 </div>
 ) : (
 <div className="space-y-2">
 {servers.map((s) => (
 <div key={s.name} className="p-3 rounded-lg bg-surface-elevated border border-line-subtle flex items-center justify-between">
 <div className="flex items-center gap-3">
 <div className={`w-2 h-2 rounded-full ${s.connected ? 'bg-emerald-500' : 'bg-slate-600'}`} />
 <div>
 <div className="text-sm font-medium text-content-primary">{s.name}</div>
 <div className="text-xs text-content-muted font-mono">{s.command} {s.args?.join(' ')}</div>
 </div>
 </div>
 <div className="flex items-center gap-1.5">
 {s.connected ? (
 <button
 onClick={() => disconnectServer(s.name)}
 className="p-1.5 rounded-md hover:bg-surface-panel text-content-muted hover:text-amber-400 transition"
 title="断开"
 >
 <Unplug className="w-4 h-4" />
 </button>
 ) : (
 <button
 onClick={() => connectServer(s.name)}
 disabled={connecting === s.name}
 className="p-1.5 rounded-md hover:bg-surface-panel text-content-muted hover:text-emerald-400 transition disabled:opacity-50"
 title="连接"
 >
 {connecting === s.name ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />}
 </button>
 )}
 <button
 onClick={() => removeServer(s.name)}
 className="p-1.5 rounded-md hover:bg-surface-panel text-content-muted hover:text-red-400 transition"
 title="删除"
 >
 <Trash2 className="w-4 h-4" />
 </button>
 </div>
 </div>
 ))}
 </div>
 )}
 </div>

 {/* MCP Tools */}
 <div>
 <h2 className="text-sm font-semibold text-content-secondary mb-3 flex items-center gap-2">
 <Wrench className="w-4 h-4 text-content-muted" /> 可用工具
 </h2>
 {tools.length === 0 ? (
 <div className="p-6 rounded-xl bg-surface-elevated border border-line-subtle text-center">
 <AlertCircle className="w-8 h-8 text-content-secondary mx-auto mb-2" />
 <p className="text-sm text-content-muted">暂无可用工具</p>
 <p className="text-xs text-content-secondary mt-1">连接 MCP Server 后将自动发现工具</p>
 </div>
 ) : (
 <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
 {tools.map((t) => (
 <div key={`${t.server}-${t.name}`} className="p-3 rounded-lg bg-surface-elevated border border-line-subtle">
 <div className="flex items-center justify-between mb-1.5">
 <span className="text-sm font-medium text-content-primary">{t.name}</span>
 <span className="text-[10px] text-content-muted bg-surface-panel px-1.5 py-0.5 rounded">{t.server}</span>
 </div>
 <p className="text-xs text-content-muted mb-2 line-clamp-2">{t.description || '无描述'}</p>
 <div className="flex items-center gap-2">
 <input
 type="text"
 value={testArgs}
 onChange={(e) => setTestArgs(e.target.value)}
 placeholder='{"path": "/tmp"}'
 className="flex-1 min-w-0 px-2 py-1 rounded bg-surface-panel border border-line-subtle text-xs text-content-secondary placeholder-content-disabled focus:outline-none focus:border-emerald-700"
 />
 <button
 onClick={() => callTool(t.name, t.server)}
 disabled={callingTool === t.name}
 className="px-2 py-1 rounded bg-emerald-900/40 hover:bg-emerald-900/60 border border-emerald-800 text-emerald-400 text-xs flex items-center gap-1 transition disabled:opacity-50"
 >
 {callingTool === t.name ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
 测试
 </button>
 </div>
 {callResult && callingTool === null && (
 <pre className="mt-2 p-2 rounded bg-surface-base text-[10px] text-content-muted overflow-auto max-h-32 border border-line-subtle">
 {JSON.stringify(callResult, null, 2)}
 </pre>
 )}
 </div>
 ))}
 </div>
 )}
 </div>
 </div>

 {/* Add Server Modal */}
 {showAdd && (
 <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
 <div className="w-full max-w-md bg-surface-elevated border border-line-subtle rounded-xl p-5 shadow-2xl">
 <div className="flex items-center justify-between mb-4">
 <h3 className="text-sm font-semibold text-content-primary">添加 MCP Server</h3>
 <button onClick={() => setShowAdd(false)} className="text-content-muted hover:text-content-secondary">✕</button>
 </div>
 <div className="space-y-3">
 <div>
 <label className="text-xs text-content-muted mb-1 block">名称</label>
 <input
 value={newServer.name}
 onChange={(e) => setNewServer({ ...newServer, name: e.target.value })}
 placeholder="filesystem"
 className="w-full px-3 py-2 rounded-lg bg-surface-panel border border-line-subtle text-sm text-content-primary focus:outline-none focus:border-emerald-600"
 />
 </div>
 <div>
 <label className="text-xs text-content-muted mb-1 block">命令</label>
 <input
 value={newServer.command}
 onChange={(e) => setNewServer({ ...newServer, command: e.target.value })}
 placeholder="npx"
 className="w-full px-3 py-2 rounded-lg bg-surface-panel border border-line-subtle text-sm text-content-primary focus:outline-none focus:border-emerald-600"
 />
 </div>
 <div>
 <label className="text-xs text-content-muted mb-1 block">参数（空格分隔）</label>
 <input
 value={newServer.args}
 onChange={(e) => setNewServer({ ...newServer, args: e.target.value })}
 placeholder="-y @modelcontextprotocol/server-filesystem /tmp"
 className="w-full px-3 py-2 rounded-lg bg-surface-panel border border-line-subtle text-sm text-content-primary focus:outline-none focus:border-emerald-600"
 />
 </div>
 <button
 onClick={addServer}
 disabled={!newServer.name.trim() || !newServer.command.trim()}
 className="w-full py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition"
 >
 添加
 </button>
 </div>
 <div className="mt-3 text-[10px] text-content-muted">
 示例：命令 <code className="bg-surface-panel px-1 rounded">npx</code>，参数 <code className="bg-surface-panel px-1 rounded">-y @modelcontextprotocol/server-filesystem /tmp</code>
 </div>
 </div>
 </div>
 )}
 </div>
 );
}
