import { apiFetch } from "./client";

export interface CandidateInterviewMcqOptionDto {
  id?: string;
  option_id?: string;
  text?: string;
  label?: string;
}

export interface CandidateInterviewQuestionDto {
  slot_id: string;
  question_order?: number;
  order?: number;
  question_format: "CONVERSATIONAL" | "CONVERSATION" | "MCQ" | "MCQ_SINGLE_ANSWER";
  question_text: string;
  competency?: string | null;
  options: CandidateInterviewMcqOptionDto[];
  is_supplemental: boolean;
  saved_text_answer?: string | null;
  saved_selected_option_id?: string | null;
  is_answered: boolean;
  saved_at?: string | null;
}

export interface CandidateInterviewSessionResponse {
  session_id: string;
  assignment_id: string;
  job_id: string;
  job_title: string;
  job_revision: number;
  status: "IN_PROGRESS" | "SUBMITTED";
  started_at: string;
  last_saved_at?: string | null;
  submitted_at?: string | null;
  total_questions: number;
  answered_questions: number;
  questions: CandidateInterviewQuestionDto[];
}

export interface CandidateSaveAnswerRequest {
  text_answer?: string | null;
  selected_option_id?: string | null;
  is_skipped?: boolean;
}

export interface CandidateSaveAnswerResponse {
  session_id: string;
  slot_id: string;
  saved_at: string;
  is_answered: boolean;
  answered_questions: number;
  total_questions: number;
}

export interface CandidateSubmitInterviewRequest {
  confirmed_incomplete?: boolean;
}

export interface CandidateSubmitInterviewResponse {
  session_id: string;
  status: "SUBMITTED";
  submitted_at: string;
  total_questions: number;
  answered_questions: number;
  message: string;
}

/**
 * Start or resume an official interview session for a released assignment.
 */
export async function startOrResumeInterview(
  releaseId: string
): Promise<CandidateInterviewSessionResponse> {
  return apiFetch<CandidateInterviewSessionResponse>(
    `/api/v1/candidate/interviews/${releaseId}/start`,
    {
      method: "POST",
    }
  );
}

/**
 * Get an official interview session state and saved answers.
 */
export async function getInterviewSession(
  sessionId: string
): Promise<CandidateInterviewSessionResponse> {
  return apiFetch<CandidateInterviewSessionResponse>(
    `/api/v1/candidate/interviews/sessions/${sessionId}`
  );
}

/**
 * Save or update one answer for an in-progress official interview session.
 */
export async function saveInterviewAnswer(
  sessionId: string,
  slotId: string,
  payload: CandidateSaveAnswerRequest
): Promise<CandidateSaveAnswerResponse> {
  return apiFetch<CandidateSaveAnswerResponse>(
    `/api/v1/candidate/interviews/sessions/${sessionId}/answers/${slotId}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    }
  );
}

/**
 * Submit an official interview session.
 */
export async function submitInterview(
  sessionId: string,
  payload: CandidateSubmitInterviewRequest = {}
): Promise<CandidateSubmitInterviewResponse> {
  return apiFetch<CandidateSubmitInterviewResponse>(
    `/api/v1/candidate/interviews/sessions/${sessionId}/submit`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}
