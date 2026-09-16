export type InterviewLifecycleState =
  | "DRAFT"
  | "VALIDATED"
  | "APPROVED"
  | "ARCHIVED"
  | "SUPERSEDED";

export type QuestionType =
  | "BEHAVIORAL"
  | "TECHNICAL"
  | "SITUATIONAL"
  | "PROBLEM_SOLVING"
  | "DOMAIN_KNOWLEDGE"
  | "SYSTEM_DESIGN"
  | "ROLE_FIT"
  | "EVIDENCE_CLARIFICATION";

export type InterviewLayer = "COMMON_CORE" | "SUPPLEMENTAL_EVIDENCE";

export type AuthoringOrigin = "DETERMINISTIC" | "AI_ASSISTED" | "RECRUITER_EDITED";

export interface RubricLevel {
  level_name: string;
  score_range: [number, number];
  description: string;
  observable_signals: string[];
}

export interface AnchoredRubric {
  rubric_id: string;
  target_competency: string;
  levels: RubricLevel[];
}

export interface TemplateQuestion {
  question_id: string;
  layer: InterviewLayer;
  question_type: QuestionType;
  competency_name: string;
  question_text: string;
  display_order: number;
  estimated_time_minutes: number;
  permitted_probes: string[];
  rubric?: AnchoredRubric | null;
  authoring_origin: AuthoringOrigin;
  source_requirement_ids: string[];
  source_gap_ids?: string[];
  source_match_level?: string | null;
  included_in_common_score?: boolean;
}

export interface JobInterviewTemplateResponse {
  template_id: string;
  job_id: string;
  job_version_id: string;
  job_revision: number;
  template_version: number;
  parent_template_id?: string | null;
  lifecycle_state: InterviewLifecycleState;
  common_core_questions: TemplateQuestion[];
  target_duration_minutes: number;
  content_hash: string;
  authoritative_snapshot_hash: string;
  created_at: string;
  approved_at?: string | null;
  approved_by_user_id?: string | null;
}

export interface CandidateInterviewPlanResponse {
  plan_id: string;
  template_id: string;
  candidate_id: string;
  resume_id: string;
  match_run_id: string;
  plan_version: number;
  parent_plan_id?: string | null;
  lifecycle_state: InterviewLifecycleState;
  common_core_questions: TemplateQuestion[];
  supplemental_questions: TemplateQuestion[];
  total_duration_minutes: number;
  common_duration_minutes: number;
  supplemental_duration_minutes: number;
  plan_hash: string;
  created_at: string;
  approved_at?: string | null;
  approved_by_user_id?: string | null;
}

export interface ValidationSummaryResponse {
  is_valid: boolean;
  lifecycle_state: InterviewLifecycleState;
  blocking_rule_violations: string[];
  warnings: string[];
  content_hash: string;
  validated_at: string;
}

export interface VersionSummary {
  version: number;
  id: string;
  lifecycle_state: InterviewLifecycleState;
  content_hash: string;
  created_at: string;
  approved_at?: string | null;
  parent_id?: string | null;
}

export interface VersionHistoryResponse {
  target_id: string;
  job_id: string;
  candidate_id?: string | null;
  current_version: number;
  versions: VersionSummary[];
}

export interface QuestionDiffItem {
  question_id: string;
  change_type: "ADDED" | "REMOVED" | "MODIFIED" | "UNCHANGED";
  field_changes: Record<string, { from: any; to: any }>;
}

export interface VersionDiffResponse {
  base_version: number;
  base_hash: string;
  target_version: number;
  target_hash: string;
  lifecycle_state_change: { from: InterviewLifecycleState; to: InterviewLifecycleState };
  question_diffs: QuestionDiffItem[];
  summary: string;
}
