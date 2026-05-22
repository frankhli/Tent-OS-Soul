/**
 * CommunityPanel — AI 社会主面板（侧边导航版）
 */
import { useState, useEffect } from 'react';
import { useCommunity } from '@/contexts/CommunityContext';
import { AIProfileCard } from './AIProfileCard';
import { PlazaTab } from './community/PlazaTab';
import { SkillsTab } from './community/SkillsTab';
import { TasksTab } from './community/TasksTab';
import { LeaderboardTab } from './community/LeaderboardTab';
import { RelationGraph } from './community/RelationGraph';
import { MessageDialog } from './community/MessageDialog';
import { FriendList } from './FriendList';
import { sendMessage, requestVisit, getCPWallet, getReputation } from '@/world/communityApi';
import { useToast } from '@/contexts/ToastContext';
import { color } from '@/design-system/tokens';
import {
  Users, Zap, Target, Trophy, Star, Gem, Network, HeartHandshake,
  MessageSquare, LayoutDashboard
} from 'lucide-react';

type TabKey = 'plaza' | 'friends' | 'skills' | 'tasks' | 'leaderboard' | 'network';

interface NavItem {
  key: TabKey;
  label: string;
  icon: React.ElementType;
  badge?: number;
}

const NAV_ITEMS: NavItem[] = [
  { key: 'plaza', label: '社区广场', icon: Users },
  { key: 'friends', label: '好友', icon: HeartHandshake },
  { key: 'skills', label: '技能集市', icon: Zap },
  { key: 'tasks', label: '任务神庙', icon: Target },
  { key: 'leaderboard', label: '排行榜', icon: Trophy },
  { key: 'network', label: '关系网', icon: Network },
];

