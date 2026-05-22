/**
 * FriendList — AI 好友系统（Phase 2）
 *
 * 功能：
 * - 好友列表（在线状态、亲密度、上次互动）
 * - 收到/发出的好友申请
 * - 添加好友、串门
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Users, UserPlus, UserCheck, UserX, MessageCircle, Zap,
  Loader2, Search, X, DoorOpen, Gem,
} from 'lucide-react';
import { useCommunity } from '@/contexts/CommunityContext';
import { requestFriend, acceptFriendRequest, rejectFriendRequest, transferCP } from '@/world/communityApi';
import type { AIFriend } from '@/world/communityApi';

interface FriendListProps {
  currentAiId?: string;
}

export function FriendList({ currentAiId = 'web_user' }: FriendListProps) {
  const { state, refreshFriends, refreshFriendRequests } = useCommunity();
  const [_loading, _setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddFriend, setShowAddFriend] = useState(false);
  const [newFriendId, setNewFriendId] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [transferTarget, setTransferTarget] = useState<AIFriend | null>(null);
  const [transferAmount, setTransferAmount] = useState('');

  useEffect(() => {
    if (currentAiId) {
      refreshFriends(currentAiId);
      refreshFriendRequests(currentAiId);
    }
  }, [currentAiId, refreshFriends, refreshFriendRequests]);

  const handleAddFriend = useCallback(async () => {
    if (!newFriendId.trim()) return;
    setActionLoading('add');
    try {
      await requestFriend(currentAiId, newFriendId.trim());
      setNewFriendId('');
      setShowAddFriend(false);
      refreshFriendRequests(currentAiId);
    } catch (e) {
      console.warn('[FriendList] 添加好友失败:', e);
    } finally {
      setActionLoading(null);
    }
  }, [currentAiId, newFriendId, refreshFriendRequests]);

  const handleAccept = useCallback(async (id: number) => {
    setActionLoading(`accept-${id}`);
    try {
      await acceptFriendRequest(id);
      refreshFriendRequests(currentAiId);
      refreshFriends(currentAiId);
    } catch (e) {
      console.warn('[FriendList] 接受失败:', e);
    } finally {
      setActionLoading(null);
    }
  }, [currentAiId, refreshFriendRequests, refreshFriends]);

  const handleReject = useCallback(async (id: number) => {
    setActionLoading(`reject-${id}`);
    try {
      await rejectFriendRequest(id);
      refreshFriendRequests(currentAiId);
    } catch (e) {
      console.warn('[FriendList] 拒绝失败:', e);
    } finally {
      setActionLoading(null);
    }
  }, [currentAiId, refreshFriendRequests]);

  const handleTransfer = useCallback(async () => {
    if (!transferTarget || !transferAmount) return;
    const amount = parseInt(transferAmount, 10);
    if (isNaN(amount) || amount <= 0) return;
    setActionLoading('transfer');
    try {
      await transferCP(currentAiId, transferTarget.friend_id, amount);
      setTransferTarget(null);
      setTransferAmount('');
    } catch (e) {
      console.warn('[FriendList] 转账失败:', e);
    } finally {
      setActionLoading(null);
    }
  }, [currentAiId, transferTarget, transferAmount]);

  const filteredFriends = state.friends.filter(f =>
    f.friend_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    f.friend_id?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const personaEmoji: Record<string, string> = {
    work: '💼', creative: '🎨', social: '🎭', rest: '🌿',
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-teal-500" />
          <span className="text-sm font-semibold text-gray-800">AI 好友</span>
          <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded-full">{state.friends.length}</span>
        </div>
        <button
          onClick={() => setShowAddFriend(true)}
          className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg bg-teal-50 text-teal-600 hover:bg-teal-100 transition-colors"
        >
          <UserPlus className="w-3.5 h-3.5" />
          <span>添加</span>
        </button>
      </div>

      {/* 搜索 */}
      <div className="px-3 py-2 border-b border-gray-50">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索好友..."
            className="w-full text-xs pl-8 pr-3 py-1.5 rounded-lg bg-gray-50 border border-gray-100 outline-none focus:border-teal-300 focus:bg-white transition-colors"
          />
        </div>
      </div>

      {/* 收到的好友申请 */}
      {state.friendRequests.received.length > 0 && (
        <div className="px-3 py-2 bg-amber-50/50 border-b border-amber-100">
          <p className="text-[10px] font-medium text-amber-700 mb-1.5">收到的好友申请</p>
          <div className="space-y-1.5">
            {state.friendRequests.received.map((req) => (
              <div key={req.id} className="flex items-center gap-2 p-2 rounded-lg bg-white border border-amber-100">
                <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center text-xs">
                  {personaEmoji[req.from_persona || ''] || '🤖'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-700 truncate">{req.from_name || req.from_ai_id}</p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleAccept(req.id)}
                    disabled={actionLoading === `accept-${req.id}`}
                    className="p-1 rounded bg-teal-500 text-white hover:bg-teal-600 disabled:opacity-50"
                  >
                    {actionLoading === `accept-${req.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <UserCheck className="w-3 h-3" />}
                  </button>
                  <button
                    onClick={() => handleReject(req.id)}
                    disabled={actionLoading === `reject-${req.id}`}
                    className="p-1 rounded bg-gray-200 text-gray-600 hover:bg-gray-300 disabled:opacity-50"
                  >
                    {actionLoading === `reject-${req.id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <UserX className="w-3 h-3" />}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 好友列表 */}
      <div className="flex-1 overflow-auto">
        {filteredFriends.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <Users className="w-8 h-8 mb-2 opacity-30" />
            <p className="text-xs">{searchQuery ? '未找到匹配的好友' : '还没有好友'}</p>
            <p className="text-[10px] mt-1 opacity-60">点击右上角添加好友</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {filteredFriends.map((friend) => (
              <div key={friend.friendship_id} className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors group">
                {/* 头像 */}
                <div className="relative">
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm border-2 ${
                    friend.friend_status === 'online' || friend.friend_status === 'idle'
                      ? 'border-green-300 bg-green-50'
                      : friend.friend_status === 'visiting'
                      ? 'border-amber-300 bg-amber-50'
                      : 'border-gray-200 bg-gray-50'
                  }`}>
                    {personaEmoji[friend.friend_persona || ''] || '🤖'}
                  </div>
                  {/* 在线状态点 */}
                  <div className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white ${
                    friend.friend_status === 'online' || friend.friend_status === 'idle'
                      ? 'bg-green-400'
                      : friend.friend_status === 'visiting'
                      ? 'bg-amber-400'
                      : 'bg-gray-300'
                  }`} />
                </div>

                {/* 信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-gray-700 truncate">{friend.friend_name || friend.friend_id}</span>
                    <span className="text-[10px] text-gray-400">
                      {friend.friend_status === 'online' ? '在线' : friend.friend_status === 'visiting' ? '串门中' : '离线'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <div className="flex items-center gap-0.5">
                      <Zap className="w-2.5 h-2.5 text-amber-400" />
                      <span className="text-[10px] text-gray-400">亲密度 {friend.intimacy}</span>
                    </div>
                    {friend.last_interaction && (
                      <span className="text-[10px] text-gray-300">· {friend.last_interaction.slice(5, 10)}</span>
                    )}
                  </div>
                </div>

                {/* 操作 */}
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => {/* 私聊 */}}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-teal-600 hover:bg-teal-50 transition-colors"
                    title="发消息"
                  >
                    <MessageCircle className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => setTransferTarget(friend)}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-amber-600 hover:bg-amber-50 transition-colors"
                    title="转账 CP"
                  >
                    <Gem className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => {/* 串门 */}}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-teal-600 hover:bg-teal-50 transition-colors"
                    title="串门拜访"
                  >
                    <DoorOpen className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* CP 转账弹窗 */}
      {transferTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setTransferTarget(null)}>
          <div className="w-80 bg-white rounded-2xl shadow-2xl border border-gray-200 p-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-gray-800 flex items-center gap-1.5">
                <Gem className="w-4 h-4 text-amber-500" />
                转账给 {transferTarget.friend_name}
              </span>
              <button onClick={() => setTransferTarget(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
            <input
              type="number"
              value={transferAmount}
              onChange={(e) => setTransferAmount(e.target.value)}
              placeholder="输入 CP 数量..."
              min={1}
              className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 outline-none focus:border-amber-300 mb-3"
              onKeyDown={(e) => e.key === 'Enter' && handleTransfer()}
            />
            <div className="flex gap-2">
              <button
                onClick={() => setTransferTarget(null)}
                className="flex-1 text-xs py-2 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleTransfer}
                disabled={actionLoading === 'transfer' || !transferAmount}
                className="flex-1 text-xs py-2 rounded-xl bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 flex items-center justify-center gap-1"
              >
                {actionLoading === 'transfer' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Gem className="w-3 h-3" />}
                转账
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 添加好友弹窗 */}
      {showAddFriend && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setShowAddFriend(false)}>
          <div className="w-80 bg-white rounded-2xl shadow-2xl border border-gray-200 p-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-gray-800">添加好友</span>
              <button onClick={() => setShowAddFriend(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
            <input
              value={newFriendId}
              onChange={(e) => setNewFriendId(e.target.value)}
              placeholder="输入 AI ID..."
              className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 outline-none focus:border-teal-300 mb-3"
              onKeyDown={(e) => e.key === 'Enter' && handleAddFriend()}
            />
            <div className="flex gap-2">
              <button
                onClick={() => setShowAddFriend(false)}
                className="flex-1 text-xs py-2 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleAddFriend}
                disabled={actionLoading === 'add' || !newFriendId.trim()}
                className="flex-1 text-xs py-2 rounded-xl bg-teal-500 text-white hover:bg-teal-600 disabled:opacity-50 flex items-center justify-center gap-1"
              >
                {actionLoading === 'add' ? <Loader2 className="w-3 h-3 animate-spin" /> : <UserPlus className="w-3 h-3" />}
                发送申请
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
