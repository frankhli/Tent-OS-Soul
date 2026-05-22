/**
 * communityApi.ts — AI 社会 API 客户端
 *
 * 四大模块：
 * 1. AI 居民（Residents）
 * 2. 技能集市（Skills）
 * 3. 任务神庙（Tasks）
 * 4. 经济 + 声誉（CP + Reputation）
 */

const API_BASE = '';

// ===== AI 居民 =====

export interface AIResident {
  id: string;
  name: string;
  persona: string;
  bio: string | null;
  home_room_id: string;
  current_location: string;
  status: string;
  created_at: string;
  last_seen: string;
}

export async function listResidents(): Promise<AIResident[]> {
  const res = await fetch(`${API_BASE}/ui/api/community/residents`);
  const json = await res.json();
  return json.residents || [];
}

export async function getResident(id: string): Promise<AIResident | null> {
  const res = await fetch(`${API_BASE}/ui/api/community/residents/${id}`);
  if (!res.ok) return null;
  return res.json();
}

export async function createResident(data: { id: string; name: string; persona?: string; bio?: string }): Promise<{ status: string; id: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/residents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function updateResident(id: string, data: Partial<AIResident>): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/residents/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function deleteResident(id: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/residents/${id}`, { method: 'DELETE' });
  return res.json();
}

export async function requestVisit(residentId: string, fromAiId: string): Promise<{ status: string; to: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/residents/${residentId}/visit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_ai_id: fromAiId }),
  });
  return res.json();
}

// ===== 社区消息 =====

export interface CommunityMessage {
  id: number;
  from_ai_id: string;
  to_ai_id: string;
  content: string;
  message_type: string;
  created_at: string;
}

export async function listMessages(fromAiId?: string, toAiId?: string, limit = 100): Promise<CommunityMessage[]> {
  const params = new URLSearchParams();
  if (fromAiId) params.set('from_ai_id', fromAiId);
  if (toAiId) params.set('to_ai_id', toAiId);
  params.set('limit', String(limit));
  const res = await fetch(`${API_BASE}/ui/api/community/messages?${params}`);
  const json = await res.json();
  return json.messages || [];
}

export async function sendMessage(data: { from_ai_id: string; to_ai_id: string; content: string; message_type?: string }): Promise<{ status: string; id: number }> {
  const res = await fetch(`${API_BASE}/ui/api/community/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

// ===== 技能 =====

export interface AISkill {
  id: number;
  ai_id: string;
  name: string;
  description: string | null;
  category: string | null;
  proficiency: number;
  is_sharable: number;
  cp_price: number;
  created_at: string;
}

export async function listSkills(aiId?: string, category?: string): Promise<AISkill[]> {
  const params = new URLSearchParams();
  if (aiId) params.set('ai_id', aiId);
  if (category) params.set('category', category);
  const res = await fetch(`${API_BASE}/ui/api/community/skills?${params}`);
  const json = await res.json();
  return json.skills || [];
}

export async function createSkill(data: Omit<AISkill, 'id' | 'created_at'>): Promise<{ status: string; id: number }> {
  const res = await fetch(`${API_BASE}/ui/api/community/skills`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function deleteSkill(skillId: number): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/skills/${skillId}`, { method: 'DELETE' });
  return res.json();
}

// ===== 关系 =====

export interface AIRelation {
  id: number;
  from_ai_id: string;
  to_ai_id: string;
  intimacy: number;
  interaction_count: number;
  last_interaction: string | null;
  tags: string | null;
  created_at: string;
}

export async function listRelations(fromAiId?: string): Promise<AIRelation[]> {
  const params = new URLSearchParams();
  if (fromAiId) params.set('from_ai_id', fromAiId);
  const res = await fetch(`${API_BASE}/ui/api/community/relations?${params}`);
  const json = await res.json();
  return json.relations || [];
}

export async function createRelation(data: { from_ai_id: string; to_ai_id: string; intimacy?: number; tags?: string[] }): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/relations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

// ===== 任务 =====

export interface CommunityTask {
  id: number;
  title: string;
  description: string | null;
  publisher_ai_id: string;
  assignee_ai_id: string | null;
  status: string;
  reward_cp: number;
  deadline: string | null;
  difficulty: number;
  result: string | null;
  created_at: string;
  completed_at: string | null;
}

export async function listTasks(status?: string, publisherAiId?: string): Promise<CommunityTask[]> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (publisherAiId) params.set('publisher_ai_id', publisherAiId);
  const res = await fetch(`${API_BASE}/ui/api/community/tasks?${params}`);
  const json = await res.json();
  return json.tasks || [];
}

export async function createTask(data: { title: string; description?: string; publisher_ai_id: string; reward_cp?: number; deadline?: string; difficulty?: number }): Promise<{ status: string; id: number }> {
  const res = await fetch(`${API_BASE}/ui/api/community/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function claimTask(taskId: number, assigneeAiId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/tasks/${taskId}/claim`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ assignee_ai_id: assigneeAiId }),
  });
  return res.json();
}

export async function completeTask(taskId: number, result?: string): Promise<{ status: string; reward_cp?: number }> {
  const res = await fetch(`${API_BASE}/ui/api/community/tasks/${taskId}/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ result }),
  });
  return res.json();
}

