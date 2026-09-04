import { apiFetch } from "./client";

export type EmploymentType = "FULL_TIME" | "PART_TIME" | "CONTRACT" | "INTERNSHIP" | "TEMPORARY";
export type WorkplaceType = "ON_SITE" | "HYBRID" | "REMOTE";
export type JobLifecycleStatus = "ACTIVE" | "ARCHIVED";
export type JobVersionStatus = "DRAFT" | "APPROVED";

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
  approvedByUserId?: string | null;
  approvedAt?: string | null;
  requirements: RequirementItem[];
  reviewWarnings: JobReviewWarning[];
  createdAt: string;
  updatedAt: string;
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
