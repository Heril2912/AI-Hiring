import { apiFetch } from "./client";

export type EmploymentType = "FULL_TIME" | "PART_TIME" | "CONTRACT" | "INTERNSHIP" | "TEMPORARY";
export type WorkplaceType = "ON_SITE" | "HYBRID" | "REMOTE";
export type JobLifecycleStatus = "ACTIVE" | "ARCHIVED";
export type JobVersionStatus = "DRAFT" | "READY_FOR_MATCHING" | "APPROVED";

export type RequirementCategory =
  | "SKILL"
  | "EXPERIENCE"
  | "RESPONSIBILITY"
  | "EDUCATION"
  | "CERTIFICATION"
  | "LANGUAGE"
  | "OTHER";

export type RequirementNecessity = "MUST_HAVE" | "PREFERRED";
export type RequirementPriority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type RequirementOrigin = "RECRUITER_ENTERED" | "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED";

export type RequirementEvidenceType =
  | "EMPLOYMENT"
  | "PROJECT"
  | "EDUCATION"
  | "CERTIFICATION"
  | "SKILL_LIST"
  | "PUBLICATION"
  | "PATENT"
  | "OTHER";

export interface RequirementItem {
  requirementId?: string;
  displayOrder: number;
  category: RequirementCategory;
  label: string;
  normalizedLabel?: string;
  taxonomySkillConceptId?: string | null;
  necessity: RequirementNecessity;
  priority: RequirementPriority;
  customWeightOverride?: number | null;
  minExperienceMonths?: number | null;
  recencyYears?: number | null;
  acceptedEvidenceTypes: RequirementEvidenceType[];
  acceptedEquivalents: string[];
  rationale?: string | null;
  origin?: RequirementOrigin;
  reviewRequired?: boolean;
  warningMetadata?: Array<{
    code: string;
    message: string;
    severity?: string;
    rule?: string;
    matched_term?: string;
  }>;
  createdAt?: string;
  updatedAt?: string;
}

export interface JobReviewWarning {
  code: string;
  message: string;
  severity: string;
  requirementId?: string | null;
  rule?: string | null;
  matchedTerm?: string | null;
}

