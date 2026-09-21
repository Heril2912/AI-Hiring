import React, { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { Icon } from "./Icon";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { VersionHistoryDrawer, ProfileSummary } from "./VersionHistoryDrawer";
import { ReviewDrawer } from "./ReviewDrawer";
import { ExtractionResultData } from "./ExtractionReview";
import { AtsExportModal } from "./ats/AtsExportModal";

export type ExtractedField = {
  fieldName: string;
  value: string | null;
  normalizedValue: string | null;
  confidence: number | null;
  confidenceBand: string;
  evidenceIds: string[];
  extractionMethod: string | null;
  reviewStatus: string;
};

export type ExperienceRecord = {
  jobTitle: ExtractedField;
  organization: ExtractedField;
  startDate: ExtractedField;
  endDate: ExtractedField;
  descriptions: ExtractedField[];
};

export type EducationRecord = {
  degree: ExtractedField;
  fieldOfStudy?: ExtractedField | null;
  institution: ExtractedField;
  startDate: ExtractedField;
  endDate: ExtractedField;
  grade: ExtractedField;
};

export type ProjectRecord = {
  name: ExtractedField;
  description: ExtractedField;
  technologies: ExtractedField[];
  projectUrl: ExtractedField;
};

export type CertificationRecord = {
  name: ExtractedField;
  issuer: ExtractedField;
  issuedDate: ExtractedField;
  expiryDate?: ExtractedField | null;
  credentialId?: ExtractedField | null;
  credentialUrl: ExtractedField;
};

export type CandidateIdentity = {
  resumeArtifactId: string;
  fullName: ExtractedField;
  emails: ExtractedField[];
  phoneNumbers: ExtractedField[];
  linkedin: ExtractedField;
  github: ExtractedField;
  portfolio: ExtractedField;
  location: ExtractedField;
};

export type CandidateProfessionalProfile = {
  headline: ExtractedField;
  summary: ExtractedField;
  skills: ExtractedField[];
  employment: ExperienceRecord[];
  education: EducationRecord[];
  projects: ProjectRecord[];
  certifications: CertificationRecord[];
  languages: ExtractedField[];
  awards: ExtractedField[];
  publications: ExtractedField[];
};

export type EvidenceSpan = {
  evidenceId: string;
  resumeArtifactId: string;
  pageNumber: number | null;
  blockNumber: number | null;
  characterStart: number;
  characterEnd: number;
  originalText: string;
  extractionMethod: string;
};

export type ProfileWarning = {
  code: string;
  category: string;
  message?: string | null;
  fieldName?: string | null;
  count?: number | null;
  evidence_id?: string | null;
};

export type CandidateProfileData = {
  artifactId: string;
  profileId: string;
  profileVersion: number;
  schemaVersion: string;
  parserPipelineVersion: string;
  provenance?: string;
  parentProfileId?: string | null;
  parentProfileVersion?: number | null;
  createdAt?: string | null;
  reviewRequired: boolean;
  warnings: ProfileWarning[];
  identity: CandidateIdentity;
  professionalProfile: CandidateProfessionalProfile;
  evidence: EvidenceSpan[];
};

export type CorrectionReasonCategory =
  | "INCORRECT_EXTRACTION"
  | "MISSING_INFORMATION"
  | "WRONG_RECORD_ASSOCIATION"
  | "DUPLICATE_RECORD"
  | "INCORRECT_NORMALIZATION"
  | "INCORRECT_DATE"
  | "OTHER";

export type CorrectionOperation = {
  operationType: "REPLACE_SCALAR" | "ADD_SET_ITEM" | "REMOVE_SET_ITEM" | "ADD_RECORD" | "UPDATE_RECORD" | "REMOVE_RECORD";
  targetSection: string;
  targetIndex?: number | null;
  value?: string | null;
  recordPayload?: Record<string, unknown> | null;
  selectedEvidenceIds?: string[];
  provenanceType: "HUMAN_PROVIDED" | "HUMAN_CORRECTED_WITH_EVIDENCE";
};

interface CandidateProfileReviewProps {
  profile: CandidateProfileData;
  extraction?: ExtractionResultData | null;
  onNavigateBack: () => void;
  onNavigateExtraction?: () => void;
}

export function CandidateProfileReview({
  profile: initialProfile,
  extraction,
  onNavigateBack,
  onNavigateExtraction,
}: CandidateProfileReviewProps) {
  const [currentProfile, setCurrentProfile] = useState<CandidateProfileData>(initialProfile);
  const [historyList, setHistoryList] = useState<ProfileSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number>(initialProfile.profileVersion);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);

  // Drawers
  const [isHistoryDrawerOpen, setIsHistoryDrawerOpen] = useState<boolean>(false);
  const [isReviewDrawerOpen, setIsReviewDrawerOpen] = useState<boolean>(false);
  const [evidenceDrawerState, setEvidenceDrawerState] = useState<{
    isOpen: boolean;
    fieldLabel: string;
    fieldValue?: string | null;
    evidenceIds: string[];
  }>({
    isOpen: false,
    fieldLabel: "",
    fieldValue: null,
    evidenceIds: [],
  });

  // Correction Workflow State
  const [isCorrectionMode, setIsCorrectionMode] = useState<boolean>(false);
  const [reasonCategory, setReasonCategory] = useState<CorrectionReasonCategory>("INCORRECT_EXTRACTION");
  const [reviewerNote, setReviewerNote] = useState<string>("");
  const [operations, setOperations] = useState<CorrectionOperation[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [conflictError, setConflictError] = useState<boolean>(false);
  const [successToast, setSuccessToast] = useState<string | null>(null);
  const [showDiffPreview, setShowDiffPreview] = useState<boolean>(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState<boolean>(false);

  // Draft scalar inputs for correction
  const [draftFullName, setDraftFullName] = useState("");
  const [draftEmail, setDraftEmail] = useState("");
  const [draftPhone, setDraftPhone] = useState("");
  const [draftLocation, setDraftLocation] = useState("");
  const [draftLinkedin, setDraftLinkedin] = useState("");
  const [draftGithub, setDraftGithub] = useState("");
  const [draftPortfolio, setDraftPortfolio] = useState("");
  const [draftHeadline, setDraftHeadline] = useState("");
  const [draftSummary, setDraftSummary] = useState("");
  const [newSkillInput, setNewSkillInput] = useState("");
  const [newLangInput, setNewLangInput] = useState("");

  // Record modals
  const [editingExperienceIndex, setEditingExperienceIndex] = useState<number | "new" | null>(null);
  const [expJobTitle, setExpJobTitle] = useState("");
  const [expOrg, setExpOrg] = useState("");
  const [expStart, setExpStart] = useState("");
  const [expEnd, setExpEnd] = useState("");
  const [expBullets, setExpBullets] = useState("");

  const [editingEducationIndex, setEditingEducationIndex] = useState<number | "new" | null>(null);
  const [eduDegree, setEduDegree] = useState("");
  const [eduField, setEduField] = useState("");
  const [eduInst, setEduInst] = useState("");
  const [eduStart, setEduStart] = useState("");
  const [eduEnd, setEduEnd] = useState("");
  const [eduGrade, setEduGrade] = useState("");

  const evidenceMap = new Map<string, EvidenceSpan>();
  currentProfile.evidence.forEach((ev) => evidenceMap.set(ev.evidenceId, ev));

  const fetchHistory = async () => {
    try {
      setIsLoadingHistory(true);
      const data = await apiFetch<ProfileSummary[]>(
        `/api/v1/resumes/${currentProfile.artifactId}/profiles`
      );
      setHistoryList(data || []);
    } catch (err) {
      console.error("Failed to fetch history", err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [currentProfile.artifactId, currentProfile.profileVersion]);

  const handleSelectVersion = async (version: number) => {
    try {
      setIsLoadingHistory(true);
      const data = await apiFetch<CandidateProfileData>(
        `/api/v1/resumes/${currentProfile.artifactId}/profile?version=${version}`
      );
      setCurrentProfile(data);
      setSelectedVersion(version);
      setIsCorrectionMode(false);
      setOperations([]);
    } catch (err) {
      console.error("Failed to load profile version", err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const handleReloadLatest = async () => {
    try {
      setIsLoadingHistory(true);
      const data = await apiFetch<CandidateProfileData>(
        `/api/v1/resumes/${currentProfile.artifactId}/profile`
      );
      setCurrentProfile(data);
      setSelectedVersion(data.profileVersion);
      setConflictError(false);
      setErrorMessage(null);
      setIsCorrectionMode(false);
      fetchHistory();
    } catch (err) {
      console.error("Failed to reload latest profile", err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const isLatestVersion =
    historyList.length === 0 || selectedVersion === Math.max(...historyList.map((h) => h.profileVersion));

  const startCorrectionMode = () => {
    setDraftFullName(currentProfile.identity.fullName?.value || "");
    setDraftEmail(currentProfile.identity.emails?.[0]?.value || "");
    setDraftPhone(currentProfile.identity.phoneNumbers?.[0]?.value || "");
    setDraftLocation(currentProfile.identity.location?.value || "");
    setDraftLinkedin(currentProfile.identity.linkedin?.value || "");
    setDraftGithub(currentProfile.identity.github?.value || "");
    setDraftPortfolio(currentProfile.identity.portfolio?.value || "");
    setDraftHeadline(currentProfile.professionalProfile.headline?.value || "");
    setDraftSummary(currentProfile.professionalProfile.summary?.value || "");
    setOperations([]);
    setErrorMessage(null);
    setConflictError(false);
    setShowDiffPreview(false);
    setIsCorrectionMode(true);
  };

  const computeScalarOperations = (): CorrectionOperation[] => {
    const ops: CorrectionOperation[] = [];

    if (draftFullName !== (currentProfile.identity.fullName?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "identity.full_name",
        value: draftFullName.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }
    if (draftEmail !== (currentProfile.identity.emails?.[0]?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "identity.primary_email",
        value: draftEmail.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }
    if (draftPhone !== (currentProfile.identity.phoneNumbers?.[0]?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "identity.primary_phone",
        value: draftPhone.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }
    if (draftLocation !== (currentProfile.identity.location?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "identity.location",
        value: draftLocation.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }
    if (draftLinkedin !== (currentProfile.identity.linkedin?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "identity.linkedin",
        value: draftLinkedin.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }
    if (draftGithub !== (currentProfile.identity.github?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "identity.github",
        value: draftGithub.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }
    if (draftPortfolio !== (currentProfile.identity.portfolio?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "identity.portfolio",
        value: draftPortfolio.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }
    if (draftHeadline !== (currentProfile.professionalProfile.headline?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "headline",
        value: draftHeadline.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }
    if (draftSummary !== (currentProfile.professionalProfile.summary?.value || "")) {
      ops.push({
        operationType: "REPLACE_SCALAR",
        targetSection: "summary",
        value: draftSummary.trim() || null,
        provenanceType: "HUMAN_PROVIDED",
      });
    }

    return ops;
  };

  const handleAddSkill = (skill: string) => {
    const trimmed = skill.trim();
    if (!trimmed) return;
    const exists = currentProfile.professionalProfile.skills.some(
      (s) => s.value?.toLowerCase() === trimmed.toLowerCase()
    );
    if (exists) {
      setErrorMessage(`Skill '${trimmed}' is already present.`);
      return;
    }
    setOperations((prev) => [
      ...prev,
      {
        operationType: "ADD_SET_ITEM",
        targetSection: "skills",
        value: trimmed,
        provenanceType: "HUMAN_PROVIDED",
      },
    ]);
    setNewSkillInput("");
    setErrorMessage(null);
  };

  const handleRemoveSkill = (skillName: string) => {
    setOperations((prev) => [
      ...prev,
      {
        operationType: "REMOVE_SET_ITEM",
        targetSection: "skills",
        value: skillName,
        provenanceType: "HUMAN_PROVIDED",
      },
    ]);
  };

  const handleAddLanguage = (lang: string) => {
    const trimmed = lang.trim();
    if (!trimmed) return;
    setOperations((prev) => [
      ...prev,
      {
        operationType: "ADD_SET_ITEM",
        targetSection: "languages",
        value: trimmed,
        provenanceType: "HUMAN_PROVIDED",
      },
    ]);
    setNewLangInput("");
    setErrorMessage(null);
  };

  const handleRemoveLanguage = (langName: string) => {
    setOperations((prev) => [
      ...prev,
      {
        operationType: "REMOVE_SET_ITEM",
        targetSection: "languages",
        value: langName,
        provenanceType: "HUMAN_PROVIDED",
      },
    ]);
  };

  const handleRemoveExperience = (index: number) => {
    setOperations((prev) => [
      ...prev,
      {
        operationType: "REMOVE_RECORD",
        targetSection: "employment",
        targetIndex: index,
        provenanceType: "HUMAN_PROVIDED",
      },
    ]);
  };

  const handleSaveExperienceModal = () => {
    if (!expJobTitle.trim() || !expOrg.trim()) {
      setErrorMessage("Job title and organization are required.");
      return;
    }
    const bullets = expBullets
      .split("\n")
      .map((b) => b.trim())
      .filter(Boolean);

    const recordPayload = {
      jobTitle: expJobTitle.trim(),
      organization: expOrg.trim(),
      startDate: expStart.trim() || null,
      endDate: expEnd.trim() || null,
      descriptions: bullets,
    };

    if (editingExperienceIndex === "new") {
      setOperations((prev) => [
        ...prev,
        {
          operationType: "ADD_RECORD",
          targetSection: "employment",
          recordPayload,
          provenanceType: "HUMAN_PROVIDED",
        },
      ]);
    } else if (typeof editingExperienceIndex === "number") {
      setOperations((prev) => [
        ...prev,
        {
          operationType: "UPDATE_RECORD",
          targetSection: "employment",
          targetIndex: editingExperienceIndex,
          recordPayload,
          provenanceType: "HUMAN_PROVIDED",
        },
      ]);
    }
    setEditingExperienceIndex(null);
    setErrorMessage(null);
  };

  const handleRemoveEducation = (index: number) => {
    setOperations((prev) => [
      ...prev,
      {
        operationType: "REMOVE_RECORD",
        targetSection: "education",
        targetIndex: index,
        provenanceType: "HUMAN_PROVIDED",
      },
    ]);
  };

  const handleSaveEducationModal = () => {
    if (!eduDegree.trim() || !eduInst.trim()) {
      setErrorMessage("Degree and institution are required.");
      return;
    }
    const recordPayload = {
      degree: eduDegree.trim(),
      fieldOfStudy: eduField.trim() || null,
      institution: eduInst.trim(),
      startDate: eduStart.trim() || null,
      endDate: eduEnd.trim() || null,
      grade: eduGrade.trim() || null,
    };

    if (editingEducationIndex === "new") {
      setOperations((prev) => [
        ...prev,
        {
          operationType: "ADD_RECORD",
          targetSection: "education",
          recordPayload,
          provenanceType: "HUMAN_PROVIDED",
        },
      ]);
    } else if (typeof editingEducationIndex === "number") {
      setOperations((prev) => [
        ...prev,
        {
          operationType: "UPDATE_RECORD",
          targetSection: "education",
          targetIndex: editingEducationIndex,
          recordPayload,
          provenanceType: "HUMAN_PROVIDED",
        },
      ]);
    }
    setEditingEducationIndex(null);
    setErrorMessage(null);
  };

  const handleSubmitCorrections = async (e: React.FormEvent) => {
    e.preventDefault();
    const scalarOps = computeScalarOperations();
    const totalOps = [...scalarOps, ...operations];

    if (totalOps.length === 0) {
      setErrorMessage("No modifications detected in draft.");
      return;
    }

    if (reasonCategory === "OTHER" && !reviewerNote.trim()) {
      setErrorMessage("Reviewer note is required when reason category is 'Other'.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setConflictError(false);

    try {
      const idempotencyKey = `corr-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const payload = {
        baseProfileId: currentProfile.profileId,
        baseProfileVersion: currentProfile.profileVersion,
        idempotencyKey,
        reasonCategory,
        reviewerNote: reviewerNote.trim() || null,
        operations: totalOps,
      };

      const responseData = await apiFetch<any>(
        `/api/v1/resumes/${currentProfile.artifactId}/profile-corrections`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );

      setCurrentProfile(responseData.profile);
      setSelectedVersion(responseData.newProfileVersion);
      setIsCorrectionMode(false);
      setOperations([]);
      setSuccessToast(`Profile Version ${responseData.newProfileVersion} created successfully.`);
      fetchHistory();
      setTimeout(() => setSuccessToast(null), 5000);
    } catch (err: any) {
      if (err?.code === "PROFILE_VERSION_CONFLICT") {
        setConflictError(true);
        setErrorMessage(
          "Conflict: A newer profile version exists. Please reload to review the latest changes before correcting."
        );
      } else {
        setErrorMessage(err?.message || "Failed to submit profile correction.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const openEvidenceInspector = (label: string, value: string | null | undefined, evidenceIds: string[]) => {
    setIsReviewDrawerOpen(false);
    setIsHistoryDrawerOpen(false);
    setEvidenceDrawerState({
      isOpen: true,
      fieldLabel: label,
      fieldValue: value || null,
      evidenceIds: evidenceIds || [],
    });
  };

  const openReviewDrawer = () => {
    setIsHistoryDrawerOpen(false);
    setEvidenceDrawerState((prev) => ({ ...prev, isOpen: false }));
    setIsReviewDrawerOpen(true);
  };

  const openHistoryDrawer = () => {
    setIsReviewDrawerOpen(false);
    setEvidenceDrawerState((prev) => ({ ...prev, isOpen: false }));
    setIsHistoryDrawerOpen(true);
  };

  const handleNavigateToSection = (sectionKey: string) => {
    const sectionMap: Record<string, string> = {
      summary: "section-summary-title",
      skills: "section-skills-title",
      employment: "section-experience-title",
      education: "section-education-title",
      projects: "section-projects-title",
      certifications: "section-certifications-title",
      languages: "section-languages-title",
      identity: "candidate-hero-name",
    };
    const elemId = sectionMap[sectionKey] || "section-summary-title";
    const elem = document.getElementById(elemId);
    if (elem) {
      elem.scrollIntoView({ behavior: "smooth", block: "center" });
      const card = elem.closest(".profile-surface-card") || elem.closest(".candidate-hero-card");
      if (card) {
        card.classList.add("target-section-highlight");
        setTimeout(() => {
          card.classList.remove("target-section-highlight");
        }, 2500);
      }
      elem.focus?.();
    }
  };

  const getInitials = (name?: string | null) => {
    if (!name || !name.trim()) return "??";
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  };

  const renderDateInterval = (startDate?: ExtractedField | null, endDate?: ExtractedField | null) => {
    if (startDate?.value && endDate?.value) {
      return `${startDate.value} — ${endDate.value}`;
    }
    if (startDate?.value) {
      return `${startDate.value} — Present`;
    }
    if (endDate?.value) {
      return `Until ${endDate.value}`;
    }
    return "Date not specified";
  };

  const formatLanguageProficiency = (normalized?: string | null, raw?: string | null) => {
    if (!normalized && !raw) return "";
    const val = (normalized || raw || "").toUpperCase();
    switch (val) {
      case "NATIVE":
      case "NATIVE_OR_BILINGUAL":
        return "Native or bilingual proficiency";
      case "PROFESSIONAL_WORKING":
      case "PROFESSIONAL":
        return "Professional working proficiency";
      case "FULL_PROFESSIONAL":
        return "Full professional proficiency";
      case "LIMITED_WORKING":
        return "Limited working proficiency";
      case "ELEMENTARY":
        return "Elementary proficiency";
      default:
        return normalized || raw || "";
    }
  };

  const { identity, professionalProfile } = currentProfile;
  const isHumanCorrected = currentProfile.provenance === "HUMAN_CORRECTED";
  const fullNameStr = identity.fullName?.value || "Candidate";
  const initials = getInitials(fullNameStr);

  const totalOps = [...computeScalarOperations(), ...operations];
  const warningCount = currentProfile.warnings?.length || 0;

  return (
    <div className="candidate-workspace-container">
      {/* Top Workspace Breadcrumb & Header */}
      <div className="workspace-header-bar">
        <button
          type="button"
          onClick={onNavigateBack}
          className="btn-back-link"
        >
          <Icon name="arrow-left" size={16} />
          <span>Back to Candidates</span>
        </button>

        <div className="workspace-header-actions">
          {historyList.length > 1 && (
            <div className="version-select-pill">
              <span className="version-pill-label">Version:</span>
              <select
                className="version-native-select"
                value={selectedVersion}
                onChange={(e) => handleSelectVersion(Number(e.target.value))}
                disabled={isLoadingHistory || isCorrectionMode}
                aria-label="Select profile version snapshot"
              >
                {historyList.map((h) => (
                  <option key={h.profileVersion} value={h.profileVersion}>
                    v{h.profileVersion} ({h.provenance === "HUMAN_CORRECTED" ? "Corrected" : "Parser"})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Compact Review Items Action */}
          {warningCount > 0 && !isCorrectionMode && (
            <button
              type="button"
              onClick={openReviewDrawer}
              className="btn btn-warning-action btn-sm"
              aria-label={`Open ${warningCount} profile review items`}
            >
              <Icon name="alert-triangle" size={14} className="text-amber" />
              <span>Review Items</span>
              <span className="warning-count-pill">{warningCount}</span>
            </button>
          )}

          {!isCorrectionMode && isLatestVersion && (
            <button
              type="button"
              onClick={startCorrectionMode}
              className="btn btn-primary btn-sm"
            >
              <Icon name="edit" size={14} /> Correct Profile
            </button>
          )}

          <button
            type="button"
            onClick={openHistoryDrawer}
            className="btn btn-secondary btn-sm"
          >
            <Icon name="history" size={14} /> History ({historyList.length})
          </button>

          {onNavigateExtraction && (
            <button
              type="button"
              onClick={onNavigateExtraction}
              className="btn btn-secondary btn-sm"
            >
              <Icon name="file-text" size={14} /> Raw Extraction
            </button>
          )}

          <button
            type="button"
            onClick={() => setIsExportModalOpen(true)}
            className="btn btn-secondary btn-sm"
            title="Export candidate review note to ATS"
          >
            <Icon name="external-link" size={14} /> Export to ATS
          </button>
        </div>
      </div>

      {/* Success Toast Banner */}
      {successToast && (
        <div className="feedback-box success toast-banner" role="status">
          <Icon name="check" size={16} />
          <span>{successToast}</span>
        </div>
      )}

      {/* Stale Version Alert */}
      {!isLatestVersion && (
        <div className="historical-view-banner" role="alert">
          <div className="banner-left">
            <Icon name="history" size={16} />
            <span>
              Viewing historical snapshot <strong>Version {currentProfile.profileVersion}</strong> (Read-Only).
            </span>
          </div>
          <button
            type="button"
            onClick={handleReloadLatest}
            className="btn btn-secondary btn-xs"
          >
            Switch to Latest (v{Math.max(...historyList.map((h) => h.profileVersion))})
          </button>
        </div>
      )}

      {/* Conflict / Error Banner */}
      {errorMessage && (
        <div className="feedback-box error" role="alert">
          <Icon name="alert-triangle" size={16} />
          <div className="error-content">
            <p className="feedback-text error">{errorMessage}</p>
            {conflictError && (
              <button
                type="button"
                onClick={handleReloadLatest}
                className="btn btn-primary btn-xs"
                style={{ marginTop: "6px" }}
              >
                <Icon name="refresh" size={13} /> Reload Latest Version
              </button>
            )}
          </div>
        </div>
      )}

      {/* CANDIDATE HEADER HERO CARD */}
      <div className="candidate-hero-card">
        <div className="hero-left">
          <div className="candidate-hero-avatar">
            <span>{initials}</span>
          </div>

          <div className="hero-details">
            <div className="hero-name-row">
              <h1 id="candidate-hero-name" className="candidate-hero-name" tabIndex={-1}>
                {fullNameStr}
              </h1>
              <div className="hero-status-tags">
                {(currentProfile.provenance?.includes("Local") || currentProfile.provenance?.includes("ATS")) ? (
                  <span className="badge badge-provenance-parser" style={{ backgroundColor: "#f0fdf4", color: "#166534" }}>
                    Source: Local Folder ATS Demo
                  </span>
                ) : (
                  <span className={`badge ${isHumanCorrected ? "badge-provenance-corrected" : "badge-provenance-parser"}`}>
                    {isHumanCorrected ? "Human Corrected" : "Parser Generated"}
                  </span>
                )}
                <span className="badge badge-version">v{currentProfile.profileVersion}</span>
                {currentProfile.reviewRequired && !isHumanCorrected && (
                  <span className="badge badge-review-warn">Needs Review</span>
                )}
              </div>
            </div>

            <p className="candidate-hero-headline">
              {professionalProfile.headline?.value || "Professional Profile"}
            </p>

            {/* Quick Contact Links (Omitted if not present) */}
            <div className="hero-contact-row">
              {identity.location?.value && (
                <span className="hero-contact-item">
                  <Icon name="map-pin" size={14} />
                  <span>{identity.location.value}</span>
                </span>
              )}

              {identity.emails?.[0]?.value && (
                <a href={`mailto:${identity.emails[0].value}`} className="hero-contact-link">
                  <Icon name="mail" size={14} />
                  <span>{identity.emails[0].value}</span>
                </a>
              )}

              {identity.phoneNumbers?.[0]?.value && (
                <a href={`tel:${identity.phoneNumbers[0].value}`} className="hero-contact-link">
                  <Icon name="phone" size={14} />
                  <span>{identity.phoneNumbers[0].value}</span>
                </a>
              )}

              {identity.linkedin?.value && (
                <a
                  href={identity.linkedin.value.startsWith("http") ? identity.linkedin.value : `https://${identity.linkedin.value}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hero-contact-link"
                >
                  <Icon name="linkedin" size={14} />
                  <span>LinkedIn</span>
                </a>
              )}

              {identity.github?.value && (
                <a
                  href={identity.github.value.startsWith("http") ? identity.github.value : `https://${identity.github.value}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hero-contact-link"
                >
                  <Icon name="github" size={14} />
                  <span>GitHub</span>
                </a>
              )}

              {identity.portfolio?.value && (
                <a
                  href={identity.portfolio.value.startsWith("http") ? identity.portfolio.value : `https://${identity.portfolio.value}`}
                  target="_blank"
                  rel="noreferrer"
                  className="hero-contact-link"
                >
                  <Icon name="globe" size={14} />
                  <span>Portfolio</span>
                </a>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* CANDIDATE OVERVIEW SECTION */}
      <section className="candidate-overview-section" aria-label="Candidate Overview">
        <div className="overview-cards-grid">
          {/* A. Candidate Snapshot */}
          <div className="overview-card snapshot-card" role="region" aria-label="Candidate Snapshot">
            <h3 className="overview-card-title">
              <Icon name="user" size={16} className="card-icon" />
              <span>Candidate Snapshot</span>
            </h3>
            <p className="overview-card-subtitle">Documented records identified in candidate profile</p>

            <div className="snapshot-metrics-grid" role="list" aria-label="Profile record counts">
              <div className="snapshot-metric-item" role="listitem">
                <div className="snapshot-icon-wrap"><Icon name="briefcase" size={15} /></div>
                <div className="snapshot-metric-details">
                  <span className="snapshot-val">{professionalProfile.employment?.length || 0}</span>
                  <span className="snapshot-lbl">Documented Positions</span>
                </div>
              </div>

              <div className="snapshot-metric-item" role="listitem">
                <div className="snapshot-icon-wrap"><Icon name="academic-cap" size={15} /></div>
                <div className="snapshot-metric-details">
                  <span className="snapshot-val">{professionalProfile.education?.length || 0}</span>
                  <span className="snapshot-lbl">Education Records</span>
                </div>
              </div>

              <div className="snapshot-metric-item" role="listitem">
                <div className="snapshot-icon-wrap"><Icon name="layers" size={15} /></div>
                <div className="snapshot-metric-details">
                  <span className="snapshot-val">{professionalProfile.projects?.length || 0}</span>
                  <span className="snapshot-lbl">Documented Projects</span>
                </div>
              </div>

              <div className="snapshot-metric-item" role="listitem">
                <div className="snapshot-icon-wrap"><Icon name="award" size={15} /></div>
                <div className="snapshot-metric-details">
                  <span className="snapshot-val">{professionalProfile.certifications?.length || 0}</span>
                  <span className="snapshot-lbl">Certifications</span>
                </div>
              </div>

              <div className="snapshot-metric-item" role="listitem">
                <div className="snapshot-icon-wrap"><Icon name="globe" size={15} /></div>
                <div className="snapshot-metric-details">
                  <span className="snapshot-val">{professionalProfile.languages?.length || 0}</span>
                  <span className="snapshot-lbl">Languages Listed</span>
                </div>
              </div>

              <div className="snapshot-metric-item" role="listitem">
                <div className="snapshot-icon-wrap"><Icon name="badge-check" size={15} /></div>
                <div className="snapshot-metric-details">
                  <span className={`snapshot-status-pill ${currentProfile.reviewRequired ? "status-warn" : "status-ok"}`}>
                    {currentProfile.reviewRequired ? "Needs Review" : "Reviewed"}
                  </span>
                  <span className="snapshot-lbl">Verification State</span>
                </div>
              </div>
            </div>
          </div>

          {/* B. Skills Composition Doughnut */}
          <div className="overview-card skills-composition-card" role="region" aria-label="Skills Composition">
            <h3 className="overview-card-title">
              <Icon name="sparkles" size={16} className="card-icon" />
              <span>Skills Composition</span>
            </h3>
            <p className="overview-card-subtitle">Grouped by recognized taxonomy domain</p>

            {(() => {
              const skillsList = professionalProfile.skills || [];
              const totalSkills = skillsList.length;

              if (totalSkills === 0) {
                return (
                  <p className="empty-field-text" style={{ padding: "16px 0" }}>
                    No technical skills recognized in current profile.
                  </p>
                );
              }

              // Group skills into domains based on available metadata or standard skill classification
              const categoryMap = new Map<string, number>();
              skillsList.forEach((sk) => {
                const rawVal = (sk.value || "").toLowerCase();
                let cat = "Technical & Domain";
                if (/python|javascript|typescript|java|c\+\+|c#|golang|rust|ruby|php|kotlin|swift|scala|sql|bash|r\b/.test(rawVal)) {
                  cat = "Programming Languages";
                } else if (/react|vue|angular|django|fastapi|flask|spring|express|next\.js|node|laravel|rails/.test(rawVal)) {
                  cat = "Frameworks & Libraries";
                } else if (/postgres|mysql|mongodb|redis|cassandra|elasticsearch|dynamodb|sqlite|oracle/.test(rawVal)) {
                  cat = "Databases & Storage";
                } else if (/docker|kubernetes|aws|azure|gcp|git|ci\/cd|terraform|linux|ansible|kafka|graphql/.test(rawVal)) {
                  cat = "Cloud, DevOps & Tools";
                }
                categoryMap.set(cat, (categoryMap.get(cat) || 0) + 1);
              });

              const catEntries = Array.from(categoryMap.entries()).sort((a, b) => b[1] - a[1]);
              const colors = [
                "var(--gap-covered)",
                "var(--gap-unverified)",
                "var(--accent-primary)",
                "var(--gap-partial)",
                "var(--gap-not-evidenced)",
              ];

              let currentDeg = 0;
              const gradStops = catEntries.map(([_, count], idx) => {
                const deg = (count / totalSkills) * 360;
                const stop = `${colors[idx % colors.length]} ${currentDeg}deg ${currentDeg + deg}deg`;
                currentDeg += deg;
                return stop;
              }).join(", ");

              const conicStyle = {
                background: `conic-gradient(${gradStops})`,
              };

              const srDesc = `Skills composition: ${totalSkills} total documented skills across ${catEntries.length} categories. ${catEntries.map(([name, count]) => `${name}: ${count} (${Math.round((count/totalSkills)*100)}%)`).join(", ")}.`;

              return (
                <div className="doughnut-content-row">
                  <div className="doughnut-wheel-wrapper" role="img" aria-label={srDesc}>
                    <div className="doughnut-wheel" style={conicStyle}>
                      <div className="doughnut-hole">
                        <span className="doughnut-center-count">{totalSkills}</span>
                        <span className="doughnut-center-label">skills recognized</span>
                      </div>
                    </div>
                  </div>

                  <div className="doughnut-legend-list" role="list" aria-label="Skill categories">
                    {catEntries.map(([catName, count], idx) => (
                      <div key={catName} className="doughnut-legend-row" role="listitem">
                        <span className="legend-swatch" style={{ backgroundColor: colors[idx % colors.length] }} />
                        <span className="legend-label-text">{catName}:</span>
                        <span className="legend-count-val">{count} ({Math.round((count / totalSkills) * 100)}%)</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      </section>

      {/* CORRECTION WORKFLOW PANEL */}
      {isCorrectionMode && (
        <form onSubmit={handleSubmitCorrections} className="correction-workspace-card">
          <div className="correction-card-header">
            <div>
              <div className="correction-badge-row">
                <span className="badge badge-indigo">
                  <Icon name="edit" size={13} className="badge-icon" />
                  Correction Workspace
                </span>
                <span className="badge badge-neutral">Drafting Version {currentProfile.profileVersion + 1}</span>
              </div>
              <h2 className="correction-workspace-title">Audited Profile Correction</h2>
              <p className="correction-workspace-desc">
                Update extracted values below. Submitting applies an audited, immutable new version without mutating original document bytes or raw extraction blocks.
              </p>
            </div>

            <div className="correction-header-actions">
              <button
                type="button"
                onClick={() => setIsCorrectionMode(false)}
                className="btn btn-secondary btn-sm"
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => setShowDiffPreview((prev) => !prev)}
                className="btn btn-secondary btn-sm"
              >
                <Icon name="eye" size={14} />
                {showDiffPreview ? "Hide Changes" : `Review Changes (${totalOps.length})`}
              </button>
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={isSubmitting}
                aria-busy={isSubmitting}
              >
                {isSubmitting ? "Saving Version..." : "Save Correction Batch"}
              </button>
            </div>
          </div>

          {/* Audit Reason & Reviewer Note Fields */}
          <div className="audit-inputs-grid">
            <div className="form-group">
              <label htmlFor="reason-category" className="field-label">
                Correction Reason <span className="req-star">*</span>
              </label>
              <select
                id="reason-category"
                className="field-input select-input"
                value={reasonCategory}
                onChange={(e) => setReasonCategory(e.target.value as CorrectionReasonCategory)}
                required
              >
                <option value="INCORRECT_EXTRACTION">Incorrect Extraction (Parser error)</option>
                <option value="MISSING_INFORMATION">Missing Information (Omitted by parser)</option>
                <option value="WRONG_RECORD_ASSOCIATION">Wrong Record Association</option>
                <option value="DUPLICATE_RECORD">Duplicate Record</option>
                <option value="INCORRECT_NORMALIZATION">Incorrect Normalization</option>
                <option value="INCORRECT_DATE">Incorrect Date or Date Range</option>
                <option value="OTHER">Other Reason (Note required)</option>
              </select>
            </div>

            <div className="form-group flex-grow">
              <label htmlFor="reviewer-note" className="field-label">
                Reviewer Note {reasonCategory === "OTHER" && <span className="req-star">*</span>}
              </label>
              <input
                id="reviewer-note"
                type="text"
                className="field-input"
                placeholder={
                  reasonCategory === "OTHER"
                    ? "Mandatory audit explanation for reason 'Other'..."
                    : "Optional note describing context for this correction batch"
                }
                value={reviewerNote}
                onChange={(e) => setReviewerNote(e.target.value)}
                required={reasonCategory === "OTHER"}
              />
            </div>
          </div>

          {/* Before vs After Diff Preview */}
          {showDiffPreview && (
            <div className="diff-preview-panel">
              <h4 className="diff-preview-title">Pending Modifications ({totalOps.length})</h4>
              {totalOps.length === 0 ? (
                <p className="diff-empty-text">No fields have been modified yet.</p>
              ) : (
                <div className="diff-items-list">
                  {totalOps.map((op, i) => (
                    <div key={i} className="diff-item-row">
                      <span className="badge badge-neutral mono">{op.targetSection}</span>
                      <span className="diff-op-type">{op.operationType}</span>
                      {op.value && <span className="diff-val">&ldquo;{op.value}&rdquo;</span>}
                      {op.recordPayload && (
                        <span className="diff-val">
                          {String(op.recordPayload.jobTitle || op.recordPayload.degree || "Structured Record")}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </form>
      )}

      {/* TWO-COLUMN CANDIDATE PROFILE WORKSPACE */}
      <div className="profile-dashboard-layout">
        {/* MAIN COLUMN (Summary, Experience, Projects) */}
        <div className="dashboard-main-col">
          {/* Professional Summary */}
          <section className="profile-surface-card" aria-labelledby="section-summary-title">
            <div className="card-header-row">
              <div className="card-title-group">
                <Icon name="file-text" size={17} className="card-icon" />
                <h3 id="section-summary-title" className="card-title" tabIndex={-1}>Profile Summary</h3>
              </div>
              {!isCorrectionMode && professionalProfile.summary?.value && (
                <button
                  type="button"
                  className="btn-evidence-subtle"
                  onClick={() =>
                    openEvidenceInspector(
                      "Profile Summary",
                      professionalProfile.summary?.value,
                      professionalProfile.summary?.evidenceIds || []
                    )
                  }
                >
                  <Icon name="search" size={13} /> Evidence
                </button>
              )}
            </div>

            {isCorrectionMode ? (
              <textarea
                rows={3}
                className="field-input textarea-input"
                value={draftSummary}
                onChange={(e) => setDraftSummary(e.target.value)}
                placeholder="Professional career summary..."
              />
            ) : professionalProfile.summary?.value ? (
              <p className="summary-body-text">{professionalProfile.summary.value}</p>
            ) : (
              <p className="empty-field-text">No summary provided in candidate document.</p>
            )}
          </section>

          {/* Employment History Timeline */}
          <section className="profile-surface-card" aria-labelledby="section-experience-title">
            <div className="card-header-row">
              <div className="card-title-group">
                <Icon name="briefcase" size={17} className="card-icon" />
                <h3 id="section-experience-title" className="card-title" tabIndex={-1}>
                  Career Timeline ({professionalProfile.employment?.length || 0})
                </h3>
              </div>

              {isCorrectionMode && (
                <button
                  type="button"
                  onClick={() => {
                    setExpJobTitle("");
                    setExpOrg("");
                    setExpStart("");
                    setExpEnd("");
                    setExpBullets("");
                    setEditingExperienceIndex("new");
                  }}
                  className="btn btn-secondary btn-xs"
                >
                  <Icon name="plus" size={13} /> Add Position
                </button>
              )}
            </div>

            {professionalProfile.employment && professionalProfile.employment.length > 0 ? (
              (() => {
                const datedPositions: { emp: ExperienceRecord; index: number }[] = [];
                const undatedPositions: { emp: ExperienceRecord; index: number }[] = [];

                professionalProfile.employment.forEach((emp, index) => {
                  if (emp.startDate?.value || emp.endDate?.value) {
                    datedPositions.push({ emp, index });
                  } else {
                    undatedPositions.push({ emp, index });
                  }
                });

                return (
                  <>
                    {datedPositions.length > 0 && (
                      <div className="employment-timeline">
                        {datedPositions.map(({ emp, index }, i) => {
                          const allEvIds = [
                            ...(emp.jobTitle?.evidenceIds || []),
                            ...(emp.organization?.evidenceIds || []),
                            ...(emp.startDate?.evidenceIds || []),
                            ...(emp.endDate?.evidenceIds || []),
                            ...(emp.descriptions?.flatMap((d) => d.evidenceIds) || []),
                          ];

                          const isCurrent = !emp.endDate?.value && !!emp.startDate?.value;

                          return (
                            <div key={index} className="timeline-item-entry">
                              <div className="timeline-spine">
                                <div className={`timeline-dot ${isCurrent ? "current-dot" : ""}`} />
                                {i !== datedPositions.length - 1 && (
                                  <div className="timeline-connector" />
                                )}
                              </div>

                              <div className="timeline-details">
                                <div className="timeline-heading-row">
                                  <div>
                                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                                      <h4 className="timeline-job-title">
                                        {emp.jobTitle?.value || "Position Title"}
                                      </h4>
                                      {isCurrent && (
                                        <span className="badge badge-indigo">Current Position</span>
                                      )}
                                    </div>
                                    <span className="timeline-org-name">
                                      {emp.organization?.value || "Organization"}
                                    </span>
                                  </div>

                                  <div className="timeline-meta-right">
                                    <span className="timeline-date-badge">
                                      {renderDateInterval(emp.startDate, emp.endDate)}
                                    </span>

                                    {!isCorrectionMode && (
                                      <button
                                        type="button"
                                        className="btn-evidence-subtle"
                                        onClick={() =>
                                          openEvidenceInspector(
                                            `${emp.jobTitle?.value || "Position"} at ${emp.organization?.value || "Company"}`,
                                            `${emp.jobTitle?.value} (${emp.organization?.value})`,
                                            allEvIds
                                          )
                                        }
                                      >
                                        <Icon name="search" size={13} /> Evidence
                                      </button>
                                    )}
                                  </div>
                                </div>

                                {emp.descriptions && emp.descriptions.length > 0 && (
                                  <ul className="timeline-achievement-list">
                                    {emp.descriptions.map((desc, di) => (
                                      <li key={di}>{desc.value}</li>
                                    ))}
                                  </ul>
                                )}

                                {isCorrectionMode && (
                                  <div className="timeline-edit-actions">
                                    <button
                                      type="button"
                                      className="btn btn-secondary btn-xs"
                                      onClick={() => {
                                        setExpJobTitle(emp.jobTitle?.value || "");
                                        setExpOrg(emp.organization?.value || "");
                                        setExpStart(emp.startDate?.value || "");
                                        setExpEnd(emp.endDate?.value || "");
                                        setExpBullets(emp.descriptions?.map((d) => d.value).join("\n") || "");
                                        setEditingExperienceIndex(index);
                                      }}
                                    >
                                      <Icon name="edit" size={12} /> Edit Position
                                    </button>
                                    <button
                                      type="button"
                                      className="btn btn-secondary btn-xs btn-destructive"
                                      onClick={() => handleRemoveExperience(index)}
                                    >
                                      <Icon name="trash" size={12} /> Remove
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {undatedPositions.length > 0 && (
                      <div className="undated-experience-section" style={{ marginTop: datedPositions.length > 0 ? "20px" : "0" }}>
                        <h4 className="undated-section-heading">Additional documented experience</h4>
                        <div className="undated-positions-list">
                          {undatedPositions.map(({ emp, index }) => {
                            const allEvIds = [
                              ...(emp.jobTitle?.evidenceIds || []),
                              ...(emp.organization?.evidenceIds || []),
                              ...(emp.descriptions?.flatMap((d) => d.evidenceIds) || []),
                            ];

                            return (
                              <div key={index} className="undated-position-card">
                                <div className="undated-position-header">
                                  <div>
                                    <span className="undated-position-title">{emp.jobTitle?.value || "Position Title"}</span>
                                    <span className="undated-position-org">{emp.organization?.value || "Organization"}</span>
                                  </div>
                                  {!isCorrectionMode && (
                                    <button
                                      type="button"
                                      className="btn-evidence-subtle"
                                      onClick={() =>
                                        openEvidenceInspector(
                                          `${emp.jobTitle?.value || "Position"} at ${emp.organization?.value || "Company"}`,
                                          `${emp.jobTitle?.value} (${emp.organization?.value})`,
                                          allEvIds
                                        )
                                      }
                                    >
                                      <Icon name="search" size={13} /> Evidence
                                    </button>
                                  )}
                                </div>
                                {emp.descriptions && emp.descriptions.length > 0 && (
                                  <ul className="timeline-achievement-list" style={{ marginTop: "6px" }}>
                                    {emp.descriptions.map((desc, di) => (
                                      <li key={di}>{desc.value}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                );
              })()
            ) : (
              <p className="empty-field-text">No employment history detected.</p>
            )}
          </section>

          {/* Projects */}
          <section className="profile-surface-card" aria-labelledby="section-projects-title">
            <div className="card-header-row">
              <div className="card-title-group">
                <Icon name="layers" size={17} className="card-icon" />
                <h3 id="section-projects-title" className="card-title" tabIndex={-1}>
                  Projects ({professionalProfile.projects?.length || 0})
                </h3>
              </div>
            </div>

            {professionalProfile.projects && professionalProfile.projects.length > 0 ? (
              <div className="projects-grid">
                {professionalProfile.projects.map((proj, i) => {
                  const allProjEvIds = [
                    ...(proj.name?.evidenceIds || []),
                    ...(proj.description?.evidenceIds || []),
                    ...(proj.technologies?.flatMap((t) => t.evidenceIds) || []),
                  ];

                  return (
                    <div key={i} className="project-display-card">
                      <div className="project-header-row">
                        <h4 className="project-display-name">{proj.name?.value || "Project"}</h4>
                        {!isCorrectionMode && (
                          <button
                            type="button"
                            className="btn-evidence-subtle"
                            onClick={() =>
                              openEvidenceInspector(
                                proj.name?.value || "Project",
                                proj.description?.value,
                                allProjEvIds
                              )
                            }
                          >
                            <Icon name="search" size={13} /> Evidence
                          </button>
                        )}
                      </div>

                      {proj.description?.value && (
                        <p className="project-display-desc">{proj.description.value}</p>
                      )}

                      {proj.technologies && proj.technologies.length > 0 && (
                        <div className="project-tech-cloud">
                          {proj.technologies.map((t, ti) => (
                            <span key={ti} className="tech-chip">{t.value}</span>
                          ))}
                        </div>
                      )}

                      {proj.projectUrl?.value && (
                        <a
                          href={proj.projectUrl.value.startsWith("http") ? proj.projectUrl.value : `https://${proj.projectUrl.value}`}
                          target="_blank"
                          rel="noreferrer"
                          className="project-display-link"
                        >
                          <Icon name="external-link" size={13} />
                          <span>{proj.projectUrl.value}</span>
                        </a>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="empty-field-text">No technical projects extracted.</p>
            )}
          </section>
        </div>

        {/* SUPPORTING COLUMN (Skills, Education, Certifications, Languages, Contact) */}
        <div className="dashboard-side-col">
          {/* Skills */}
          <section className="profile-surface-card" aria-labelledby="section-skills-title">
            <div className="card-header-row">
              <div className="card-title-group">
                <Icon name="sparkles" size={17} className="card-icon" />
                <h3 id="section-skills-title" className="card-title" tabIndex={-1}>
                  Skills ({professionalProfile.skills?.length || 0})
                </h3>
              </div>

              {!isCorrectionMode && professionalProfile.skills?.length > 0 && (
                <button
                  type="button"
                  className="btn-evidence-subtle"
                  onClick={() => {
                    const allSkillEvs = professionalProfile.skills.flatMap((s) => s.evidenceIds);
                    openEvidenceInspector("Skills Inventory", `${professionalProfile.skills.length} skills recognized`, allSkillEvs);
                  }}
                >
                  <Icon name="search" size={13} /> Evidence
                </button>
              )}
            </div>

            {isCorrectionMode && (
              <div className="skill-input-row">
                <input
                  type="text"
                  className="field-input"
                  placeholder="Type new skill and press Enter..."
                  value={newSkillInput}
                  onChange={(e) => setNewSkillInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddSkill(newSkillInput);
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={() => handleAddSkill(newSkillInput)}
                  className="btn btn-secondary btn-sm"
                >
                  <Icon name="plus" size={13} /> Add
                </button>
              </div>
            )}

            {professionalProfile.skills && professionalProfile.skills.length > 0 ? (
              <div className="skills-chip-cloud">
                {professionalProfile.skills.map((sk, i) => (
                  <div key={i} className="skill-badge-chip">
                    <span>{sk.value}</span>
                    {isCorrectionMode ? (
                      <button
                        type="button"
                        className="chip-remove-btn"
                        onClick={() => handleRemoveSkill(sk.value || "")}
                        aria-label={`Remove ${sk.value}`}
                      >
                        <Icon name="x" size={12} />
                      </button>
                    ) : sk.evidenceIds && sk.evidenceIds.length > 0 ? (
                      <button
                        type="button"
                        className="chip-evidence-btn"
                        onClick={() => openEvidenceInspector(`Skill: ${sk.value}`, sk.value, sk.evidenceIds)}
                        title="View evidence"
                        aria-label={`View evidence for ${sk.value}`}
                      >
                        <Icon name="search" size={11} />
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-field-text">No technical skills detected.</p>
            )}
          </section>

          {/* Education */}
          <section className="profile-surface-card" aria-labelledby="section-education-title">
            <div className="card-header-row">
              <div className="card-title-group">
                <Icon name="academic-cap" size={17} className="card-icon" />
                <h3 id="section-education-title" className="card-title" tabIndex={-1}>
                  Education ({professionalProfile.education?.length || 0})
                </h3>
              </div>

              {isCorrectionMode && (
                <button
                  type="button"
                  onClick={() => {
                    setEduDegree("");
                    setEduField("");
                    setEduInst("");
                    setEduStart("");
                    setEduEnd("");
                    setEduGrade("");
                    setEditingEducationIndex("new");
                  }}
                  className="btn btn-secondary btn-xs"
                >
                  <Icon name="plus" size={13} /> Add Degree
                </button>
              )}
            </div>

            {professionalProfile.education && professionalProfile.education.length > 0 ? (
              <div className="education-stack">
                {professionalProfile.education.map((edu, i) => {
                  const allEduEvs = [
                    ...(edu.degree?.evidenceIds || []),
                    ...(edu.institution?.evidenceIds || []),
                    ...(edu.startDate?.evidenceIds || []),
                    ...(edu.endDate?.evidenceIds || []),
                  ];

                  return (
                    <div key={i} className="education-entry-card">
                      <div className="education-entry-header">
                        <div>
                          <h4 className="education-entry-degree">
                            {edu.degree?.value} {edu.fieldOfStudy?.value ? `in ${edu.fieldOfStudy.value}` : ""}
                          </h4>
                          <span className="education-entry-school">{edu.institution?.value}</span>
                        </div>

                        {!isCorrectionMode && (
                          <button
                            type="button"
                            className="btn-evidence-subtle"
                            onClick={() =>
                              openEvidenceInspector(
                                `${edu.degree?.value} at ${edu.institution?.value}`,
                                `${edu.degree?.value} (${edu.institution?.value})`,
                                allEduEvs
                              )
                            }
                          >
                            <Icon name="search" size={13} />
                          </button>
                        )}
                      </div>

                      <div className="education-entry-footer">
                        <span className="education-date-text">
                          {renderDateInterval(edu.startDate, edu.endDate)}
                        </span>
                        {edu.grade?.value && (
                          <span className="education-gpa-badge">GPA: {edu.grade.value}</span>
                        )}
                      </div>

                      {isCorrectionMode && (
                        <div className="timeline-edit-actions">
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs"
                            onClick={() => {
                              setEduDegree(edu.degree?.value || "");
                              setEduField(edu.fieldOfStudy?.value || "");
                              setEduInst(edu.institution?.value || "");
                              setEduStart(edu.startDate?.value || "");
                              setEduEnd(edu.endDate?.value || "");
                              setEduGrade(edu.grade?.value || "");
                              setEditingEducationIndex(i);
                            }}
                          >
                            <Icon name="edit" size={12} /> Edit
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-xs btn-destructive"
                            onClick={() => handleRemoveEducation(i)}
                          >
                            <Icon name="trash" size={12} /> Remove
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="empty-field-text">No education records extracted.</p>
            )}
          </section>

          {/* Certifications */}
          <section className="profile-surface-card" aria-labelledby="section-certifications-title">
            <div className="card-header-row">
              <div className="card-title-group">
                <Icon name="badge-check" size={17} className="card-icon" />
                <h3 id="section-certifications-title" className="card-title" tabIndex={-1}>
                  Certifications ({professionalProfile.certifications?.length || 0})
                </h3>
              </div>
            </div>

            {professionalProfile.certifications && professionalProfile.certifications.length > 0 ? (
              <div className="cert-stack">
                {professionalProfile.certifications.map((cert, i) => (
                  <div key={i} className="cert-entry-card">
                    <h4 className="cert-entry-name">{cert.name?.value}</h4>
                    {cert.issuer?.value && <span className="cert-entry-issuer">{cert.issuer.value}</span>}
                    {cert.issuedDate?.value && (
                      <span className="cert-entry-date">Issued: {cert.issuedDate.value}</span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-field-text">No certifications found.</p>
            )}
          </section>

          {/* Languages */}
          <section className="profile-surface-card" aria-labelledby="section-languages-title">
            <div className="card-header-row">
              <div className="card-title-group">
                <Icon name="globe" size={17} className="card-icon" />
                <h3 id="section-languages-title" className="card-title" tabIndex={-1}>
                  Languages ({professionalProfile.languages?.length || 0})
                </h3>
              </div>
            </div>

            {isCorrectionMode && (
              <div className="skill-input-row">
                <input
                  type="text"
                  className="field-input"
                  placeholder="Type language..."
                  value={newLangInput}
                  onChange={(e) => setNewLangInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddLanguage(newLangInput);
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={() => handleAddLanguage(newLangInput)}
                  className="btn btn-secondary btn-sm"
                >
                  <Icon name="plus" size={13} /> Add
                </button>
              </div>
            )}

            {professionalProfile.languages && professionalProfile.languages.length > 0 ? (
              <div className="languages-stack">
                {professionalProfile.languages.map((l, i) => {
                  const profText = formatLanguageProficiency(l.normalizedValue, l.value);
                  return (
                    <div key={i} className="language-entry-row">
                      <span className="language-name">{l.value}</span>
                      {profText && profText !== l.value && (
                        <span className="language-prof-badge">{profText}</span>
                      )}
                      {isCorrectionMode && (
                        <button
                          type="button"
                          className="chip-remove-btn"
                          onClick={() => handleRemoveLanguage(l.value || "")}
                        >
                          <Icon name="x" size={12} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="empty-field-text">No languages extracted.</p>
            )}
          </section>
        </div>
      </div>

      {/* Slide-over Evidence Drawer */}
      <EvidenceDrawer
        isOpen={evidenceDrawerState.isOpen}
        onClose={() => setEvidenceDrawerState((prev) => ({ ...prev, isOpen: false }))}
        fieldLabel={evidenceDrawerState.fieldLabel}
        fieldValue={evidenceDrawerState.fieldValue}
        evidenceIds={evidenceDrawerState.evidenceIds}
        evidenceMap={evidenceMap}
        rawBlocks={extraction?.blocks || []}
      />

      {/* Version History Drawer */}
      <VersionHistoryDrawer
        isOpen={isHistoryDrawerOpen}
        onClose={() => setIsHistoryDrawerOpen(false)}
        historyList={historyList}
        currentVersion={selectedVersion}
        onSelectVersion={handleSelectVersion}
      />

      {/* Review Items Drawer */}
      <ReviewDrawer
        isOpen={isReviewDrawerOpen}
        onClose={() => setIsReviewDrawerOpen(false)}
        warnings={currentProfile.warnings}
        onNavigateToSection={handleNavigateToSection}
        onOpenEvidence={(evId, label) => openEvidenceInspector(label, null, [evId])}
        onStartCorrection={startCorrectionMode}
      />

      {/* EDIT EXPERIENCE RECORD MODAL */}
      {editingExperienceIndex !== null && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-exp-title">
          <div className="modal-content">
            <h3 id="modal-exp-title" className="modal-title">
              {editingExperienceIndex === "new" ? "Add Position Record" : "Edit Position Record"}
            </h3>
            <div className="form-group" style={{ marginBottom: "12px" }}>
              <label className="field-label">Job Title <span className="req-star">*</span></label>
              <input
                type="text"
                className="field-input"
                value={expJobTitle}
                onChange={(e) => setExpJobTitle(e.target.value)}
                placeholder="e.g. Senior Software Engineer"
                required
              />
            </div>
            <div className="form-group" style={{ marginBottom: "12px" }}>
              <label className="field-label">Organization <span className="req-star">*</span></label>
              <input
                type="text"
                className="field-input"
                value={expOrg}
                onChange={(e) => setExpOrg(e.target.value)}
                placeholder="e.g. Acme Corp"
                required
              />
            </div>
            <div className="two-col-inputs" style={{ marginBottom: "12px" }}>
              <div className="form-group">
                <label className="field-label">Start Date</label>
                <input
                  type="text"
                  className="field-input"
                  value={expStart}
                  onChange={(e) => setExpStart(e.target.value)}
                  placeholder="e.g. January 2021"
                />
              </div>
              <div className="form-group">
                <label className="field-label">End Date</label>
                <input
                  type="text"
                  className="field-input"
                  value={expEnd}
                  onChange={(e) => setExpEnd(e.target.value)}
                  placeholder="e.g. Present or Dec 2023"
                />
              </div>
            </div>
            <div className="form-group" style={{ marginBottom: "16px" }}>
              <label className="field-label">Descriptions / Achievements (one bullet per line)</label>
              <textarea
                rows={4}
                className="field-input textarea-input"
                value={expBullets}
                onChange={(e) => setExpBullets(e.target.value)}
                placeholder="• Designed distributed backend services..."
              />
            </div>
            <div className="action-row modal-actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setEditingExperienceIndex(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={handleSaveExperienceModal}
              >
                Save Record
              </button>
            </div>
          </div>
        </div>
      )}

      {/* EDIT EDUCATION RECORD MODAL */}
      {editingEducationIndex !== null && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-edu-title">
          <div className="modal-content">
            <h3 id="modal-edu-title" className="modal-title">
              {editingEducationIndex === "new" ? "Add Education Record" : "Edit Education Record"}
            </h3>
            <div className="form-group" style={{ marginBottom: "12px" }}>
              <label className="field-label">Degree <span className="req-star">*</span></label>
              <input
                type="text"
                className="field-input"
                value={eduDegree}
                onChange={(e) => setEduDegree(e.target.value)}
                placeholder="e.g. Bachelor of Science"
                required
              />
            </div>
            <div className="form-group" style={{ marginBottom: "12px" }}>
              <label className="field-label">Field of Study</label>
              <input
                type="text"
                className="field-input"
                value={eduField}
                onChange={(e) => setEduField(e.target.value)}
                placeholder="e.g. Computer Science"
              />
            </div>
            <div className="form-group" style={{ marginBottom: "12px" }}>
              <label className="field-label">Institution <span className="req-star">*</span></label>
              <input
                type="text"
                className="field-input"
                value={eduInst}
                onChange={(e) => setEduInst(e.target.value)}
                placeholder="e.g. Stanford University"
                required
              />
            </div>
            <div className="two-col-inputs" style={{ marginBottom: "12px" }}>
              <div className="form-group">
                <label className="field-label">Start Date</label>
                <input
                  type="text"
                  className="field-input"
                  value={eduStart}
                  onChange={(e) => setEduStart(e.target.value)}
                  placeholder="e.g. 2016"
                />
              </div>
              <div className="form-group">
                <label className="field-label">End Date</label>
                <input
                  type="text"
                  className="field-input"
                  value={eduEnd}
                  onChange={(e) => setEduEnd(e.target.value)}
                  placeholder="e.g. 2020"
                />
              </div>
            </div>
            <div className="form-group" style={{ marginBottom: "16px" }}>
              <label className="field-label">Grade / GPA</label>
              <input
                type="text"
                className="field-input"
                value={eduGrade}
                onChange={(e) => setEduGrade(e.target.value)}
                placeholder="e.g. 3.8 GPA"
              />
            </div>
            <div className="action-row modal-actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setEditingEducationIndex(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={handleSaveEducationModal}
              >
                Save Record
              </button>
            </div>
          </div>
        </div>
      )}

      {isExportModalOpen && (
        <AtsExportModal
          isOpen={isExportModalOpen}
          candidateId={currentProfile.profileId}
          candidateName={currentProfile.identity?.fullName?.value || "Candidate"}
          onClose={() => setIsExportModalOpen(false)}
        />
      )}
    </div>
  );
}
