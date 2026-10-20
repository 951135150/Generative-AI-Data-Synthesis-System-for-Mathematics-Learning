export type WorkspaceView = 'studio' | 'agents';

export interface Problem {
  id: string;
  topic: string;
  sub_topic?: string;
  problem_statement: string;
  difficulty: number;
  mode?: string;
  question_type?: string;
  scaffolding?: Array<{ step: number; hint: string }>;
  options?: Record<string, string>;
  answer?: string;
  correct_values?: string[];
  ai_mode?: string;
  simulation_note?: string;
  concept_ids?: string[];
}

export interface CourseCitation {
  citation_id: string;
  id: string;
  title: string;
  section: string;
  source_title: string;
  source_version: string;
  content_hash: string;
  text: string;
  provenance: string;
}

export interface AuditResult {
  is_correct: boolean;
  logic_alignment_score: number;
  error_analysis: string;
  tutor_feedback: string;
  next_hint: string;
  ocr_text?: string;
  citations?: CourseCitation[];
  ai_mode?: string;
  grounding_status?: string;
  retrieval_method?: string;
  progress_recorded?: boolean;
}

export interface GeneratePayload {
  topics: string[];
  num: number;
  mode: string;
  difficulty: number;
  question_type: string;
  user_id?: string;
}

export interface AgentMessage {
  sender?: string;
  recipient?: string;
  type?: string;
  content?: unknown;
}

export interface SynthesisStatistics {
  topics_covered?: string[];
  avg_difficulty?: number;
  avg_quality_score?: number;
}

export interface SynthesisResult {
  event?: string;
  total_problems?: number;
  total_llm_calls?: number;
  total_agent_messages?: number;
  duration_seconds?: number;
  terminated_by?: string;
  statistics?: SynthesisStatistics;
  problems?: Problem[];
}
