import { apiFetch } from "./client";
import {
  CandidatePracticeDiscoveryResponse,
  RecruiterPracticeReleaseSummary,
} from "../types/ai_question_set";

export interface PracticeEligibleJob {
  job_id: string;
  job_title: string;
  job_revision: number;
  ai_set_id: string;
  set_version: number;
  approved_at: string;
  conversation_count: number;
  mcq_count: number;
  total_question_count: number;
  already_released: boolean;
}

export interface PracticeEligibleJobsResponse {
  items: PracticeEligibleJob[];
}

export async function listEligibleJobsForPracticeRelease(
  candidateId: string
): Promise<PracticeEligibleJobsResponse> {
  return apiFetch<PracticeEligibleJobsResponse>(
    `/api/v1/recruiter/candidate-practice/candidates/${candidateId}/eligible-jobs`
  );
}

export async function releasePracticeToCandidate(
  candidateId: string,
  jobId: string
): Promise<RecruiterPracticeReleaseSummary> {
  return apiFetch<RecruiterPracticeReleaseSummary>(
    `/api/v1/recruiter/candidate-practice/candidates/${candidateId}/release`,
    {
      method: "POST",
      body: JSON.stringify({ job_id: jobId }),
    }
  );
}

export async function listCandidatePracticeReleases(
  candidateId: string
): Promise<RecruiterPracticeReleaseSummary[]> {
  return apiFetch<RecruiterPracticeReleaseSummary[]>(
    `/api/v1/recruiter/candidate-practice/candidates/${candidateId}/releases`
  );
}

export async function revokeCandidatePracticeRelease(
  releaseId: string
): Promise<{ success: boolean; release_id: string; status: string; safe_message: string }> {
  return apiFetch<{ success: boolean; release_id: string; status: string; safe_message: string }>(
    `/api/v1/recruiter/candidate-practice/releases/${releaseId}/revoke`,
    {
      method: "POST",
    }
  );
}

export async function getCandidatePracticeDiscovery(): Promise<CandidatePracticeDiscoveryResponse> {
  return apiFetch<CandidatePracticeDiscoveryResponse>("/api/v1/candidate/practice-jobs");
}
