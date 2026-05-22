export interface SoulProfile {
  user_id: string;
  decision_style: number;
  language_style: number;
  core_values: string[];
  catchphrases: string[];
  emotion_patterns: Record<string, any>;
  updated_at: string | null;
}

export interface SoulCompleteness {
  thought: number;
  voice: number;
  appearance: number;
  overall: number;
}

export interface VoiceProfile {
  sample_count: number;
  total_duration_seconds: number;
  pitch_range: Record<string, any>;
  speed_wpm: number;
  timbre_tags: string[];
  model_path: string | null;
}

export interface AppearanceProfile {
  photo_count: number;
  video_count: number;
  face_shape: string | null;
  expression_tags: string[];
  action_style: Record<string, any>;
  model_path: string | null;
}

export interface Will {
  user_id: string;
  heirs: Array<{id: string; name: string; relationship: string; contact: string}>;
  topic_whitelist: string[];
  topic_blacklist: string[];
  activation_condition: 'after_death' | 'specific_date';
  activation_date: string | null;
  is_active: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  reasoning?: string;
  audioUrl?: string;
  images?: string[];
  timestamp: number;
}

export interface Task {
  id: string;
  title: string;
  completed: boolean;
  created_at: string;
}

export interface KnowledgeItem {
  id: string;
  title: string;
  summary: string;
  created_at: string;
}
