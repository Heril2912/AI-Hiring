import React, { useEffect, useState } from "react";
import { ExtractionResultData } from "./ExtractionReview";

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
  evidenceId?: string | null;
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

export type ProfileSummary = {
  profileId: string;
  profileVersion: number;
  schemaVersion: string;
  parserPipelineVersion: string;
  provenance: string;
  reviewRequired: boolean;
  createdAt: string;
  parentProfileId?: string | null;
  parentProfileVersion?: number | null;
  correctionSummary?: {
    correctionId: string;
    reasonCategory: string;
    reviewerNote?: string | null;
    operationCount: number;
  } | null;
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
  onReset: () => void;
}

export function CandidateProfileReview({ profile: initialProfile, onReset }: CandidateProfileReviewProps) {
  const [currentProfile, setCurrentProfile] = useState<CandidateProfileData>(initialProfile);
  const [historyList, setHistoryList] = useState<ProfileSummary[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number>(initialProfile.profileVersion);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);
  const [showHistoryModal, setShowHistoryModal] = useState<boolean>(false);

  // Correction Workflow State
  const [isCorrectionMode, setIsCorrectionMode] = useState<boolean>(false);
  const [reasonCategory, setReasonCategory] = useState<CorrectionReasonCategory>("INCORRECT_EXTRACTION");
  const [reviewerNote, setReviewerNote] = useState<string>("");
  const [operations, setOperations] = useState<CorrectionOperation[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [conflictError, setConflictError] = useState<boolean>(false);
  const [successToast, setSuccessToast] = useState<string | null>(null);

  // Expanded evidence span accordion
  const [expandedEvidenceKey, setExpandedEvidenceKey] = useState<string | null>(null);

  // Temp draft state during correction
  const [draftFullName, setDraftFullName] = useState(currentProfile.identity.fullName?.value || "");
  const [draftEmail, setDraftEmail] = useState(currentProfile.identity.emails?.[0]?.value || "");
  const [draftPhone, setDraftPhone] = useState(currentProfile.identity.phoneNumbers?.[0]?.value || "");
  const [draftLocation, setDraftLocation] = useState(currentProfile.identity.location?.value || "");
  const [draftLinkedin, setDraftLinkedin] = useState(currentProfile.identity.linkedin?.value || "");
  const [draftGithub, setDraftGithub] = useState(currentProfile.identity.github?.value || "");
  const [draftPortfolio, setDraftPortfolio] = useState(currentProfile.identity.portfolio?.value || "");
  const [draftHeadline, setDraftHeadline] = useState(currentProfile.professionalProfile.headline?.value || "");
  const [draftSummary, setDraftSummary] = useState(currentProfile.professionalProfile.summary?.value || "");
  const [newSkillInput, setNewSkillInput] = useState("");
  const [newLangInput, setNewLangInput] = useState("");

  // Record modal states
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

  // Fetch Version History on mount
  const fetchHistory = async () => {
    try {
      setIsLoadingHistory(true);
      const res = await fetch(`/api/v1/resumes/${currentProfile.artifactId}/profiles`);
      if (res.ok) {
        const data: ProfileSummary[] = await res.json();
        setHistoryList(data);
      }
    } catch (e) {
      console.error("Failed to fetch profile history", e);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [currentProfile.artifactId, currentProfile.profileVersion]);

  // Load a specific version from history
  const handleSelectVersion = async (version: number) => {
    if (version === currentProfile.profileVersion) return;
    try {
      setIsLoadingHistory(true);
      const res = await fetch(`/api/v1/resumes/${currentProfile.artifactId}/profile?version=${version}`);
      if (res.ok) {
        const data: CandidateProfileData = await res.json();
        setCurrentProfile(data);
        setSelectedVersion(version);
        setIsCorrectionMode(false);
        setErrorMessage(null);
        setConflictError(false);
      }
    } catch (e) {
      console.error("Failed to load profile version", e);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  // Reload latest version (e.g. after 409 conflict)
  const handleReloadLatest = async () => {
    try {
      setIsLoadingHistory(true);
      const res = await fetch(`/api/v1/resumes/${currentProfile.artifactId}/profile`);
      if (res.ok) {
        const data: CandidateProfileData = await res.json();
        setCurrentProfile(data);
        setSelectedVersion(data.profileVersion);
        setConflictError(false);
        setErrorMessage(null);
        setIsCorrectionMode(false);
        fetchHistory();
      }
    } catch (e) {
      console.error("Failed to reload latest profile", e);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const toggleEvidence = (key: string) => {
    setExpandedEvidenceKey((prev) => (prev === key ? null : key));
  };

  const isLatestVersion = historyList.length === 0 || selectedVersion === Math.max(...historyList.map((h) => h.profileVersion));

  // Initialize draft fields when entering correction mode
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
    setIsCorrectionMode(true);
  };

  // Build scalar changes into operations
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
      setErrorMessage(`Skill '${trimmed}' is already present in this profile.`);
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

  // Submit Correction Batch
  const handleSubmitCorrections = async (e: React.FormEvent) => {
    e.preventDefault();
    const scalarOps = computeScalarOperations();
    const totalOps = [...scalarOps, ...operations];

    if (totalOps.length === 0) {
      setErrorMessage("No corrections were made. Make changes to submit a correction batch.");
      return;
    }

    if (reasonCategory === "OTHER" && !reviewerNote.trim()) {
      setErrorMessage("A reviewer note is mandatory when selecting reason 'OTHER'.");
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

      const res = await fetch(`/api/v1/resumes/${currentProfile.artifactId}/profile-corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.status === 409) {
        const errJson = await res.json();
        if (errJson?.detail?.code === "PROFILE_VERSION_CONFLICT") {
          setConflictError(true);
          setErrorMessage(
            "Conflict: A newer version of this profile was created. Please reload to review the latest changes before correcting."
          );
        } else {
          setErrorMessage(errJson?.detail?.message || "Correction conflict encountered.");
        }
        return;
      }

      if (!res.ok) {
        const errJson = await res.json();
        setErrorMessage(errJson?.detail?.message || "Failed to submit profile correction.");
        return;
      }

      const responseData = await res.json();
      setCurrentProfile(responseData.profile);
      setSelectedVersion(responseData.newProfileVersion);
      setIsCorrectionMode(false);
      setOperations([]);
      setSuccessToast(`Created Profile Version ${responseData.newProfileVersion} successfully.`);
      fetchHistory();
      setTimeout(() => setSuccessToast(null), 5000);
    } catch (err) {
      console.error("Submission error", err);
      setErrorMessage("An unexpected network or service error occurred.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderEvidenceAccordion = (key: string, evidenceIds: string[]) => {
    if (!evidenceIds || evidenceIds.length === 0) return null;
    const isExpanded = expandedEvidenceKey === key;
    const matchingSpans = evidenceIds
      .map((id) => evidenceMap.get(id))
      .filter((s): s is EvidenceSpan => Boolean(s));

    if (matchingSpans.length === 0) return null;

    return (
      <div className="evidence-accordion-wrapper">
        <button
          type="button"
          className="btn-evidence-toggle"
          onClick={() => toggleEvidence(key)}
          aria-expanded={isExpanded}
        >
          🔍 {isExpanded ? "Hide Evidence" : `View Evidence (${matchingSpans.length})`}
        </button>
        {isExpanded && (
          <div className="evidence-panel">
            {matchingSpans.map((span) => (
              <div key={span.evidenceId} className="evidence-item-card">
                <div className="evidence-meta-row">
                  <span className="badge badge-index">
                    Block #{span.blockNumber !== null ? span.blockNumber : "N/A"}
                  </span>
                  {span.pageNumber !== null && (
                    <span className="badge badge-type">Page {span.pageNumber}</span>
                  )}
                  <span className="evidence-method">{span.extractionMethod}</span>
                  <span className="evidence-offsets mono">
                    chars [{span.characterStart}:{span.characterEnd}]
                  </span>
                </div>
                <div className="evidence-snippet">&ldquo;{span.originalText}&rdquo;</div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderDateInterval = (startDate: ExtractedField, endDate: ExtractedField) => {
    if (startDate?.value && endDate?.value) {
      return `${startDate.value} — ${endDate.value}`;
    }
    if (startDate?.value) {
      return `${startDate.value} — Present`;
    }
    if (endDate?.value) {
      return `Until ${endDate.value}`;
    }
    return "Date Not Specified";
  };

  const { identity, professionalProfile } = currentProfile;
  const isCorrectedProfile = currentProfile.provenance === "HUMAN_CORRECTED";

  return (
    <section className="profile-review-container" aria-labelledby="profile-review-title">
      {/* Header Bar */}
      <div className="extraction-review-header">
        <div>
          <div className="profile-version-tag-row">
            <h2 id="profile-review-title" className="extraction-review-title">
              Candidate Profile Review
            </h2>
            <span className={`badge ${isCorrectedProfile ? "badge-provenance-corrected" : "badge-provenance-parser"}`}>
              {isCorrectedProfile ? "HUMAN CORRECTED" : "PARSER EXTRACTED"}
            </span>
            <span className="badge badge-version">v{currentProfile.profileVersion}</span>
          </div>
          <p className="extraction-meta-subtitle">
            Pipeline: <span className="mono">{currentProfile.parserPipelineVersion}</span> &bull; Schema:{" "}
            <span className="mono">v{currentProfile.schemaVersion}</span>
            {currentProfile.parentProfileVersion && (
              <span> &bull; Derived from: <span className="mono">v{currentProfile.parentProfileVersion}</span></span>
            )}
          </p>
        </div>

        <div className="header-action-group">
          {historyList.length > 1 && (
            <div className="version-selector-container">
              <label htmlFor="version-select" className="sr-only">Select Version</label>
              <select
                id="version-select"
                className="version-select"
                value={selectedVersion}
                onChange={(e) => handleSelectVersion(Number(e.target.value))}
                disabled={isLoadingHistory || isCorrectionMode}
              >
                {historyList.map((h) => (
                  <option key={h.profileVersion} value={h.profileVersion}>
                    v{h.profileVersion} ({h.provenance === "HUMAN_CORRECTED" ? "Human Corrected" : "Parser"})
                  </option>
                ))}
              </select>
            </div>
          )}

          {!isCorrectionMode && isLatestVersion && (
            <button
              type="button"
              onClick={startCorrectionMode}
              className="btn btn-primary btn-sm btn-correct"
            >
              ✏️ Correct Profile
            </button>
          )}

          <button
            type="button"
            onClick={() => setShowHistoryModal(true)}
            className="btn btn-secondary btn-sm"
          >
            📋 Audit History ({historyList.length})
          </button>

          <button type="button" onClick={onReset} className="btn btn-secondary btn-sm">
            Upload Another
          </button>
        </div>
      </div>

      {/* Success Toast */}
      {successToast && (
        <div className="feedback-box success toast-banner" role="status">
          ✓ {successToast}
        </div>
      )}

      {/* Historical View Warning Banner */}
      {!isLatestVersion && (
        <div className="historical-view-banner" role="alert">
          <span>📜 Viewing historical profile version <strong>v{currentProfile.profileVersion}</strong> (Read-Only).</span>
          <button
            type="button"
            onClick={handleReloadLatest}
            className="btn btn-secondary btn-sm"
          >
            Switch to Latest (v{Math.max(...historyList.map((h) => h.profileVersion))})
          </button>
        </div>
      )}

      {/* Review Required Banner */}
      {currentProfile.reviewRequired && !isCorrectedProfile && (
        <div className="review-required-banner" role="alert">
          <span className="warning-icon" aria-hidden="true">⚠️</span>
          <div>
            <strong>Manual Review Required</strong>
            <p>
              Parser ambiguity or potential extraction anomalies were detected.
              Please inspect the highlighted fields and evidence references.
            </p>
          </div>
        </div>
      )}

      {/* Conflict / Error Banner */}
      {errorMessage && (
        <div className="feedback-box error" role="alert">
          <p className="feedback-text error">{errorMessage}</p>
          {conflictError && (
            <div className="action-row" style={{ marginTop: "8px" }}>
              <button
                type="button"
                onClick={handleReloadLatest}
                className="btn btn-primary btn-sm"
              >
                🔄 Reload Latest Version
              </button>
            </div>
          )}
        </div>
      )}

      {/* Quality Warnings Breakdown */}
      {currentProfile.warnings.length > 0 && !isCorrectionMode && (
        <div className="warning-breakdown-card">
          <h3 className="section-subtitle">Extraction Quality &amp; Parser Warnings ({currentProfile.warnings.length})</h3>
          <ul className="warning-list">
            {currentProfile.warnings.map((w, idx) => (
              <li key={idx} className="warning-item">
                <span className="badge badge-review-warn">{w.code}</span>
                <span className="warning-cat">[{w.category}]</span>
                {w.fieldName && <span> Field: <strong>{w.fieldName}</strong></span>}
                {w.message && <span> - {w.message}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* CORRECTION WORKFLOW FORM CONTAINER */}
      {isCorrectionMode && (
        <form onSubmit={handleSubmitCorrections} className="correction-mode-banner">
          <div className="correction-mode-header">
            <div>
              <h3 className="correction-mode-title">Editing Candidate Profile (Drafting v{currentProfile.profileVersion + 1})</h3>
              <p className="correction-mode-desc">
                Review and update fields below. Corrected profiles create an immutable new version with an audit trail. Original extractions and previous profile versions remain untouched.
              </p>
            </div>
            <div className="action-row">
              <button
                type="button"
                onClick={() => setIsCorrectionMode(false)}
                className="btn btn-secondary btn-sm"
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={isSubmitting}
                aria-busy={isSubmitting}
              >
                {isSubmitting ? "Saving Version..." : "Submit Correction Batch"}
              </button>
            </div>
          </div>

          {/* Audit Metadata Inputs */}
          <div className="audit-reason-row">
            <div className="form-group audit-field">
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
                <option value="OTHER">Other (Reviewer note mandatory)</option>
              </select>
            </div>

            <div className="form-group audit-field flex-grow">
              <label htmlFor="reviewer-note" className="field-label">
                Reviewer Note {reasonCategory === "OTHER" && <span className="req-star">*</span>}
              </label>
              <input
                id="reviewer-note"
                type="text"
                className="field-input"
                placeholder={reasonCategory === "OTHER" ? "Explain the reason for this correction..." : "Optional audit note for this change batch"}
                value={reviewerNote}
                onChange={(e) => setReviewerNote(e.target.value)}
                required={reasonCategory === "OTHER"}
              />
            </div>
          </div>

          {/* Pending Operations Count */}
          {(operations.length > 0 || computeScalarOperations().length > 0) && (
            <div className="pending-ops-bar">
              <span>
                <strong>{operations.length + computeScalarOperations().length}</strong> pending change(s) in draft.
              </span>
            </div>
          )}
        </form>
      )}

      {/* 1. Identity & Contact Information (Visibly Separated) */}
      <div className="profile-section-card identity-card">
        <div className="section-card-header">
          <span className="section-icon">👤</span>
          <div>
            <h3 className="section-title">Candidate Identity &amp; Contact Details</h3>
            <p className="section-caption">Isolated from matcher-facing features</p>
          </div>
        </div>

        <div className="identity-grid">
          {/* Full Name */}
          <div className="field-group">
            <label htmlFor="input-full-name" className="field-label">Full Name</label>
            {isCorrectionMode ? (
              <input
                id="input-full-name"
                type="text"
                className="field-input"
                value={draftFullName}
                onChange={(e) => setDraftFullName(e.target.value)}
                placeholder="Candidate full name"
              />
            ) : (
              <div className="field-value">{identity.fullName?.value || <span className="null-val">Not Detected</span>}</div>
            )}
            {identity.fullName?.confidence && !isCorrectionMode && (
              <span className="badge badge-confidence">{(identity.fullName.confidence * 100).toFixed(0)}% conf</span>
            )}
            {!isCorrectionMode && renderEvidenceAccordion("identity-fullname", identity.fullName?.evidenceIds || [])}
          </div>

          {/* Primary Email */}
          <div className="field-group">
            <label htmlFor="input-primary-email" className="field-label">Primary Email</label>
            {isCorrectionMode ? (
              <input
                id="input-primary-email"
                type="email"
                className="field-input"
                value={draftEmail}
                onChange={(e) => setDraftEmail(e.target.value)}
                placeholder="name@example.com"
              />
            ) : (
              <div className="field-value">
                {identity.emails && identity.emails.length > 0 ? (
                  identity.emails[0].value
                ) : (
                  <span className="null-val">Not Detected</span>
                )}
              </div>
            )}
            {!isCorrectionMode && identity.emails && identity.emails.length > 0 && renderEvidenceAccordion("identity-email-0", identity.emails[0].evidenceIds)}
          </div>

          {/* Primary Phone */}
          <div className="field-group">
            <label htmlFor="input-primary-phone" className="field-label">Phone Number</label>
            {isCorrectionMode ? (
              <input
                id="input-primary-phone"
                type="tel"
                className="field-input"
                value={draftPhone}
                onChange={(e) => setDraftPhone(e.target.value)}
                placeholder="+1 555-0199"
              />
            ) : (
              <div className="field-value">
                {identity.phoneNumbers && identity.phoneNumbers.length > 0 ? (
                  identity.phoneNumbers[0].value
                ) : (
                  <span className="null-val">Not Detected</span>
                )}
              </div>
            )}
            {!isCorrectionMode && identity.phoneNumbers && identity.phoneNumbers.length > 0 && renderEvidenceAccordion("identity-phone-0", identity.phoneNumbers[0].evidenceIds)}
          </div>

          {/* Location */}
          <div className="field-group">
            <label htmlFor="input-location" className="field-label">Location</label>
            {isCorrectionMode ? (
              <input
                id="input-location"
                type="text"
                className="field-input"
                value={draftLocation}
                onChange={(e) => setDraftLocation(e.target.value)}
                placeholder="City, State / Country"
              />
            ) : (
              <div className="field-value">{identity.location?.value || <span className="null-val">Not Detected</span>}</div>
            )}
            {!isCorrectionMode && renderEvidenceAccordion("identity-location", identity.location?.evidenceIds || [])}
          </div>

          {/* LinkedIn */}
          <div className="field-group">
            <label htmlFor="input-linkedin" className="field-label">LinkedIn</label>
            {isCorrectionMode ? (
              <input
                id="input-linkedin"
                type="text"
                className="field-input"
                value={draftLinkedin}
                onChange={(e) => setDraftLinkedin(e.target.value)}
                placeholder="https://linkedin.com/in/username"
              />
            ) : (
              <div className="field-value mono">
                {identity.linkedin?.value ? (
                  <a href={identity.linkedin.value.startsWith("http") ? identity.linkedin.value : `https://${identity.linkedin.value}`} target="_blank" rel="noreferrer" className="link-text">
                    {identity.linkedin.value}
                  </a>
                ) : (
                  <span className="null-val">Not Detected</span>
                )}
              </div>
            )}
            {!isCorrectionMode && renderEvidenceAccordion("identity-linkedin", identity.linkedin?.evidenceIds || [])}
          </div>

          {/* GitHub */}
          <div className="field-group">
            <label htmlFor="input-github" className="field-label">GitHub</label>
            {isCorrectionMode ? (
              <input
                id="input-github"
                type="text"
                className="field-input"
                value={draftGithub}
                onChange={(e) => setDraftGithub(e.target.value)}
                placeholder="https://github.com/username"
              />
            ) : (
              <div className="field-value mono">
                {identity.github?.value ? (
                  <a href={identity.github.value.startsWith("http") ? identity.github.value : `https://${identity.github.value}`} target="_blank" rel="noreferrer" className="link-text">
                    {identity.github.value}
                  </a>
                ) : (
                  <span className="null-val">Not Detected</span>
                )}
              </div>
            )}
            {!isCorrectionMode && renderEvidenceAccordion("identity-github", identity.github?.evidenceIds || [])}
          </div>

          {/* Portfolio */}
          <div className="field-group">
            <label htmlFor="input-portfolio" className="field-label">Portfolio / Web</label>
            {isCorrectionMode ? (
              <input
                id="input-portfolio"
                type="text"
                className="field-input"
                value={draftPortfolio}
                onChange={(e) => setDraftPortfolio(e.target.value)}
                placeholder="https://portfolio.me"
              />
            ) : (
              <div className="field-value mono">
                {identity.portfolio?.value ? (
                  <a href={identity.portfolio.value.startsWith("http") ? identity.portfolio.value : `https://${identity.portfolio.value}`} target="_blank" rel="noreferrer" className="link-text">
                    {identity.portfolio.value}
                  </a>
                ) : (
                  <span className="null-val">Not Detected</span>
                )}
              </div>
            )}
            {!isCorrectionMode && renderEvidenceAccordion("identity-portfolio", identity.portfolio?.evidenceIds || [])}
          </div>
        </div>
      </div>

      {/* 2. Professional Headline & Summary */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">💼</span>
          <h3 className="section-title">Headline &amp; Professional Summary</h3>
        </div>

        <div className="field-group" style={{ marginBottom: "16px" }}>
          <label htmlFor="input-headline" className="field-label">Headline</label>
          {isCorrectionMode ? (
            <input
              id="input-headline"
              type="text"
              className="field-input"
              value={draftHeadline}
              onChange={(e) => setDraftHeadline(e.target.value)}
              placeholder="e.g. Senior Backend Engineer"
            />
          ) : (
            <div className="field-value font-medium">{professionalProfile.headline?.value || <span className="null-val">Not Extracted</span>}</div>
          )}
          {!isCorrectionMode && renderEvidenceAccordion("prof-headline", professionalProfile.headline?.evidenceIds || [])}
        </div>

        <div className="field-group">
          <label htmlFor="input-summary" className="field-label">Summary</label>
          {isCorrectionMode ? (
            <textarea
              id="input-summary"
              rows={3}
              className="field-input textarea-input"
              value={draftSummary}
              onChange={(e) => setDraftSummary(e.target.value)}
              placeholder="Professional summary..."
            />
          ) : (
            <div className="field-value summary-text">{professionalProfile.summary?.value || <span className="null-val">Not Extracted</span>}</div>
          )}
          {!isCorrectionMode && renderEvidenceAccordion("prof-summary", professionalProfile.summary?.evidenceIds || [])}
        </div>
      </div>

      {/* 3. Skills */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">⚡</span>
          <h3 className="section-title">Skills ({professionalProfile.skills?.length || 0})</h3>
        </div>

        {isCorrectionMode && (
          <div className="skill-add-row">
            <input
              type="text"
              className="field-input"
              placeholder="Type new skill and press Enter or click Add"
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
              + Add Skill
            </button>
          </div>
        )}

        {professionalProfile.skills && professionalProfile.skills.length > 0 ? (
          <div className="skills-cloud">
            {professionalProfile.skills.map((sk, i) => (
              <div key={i} className="skill-chip">
                <span className="skill-label">{sk.value}</span>
                {isCorrectionMode && (
                  <button
                    type="button"
                    className="btn-chip-remove"
                    title={`Remove ${sk.value}`}
                    onClick={() => handleRemoveSkill(sk.value || "")}
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <span className="null-val">No skills extracted</span>
        )}
      </div>

      {/* 4. Employment Experience */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">🏢</span>
          <h3 className="section-title">Experience &amp; Work History ({professionalProfile.employment?.length || 0})</h3>
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
              className="btn btn-secondary btn-sm"
              style={{ marginLeft: "auto" }}
            >
              + Add Position
            </button>
          )}
        </div>

        {professionalProfile.employment && professionalProfile.employment.length > 0 ? (
          <div className="timeline-container">
            {professionalProfile.employment.map((emp, i) => {
              const allEmpEvIds = [
                ...(emp.jobTitle?.evidenceIds || []),
                ...(emp.organization?.evidenceIds || []),
                ...(emp.startDate?.evidenceIds || []),
                ...(emp.endDate?.evidenceIds || []),
                ...(emp.descriptions?.flatMap((d) => d.evidenceIds) || []),
              ];
              return (
                <div key={i} className="timeline-item">
                  <div className="timeline-marker" />
                  <div className="timeline-content">
                    <div className="timeline-header-row">
                      <h4 className="timeline-title">
                        {emp.jobTitle?.value || "Role Not Specified"} &bull; {emp.organization?.value || "Organization Not Specified"}
                      </h4>
                      <span className="timeline-date">{renderDateInterval(emp.startDate, emp.endDate)}</span>
                    </div>

                    {emp.descriptions && emp.descriptions.length > 0 && (
                      <ul className="timeline-bullets">
                        {emp.descriptions.map((desc, di) => (
                          <li key={di}>{desc.value}</li>
                        ))}
                      </ul>
                    )}

                    {isCorrectionMode && (
                      <div className="action-row" style={{ marginTop: "10px" }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setExpJobTitle(emp.jobTitle?.value || "");
                            setExpOrg(emp.organization?.value || "");
                            setExpStart(emp.startDate?.value || "");
                            setExpEnd(emp.endDate?.value || "");
                            setExpBullets(emp.descriptions?.map((d) => d.value).join("\n") || "");
                            setEditingExperienceIndex(i);
                          }}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm btn-danger"
                          onClick={() => handleRemoveExperience(i)}
                        >
                          Delete
                        </button>
                      </div>
                    )}

                    {!isCorrectionMode && renderEvidenceAccordion(`emp-${i}`, allEmpEvIds)}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <span className="null-val">No employment history extracted</span>
        )}
      </div>

      {/* 5. Education */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">🎓</span>
          <h3 className="section-title">Education ({professionalProfile.education?.length || 0})</h3>
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
              className="btn btn-secondary btn-sm"
              style={{ marginLeft: "auto" }}
            >
              + Add Degree
            </button>
          )}
        </div>

        {professionalProfile.education && professionalProfile.education.length > 0 ? (
          <div className="education-grid">
            {professionalProfile.education.map((edu, i) => {
              const allEduEvIds = [
                ...(edu.degree?.evidenceIds || []),
                ...(edu.fieldOfStudy ? edu.fieldOfStudy.evidenceIds : []),
                ...(edu.institution?.evidenceIds || []),
                ...(edu.startDate?.evidenceIds || []),
                ...(edu.endDate?.evidenceIds || []),
                ...(edu.grade?.evidenceIds || []),
              ];
              return (
                <div key={i} className="education-card">
                  <h4 className="education-degree">
                    {edu.degree?.value} {edu.fieldOfStudy?.value ? `in ${edu.fieldOfStudy.value}` : ""}
                  </h4>
                  <div className="education-inst">{edu.institution?.value}</div>
                  <div className="education-dates">{renderDateInterval(edu.startDate, edu.endDate)}</div>
                  {edu.grade?.value && <div className="education-grade">Grade/GPA: {edu.grade.value}</div>}

                  {isCorrectionMode && (
                    <div className="action-row" style={{ marginTop: "10px" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
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
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm btn-danger"
                        onClick={() => handleRemoveEducation(i)}
                      >
                        Delete
                      </button>
                    </div>
                  )}

                  {!isCorrectionMode && renderEvidenceAccordion(`edu-${i}`, allEduEvIds)}
                </div>
              );
            })}
          </div>
        ) : (
          <span className="null-val">No education records extracted</span>
        )}
      </div>

      {/* 6. Languages */}
      <div className="profile-section-card">
        <div className="section-card-header">
          <span className="section-icon">🌐</span>
          <h3 className="section-title">Languages ({professionalProfile.languages?.length || 0})</h3>
        </div>

        {isCorrectionMode && (
          <div className="skill-add-row">
            <input
              type="text"
              className="field-input"
              placeholder="Type language and press Enter"
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
              + Add Language
            </button>
          </div>
        )}

        {professionalProfile.languages && professionalProfile.languages.length > 0 ? (
          <ul className="lang-list">
            {professionalProfile.languages.map((l, i) => {
              const hasProficiency = l.normalizedValue && l.normalizedValue.toLowerCase() !== l.value?.toLowerCase();
              return (
                <li key={i} className="lang-item">
                  <span className="lang-name">{l.value}</span>
                  {hasProficiency && <span className="badge badge-index">{l.normalizedValue}</span>}
                  {isCorrectionMode && (
                    <button
                      type="button"
                      className="btn-chip-remove"
                      onClick={() => handleRemoveLanguage(l.value || "")}
                    >
                      ×
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <span className="null-val">No languages extracted</span>
        )}
      </div>

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
                placeholder="• Designed microservices..."
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
                placeholder="e.g. Bachelor of Technology"
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
                placeholder="e.g. 3.9 GPA"
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

      {/* AUDIT HISTORY MODAL */}
      {showHistoryModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-history-title">
          <div className="modal-content modal-history">
            <div className="modal-header-row">
              <h3 id="modal-history-title" className="modal-title">Profile Version &amp; Audit History</h3>
              <button
                type="button"
                className="btn-modal-close"
                onClick={() => setShowHistoryModal(false)}
              >
                ×
              </button>
            </div>

            <div className="history-timeline-list">
              {historyList.map((h) => (
                <div
                  key={h.profileVersion}
                  className={`history-card ${h.profileVersion === selectedVersion ? "active-version" : ""}`}
                >
                  <div className="history-card-header">
                    <span className="badge badge-version">Version {h.profileVersion}</span>
                    <span className={`badge ${h.provenance === "HUMAN_CORRECTED" ? "badge-provenance-corrected" : "badge-provenance-parser"}`}>
                      {h.provenance}
                    </span>
                    <span className="history-timestamp">{new Date(h.createdAt).toLocaleString()}</span>
                  </div>

                  {h.parentProfileVersion && (
                    <div className="history-meta">
                      Parent Version: <strong>v{h.parentProfileVersion}</strong>
                    </div>
                  )}

                  {h.correctionSummary && (
                    <div className="history-correction-box">
                      <div>Reason: <strong>{h.correctionSummary.reasonCategory}</strong></div>
                      {h.correctionSummary.reviewerNote && (
                        <div>Note: <em>&ldquo;{h.correctionSummary.reviewerNote}&rdquo;</em></div>
                      )}
                      <div>Operations: {h.correctionSummary.operationCount} change(s)</div>
                    </div>
                  )}

                  <div className="action-row" style={{ marginTop: "8px" }}>
                    {h.profileVersion !== selectedVersion ? (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          handleSelectVersion(h.profileVersion);
                          setShowHistoryModal(false);
                        }}
                      >
                        Inspect Version v{h.profileVersion}
                      </button>
                    ) : (
                      <span className="badge badge-index">Currently Viewing</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
