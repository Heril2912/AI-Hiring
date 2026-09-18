export type AiSetLifecycle = "DRAFT" | "VALIDATED" | "APPROVED" | "STALE";

export type SlotReviewState = "UNREVIEWED" | "KEPT" | "EDITED" | "REVISED" | "RECRUITER_AUTHORED";

export interface SafeRubricDto {
  rubric_id: string;
  rubric_version: number;
  competency_definition: string;
  question_intent: string;
  observable_indicators: string[];
  rating_anchors: Record<string, string>;
  sufficient_evidence_guidance?: string | null;
  insufficient_evidence_guidance?: string | null;
  permitted_probes: string[];
}

export interface AiQuestionSlotItem {
  slot_id: string;
  display_order: number;
  competency_name: string;
  question_type: string;
  estimated_time_minutes: number;
  permitted_probes: string[];
  rubric?: SafeRubricDto | null;
  ai_wording?: string | null;
  review_state: SlotReviewState;
  authoring_origin: string;
  validation_status: "PASSED" | "FAILED";
  safe_failure_code?: string | null;
  rationale_code?: string | null;
  updated_at?: string | null;
}

export interface AiQuestionSetDetail {
  ai_set_id: string;
  set_version: number;
  template_id?: string | null;
  source_template_version?: number | null;
  source_mode?: string;
  source_content_hash: string;
  source_requirement_ids?: string[];
  job_id: string;
  job_title: string;
  job_revision: number;
  lifecycle_status: AiSetLifecycle;
  is_immutable: boolean;
  content_hash?: string | null;
  action?: string | null;
  slots: AiQuestionSlotItem[];
  total_slots_count: number;
  generated_slots_count: number;
  reviewed_slots_count: number;
  is_source_stale: boolean;
  stale_reason?: string | null;
  created_at: string;
  updated_at: string;
  approved_at?: string | null;
}

export interface AiQuestionSetSummary {
  ai_set_id: string;
  set_version: number;
  template_id?: string | null;
  source_mode?: string;
  job_id: string;
  job_title: string;
  lifecycle_status: AiSetLifecycle;
  is_immutable: boolean;
  is_source_stale: boolean;
  generated_question_count: number;
  total_blueprint_slots: number;
  created_at: string;
  updated_at: string;
}

export interface AiQuestionSetDirectory {
  sets: AiQuestionSetSummary[];
  total_count: number;
  awaiting_review_count: number;
  ready_for_approval_count: number;
  approved_count: number;
}

export interface AiQuestionSetValidateResult {
  is_valid: boolean;
  lifecycle_status: string;
  blocking_errors: string[];
  safe_message: string;
}

export interface AiQuestionSetApproveResult {
  ai_set_id: string;
  set_version: number;
  lifecycle_status: string;
  is_immutable: boolean;
  content_hash: string;
  approved_at: string;
  safe_message: string;
}

export interface EligibleJobItem {
  job_id: string;
  job_title: string;
  requirement_count: number;
  current_ai_set_id?: string | null;
  current_ai_set_status?: string | null;
}

export interface EligibleJobsResponse {
  items: EligibleJobItem[];
}
