import { apiFetch } from "./client";

export interface CreateInvitationResponse {
  invitationId: string;
  candidateId: string;
  organizationId: string;
  rawToken: string;
  activationUrl: string;
  expiresAt: string;
  createdAt: string;
}

export interface CandidateInvitationSummary {
  invitationId: string;
  candidateId: string;
  organizationId: string;
  purpose: string;
  status: "ACTIVE" | "CONSUMED" | "EXPIRED" | "REVOKED";
  expiresAt: string;
  consumedAt?: string | null;
  revokedAt?: string | null;
  createdByUserId: string;
  createdAt: string;
}

export interface CandidateAuthResponse {
  userId: string;
  email: string;
  displayName: string;
  role: string;
  candidateId: string;
  organizationId: string;
  bindingStatus: string;
  csrfToken: string;
  idleExpiresAt?: string;
  absoluteExpiresAt?: string;
}

export async function createCandidateInvitation(
  candidateId: string,
  validHours: number = 24
): Promise<CreateInvitationResponse> {
  return apiFetch<CreateInvitationResponse>("/api/v1/recruiter/candidate-invitations", {
    method: "POST",
    body: JSON.stringify({
      candidate_id: candidateId,
      valid_hours: validHours,
    }),
  });
}

export async function listCandidateInvitations(
  candidateId: string
): Promise<CandidateInvitationSummary[]> {
  return apiFetch<CandidateInvitationSummary[]>(
    `/api/v1/recruiter/candidate-invitations/${candidateId}`
  );
}

export async function revokeCandidateInvitation(
  invitationId: string
): Promise<CandidateInvitationSummary> {
  return apiFetch<CandidateInvitationSummary>(
    `/api/v1/recruiter/candidate-invitations/${invitationId}/revoke`,
    {
      method: "POST",
    }
  );
}

export async function activateCandidateAccount(
  token: string,
  password: string,
  passwordConfirmation: string
): Promise<CandidateAuthResponse> {
  return apiFetch<CandidateAuthResponse>("/api/v1/candidate/auth/activate", {
    method: "POST",
    body: JSON.stringify({
      token,
      password,
      password_confirmation: passwordConfirmation,
    }),
  });
}

export async function candidateLogin(
  email: string,
  password: string
): Promise<CandidateAuthResponse> {
  return apiFetch<CandidateAuthResponse>("/api/v1/candidate/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
    }),
  });
}

export async function getCandidateMe(): Promise<CandidateAuthResponse> {
  return apiFetch<CandidateAuthResponse>("/api/v1/candidate/auth/me");
}

export async function candidateLogout(): Promise<void> {
  return apiFetch("/api/v1/candidate/auth/logout", {
    method: "POST",
  });
}
