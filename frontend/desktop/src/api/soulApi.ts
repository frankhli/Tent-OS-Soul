const API_BASE = '/api/v1';

function getUserId(): string {
  try {
    const uid = localStorage.getItem('tent_user_id');
    if (!uid) {
      const newId = `user_${Math.random().toString(36).slice(2, 10)}`;
      localStorage.setItem('tent_user_id', newId);
      return newId;
    }
    return uid;
  } catch {
    return `user_${Math.random().toString(36).slice(2, 10)}`;
  }
}

export const USER_ID = getUserId();

async function fetchJson<T>(path: string, init?: RequestInit & { timeout?: number }): Promise<T> {
  const { timeout = 10000, ...rest } = init || {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...rest, signal: controller.signal });
    if (!res.ok) {
      const err = await res.text().catch(() => res.statusText);
      throw new Error(`${res.status}: ${err}`);
    }
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}

// Soul Profile
export const getSoulProfile = () =>
  fetchJson<{user_id: string; decision_style: number; language_style: number; core_values: string[]; catchphrases: string[]; updated_at: string | null; soul_dimensions?: Record<string, number>}>(`/soul/profile/${USER_ID}`);

export const updateSoulProfile = (updates: {decision_style?: number; language_style?: number; core_values?: string[]; catchphrases?: string[]}) =>
  fetchJson<{status: string}>(`/soul/profile/${USER_ID}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });

export interface SubDimension {
  score: number;
  status: 'complete' | 'collecting' | 'pending';
  label: string;
  have: number;
  need: number;
  unit?: string;
  note?: string;
}

export interface SoulCompletenessResponse {
  thought: number;
  voice: number;
  appearance: number;
  overall: number;
  details?: {
    thought: Record<string, SubDimension>;
    voice: Record<string, SubDimension>;
    appearance: Record<string, SubDimension>;
  };
}

export const getSoulCompleteness = () =>
  fetchJson<SoulCompletenessResponse>(`/soul/completeness/${USER_ID}`);

// Voice
export const getVoiceProfile = () =>
  fetchJson<{status: string; profile?: any}>(`/soul/voice/${USER_ID}`);

export const uploadVoiceSample = (blob: Blob, filename: string) => {
  const form = new FormData();
  form.append('file', blob, filename);
  return fetchJson<{status: string; sample_path?: string; sample_count?: number}>(`/soul/voice/${USER_ID}/sample`, {
    method: 'POST',
    body: form,
  });
};

export const uploadVoiceMessage = (blob: Blob, filename: string) => {
  const form = new FormData();
  form.append('file', blob, filename);
  return fetchJson<{status: string; url?: string; filename?: string}>(`/soul/voice_message/${USER_ID}`, {
    method: 'POST',
    body: form,
  });
};

export const transcribeAudio = (blob: Blob, filename: string) => {
  const form = new FormData();
  form.append('file', blob, filename);
  return fetchJson<{text?: string; provider?: string; fallback?: boolean; error?: string}>(`/soul/asr/${USER_ID}`, {
    method: 'POST',
    body: form,
  });
};

export const getASRStatus = () =>
  fetchJson<{provider: string; available: boolean}>('/soul/asr/status');

// Appearance
export const getAppearanceProfile = () =>
  fetchJson<{status: string; profile?: any}>(`/soul/appearance/${USER_ID}`);

export const uploadAppearancePhoto = (blob: Blob, filename: string) => {
  const form = new FormData();
  form.append('file', blob, filename);
  return fetchJson<{status: string; photo_path?: string}>(`/soul/appearance/${USER_ID}/photo`, {
    method: 'POST',
    body: form,
  });
};

// Will
export const getWill = () =>
  fetchJson<{status: string; will?: any}>(`/soul/will/${USER_ID}`);

export const setWill = (will: {
  heirs: any[];
  topic_whitelist: string[];
  topic_blacklist: string[];
  activation_condition: string;
  activation_date: string | null;
  farewell_letter?: string | null;
  access_code?: string | null;
}) =>
  fetchJson<{status: string}>(`/soul/will/${USER_ID}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(will),
  });

// Tasks (scheduler)
export const getTasks = () =>
  fetchJson<{tasks: any[]}>(`/tasks/recent?limit=10&user_id=${USER_ID}`).catch(() => ({ tasks: [] as any[] }));

// Knowledge (memory)
export const getKnowledge = () =>
  fetchJson<{items: any[]}>(`/memory/knowledge?user_id=${USER_ID}`).catch(() => ({ items: [] as any[] }));

// Sessions
export const getSessions = () =>
  fetchJson<{sessions: any[]}>(`/chat/sessions?user_id=${USER_ID}`).catch(() => ({ sessions: [] as any[] }));

// TTS
export const synthesizeTTS = (text: string, emotion?: string, voiceKey?: string): Promise<{audio_url: string; status: string; source?: string; message?: string; voice?: string; cached?: boolean}> =>
  fetchJson(`/soul/tts/${USER_ID}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, emotion: emotion || 'neutral', voice_key: voiceKey }),
  });

export const getTTSStreamUrl = (text: string, emotion?: string, voiceKey?: string): string => {
  const params = new URLSearchParams();
  params.set('text', text);
  params.set('emotion', emotion || 'neutral');
  if (voiceKey) params.set('voice_key', voiceKey);
  params.set('stream', 'true');
  return `/api/v1/soul/tts/${USER_ID}?${params.toString()}`;
};

export const getTTSVoices = () =>
  fetchJson<{status: string; voices: {key: string; voice_id: string; name: string; gender: string; style: string; age: string}[]}>(`/soul/tts/voices`);

export const getVoiceStats = () =>
  fetchJson<{status: string; stats: any}>(`/soul/voice/${USER_ID}/stats`).catch(() => ({ status: 'error', stats: null }));

// Avatar
export const getAvatarConfig = () =>
  fetchJson<{status: string; config: any}>(`/soul/avatar/${USER_ID}/config`).catch(() => ({ status: 'error', config: null }));

export const setAvatarConfig = (config: any) =>
  fetchJson<{status: string}>(`/soul/avatar/${USER_ID}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });

export const getAvatarStats = () =>
  fetchJson<{status: string; stats: any}>(`/soul/avatar/${USER_ID}/stats`).catch(() => ({ status: 'error', stats: null }));

export const submitApproval = (sessionId: string, approved: boolean) =>
  fetchJson<{session_id: string; approved: boolean}>(`/api/v1/approval/${encodeURIComponent(sessionId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved }),
  });
