import { apiFetch } from "./client";
import { QuestionFormat } from "../types/ai_question_set";

export type PracticeSessionLifecycle =
  | "INITIALIZED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "ABANDONED"
  | "EXPIRED";

export type PracticeSection = "CONVERSATION" | "MCQ" | "COMPLETE";

export type PracticeMessageRole = "CANDIDATE" | "INTERVIEWER" | "SYSTEM";

export type PracticeMessageKind =
  | "GREETING"
  | "PRIMARY_QUESTION"
  | "ANSWER"
  | "FOLLOW_UP"
  | "ACKNOWLEDGEMENT"
  | "SYSTEM_NOTICE";

export interface PracticeMessageDto {
  message_id: string;
  sequence_number: number;
  role: PracticeMessageRole;
  message_kind: PracticeMessageKind;
  text: string;
  source_question_id?: string | null;
  created_at: string;
}

export interface PracticeActiveQuestionOptionDto {
  option_id: string;
  text: string;
  display_order: number;
}

export interface PracticeActiveQuestionDto {
  question_id: string;
  question_format: QuestionFormat;
  wording: string;
  competency_name: string;
  difficulty?: string | null;
  options?: PracticeActiveQuestionOptionDto[] | null;
  turn_count_for_question: number;
  follow_up_available: boolean;
}

export interface PracticeSessionDetailResponse {
  session_id: string;
  release_id: string;
  job_id: string;
  lifecycle_status: PracticeSessionLifecycle;
  current_section: PracticeSection;
  current_conv_index: number;
  total_conv_count: number;
  current_mcq_index: number;
  total_mcq_count: number;
  total_response_count: number;
  turn_count_for_question: number;
  active_question?: PracticeActiveQuestionDto | null;
  messages: PracticeMessageDto[];
  started_at?: string | null;
  completed_at?: string | null;
  expires_at: string;
  time_remaining_seconds: number;
  safe_fallback_notice?: string | null;
}

export interface PracticeSessionAbandonResponse {
  session_id: string;
  lifecycle_status: PracticeSessionLifecycle;
  message: string;
}

export async function startOrResumePracticeSession(
  releaseId: string
): Promise<PracticeSessionDetailResponse> {
  return apiFetch<PracticeSessionDetailResponse>(
    "/api/v1/candidate/practice-sessions/start",
    {
      method: "POST",
      body: JSON.stringify({ release_id: releaseId }),
    }
  );
}

export async function getPracticeSessionState(
  sessionId: string
): Promise<PracticeSessionDetailResponse> {
  return apiFetch<PracticeSessionDetailResponse>(
    `/api/v1/candidate/practice-sessions/${sessionId}`
  );
}

export async function submitConversationalAnswer(
  sessionId: string,
  questionId: string,
  answerText: string,
  idempotencyKey?: string
): Promise<PracticeSessionDetailResponse> {
  return apiFetch<PracticeSessionDetailResponse>(
    `/api/v1/candidate/practice-sessions/${sessionId}/answer-conversation`,
    {
      method: "POST",
      body: JSON.stringify({
        question_id: questionId,
        answer_text: answerText,
        idempotency_key: idempotencyKey || crypto.randomUUID(),
      }),
    }
  );
}

export async function submitMcqAnswer(
  sessionId: string,
  questionId: string,
  selectedOptionId: string,
  idempotencyKey?: string
): Promise<PracticeSessionDetailResponse> {
  return apiFetch<PracticeSessionDetailResponse>(
    `/api/v1/candidate/practice-sessions/${sessionId}/answer-mcq`,
    {
      method: "POST",
      body: JSON.stringify({
        question_id: questionId,
        selected_option_id: selectedOptionId,
        idempotency_key: idempotencyKey || crypto.randomUUID(),
      }),
    }
  );
}

export async function abandonPracticeSession(
  sessionId: string
): Promise<PracticeSessionAbandonResponse> {
  return apiFetch<PracticeSessionAbandonResponse>(
    `/api/v1/candidate/practice-sessions/${sessionId}/abandon`,
    {
      method: "POST",
    }
  );
}