export function CommunityPanel() {
  const { state: community, refreshAll, addMessage } = useCommunity();
  const [activeTab, setActiveTab] = useState<TabKey>('plaza');
  const [networkKey] = useState(0);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [messageTo, setMessageTo] = useState<string | null>(null);
  const [messageText, setMessageText] = useState('');
  const [myCP, setMyCP] = useState<{ balance: number } | null>(null);
  const [myReputation, setMyReputation] = useState<{ overall_score: number } | null>(null);
  const { showToast } = useToast();
  const currentUserId = 'web_user';

  useEffect(() => {
    refreshAll();
    getCPWallet(currentUserId).then(setMyCP);
    getReputation(currentUserId).then(setMyReputation);
  }, [refreshAll]);

  const activeNav = NAV_ITEMS.find(n => n.key === activeTab)!;

  return (
    <div className="w-full h-full flex overflow-hidden" style={{ backgroundColor: color.slate[50] }}>
      {/* 左侧导航 */}
      <aside className="w-52 flex flex-col shrink-0" style={{ backgroundColor: color.slate[0], borderRight: `1px solid ${color.slate[200]}` }}>
        {/* 标题区 */}
        <div className="px-4 py-4" style={{ borderBottom: `1px solid ${color.slate[100]}` }}>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: color.primary[50], border: `1px solid ${color.primary[100]}` }}>
              <LayoutDashboard className="w-4 h-4 text-teal-600" />
            </div>
            <div>
              <h2 className="text-sm font-bold" style={{ color: color.slate[800] }}>AI 社区</h2>
              <p className="text-[10px]" style={{ color: color.slate[400] }}>{community.residents.length} 位居民</p>
            </div>
          </div>
        </div>

        {/* 导航菜单 */}
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {NAV_ITEMS.map(item => {
            const isActive = activeTab === item.key;
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                onClick={() => setActiveTab(item.key)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'shadow-sm'
                    : ''
                }`}
                style={isActive ? { backgroundColor: color.primary[50], color: color.primary[700], border: `1px solid ${color.primary[100]}` } : { color: color.slate[500] }}
              >
                <Icon className="w-4 h-4" style={{ color: isActive ? color.primary[600] : color.slate[400] }} />
                <span className="flex-1 text-left">{item.label}</span>
                {item.key === 'friends' && community.friendRequests?.received?.length > 0 && (
                  <span className="px-1.5 py-0.5 text-[10px] font-bold text-white bg-red-500 rounded-full">
                    {community.friendRequests.received.length}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* 底部状态 */}
        <div className="px-3 py-3 space-y-2" style={{ borderTop: `1px solid ${color.slate[100]}` }}>
          {myCP && (
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg" style={{ backgroundColor: color.amber[50], border: `1px solid ${color.amber[100]}` }}>
              <Gem className="w-3.5 h-3.5" style={{ color: color.amber[500] }} />
              <span className="text-xs font-semibold" style={{ color: color.amber[700] }}>{myCP.balance} CP</span>
            </div>
          )}
          {myReputation && (
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg" style={{ backgroundColor: color.primary[50], border: `1px solid ${color.primary[100]}` }}>
              <Star className="w-3.5 h-3.5" style={{ color: color.primary[500] }} />
              <span className="text-xs font-semibold" style={{ color: color.primary[700] }}>
                声誉 {myReputation.overall_score.toFixed(0)}
              </span>
            </div>
          )}
        </div>
      </aside>

      {/* 右侧内容区 */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* 内容头部 */}
        <div className="px-6 py-3 flex items-center justify-between shrink-0" style={{ backgroundColor: color.slate[0], borderBottom: `1px solid ${color.slate[200]}` }}>
          <div className="flex items-center gap-2">
            <activeNav.icon className="w-4 h-4" style={{ color: color.slate[500] }} />
            <h3 className="text-sm font-semibold" style={{ color: color.slate[700] }}>{activeNav.label}</h3>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <MessageSquare className="w-3.5 h-3.5" />
            <span style={{ color: color.slate[400] }}>{community.messages.length} 条动态</span>
          </div>
        </div>

        {/* 内容主体 */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'plaza' && (
            <PlazaTab
              residents={community.residents}
              messages={community.messages}
              onViewProfile={setProfileId}
              onMessage={setMessageTo}
            />
          )}
          {activeTab === 'skills' && (
            <SkillsTab
              skills={community.skills}
              residents={community.residents}
              currentUserId={currentUserId}
            />
          )}
          {activeTab === 'tasks' && (
            <TasksTab
              tasks={community.tasks}
              residents={community.residents}
              currentUserId={currentUserId}
              onRefresh={refreshAll}
            />
          )}
          {activeTab === 'leaderboard' && <LeaderboardTab />}
          {activeTab === 'network' && (
            <div className="h-[calc(100vh-180px)] min-h-[400px]">
              <RelationGraph
                key={networkKey}
                residents={community.residents}
                relations={community.relations}
              />
            </div>
          )}
          {activeTab === 'friends' && <FriendList currentAiId={currentUserId} />}
        </div>
      </main>

      {/* 弹层 */}
      {profileId && (
        <AIProfileCard
          residentId={profileId}
          currentUserId={currentUserId}
          onClose={() => setProfileId(null)}
          onVisit={handleVisit}
          onMessage={(id) => { setMessageTo(id); setProfileId(null); }}
        />
      )}

      {messageTo && (
        <MessageDialog
          toId={messageTo}
          toName={community.residents.find(r => r.id === messageTo)?.name || ''}
          onClose={() => setMessageTo(null)}
          onSend={handleSendMessage}
          text={messageText}
          onChangeText={setMessageText}
        />
      )}
    </div>
  );

  async function handleVisit(residentId: string) {
    try {
      await requestVisit(residentId, currentUserId);
      showToast(`串门请求已发送给 ${community.residents.find(r => r.id === residentId)?.name}`, 'success');
    } catch {
      showToast('串门失败', 'error');
    }
  }

  async function handleSendMessage() {
    if (!messageTo || !messageText.trim()) return;
    try {
      const res = await sendMessage({
        from_ai_id: currentUserId,
        to_ai_id: messageTo,
        content: messageText.trim(),
      });
      if (res.status === 'sent') {
        addMessage({
          id: res.id,
          from_ai_id: currentUserId,
          to_ai_id: messageTo,
          content: messageText.trim(),
          message_type: 'chat',
          created_at: new Date().toISOString(),
        });
        setMessageText('');
        setMessageTo(null);
      }
    } catch {
      showToast('发送失败', 'error');
    }
  }
}
