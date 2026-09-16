import React, { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import { Icon } from "../Icon";
import {
  JobInterviewTemplateResponse,
  CandidateInterviewPlanResponse,
  ValidationSummaryResponse,
  VersionHistoryResponse,
  VersionDiffResponse,
  TemplateQuestion,
} from "../../types/interview";

export interface RecruiterAIAvailability {
  ai_enabled: boolean;
  provider_class: string;
  availability_label: string;
  egress_class: "LOCAL_ONLY" | "APPROVED_REMOTE";
  active_model_name?: string | null;
  message?: string | null;
}

export interface InterviewContextData {
  job_id: string;
  job_title: string;
  job_version_id: string;
  job_revision: number;
  candidate_id: string;
  candidate_name: string;
  candidate_email?: string | null;
  resume_artifact_id: string;
  match_run_id?: string | null;
  match_score?: number | null;
  skill_gap_summary?: string | null;
  ai_capability: RecruiterAIAvailability;
  interview_plan_state: string;
  message: string;
}

interface InterviewWorkspaceProps {
  jobId: string;
  resumeId: string;
  onNavigateBack: () => void;
}

export function InterviewWorkspace({
  jobId,
  resumeId,
  onNavigateBack,
}: InterviewWorkspaceProps) {
  const [context, setContext] = useState<InterviewContextData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Template and Plan state
  const [template, setTemplate] = useState<JobInterviewTemplateResponse | null>(null);
  const [candidatePlan, setCandidatePlan] = useState<CandidateInterviewPlanResponse | null>(null);
  const [isGeneratingTemplate, setIsGeneratingTemplate] = useState<boolean>(false);
  const [isGeneratingPlan, setIsGeneratingPlan] = useState<boolean>(false);

  // Active edits & tracking
  const [editableQuestions, setEditableQuestions] = useState<TemplateQuestion[]>([]);
  const [editablePlanQuestions, setEditablePlanQuestions] = useState<TemplateQuestion[]>([]);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Validation report
  const [validationReport, setValidationReport] = useState<ValidationSummaryResponse | null>(null);
  const [isValidating, setIsValidating] = useState<boolean>(false);

  // Version History & Diff Modal
  const [showHistoryModal, setShowHistoryModal] = useState<boolean>(false);
  const [historyData, setHistoryData] = useState<VersionHistoryResponse | null>(null);
  const [diffData, setDiffData] = useState<VersionDiffResponse | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);

  // Selected Rubric for Drawer Modal
  const [selectedRubricQuestion, setSelectedRubricQuestion] = useState<TemplateQuestion | null>(null);

  // Success and notification messages
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const loadData = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const ctxData = await apiFetch<InterviewContextData>(
          `/api/v1/jobs/${jobId}/candidates/${resumeId}/interview-context`
        );
        if (isMounted) {
          setContext(ctxData);
        }

        // Try to fetch existing template
        try {
          const tData = await apiFetch<JobInterviewTemplateResponse>(
            `/api/v1/jobs/${jobId}/interview-templates/latest?revision=${ctxData.job_revision}`
          );
          if (isMounted && tData) {
            setTemplate(tData);
            setEditableQuestions(tData.common_core_questions || []);

            // If template exists and resume is present, check for candidate plan
            try {
              const pData = await apiFetch<CandidateInterviewPlanResponse>(
                `/api/v1/jobs/${jobId}/interview-templates/${tData.template_id}/candidate-plans/${ctxData.candidate_id}/latest`
              );
              if (isMounted && pData) {
                setCandidatePlan(pData);
                setEditablePlanQuestions(pData.supplemental_questions || []);
              }
            } catch {
              // No existing candidate plan yet
            }
          }
        } catch {
          // No existing template draft yet
        }
      } catch (err: any) {
        if (isMounted) {
          setError(
            err?.message ||
              "Failed to load authorized interview context. Please verify requisition ownership."
          );
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    loadData();
    return () => {
      isMounted = false;
    };
  }, [jobId, resumeId]);

  const handleGenerateTemplate = async () => {
    if (!context) return;
    try {
      setIsGeneratingTemplate(true);
      setActionError(null);
      const newTemplate = await apiFetch<JobInterviewTemplateResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/draft?revision=${context.job_revision}`,
        { method: "POST" }
      );
      setTemplate(newTemplate);
      setEditableQuestions(newTemplate.common_core_questions);
      setValidationReport(null);
      setSuccessMessage("Deterministic interview template generated successfully.");
    } catch (err: any) {
      setActionError(err?.message || "Failed to generate interview template.");
    } finally {
      setIsGeneratingTemplate(false);
    }
  };

  const handleGeneratePlan = async () => {
    if (!context || !template) return;
    try {
      setIsGeneratingPlan(true);
      setActionError(null);
      const newPlan = await apiFetch<CandidateInterviewPlanResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/candidates/${resumeId}/plan/draft`,
        { method: "POST" }
      );
      setCandidatePlan(newPlan);
      setEditablePlanQuestions(newPlan.supplemental_questions);
      setValidationReport(null);
      setSuccessMessage("Candidate supplemental interview plan generated successfully.");
    } catch (err: any) {
      setActionError(err?.message || "Failed to generate candidate interview plan.");
    } finally {
      setIsGeneratingPlan(false);
    }
  };

  // Question Editing Handlers
  const handleQuestionTextChange = (index: number, newText: string) => {
    const updated = [...editableQuestions];
    updated[index] = { ...updated[index], question_text: newText, authoring_origin: "RECRUITER_EDITED" };
    setEditableQuestions(updated);
    setHasUnsavedChanges(true);
  };

  const handlePlanQuestionTextChange = (index: number, newText: string) => {
    const updated = [...editablePlanQuestions];
    updated[index] = { ...updated[index], question_text: newText, authoring_origin: "RECRUITER_EDITED" };
    setEditablePlanQuestions(updated);
    setHasUnsavedChanges(true);
  };

  const handleMoveQuestion = (index: number, direction: "UP" | "DOWN") => {
    const targetIndex = direction === "UP" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= editableQuestions.length) return;
    const updated = [...editableQuestions];
    const temp = updated[index];
    updated[index] = updated[targetIndex];
    updated[targetIndex] = temp;
    // Update display_order
    updated.forEach((q, idx) => {
      q.display_order = idx;
    });
    setEditableQuestions(updated);
    setHasUnsavedChanges(true);
  };

  const handleSaveDraft = async () => {
    if (!template) return;
    try {
      setIsSaving(true);
      setActionError(null);
      const updatedTemplate = await apiFetch<JobInterviewTemplateResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/edit`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_record_version: template.template_version,
            expected_content_hash: template.content_hash,
            questions: editableQuestions.map((q, idx) => ({
              question_id: q.question_id,
              question_text: q.question_text,
              display_order: idx,
              estimated_time_minutes: q.estimated_time_minutes,
              permitted_probes: q.permitted_probes,
            })),
          }),
        }
      );
      setTemplate(updatedTemplate);
      setEditableQuestions(updatedTemplate.common_core_questions);
      setHasUnsavedChanges(false);
      setSuccessMessage("Changes saved successfully.");
    } catch (err: any) {
      setActionError(err?.message || "Failed to save draft.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleValidate = async () => {
    if (!template) return;
    try {
      setIsValidating(true);
      setActionError(null);
      const report = await apiFetch<ValidationSummaryResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/validate`,
        { method: "POST" }
      );
      setValidationReport(report);
      if (report.is_valid) {
        setTemplate((prev) => (prev ? { ...prev, lifecycle_state: "VALIDATED" } : null));
        setSuccessMessage("Validation passed! Template is ready for approval.");
      } else {
        setActionError("Template validation failed. Please address blocking violations.");
      }
    } catch (err: any) {
      setActionError(err?.message || "Validation request failed.");
    } finally {
      setIsValidating(false);
    }
  };

  const handleApprove = async () => {
    if (!template) return;
    try {
      setActionError(null);
      const approvedTemplate = await apiFetch<JobInterviewTemplateResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/approve`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_record_version: template.template_version,
            expected_content_hash: template.content_hash,
            approval_notes: "Recruiter reviewed and approved.",
          }),
        }
      );
      setTemplate(approvedTemplate);
      setValidationReport(null);
      setSuccessMessage("Template approved and locked as immutable authoritative baseline.");
    } catch (err: any) {
      setActionError(err?.message || "Failed to approve template.");
    }
  };

  const handleCreateSuccessor = async () => {
    if (!template) return;
    try {
      setActionError(null);
      const successorTemplate = await apiFetch<JobInterviewTemplateResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/successor`,
        {
          method: "POST",
          body: JSON.stringify({
            reason: "Creating new draft version from approved baseline.",
          }),
        }
      );
      setTemplate(successorTemplate);
      setEditableQuestions(successorTemplate.common_core_questions);
      setValidationReport(null);
      setSuccessMessage(`Successor version ${successorTemplate.template_version} draft created.`);
    } catch (err: any) {
      setActionError(err?.message || "Failed to create successor draft.");
    }
  };

  const handleViewHistory = async () => {
    if (!template) return;
    try {
      setIsLoadingHistory(true);
      setShowHistoryModal(true);
      const history = await apiFetch<VersionHistoryResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/history?revision=${template.job_revision}`
      );
      setHistoryData(history);
    } catch (err: any) {
      setActionError(err?.message || "Failed to load version history.");
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const handleCompareVersions = async (baseVer: number, targetVer: number) => {
    if (!template) return;
    try {
      setIsLoadingHistory(true);
      const diff = await apiFetch<VersionDiffResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/diff?revision=${template.job_revision}&base_version=${baseVer}&target_version=${targetVer}`
      );
      setDiffData(diff);
    } catch (err: any) {
      setActionError(err?.message || "Failed to compute version difference.");
    } finally {
      setIsLoadingHistory(false);
    }
  };

  if (isLoading) {
    return (
      <div className="interview-workspace-loading" role="status" aria-live="polite">
        <div className="loading-spinner" />
        <p className="loading-text">Loading verified candidate context &amp; interview workspace...</p>
      </div>
    );
  }

  if (error || !context) {
    return (
      <div className="interview-workspace-error" role="alert">
        <div className="feedback-box error">
          <Icon name="alert-triangle" size={18} />
          <div>
            <strong>Access Restricted</strong>
            <p className="feedback-text">{error || "Unable to access interview workspace."}</p>
          </div>
        </div>
        <button type="button" className="btn btn-secondary mt-4" onClick={onNavigateBack}>
          <Icon name="arrow-left" size={16} />
          <span>Return to Candidates</span>
        </button>
      </div>
    );
  }

  const { ai_capability } = context;
  const isTemplateApproved = template?.lifecycle_state === "APPROVED";
  const isTemplateDraft = template?.lifecycle_state === "DRAFT" || template?.lifecycle_state === "VALIDATED";

  return (
    <div className="interview-workspace-container" role="region" aria-label="Recruiter Interview Workspace">
      {/* Top Header & Navigation */}
      <div className="interview-header-section">
        <div className="flex justify-between items-center mb-3">
          <button
            type="button"
            className="btn btn-secondary btn-sm back-nav-btn"
            onClick={onNavigateBack}
          >
            <Icon name="arrow-left" size={15} />
            <span>Back to Candidates</span>
          </button>

          {template && (
            <div className="flex items-center gap-2">
              <span className={`badge ${isTemplateApproved ? "badge-success" : "badge-warning"}`}>
                Template v{template.template_version} &bull; {template.lifecycle_state}
              </span>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={handleViewHistory}
              >
                <Icon name="history" size={14} />
                <span>Version History</span>
              </button>
            </div>
          )}
        </div>

        <div className="interview-header-titles">
          <div className="title-row">
            <h1 className="interview-main-title">
              Interview Plan: {context.candidate_name}
            </h1>
            {/* AI Capability Pill */}
            <div
              className={`ai-availability-pill ${
                ai_capability.ai_enabled ? "ai-active" : "ai-disabled"
              }`}
              title={ai_capability.message || undefined}
            >
              <Icon name="sparkles" size={14} />
              <span>{ai_capability.availability_label}</span>
              {ai_capability.ai_enabled && ai_capability.active_model_name && (
                <span className="model-chip">({ai_capability.active_model_name})</span>
              )}
            </div>
          </div>
          <p className="interview-subtitle">
            Requisition: <strong>{context.job_title}</strong> (Rev {context.job_revision}) &bull; Candidate ID: <code>{context.candidate_id.substring(0, 8)}</code>
          </p>
        </div>
      </div>

      {/* Action Alerts */}
      {actionError && (
        <div className="feedback-box error mb-4" role="alert">
          <Icon name="alert-triangle" size={16} />
          <span>{actionError}</span>
        </div>
      )}
      {successMessage && (
        <div className="feedback-box success mb-4" role="status">
          <Icon name="check-circle" size={16} />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Overview Context Grid */}
      <div className="interview-context-grid">
        <div className="context-card candidate-card">
          <div className="card-header">
            <Icon name="user" size={16} />
            <h3>Candidate Evidence Context</h3>
          </div>
          <div className="card-body">
            <div className="meta-row">
              <span className="meta-label">Full Name:</span>
              <span className="meta-val">{context.candidate_name}</span>
            </div>
            {context.candidate_email && (
              <div className="meta-row">
                <span className="meta-label">Primary Email:</span>
                <span className="meta-val">{context.candidate_email}</span>
              </div>
            )}
            <div className="meta-row">
              <span className="meta-label">Resume Artifact ID:</span>
              <span className="meta-val"><code>{context.resume_artifact_id.substring(0, 8)}</code></span>
            </div>
          </div>
        </div>

        <div className="context-card match-card">
          <div className="card-header">
            <Icon name="award" size={16} />
            <h3>Match Evaluation &amp; Gaps</h3>
          </div>
          <div className="card-body">
            {context.match_score !== null && context.match_score !== undefined ? (
              <>
                <div className="meta-row">
                  <span className="meta-label">Deterministic Score:</span>
                  <span className="meta-val score-val"><strong>{context.match_score.toFixed(1)}%</strong></span>
                </div>
                {context.skill_gap_summary && (
                  <div className="meta-row">
                    <span className="meta-label">Gap Analysis:</span>
                    <span className="meta-val gap-val">{context.skill_gap_summary}</span>
                  </div>
                )}
              </>
            ) : (
              <p className="text-muted">No match evaluation run recorded for this candidate requisition.</p>
            )}
          </div>
        </div>
      </div>

      {/* Validation Report Drawer / Alert Box */}
      {validationReport && (
        <div className={`validation-report-card ${validationReport.is_valid ? "valid" : "invalid"} mb-4`}>
          <div className="card-header">
            <Icon name={validationReport.is_valid ? "check-circle" : "alert-circle"} size={18} />
            <h3>Validation Report: {validationReport.is_valid ? "Passed" : "Action Required"}</h3>
          </div>
          <div className="card-body">
            {validationReport.blocking_rule_violations.length > 0 && (
              <div className="violations-list mb-2">
                <strong>Blocking Violations:</strong>
                <ul>
                  {validationReport.blocking_rule_violations.map((v, i) => (
                    <li key={i} className="text-danger">{v}</li>
                  ))}
                </ul>
              </div>
            )}
            {validationReport.warnings.length > 0 && (
              <div className="warnings-list">
                <strong>Warnings:</strong>
                <ul>
                  {validationReport.warnings.map((w, i) => (
                    <li key={i} className="text-warning">{w}</li>
                  ))}
                </ul>
              </div>
            )}
            {validationReport.is_valid && (
              <p className="text-success mb-0">All 7 safety &amp; consistency rules verified. Ready for approval.</p>
            )}
          </div>
        </div>
      )}

      {/* Template Section */}
      {!template ? (
        <div className="empty-plan-placeholder">
          <div className="empty-icon-wrap">
            <Icon name="sparkles" size={32} />
          </div>
          <h3>Standardized Job Interview Template</h3>
          <p>
            Generate the deterministic, job-aligned common core interview template derived from the verified job requirements.
          </p>
          <button
            type="button"
            className="btn btn-primary mt-3"
            onClick={handleGenerateTemplate}
            disabled={isGeneratingTemplate}
          >
            <Icon name="plus" size={16} />
            <span>{isGeneratingTemplate ? "Generating..." : "Generate Standardized Template"}</span>
          </button>
        </div>
      ) : (
        <div className="interview-plan-section mb-6">
          <div className="plan-section-header">
            <div>
              <h2>Standardized Common Core Questions</h2>
              <p className="text-sm text-muted">
                Uniform across all applicants for this requisition. Standard core scores are strictly comparable.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="badge badge-info">
                Target Duration: {template.target_duration_minutes} min
              </span>
              <span className="badge badge-secondary">
                Hash: <code>{template.content_hash.substring(0, 8)}</code>
              </span>
            </div>
          </div>

          {/* Question List */}
          <div className="questions-container space-y-4">
            {editableQuestions.map((q, idx) => (
              <div key={q.question_id} className="question-card border rounded p-4 bg-white shadow-sm">
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-primary">#{idx + 1}</span>
                    <span className="badge badge-outline">{q.question_type}</span>
                    <span className="text-sm font-medium text-gray-700">{q.competency_name}</span>
                    <span className={`badge badge-xs ${q.authoring_origin === "RECRUITER_EDITED" ? "badge-warning" : "badge-info"}`}>
                      {q.authoring_origin}
                    </span>
                  </div>
                  {isTemplateDraft && (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs"
                        onClick={() => handleMoveQuestion(idx, "UP")}
                        disabled={idx === 0}
                        title="Move Up"
                      >
                        <Icon name="chevron-up" size={14} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs"
                        onClick={() => handleMoveQuestion(idx, "DOWN")}
                        disabled={idx === editableQuestions.length - 1}
                        title="Move Down"
                      >
                        <Icon name="chevron-down" size={14} />
                      </button>
                    </div>
                  )}
                </div>

                {isTemplateDraft ? (
                  <textarea
                    className="form-control w-full mb-2"
                    rows={3}
                    value={q.question_text}
                    onChange={(e) => handleQuestionTextChange(idx, e.target.value)}
                  />
                ) : (
                  <p className="text-gray-900 mb-2 whitespace-pre-wrap">{q.question_text}</p>
                )}

                <div className="flex justify-between items-center text-xs text-muted pt-2 border-t">
                  <span>Estimated Time: {q.estimated_time_minutes} min</span>
                  <div className="flex gap-2">
                    {q.rubric && (
                      <button
                        type="button"
                        className="btn btn-link btn-xs"
                        onClick={() => setSelectedRubricQuestion(q)}
                      >
                        <Icon name="file-text" size={12} />
                        <span>View Anchored Rubric</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Sticky Lifecycle Action Bar */}
          <div className="sticky-action-bar flex justify-between items-center mt-4 p-3 bg-gray-50 border rounded">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted">
                Status: <strong>{template.lifecycle_state}</strong>
              </span>
              {hasUnsavedChanges && (
                <span className="badge badge-warning text-xs">Unsaved Edits</span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {isTemplateDraft && (
                <>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleSaveDraft}
                    disabled={isSaving || !hasUnsavedChanges}
                  >
                    <Icon name="save" size={14} />
                    <span>{isSaving ? "Saving..." : "Save Draft"}</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-outline btn-sm"
                    onClick={handleValidate}
                    disabled={isValidating || hasUnsavedChanges}
                  >
                    <Icon name="shield-check" size={14} />
                    <span>{isValidating ? "Validating..." : "Validate"}</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={handleApprove}
                    disabled={template.lifecycle_state !== "VALIDATED" || hasUnsavedChanges}
                  >
                    <Icon name="check" size={14} />
                    <span>Approve &amp; Lock</span>
                  </button>
                </>
              )}

              {isTemplateApproved && (
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={handleCreateSuccessor}
                >
                  <Icon name="edit" size={14} />
                  <span>Create Successor Draft</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Candidate Supplemental Section */}
      {template && (
        <div className="candidate-supplemental-section mt-8">
          <div className="section-header flex justify-between items-center mb-3">
            <div>
              <h2 className="text-lg font-semibold">Candidate-Specific Supplemental Evidence Plan</h2>
              <p className="text-xs text-muted">
                Zero to four neutral evidence-clarification questions bound to candidate match gaps.
                <strong> NOT included in common core interview score.</strong>
              </p>
            </div>
            {!candidatePlan && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleGeneratePlan}
                disabled={isGeneratingPlan}
              >
                <Icon name="plus" size={14} />
                <span>{isGeneratingPlan ? "Generating Plan..." : "Generate Supplemental Plan"}</span>
              </button>
            )}
          </div>

          {candidatePlan ? (
            <div className="candidate-plan-box border rounded p-4 bg-gray-50">
              <div className="flex justify-between items-center mb-3">
                <span className="badge badge-info">
                  Plan v{candidatePlan.plan_version} &bull; {candidatePlan.lifecycle_state}
                </span>
                <span className="text-xs text-muted">
                  Supplemental Duration: {candidatePlan.supplemental_duration_minutes} min &bull; Total: {candidatePlan.total_duration_minutes} min
                </span>
              </div>

              {editablePlanQuestions.length === 0 ? (
                <p className="text-muted text-sm italic">
                  No supplemental evidence clarification questions required for this candidate (no significant gaps detected).
                </p>
              ) : (
                <div className="supplemental-questions-list space-y-3">
                  {editablePlanQuestions.map((q, idx) => (
                    <div key={q.question_id} className="supplemental-card border rounded p-3 bg-white">
                      <div className="flex justify-between items-center mb-1">
                        <div className="flex items-center gap-2">
                          <span className="badge badge-warning">Supplemental #{idx + 1}</span>
                          <span className="badge badge-outline text-xs">NOT IN COMMON SCORE</span>
                          <span className="text-xs font-semibold">{q.competency_name}</span>
                        </div>
                      </div>
                      <p className="text-sm text-gray-800">{q.question_text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="p-4 border border-dashed rounded text-center text-muted text-sm">
              No candidate supplemental plan generated yet.
            </div>
          )}
        </div>
      )}

      {/* Anchored Rubric Modal / Drawer */}
      {selectedRubricQuestion && selectedRubricQuestion.rubric && (
        <div className="modal-backdrop fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="modal-box bg-white rounded-lg max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4 border-b pb-2">
              <h3 className="font-semibold text-lg">
                Anchored Rubric: {selectedRubricQuestion.competency_name}
              </h3>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setSelectedRubricQuestion(null)}
              >
                <Icon name="x" size={18} />
              </button>
            </div>
            <div className="rubric-levels space-y-4">
              {selectedRubricQuestion.rubric.levels.map((level, idx) => (
                <div key={idx} className="rubric-level-card border rounded p-3 bg-gray-50">
                  <div className="flex justify-between items-center mb-1">
                    <span className="font-bold text-primary">{level.level_name}</span>
                    <span className="badge badge-secondary text-xs">
                      Score: {level.score_range[0]} - {level.score_range[1]}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 mb-2">{level.description}</p>
                  {level.observable_signals.length > 0 && (
                    <div className="text-xs">
                      <strong>Observable Signals:</strong>
                      <ul className="list-disc pl-4 mt-1 text-gray-600">
                        {level.observable_signals.map((sig, sIdx) => (
                          <li key={sIdx}>{sig}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-6 flex justify-end">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setSelectedRubricQuestion(null)}
              >
                Close Rubric
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {showHistoryModal && (
        <div className="modal-backdrop fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="modal-box bg-white rounded-lg max-w-3xl w-full p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4 border-b pb-2">
              <h3 className="font-semibold text-lg">Template Version History</h3>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setShowHistoryModal(false);
                  setDiffData(null);
                }}
              >
                <Icon name="x" size={18} />
              </button>
            </div>

            {isLoadingHistory ? (
              <div className="p-4 text-center">Loading version history...</div>
            ) : historyData ? (
              <div className="space-y-4">
                <table className="table w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="p-2">Version</th>
                      <th className="p-2">Status</th>
                      <th className="p-2">Hash</th>
                      <th className="p-2">Created</th>
                      <th className="p-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historyData.versions.map((ver) => (
                      <tr key={ver.id} className="border-b">
                        <td className="p-2 font-semibold">v{ver.version}</td>
                        <td className="p-2">
                          <span className={`badge badge-sm ${ver.lifecycle_state === "APPROVED" ? "badge-success" : "badge-outline"}`}>
                            {ver.lifecycle_state}
                          </span>
                        </td>
                        <td className="p-2"><code>{ver.content_hash.substring(0, 8)}</code></td>
                        <td className="p-2">{new Date(ver.created_at).toLocaleString()}</td>
                        <td className="p-2">
                          {ver.version > 1 && (
                            <button
                              type="button"
                              className="btn btn-link btn-xs"
                              onClick={() => handleCompareVersions(ver.version - 1, ver.version)}
                            >
                              Diff with v{ver.version - 1}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Diff Viewer */}
                {diffData && (
                  <div className="diff-viewer border rounded p-4 bg-gray-50 mt-4">
                    <h4 className="font-semibold mb-2">
                      Diff: v{diffData.base_version} &rarr; v{diffData.target_version}
                    </h4>
                    <p className="text-xs text-muted mb-3">{diffData.summary}</p>
                    <div className="space-y-2">
                      {diffData.question_diffs.map((qd) => (
                        <div key={qd.question_id} className="diff-item p-2 border rounded bg-white text-xs">
                          <div className="flex justify-between mb-1">
                            <span className="font-semibold">Question {qd.question_id.substring(0, 8)}</span>
                            <span className={`badge badge-xs ${qd.change_type === "MODIFIED" ? "badge-warning" : "badge-secondary"}`}>
                              {qd.change_type}
                            </span>
                          </div>
                          {Object.entries(qd.field_changes).map(([field, delta]) => (
                            <div key={field} className="delta-row">
                              <span className="font-medium">{field}: </span>
                              <span className="text-danger line-through">{String(delta.from)}</span>
                              <span className="text-success ml-2">{String(delta.to)}</span>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
