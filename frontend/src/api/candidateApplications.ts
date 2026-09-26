/**
 * Candidate Applications API (Phase 4B.4).
 *
 * Provides typed functions to submit applications, fetch applications,
 * fetch single application details, and withdraw applications.
 */
import { apiFetch } from "./client";
import { CandidateJobSummary } from "./candidateJobs";

export type ApplicationStatus = "SUBMITTED" | "WITHDRAWN";

export interface CandidateApplication {
  applicationId: string;
  jobId: string;
  jobVersionId: string;
  jobRevision: number;
  profileVersion: number;
  status: ApplicationStatus;
  submittedAt: string;
  withdrawnAt?: string | null;
  canWithdraw: boolean;
  job: CandidateJobSummary;
}

export interface CandidateApplicationListResponse {
  items: CandidateApplication[];
  total: number;
  page: number;
  limit: number;
}

export interface SubmitApplicationPayload {
  idempotencyKey?: string;
  expectedRevision?: number;
}

export async function submitApplication(
  jobId: string,
  payload?: SubmitApplicationPayload
): Promise<CandidateApplication> {
  return apiFetch<CandidateApplication>(`/api/v1/candidate/applications/jobs/${jobId}`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export async function fetchMyApplications(params?: {
  page?: number;
  limit?: number;
}): Promise<CandidateApplicationListResponse> {
  const queryParams = new URLSearchParams();
  if (params?.page) queryParams.set("page", params.page.toString());
  if (params?.limit) queryParams.set("limit", params.limit.toString());

  const qs = queryParams.toString();
  const endpoint = `/api/v1/candidate/applications${qs ? `?${qs}` : ""}`;
  return apiFetch<CandidateApplicationListResponse>(endpoint, {
    method: "GET",
  });
}

export async function fetchApplicationDetail(
  applicationId: string
): Promise<CandidateApplication> {
  return apiFetch<CandidateApplication>(`/api/v1/candidate/applications/${applicationId}`, {
    method: "GET",
  });
}

export async function withdrawApplication(
  applicationId: string
): Promise<CandidateApplication> {
  return apiFetch<CandidateApplication>(
    `/api/v1/candidate/applications/${applicationId}/withdraw`,
    {
      method: "POST",
    }
  );
}
