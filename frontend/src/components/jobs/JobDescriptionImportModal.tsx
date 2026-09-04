import React, { useState, useId } from "react";
import {
  JobImportAnalyzeResponse,
  JobSuggestionItem,
  RequirementItem,
  RequirementCategory,
  RequirementNecessity,
  analyzeJobDescriptionText,
  analyzeJobDescriptionFile,
  applyImportSuggestions,
  discardImportSession,
} from "../../api/jobs";
import { Icon } from "../Icon";

export interface CurrentFormValues {
  title: string;
  department: string;
  location: string;
  employmentType: string;
  workplaceType: string;
  openingsCount: string;
  summary: string;
  responsibilities: string;
  requirements: RequirementItem[];
}

export interface AppliedSuggestionsPayload {
  title?: string;
  department?: string;
  location?: string;
  employmentType?: string;
  workplaceType?: string;
  openingsCount?: string;
  summary?: string;
  responsibilities?: string[];
  newRequirements: RequirementItem[];
}

interface JobDescriptionImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  jobId?: string | null;
  currentRevision?: number;
  currentFormValues: CurrentFormValues;
  onApplySuggestions: (applied: AppliedSuggestionsPayload) => void;
}

type TabMode = "PASTE" | "UPLOAD";

export function JobDescriptionImportModal({
  isOpen,
  onClose,
  jobId,
  currentRevision,
  currentFormValues,
  onApplySuggestions,
}: JobDescriptionImportModalProps) {
  const modalTitleId = useId();
  // Mode selection & inputs
  const [tabMode, setTabMode] = useState<TabMode>("PASTE");
  const [pastedText, setPastedText] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Analysis State
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<JobImportAnalyzeResponse | null>(null);

  // Selected Suggestions Set (Empty by default: nothing selected by default)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Edited Values Map (suggestionId -> modified value)
  const [editedValues, setEditedValues] = useState<Record<string, any>>({});

  // Preview confirmation step
  const [showConfirmationPreview, setShowConfirmationPreview] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  if (!isOpen) return null;

  // Handle Analysis Trigger
  const handleAnalyze = async () => {
    setAnalysisError(null);
    if (tabMode === "PASTE") {
      if (!pastedText.trim()) {
        setAnalysisError("Please paste job description text to analyze.");
        return;
      }
      try {
        setIsAnalyzing(true);
        const res = await analyzeJobDescriptionText(pastedText.trim(), jobId, currentRevision);
        setAnalysisResult(res);
        setSelectedIds(new Set()); // Explicit rule: nothing selected by default
        setEditedValues({});
        setShowConfirmationPreview(false);
      } catch (err: any) {
        setAnalysisError(err?.message || "Failed to analyze job description text.");
      } finally {
        setIsAnalyzing(false);
      }
    } else {
      if (!selectedFile) {
        setAnalysisError("Please select a valid PDF or DOCX file to upload.");
        return;
      }
      try {
        setIsAnalyzing(true);
        const res = await analyzeJobDescriptionFile(selectedFile, jobId, currentRevision);
        setAnalysisResult(res);
        setSelectedIds(new Set()); // Explicit rule: nothing selected by default
        setEditedValues({});
        setShowConfirmationPreview(false);
      } catch (err: any) {
        setAnalysisError(err?.message || "Failed to analyze uploaded document.");
      } finally {
        setIsAnalyzing(false);
      }
    }
  };

  const handleToggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  };

  const handleSelectAll = () => {
    if (!analysisResult) return;
    const allIds = new Set(analysisResult.suggestions.map((s) => s.suggestionId));
    setSelectedIds(allIds);
  };

  const handleDeselectAll = () => {
    setSelectedIds(new Set());
  };

  const handleUpdateEditedValue = (id: string, newVal: any) => {
    setEditedValues((prev) => ({
      ...prev,
      [id]: newVal,
    }));
  };

  const handleResetSession = async () => {
    if (analysisResult?.sessionId) {
      try {
        await discardImportSession(analysisResult.sessionId);
      } catch {
        // ignore
      }
    }
    setAnalysisResult(null);
    setSelectedIds(new Set());
    setEditedValues({});
    setShowConfirmationPreview(false);
    setAnalysisError(null);
  };

  const handleCloseModal = () => {
    if (analysisResult?.sessionId && analysisResult.status === "PENDING_REVIEW") {
      try {
        const res = discardImportSession(analysisResult.sessionId);
        if (res && typeof res.catch === "function") {
          res.catch(() => {});
        }
      } catch {
        // ignore
      }
    }
    onClose();
  };

  // Group Suggestions
  const groupedSuggestions = {
    jobDetails: [] as JobSuggestionItem[],
    summary: [] as JobSuggestionItem[],
    responsibilities: [] as JobSuggestionItem[],
    requirements: [] as JobSuggestionItem[],
  };

  if (analysisResult) {
    for (const sug of analysisResult.suggestions) {
      if (
        sug.targetField === "TITLE" ||
        sug.targetField === "DEPARTMENT" ||
        sug.targetField === "LOCATION" ||
        sug.targetField === "EMPLOYMENT_TYPE" ||
        sug.targetField === "WORKPLACE_TYPE" ||
        sug.targetField === "OPENINGS_COUNT"
      ) {
        groupedSuggestions.jobDetails.push(sug);
      } else if (sug.targetField === "SUMMARY") {
        groupedSuggestions.summary.push(sug);
      } else if (sug.targetField === "RESPONSIBILITY") {
        groupedSuggestions.responsibilities.push(sug);
      } else if (sug.targetField === "REQUIREMENT") {
        groupedSuggestions.requirements.push(sug);
      }
    }
  }

  // Check Current Form Value for Conflict Detection
  const getCurrentValueForField = (targetField: string): string => {
    switch (targetField) {
      case "TITLE":
        return currentFormValues.title;
      case "DEPARTMENT":
        return currentFormValues.department;
      case "LOCATION":
        return currentFormValues.location;
      case "EMPLOYMENT_TYPE":
        return currentFormValues.employmentType;
      case "WORKPLACE_TYPE":
        return currentFormValues.workplaceType;
      case "OPENINGS_COUNT":
        return currentFormValues.openingsCount;
      case "SUMMARY":
        return currentFormValues.summary;
      default:
        return "";
    }
  };

  // Check if requirement is duplicate with existing form
  const isRequirementDuplicate = (label: string): boolean => {
    if (!label) return false;
    const norm = label.trim().toLowerCase();
    return currentFormValues.requirements.some(
      (r) => r.label.trim().toLowerCase() === norm
    );
  };

  // Compute what will be applied for confirmation preview
  const buildAppliedPayload = (): AppliedSuggestionsPayload => {
    if (!analysisResult) return { newRequirements: [] };

    const payload: AppliedSuggestionsPayload = {
      newRequirements: [],
    };
    const respList: string[] = [];

    for (const sug of analysisResult.suggestions) {
      if (!selectedIds.has(sug.suggestionId)) continue;
      const effectiveVal = editedValues[sug.suggestionId] !== undefined
        ? editedValues[sug.suggestionId]
        : sug.proposedValue;

      switch (sug.targetField) {
        case "TITLE":
          payload.title = String(effectiveVal);
          break;
        case "DEPARTMENT":
          payload.department = String(effectiveVal);
          break;
        case "LOCATION":
          payload.location = String(effectiveVal);
          break;
        case "EMPLOYMENT_TYPE":
          payload.employmentType = String(effectiveVal);
          break;
        case "WORKPLACE_TYPE":
          payload.workplaceType = String(effectiveVal);
          break;
        case "OPENINGS_COUNT":
          payload.openingsCount = String(effectiveVal);
          break;
        case "SUMMARY":
          payload.summary = String(effectiveVal);
          break;
        case "RESPONSIBILITY":
          respList.push(String(effectiveVal));
          break;
        case "REQUIREMENT": {
          const reqObj = typeof effectiveVal === "object" ? effectiveVal : {};
          const necessity: RequirementNecessity = reqObj.necessity === "PREFERRED" ? "PREFERRED" : "MUST_HAVE";
          const category: RequirementCategory = reqObj.category || "SKILL";
          const label: string = reqObj.label || sug.sourceExcerpt;
          const isOnet = Boolean(reqObj.taxonomySkillConceptId);

          const newReq: RequirementItem = {
            displayOrder: currentFormValues.requirements.length + payload.newRequirements.length,
            category,
            label,
            taxonomySkillConceptId: reqObj.taxonomySkillConceptId || null,
            necessity,
            priority: "MEDIUM",
            acceptedEvidenceTypes: reqObj.acceptedEvidenceTypes || ["EMPLOYMENT", "PROJECT"],
            acceptedEquivalents: [],
            origin: isOnet ? "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED" : "RECRUITER_ENTERED",
            minExperienceMonths: reqObj.minExperienceMonths ?? null,
          };
          payload.newRequirements.push(newReq);
          break;
        }
      }
    }

    if (respList.length > 0) {
      payload.responsibilities = respList;
    }

    return payload;
  };

  const handleConfirmApply = async () => {
    if (!analysisResult) return;
    setApplyError(null);
    try {
      setIsApplying(true);
      const appliedPayload = buildAppliedPayload();

      // Call backend apply endpoint to mark session as APPLIED
      await applyImportSuggestions(analysisResult.sessionId, {
        expectedRevision: currentRevision,
        acceptedSuggestionIds: Array.from(selectedIds),
        editedSuggestions: editedValues,
      });

      // Pass applied updates to parent form state
      onApplySuggestions(appliedPayload);
      onClose();
    } catch (err: any) {
      if (err?.code === "REVISION_CONFLICT" || err?.status === 409) {
        setApplyError("Requisition revision changed since analysis. Local suggestions cannot be applied to older revision.");
      } else {
        setApplyError(err?.message || "Failed to apply suggestions.");
      }
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <div
      className="import-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby={modalTitleId}
    >
      <div className="import-modal-container">
        {/* Header */}
        <div className="import-modal-header">
          <div className="import-modal-header-left">
            <div className="import-modal-icon-wrap">
              <Icon name="file-text" size={20} />
            </div>
            <div>
              <h2 id={modalTitleId} className="import-modal-title">Import from job description</h2>
              <p className="import-modal-subtitle">
                Deterministic extraction suggestions for recruiter review. Suggestions are strictly advisory.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn-icon-subtle"
            onClick={handleCloseModal}
            aria-label="Close import dialog"
          >
            <Icon name="x" size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="import-modal-body">
          {/* Step 1: Input & Analysis */}
          {!analysisResult && (
            <div className="import-input-step">
              <div className="import-tabs-bar" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={tabMode === "PASTE"}
                  className={`import-tab-btn ${tabMode === "PASTE" ? "active" : ""}`}
                  onClick={() => setTabMode("PASTE")}
                >
                  <Icon name="file-text" size={15} />
                  <span>Paste plain text (Default)</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={tabMode === "UPLOAD"}
                  className={`import-tab-btn ${tabMode === "UPLOAD" ? "active" : ""}`}
                  onClick={() => setTabMode("UPLOAD")}
                >
                  <Icon name="upload" size={15} />
                  <span>Upload PDF or DOCX</span>
                </button>
              </div>

              {tabMode === "PASTE" ? (
                <div className="import-tab-content">
                  <label htmlFor="jd-pasted-text" className="form-label">
                    Job Description Text
                  </label>
                  <p className="field-hint">
                    Paste raw text including job title, role summary, responsibilities, and requirements.
                  </p>
                  <textarea
                    id="jd-pasted-text"
                    className="form-input form-textarea jd-textarea"
                    rows={12}
                    placeholder="Paste job description text here (e.g. Senior Backend Developer&#10;&#10;About the role...&#10;&#10;Responsibilities...&#10;&#10;Required qualifications...)"
                    value={pastedText}
                    onChange={(e) => setPastedText(e.target.value)}
                    maxLength={50000}
                  />
                  <div className="textarea-char-count">
                    {pastedText.length.toLocaleString()} / 50,000 characters
                  </div>
                </div>
              ) : (
                <div className="import-tab-content">
                  <label htmlFor="jd-file-upload" className="form-label">
                    Upload Job Description Document (.pdf, .docx)
                  </label>
                  <p className="field-hint">
                    Secure text extraction directly from machine-readable PDF or DOCX. Maximum size: 10 MB.
                  </p>
                  <div className="file-drop-zone">
                    <input
                      id="jd-file-upload"
                      type="file"
                      accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        setSelectedFile(file || null);
                      }}
                      className="file-input-hidden"
                    />
                    <label htmlFor="jd-file-upload" className="file-drop-label">
                      <Icon name="upload" size={28} className="upload-icon" />
                      {selectedFile ? (
                        <div className="file-selected-info">
                          <span className="file-name">{selectedFile.name}</span>
                          <span className="file-size">
                            ({(selectedFile.size / 1024).toFixed(1)} KB)
                          </span>
                        </div>
                      ) : (
                        <div>
                          <span className="drop-title">Click to select PDF or DOCX file</span>
                          <span className="drop-hint">Direct text extraction only &bull; No OCR</span>
                        </div>
                      )}
                    </label>
                  </div>
                  <div className="security-notice-box">
                    <Icon name="info" size={15} />
                    <span>
                      Scanned or image-only documents cannot be processed with OCR. If your document has no embedded text, please copy and paste the plain text instead.
                    </span>
                  </div>
                </div>
              )}

              {analysisError && (
                <div className="feedback-box error" role="alert">
                  <Icon name="alert-triangle" size={16} />
                  <p className="feedback-text error">{analysisError}</p>
                </div>
              )}

              <div className="import-action-footer">
                <button
                  type="button"
                  className="btn btn-secondary btn-md"
                  onClick={handleCloseModal}
                  disabled={isAnalyzing}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-md"
                  onClick={handleAnalyze}
                  disabled={isAnalyzing}
                >
                  {isAnalyzing ? (
                    <>
                      <div className="btn-spinner" />
                      <span>Analysing job description...</span>
                    </>
                  ) : (
                    <>
                      <Icon name="sparkles" size={15} />
                      <span>Analyse job description</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Suggestions Review Screen */}
          {analysisResult && !showConfirmationPreview && (
            <div className="import-review-step">
              {/* Session Meta Bar */}
              <div className="session-meta-bar">
                <div className="meta-left">
                  <span className="badge badge-meta">Source: {analysisResult.sourceType}</span>
                  {analysisResult.taxonomyVersion && (
                    <span className="badge badge-meta">O*NET {analysisResult.taxonomyVersion}</span>
                  )}
                  <span className="badge badge-meta">
                    {analysisResult.suggestions.length} suggestions extracted
                  </span>
                </div>
                <div className="meta-right">
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={handleResetSession}
                  >
                    <Icon name="refresh" size={12} />
                    <span>Re-analyse text</span>
                  </button>
                </div>
              </div>

              {/* Safeguards & Protected Info Warnings */}
              {analysisResult.warnings && analysisResult.warnings.length > 0 && (
                <div className="protected-warning-banner" role="alert">
                  <div className="warning-banner-header">
                    <Icon name="alert-triangle" size={18} className="warn-icon" />
                    <strong>Sensitive / Protected Information Detected</strong>
                  </div>
                  <ul className="warning-list">
                    {analysisResult.warnings.map((w, i) => (
                      <li key={i} className="warning-item">
                        <span>{w.message}</span>
                        {w.sourceExcerpt && (
                          <div className="warning-excerpt">&ldquo;{w.sourceExcerpt}&rdquo;</div>
                        )}
                      </li>
                    ))}
                  </ul>
                  <p className="warning-footer-note">
                    Safeguard active: Potentially discriminatory or protected characteristics are flagged for recruiter awareness and are never automatically transformed into structured job requirements.
                  </p>
                </div>
              )}

              {/* Selection Controls */}
              <div className="selection-quick-bar">
                <div className="selection-count">
                  <strong>{selectedIds.size}</strong> of {analysisResult.suggestions.length} suggestions selected
                </div>
                <div className="selection-actions">
                  <button
                    type="button"
                    className="btn-link-action"
                    onClick={handleSelectAll}
                  >
                    Select All
                  </button>
                  <span className="divider-dot">&bull;</span>
                  <button
                    type="button"
                    className="btn-link-action"
                    onClick={handleDeselectAll}
                  >
                    Deselect All
                  </button>
                </div>
              </div>

              {/* Suggestions Groups */}
              <div className="suggestions-groups-container">
                {/* 1. Job Details Group */}
                {groupedSuggestions.jobDetails.length > 0 && (
                  <div className="suggestion-group-card">
                    <div className="group-card-header">
                      <Icon name="building" size={16} />
                      <h4>Job Details</h4>
                    </div>
                    <div className="group-items-stack">
                      {groupedSuggestions.jobDetails.map((sug) => {
                        const isSelected = selectedIds.has(sug.suggestionId);
                        const currentVal = getCurrentValueForField(sug.targetField);
                        const hasConflict = Boolean(
                          currentVal &&
                          String(currentVal).trim().toLowerCase() !== String(sug.proposedValue).trim().toLowerCase()
                        );
                        const effectiveVal = editedValues[sug.suggestionId] !== undefined
                          ? editedValues[sug.suggestionId]
                          : sug.proposedValue;

                        return (
                          <div
                            key={sug.suggestionId}
                            className={`suggestion-item-row ${isSelected ? "selected" : ""}`}
                          >
                            <div className="item-checkbox-wrap">
                              <input
                                type="checkbox"
                                id={`sug-${sug.suggestionId}`}
                                checked={isSelected}
                                onChange={() => handleToggleSelect(sug.suggestionId)}
                              />
                            </div>
                            <div className="item-content-wrap">
                              <div className="item-field-badge">
                                {sug.targetField.replace(/_/g, " ")}
                              </div>

                              {hasConflict && (
                                <div className="conflict-box">
                                  <div className="conflict-label">
                                    <Icon name="alert-triangle" size={13} />
                                    <span>Conflict with current form:</span>
                                  </div>
                                  <div className="conflict-diff">
                                    <div className="conflict-current">
                                      <span className="diff-tag">Current:</span> &ldquo;{currentVal}&rdquo;
                                    </div>
                                    <div className="conflict-suggested">
                                      <span className="diff-tag">Suggested:</span> &ldquo;{String(sug.proposedValue)}&rdquo;
                                    </div>
                                  </div>
                                </div>
                              )}

                              <div className="item-value-edit">
                                <label htmlFor={`edit-val-${sug.suggestionId}`} className="sr-only">
                                  {sug.targetField}
                                </label>
                                <input
                                  id={`edit-val-${sug.suggestionId}`}
                                  type="text"
                                  className="form-input form-input-sm"
                                  value={effectiveVal}
                                  onChange={(e) =>
                                    handleUpdateEditedValue(sug.suggestionId, e.target.value)
                                  }
                                />
                              </div>

                              <div className="item-excerpt">
                                <span className="excerpt-label">Source evidence:</span> &ldquo;{sug.sourceExcerpt}&rdquo;
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 2. About the Role (Summary) Group */}
                {groupedSuggestions.summary.length > 0 && (
                  <div className="suggestion-group-card">
                    <div className="group-card-header">
                      <Icon name="file-text" size={16} />
                      <h4>About the role</h4>
                    </div>
                    <div className="group-items-stack">
                      {groupedSuggestions.summary.map((sug) => {
                        const isSelected = selectedIds.has(sug.suggestionId);
                        const currentVal = getCurrentValueForField("SUMMARY");
                        const hasConflict = Boolean(
                          currentVal &&
                          currentVal.trim().toLowerCase() !== String(sug.proposedValue).trim().toLowerCase()
                        );
                        const effectiveVal = editedValues[sug.suggestionId] !== undefined
                          ? editedValues[sug.suggestionId]
                          : sug.proposedValue;

                        return (
                          <div
                            key={sug.suggestionId}
                            className={`suggestion-item-row ${isSelected ? "selected" : ""}`}
                          >
                            <div className="item-checkbox-wrap">
                              <input
                                type="checkbox"
                                id={`sug-${sug.suggestionId}`}
                                checked={isSelected}
                                onChange={() => handleToggleSelect(sug.suggestionId)}
                              />
                            </div>
                            <div className="item-content-wrap">
                              {hasConflict && (
                                <div className="conflict-box">
                                  <div className="conflict-label">
                                    <Icon name="alert-triangle" size={13} />
                                    <span>Conflict with current form summary</span>
                                  </div>
                                </div>
                              )}

                              <div className="item-value-edit">
                                <textarea
                                  className="form-input form-textarea"
                                  rows={3}
                                  value={effectiveVal}
                                  onChange={(e) =>
                                    handleUpdateEditedValue(sug.suggestionId, e.target.value)
                                  }
                                />
                              </div>

                              <div className="item-excerpt">
                                <span className="excerpt-label">Source evidence:</span> &ldquo;{sug.sourceExcerpt}&rdquo;
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 3. Responsibilities Group */}
                {groupedSuggestions.responsibilities.length > 0 && (
                  <div className="suggestion-group-card">
                    <div className="group-card-header">
                      <Icon name="check" size={16} />
                      <h4>Responsibilities ({groupedSuggestions.responsibilities.length} items)</h4>
                    </div>
                    <div className="group-items-stack">
                      {groupedSuggestions.responsibilities.map((sug) => {
                        const isSelected = selectedIds.has(sug.suggestionId);
                        const effectiveVal = editedValues[sug.suggestionId] !== undefined
                          ? editedValues[sug.suggestionId]
                          : sug.proposedValue;

                        return (
                          <div
                            key={sug.suggestionId}
                            className={`suggestion-item-row ${isSelected ? "selected" : ""}`}
                          >
                            <div className="item-checkbox-wrap">
                              <input
                                type="checkbox"
                                id={`sug-${sug.suggestionId}`}
                                checked={isSelected}
                                onChange={() => handleToggleSelect(sug.suggestionId)}
                              />
                            </div>
                            <div className="item-content-wrap">
                              <div className="item-value-edit">
                                <input
                                  type="text"
                                  className="form-input form-input-sm"
                                  value={effectiveVal}
                                  onChange={(e) =>
                                    handleUpdateEditedValue(sug.suggestionId, e.target.value)
                                  }
                                />
                              </div>
                              <div className="item-excerpt">
                                <span className="excerpt-label">Source evidence:</span> &ldquo;{sug.sourceExcerpt}&rdquo;
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 4. Requirements Group */}
                {groupedSuggestions.requirements.length > 0 && (
                  <div className="suggestion-group-card">
                    <div className="group-card-header">
                      <Icon name="badge-check" size={16} />
                      <h4>Structured Requirements ({groupedSuggestions.requirements.length} items)</h4>
                    </div>
                    <div className="group-items-stack">
                      {groupedSuggestions.requirements.map((sug) => {
                        const isSelected = selectedIds.has(sug.suggestionId);
                        const currentReq = editedValues[sug.suggestionId] || sug.proposedValue || {};
                        const isDuplicate = isRequirementDuplicate(currentReq.label);
                        const isOnet = Boolean(currentReq.taxonomySkillConceptId);
                        const isUndecided = Boolean(currentReq.isUndecidedNecessity);

                        return (
                          <div
                            key={sug.suggestionId}
                            className={`suggestion-item-row req-suggestion-row ${isSelected ? "selected" : ""}`}
                          >
                            <div className="item-checkbox-wrap">
                              <input
                                type="checkbox"
                                id={`sug-${sug.suggestionId}`}
                                checked={isSelected}
                                onChange={() => handleToggleSelect(sug.suggestionId)}
                              />
                            </div>
                            <div className="item-content-wrap">
                              <div className="req-meta-line">
                                <span className={`badge ${isOnet ? "badge-onet" : "badge-custom"}`}>
                                  {isOnet ? "O*NET 31.0 Skill" : "Custom Requirement"}
                                </span>
                                {isDuplicate && (
                                  <span className="badge badge-warn">Duplicate Label</span>
                                )}
                                {isUndecided && (
                                  <span className="badge badge-undecided">
                                    Undecided (Recruiter Choice)
                                  </span>
                                )}
                              </div>

                              <div className="req-edit-grid">
                                <div className="form-group flex-2">
                                  <label className="form-label-xs">Requirement Name</label>
                                  <input
                                    type="text"
                                    className="form-input form-input-sm"
                                    value={currentReq.label || ""}
                                    onChange={(e) =>
                                      handleUpdateEditedValue(sug.suggestionId, {
                                        ...currentReq,
                                        label: e.target.value,
                                      })
                                    }
                                  />
                                </div>

                                <div className="form-group flex-1">
                                  <label className="form-label-xs">Category</label>
                                  <select
                                    className="form-input form-input-sm"
                                    value={currentReq.category || "SKILL"}
                                    onChange={(e) =>
                                      handleUpdateEditedValue(sug.suggestionId, {
                                        ...currentReq,
                                        category: e.target.value,
                                      })
                                    }
                                  >
                                    <option value="SKILL">Skill</option>
                                    <option value="EXPERIENCE">Experience</option>
                                    <option value="EDUCATION">Education</option>
                                    <option value="CERTIFICATION">Certification</option>
                                    <option value="OTHER">Other</option>
                                  </select>
                                </div>

                                <div className="form-group flex-1">
                                  <label className="form-label-xs">Necessity</label>
                                  <select
                                    className="form-input form-input-sm"
                                    value={currentReq.necessity || "MUST_HAVE"}
                                    onChange={(e) =>
                                      handleUpdateEditedValue(sug.suggestionId, {
                                        ...currentReq,
                                        necessity: e.target.value,
                                        isUndecidedNecessity: false,
                                      })
                                    }
                                  >
                                    <option value="MUST_HAVE">Required (Must-Have)</option>
                                    <option value="PREFERRED">Preferred (Nice-to-Have)</option>
                                  </select>
                                </div>
                              </div>

                              {currentReq.category === "EXPERIENCE" && (
                                <div className="req-exp-row">
                                  <label className="form-label-xs">Min Experience (Months):</label>
                                  <input
                                    type="number"
                                    min={0}
                                    className="form-input form-input-sm form-input-num"
                                    value={currentReq.minExperienceMonths ?? ""}
                                    onChange={(e) =>
                                      handleUpdateEditedValue(sug.suggestionId, {
                                        ...currentReq,
                                        minExperienceMonths: e.target.value ? parseInt(e.target.value, 10) : null,
                                      })
                                    }
                                  />
                                </div>
                              )}

                              <div className="item-excerpt">
                                <span className="excerpt-label">Source evidence:</span> &ldquo;{sug.sourceExcerpt}&rdquo;
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Review Action Footer */}
              <div className="import-action-footer">
                <button
                  type="button"
                  className="btn btn-secondary btn-md"
                  onClick={handleCloseModal}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-md"
                  onClick={() => setShowConfirmationPreview(true)}
                  disabled={selectedIds.size === 0}
                >
                  <Icon name="check" size={15} />
                  <span>Apply selected suggestions ({selectedIds.size})</span>
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Confirmation Preview */}
          {analysisResult && showConfirmationPreview && (
            <div className="import-preview-step">
              <div className="preview-header">
                <h3>Confirm Applying Suggestions to Form</h3>
                <p className="preview-desc">
                  Review the fields that will be updated in your editable form draft.
                </p>
              </div>

              {(() => {
                const payload = buildAppliedPayload();
                return (
                  <div className="preview-content-card">
                    {payload.title && (
                      <div className="preview-item">
                        <span className="preview-key">Title:</span>
                        <span className="preview-val">&ldquo;{payload.title}&rdquo;</span>
                      </div>
                    )}
                    {payload.department && (
                      <div className="preview-item">
                        <span className="preview-key">Department:</span>
                        <span className="preview-val">&ldquo;{payload.department}&rdquo;</span>
                      </div>
                    )}
                    {payload.location && (
                      <div className="preview-item">
                        <span className="preview-key">Location:</span>
                        <span className="preview-val">&ldquo;{payload.location}&rdquo;</span>
                      </div>
                    )}
                    {payload.employmentType && (
                      <div className="preview-item">
                        <span className="preview-key">Employment Type:</span>
                        <span className="preview-val">{payload.employmentType}</span>
                      </div>
                    )}
                    {payload.workplaceType && (
                      <div className="preview-item">
                        <span className="preview-key">Workplace Type:</span>
                        <span className="preview-val">{payload.workplaceType}</span>
                      </div>
                    )}
                    {payload.openingsCount && (
                      <div className="preview-item">
                        <span className="preview-key">Openings:</span>
                        <span className="preview-val">{payload.openingsCount}</span>
                      </div>
                    )}
                    {payload.summary && (
                      <div className="preview-item">
                        <span className="preview-key">Summary:</span>
                        <span className="preview-val">&ldquo;{payload.summary}&rdquo;</span>
                      </div>
                    )}
                    {payload.responsibilities && (
                      <div className="preview-item">
                        <span className="preview-key">Responsibilities:</span>
                        <span className="preview-val">{payload.responsibilities.length} items to add</span>
                      </div>
                    )}
                    {payload.newRequirements.length > 0 && (
                      <div className="preview-item">
                        <span className="preview-key">Requirements:</span>
                        <span className="preview-val">
                          {payload.newRequirements.length} requirements ({payload.newRequirements.map((r) => r.label).join(", ")})
                        </span>
                      </div>
                    )}
                  </div>
                );
              })()}

              <div className="preview-notice-box">
                <Icon name="info" size={16} />
                <p>
                  <strong>Note:</strong> Applying suggestions updates your local draft in the form. You must still click <strong>&ldquo;Save Draft&rdquo;</strong> to persist the changes to the server.
                </p>
              </div>

              {applyError && (
                <div className="feedback-box error" role="alert">
                  <Icon name="alert-triangle" size={16} />
                  <p className="feedback-text error">{applyError}</p>
                </div>
              )}

              <div className="import-action-footer">
                <button
                  type="button"
                  className="btn btn-secondary btn-md"
                  onClick={() => setShowConfirmationPreview(false)}
                  disabled={isApplying}
                >
                  Back to Review
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-md"
                  onClick={handleConfirmApply}
                  disabled={isApplying}
                >
                  {isApplying ? (
                    <>
                      <div className="btn-spinner" />
                      <span>Applying...</span>
                    </>
                  ) : (
                    <>
                      <Icon name="check" size={15} />
                      <span>Confirm &amp; Apply to Form</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