export interface JobVersionSummary {
  jobVersionId: string;
  versionNumber: number;
  versionStatus: JobVersionStatus;
  revision: number;
  title: string;
  department?: string | null;
  location?: string | null;
  employmentType?: EmploymentType | null;
  workplaceType?: WorkplaceType | null;
  openingsCount?: number | null;
  internalReference?: string | null;
  requirementsCount: number;
  readyByUserId?: string | null;
  readyAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface JobVersionDetail {
  jobVersionId: string;
  jobId: string;
  versionNumber: number;
  versionStatus: JobVersionStatus;
  revision: number;
  title: string;
  department?: string | null;
  location?: string | null;
  employmentType?: EmploymentType | null;
  workplaceType?: WorkplaceType | null;
  openingsCount?: number | null;
  internalReference?: string | null;
  summary?: string | null;
  responsibilities?: string | null;
  jobDescriptionText?: string | null;
  occupationConceptId?: string | null;
  occupationTitle?: string | null;
  taxonomyVersion?: string | null;
  parserVersion?: string | null;
  createdByUserId: string;
  readyByUserId?: string | null;
  readyAt?: string | null;
  approvedByUserId?: string | null;
  approvedAt?: string | null;
  requirements: RequirementItem[];
  reviewWarnings: JobReviewWarning[];
  createdAt: string;
  updatedAt: string;
}

export type JobReadinessSeverity = "ERROR" | "WARNING" | "INFO";

export interface JobReadinessFinding {
  code: string;
  severity: JobReadinessSeverity;
  message: string;
  requirementId?: string | null;
  field?: string | null;
  rule?: string | null;
  blocksReadiness: boolean;
}

export interface JobReadinessResponse {
  jobId: string;
  jobVersionId: string;
  versionNumber: number;
  revision: number;
  versionStatus: JobVersionStatus;
  ready: boolean;
  errors: JobReadinessFinding[];
  warnings: JobReadinessFinding[];
  info: JobReadinessFinding[];
  checkedAt: string;
}

export interface JobSummary {
  jobId: string;
  createdByUserId: string;
  status: JobLifecycleStatus;
  createdAt: string;
  updatedAt: string;
  currentVersion: JobVersionSummary;
}

export interface JobDetail {
  jobId: string;
  createdByUserId: string;
  status: JobLifecycleStatus;
  createdAt: string;
  updatedAt: string;
  currentVersion: JobVersionDetail;
}

export interface JobCreatePayload {
  title: string;
  department?: string | null;
  location?: string | null;
  employmentType?: EmploymentType | null;
  workplaceType?: WorkplaceType | null;
  openingsCount?: number | null;
  internalReference?: string | null;
  summary?: string | null;
  responsibilities?: string | null;
  jobDescriptionText?: string | null;
  occupationConceptId?: string | null;
}

export interface JobDraftUpdatePayload {
  expectedRevision: number;
  title?: string;
  department?: string | null;
  location?: string | null;
  employmentType?: EmploymentType | null;
  workplaceType?: WorkplaceType | null;
  openingsCount?: number | null;
  internalReference?: string | null;
  summary?: string | null;
  responsibilities?: string | null;
  jobDescriptionText?: string | null;
  occupationConceptId?: string | null;
}

export interface JobRequirementsSavePayload {
  expectedRevision: number;
  requirements: Array<{
    displayOrder: number;
    category: RequirementCategory;
    label: string;
    taxonomySkillConceptId?: string | null;
    necessity: RequirementNecessity;
    priority: RequirementPriority;
    customWeightOverride?: number | null;
    minExperienceMonths?: number | null;
    recencyYears?: number | null;
    acceptedEvidenceTypes?: RequirementEvidenceType[];
    acceptedEquivalents?: string[];
    rationale?: string | null;
  }>;
}

export async function fetchJobs(): Promise<JobSummary[]> {
  return apiFetch<JobSummary[]>("/api/v1/jobs");
}

export async function fetchJobDetail(jobId: string): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/v1/jobs/${jobId}`);
}

export async function createJobRequisition(payload: JobCreatePayload, idempotencyKey?: string): Promise<JobDetail> {
  const headers: Record<string, string> = {};
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }
  return apiFetch<JobDetail>("/api/v1/jobs", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
}

export async function updateJobDraft(jobId: string, payload: JobDraftUpdatePayload): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/v1/jobs/${jobId}/draft`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function saveDraftRequirements(jobId: string, payload: JobRequirementsSavePayload): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/v1/jobs/${jobId}/draft/requirements`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function checkJobReadiness(
  jobId: string,
  expectedRevision?: number
): Promise<JobReadinessResponse> {
  const qs = expectedRevision !== undefined ? `?expected_revision=${expectedRevision}` : "";
  return apiFetch<JobReadinessResponse>(`/api/v1/jobs/${jobId}/readiness${qs}`);
}

export async function markJobReady(
  jobId: string,
  expectedRevision: number
): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/v1/jobs/${jobId}/ready`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: expectedRevision }),
  });
}

export async function createSuccessorVersion(
  jobId: string,
  fromVersionNumber?: number
): Promise<JobDetail> {
  return apiFetch<JobDetail>(`/api/v1/jobs/${jobId}/versions`, {
    method: "POST",
    body: JSON.stringify({ from_version_number: fromVersionNumber }),
  });
}

export async function fetchJobVersions(jobId: string): Promise<JobVersionSummary[]> {
  return apiFetch<JobVersionSummary[]>(`/api/v1/jobs/${jobId}/versions`);
}

export type JobImportSourceType = "PASTED_TEXT" | "PDF" | "DOCX";
export type JobImportStatus = "PENDING_REVIEW" | "APPLIED" | "DISCARDED";

