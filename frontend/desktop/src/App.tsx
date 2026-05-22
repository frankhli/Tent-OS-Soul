import { useState, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, useParams } from 'react-router-dom';
import { ThemeProvider } from './contexts/ThemeContext';
import AppShell from './components/AppShell';
import ChatPage from './pages/ChatPage';

// Lazy load non-critical pages to reduce initial bundle size
const MemoryPage = lazy(() => import('./pages/MemoryPage'));
const RelationPage = lazy(() => import('./pages/RelationPage'));
const AgentTeamPage = lazy(() => import('./pages/AgentTeamPage'));
const SoulPage = lazy(() => import('./pages/SoulPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const EmotionPage = lazy(() => import('./pages/EmotionPage'));
const TasksPage = lazy(() => import('./pages/TasksPage'));
const ToolsPage = lazy(() => import('./pages/ToolsPage'));
const HeirLogin = lazy(() => import('./components/HeirLogin'));
const EternalMode = lazy(() => import('./components/EternalMode'));

const PageLoader = () => (
 <div className="h-screen flex items-center justify-center">
 <div className="flex flex-col items-center gap-3">
 <div className="w-8 h-8 border-2 border-accent-border border-t-violet-600 rounded-full animate-spin" />
 <span className="text-sm text-content-muted">加载中...</span>
 </div>
 </div>
);

function EternalRoute() {
 const { userId } = useParams<{ userId: string }>();
 const [accessed, setAccessed] = useState(false);
 const [heirName, setHeirName] = useState('');
 const [token, setToken] = useState('');

 if (!userId) {
 return <div className="h-screen flex items-center justify-center text-content-muted">无效的访问链接</div>;
 }

 if (!accessed) {
 return (
 <Suspense fallback={<PageLoader />}>
 <HeirLogin
 onAccess={(_uid, name, tok) => {
 setHeirName(name);
 setToken(tok);
 setAccessed(true);
 }}
 />
 </Suspense>
 );
 }

 return (
 <Suspense fallback={<PageLoader />}>
 <EternalMode userId={userId} heirName={heirName} token={token} onExit={() => setAccessed(false)} />
 </Suspense>
 );
}

function AppRoutes() {
 return (
 <Routes>
 <Route
 path="/"
 element={
 <AppShell>
 <ChatPage />
 </AppShell>
 }
 />
 <Route
 path="/memory"
 element={
 <AppShell>
 <Suspense fallback={<PageLoader />}><MemoryPage /></Suspense>
 </AppShell>
 }
 />
 <Route
 path="/relations"
 element={
 <AppShell>
 <Suspense fallback={<PageLoader />}><RelationPage /></Suspense>
 </AppShell>
 }
 />
 <Route
 path="/agents"
 element={
 <AppShell>
 <Suspense fallback={<PageLoader />}><AgentTeamPage /></Suspense>
 </AppShell>
 }
 />
 <Route
 path="/soul"
 element={
 <AppShell>
 <Suspense fallback={<PageLoader />}><SoulPage /></Suspense>
 </AppShell>
 }
 />
 <Route
 path="/settings"
 element={
 <AppShell>
 <Suspense fallback={<PageLoader />}><SettingsPage /></Suspense>
 </AppShell>
 }
 />
 <Route
 path="/emotions"
 element={
 <AppShell>
 <Suspense fallback={<PageLoader />}><EmotionPage /></Suspense>
 </AppShell>
 }
 />
 <Route
 path="/tasks"
 element={
 <AppShell>
 <Suspense fallback={<PageLoader />}><TasksPage /></Suspense>
 </AppShell>
 }
 />
 <Route
 path="/tools"
 element={
 <AppShell>
 <Suspense fallback={<PageLoader />}><ToolsPage /></Suspense>
 </AppShell>
 }
 />
 <Route path="/eternal/:userId" element={<EternalRoute />} />
 <Route
 path="*"
 element={
 <AppShell>
 <ChatPage />
 </AppShell>
 }
 />
 </Routes>
 );
}

export default function App() {
 return (
 <ThemeProvider>
 <BrowserRouter>
 <AppRoutes />
 </BrowserRouter>
 </ThemeProvider>
 );
}