// ===== 贡献点 =====

export interface CPWalletData {
  ai_id: string;
  balance: number;
  total_earned: number;
  total_spent: number;
}

export interface CPTransaction {
  id: number;
  from_ai_id: string | null;
  to_ai_id: string | null;
  amount: number;
  transaction_type: string;
  reference_id: string | null;
  created_at: string;
}

export async function getCPWallet(aiId: string): Promise<CPWalletData> {
  const res = await fetch(`${API_BASE}/ui/api/community/cp/${aiId}`);
  return res.json();
}

export async function listCPTransactions(aiId: string, limit = 50): Promise<CPTransaction[]> {
  const res = await fetch(`${API_BASE}/ui/api/community/cp/${aiId}/transactions?limit=${limit}`);
  const json = await res.json();
  return json.transactions || [];
}

// ===== 声誉 =====

export interface AIReputation {
  ai_id: string;
  reliability: number;
  skill_level: number;
  friendliness: number;
  responsiveness: number;
  overall_score: number;
  review_count: number;
}

export interface AIReview {
  id: number;
  from_ai_id: string;
  to_ai_id: string;
  rating: number;
  comment: string | null;
  review_type: string;
  reference_id: string | null;
  created_at: string;
}

export async function getReputation(aiId: string): Promise<AIReputation> {
  const res = await fetch(`${API_BASE}/ui/api/community/reputation/${aiId}`);
  return res.json();
}

export async function createReview(data: { from_ai_id: string; to_ai_id: string; rating: number; comment?: string; review_type?: string; reference_id?: string }): Promise<{ status: string; id: number }> {
  const res = await fetch(`${API_BASE}/ui/api/community/reviews`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function listReviews(aiId: string, limit = 50): Promise<AIReview[]> {
  const res = await fetch(`${API_BASE}/ui/api/community/reviews/${aiId}?limit=${limit}`);
  const json = await res.json();
  return json.reviews || [];
}

// ===== 好友系统（Phase 2）=====

export interface AIFriend {
  friendship_id: number;
  friend_id: string;
  friend_name: string;
  friend_persona: string;
  friend_status: string;
  intimacy: number;
  interaction_count: number;
  last_interaction: string | null;
  tags: string | null;
  created_at: string;
}

export interface FriendRequest {
  id: number;
  from_ai_id: string;
  to_ai_id: string;
  status: string;
  intimacy: number;
  interaction_count: number;
  last_interaction: string | null;
  tags: string | null;
  created_at: string;
  from_name?: string;
  from_persona?: string;
  to_name?: string;
  to_persona?: string;
}

export async function listFriends(aiId: string): Promise<AIFriend[]> {
  const res = await fetch(`${API_BASE}/ui/api/community/friends?ai_id=${aiId}`);
  const json = await res.json();
  return json.friends || [];
}

export async function listFriendRequests(aiId: string): Promise<{ received: FriendRequest[]; sent: FriendRequest[] }> {
  const res = await fetch(`${API_BASE}/ui/api/community/friends/requests?ai_id=${aiId}`);
  return res.json();
}

export async function requestFriend(fromAiId: string, toAiId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/friends/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_ai_id: fromAiId, to_ai_id: toAiId }),
  });
  return res.json();
}

export async function acceptFriendRequest(friendshipId: number): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/friends/${friendshipId}/accept`, { method: 'POST' });
  return res.json();
}

export async function rejectFriendRequest(friendshipId: number): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/friends/${friendshipId}/reject`, { method: 'POST' });
  return res.json();
}

export async function respondVisit(visitId: string, toAiId: string, response: 'accept' | 'reject' | 'later'): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/visit/${visitId}/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to_ai_id: toAiId, response }),
  });
  return res.json();
}

// ===== 技能市场（Phase 3）=====

export async function hireSkill(skillId: number, fromAiId: string, note?: string): Promise<{ status: string; task_id?: number; price?: number }> {
  const res = await fetch(`${API_BASE}/ui/api/market/skills/${skillId}/hire`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_ai_id: fromAiId, note }),
  });
  return res.json();
}

export async function transferCP(fromAiId: string, toAiId: string, amount: number, note?: string): Promise<{ status: string; amount?: number }> {
  const res = await fetch(`${API_BASE}/ui/api/market/cp/transfer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_ai_id: fromAiId, to_ai_id: toAiId, amount, note }),
  });
  return res.json();
}

// ===== 排行榜 =====

export async function getLeaderboard(category: 'overall' | 'wealth' | 'reliable' | 'skilled' = 'overall'): Promise<{ leaderboard: Array<Record<string, unknown>>; category: string }> {
  const res = await fetch(`${API_BASE}/ui/api/community/leaderboard?category=${category}`);
  return res.json();
}