export interface JobSuggestionItem {
  suggestionId: string;
  targetField: "TITLE" | "DEPARTMENT" | "LOCATION" | "EMPLOYMENT_TYPE" | "WORKPLACE_TYPE" | "OPENINGS_COUNT" | "SUMMARY" | "RESPONSIBILITY" | "REQUIREMENT";
  proposedValue: any;
  normalizedValue?: string | null;
  sourceExcerpt: string;
  startOffset: number;
  endOffset: number;
  extractionMethod: string;
  confidence: string;
  reviewStatus: "PENDING" | "ACCEPTED" | "REJECTED" | "EDITED";
}

export interface JobImportWarning {
  code: string;
  message: string;
  sourceExcerpt?: string | null;
  startOffset?: number | null;
  endOffset?: number | null;
  rule?: string | null;
  matchedTerm?: string | null;
}

export interface JobImportAnalyzeResponse {
  sessionId: string;
  jobId?: string | null;
  jobVersionId?: string | null;
  expectedRevision?: number | null;
  sourceType: JobImportSourceType;
  sourceFilename?: string | null;
  sourceText: string;
  parserVersion: string;
  taxonomyVersion?: string | null;
  status: JobImportStatus;
  suggestions: JobSuggestionItem[];
  warnings: JobImportWarning[];
  createdAt: string;
  updatedAt: string;
}

export async function analyzeJobDescriptionText(
  text: string,
  jobId?: string | null,
  expectedRevision?: number | null
): Promise<JobImportAnalyzeResponse> {
  const params = new URLSearchParams();
  if (jobId) params.append("job_id", jobId);
  if (expectedRevision) params.append("expected_revision", String(expectedRevision));

  const qs = params.toString();
  const url = `/api/v1/jobs/imports/analyze-text${qs ? `?${qs}` : ""}`;

  return apiFetch<JobImportAnalyzeResponse>(url, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export async function analyzeJobDescriptionFile(
  file: File,
  jobId?: string | null,
  expectedRevision?: number | null
): Promise<JobImportAnalyzeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (jobId) formData.append("job_id", jobId);
  if (expectedRevision) formData.append("expected_revision", String(expectedRevision));

  // Use raw fetch for multipart/form-data with credentials
  const resp = await fetch("/api/v1/jobs/imports/analyze-file", {
    method: "POST",
    body: formData,
    credentials: "include",
  });

  if (!resp.ok) {
    let errData: any = {};
    try {
      errData = await resp.json();
    } catch {
      // ignore
    }
    const msg = errData?.detail?.message || errData?.message || `File analysis failed with status ${resp.status}`;
    const code = errData?.detail?.code || errData?.code;
    const err = new Error(msg);
    (err as any).code = code;
    (err as any).status = resp.status;
    throw err;
  }

  return resp.json();
}

export async function getImportSession(sessionId: string): Promise<JobImportAnalyzeResponse> {
  return apiFetch<JobImportAnalyzeResponse>(`/api/v1/jobs/imports/${sessionId}`);
}

export async function updateSuggestionStatus(
  sessionId: string,
  suggestionId: string,
  reviewStatus: string,
  editedValue?: any
): Promise<JobImportAnalyzeResponse> {
  return apiFetch<JobImportAnalyzeResponse>(`/api/v1/jobs/imports/${sessionId}/suggestions/${suggestionId}`, {
    method: "PATCH",
    body: JSON.stringify({ review_status: reviewStatus, edited_value: editedValue }),
  });
}

export async function applyImportSuggestions(
  sessionId: string,
  payload: {
    expectedRevision?: number | null;
    acceptedSuggestionIds: string[];
    editedSuggestions?: Record<string, any>;
  }
): Promise<{ status: string; sessionId: string; appliedCount: number; appliedItems: any[] }> {
  return apiFetch(`/api/v1/jobs/imports/${sessionId}/apply`, {
    method: "POST",
    body: JSON.stringify({
      expected_revision: payload.expectedRevision,
      accepted_suggestion_ids: payload.acceptedSuggestionIds,
      edited_suggestions: payload.editedSuggestions,
    }),
  });
}

export async function discardImportSession(sessionId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/jobs/imports/${sessionId}`, {
    method: "DELETE",
  });
}

