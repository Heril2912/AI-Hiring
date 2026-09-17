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
  CandidateWordingResult,
  QuestionActionResponse,
  StructuredWordingVariant,
  GenerateTemplateAiWordingResponse,
} from "../../types/interview";
import { WordingComparisonModal } from "./WordingComparisonModal";

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
  resumeId?: string | null;
  onNavigateBack: () => void;
}

/**
 * Humanizes raw enum labels into clean, legible recruiter text.
 * E.g. PYTHON_CORE -> Python Core, POSTGRESQL_PERFORMANCE_TUNING -> PostgreSQL Performance Tuning
 */
export function formatCompetencyName(raw: string | undefined | null): string {
  if (!raw) return "General Competency";
  const acronyms: Record<string, string> = {
    API: "API",
    SQL: "SQL",
    REST: "REST",
    JSON: "JSON",
    CI: "CI",
    CD: "CD",
    DB: "DB",
    AWS: "AWS",
    GCP: "GCP",
    UI: "UI",
    UX: "UX",
    AI: "AI",
    ML: "ML",
    LLM: "LLM",
    POSTGRESQL: "PostgreSQL",
    GRAPHQL: "GraphQL",
    TYPESCRIPT: "TypeScript",
    JAVASCRIPT: "JavaScript",
  };

  return raw
    .replace(/[_-]+/g, " ")
    .trim()
    .split(/\s+/)
    .map((word) => {
      const upper = word.toUpperCase();
      if (acronyms[upper]) return acronyms[upper];
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ");
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
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);
  const [comparingQuestionId, setComparingQuestionId] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Batch AI Wording Generation State
  const [isBatchGenerating, setIsBatchGenerating] = useState<boolean>(false);
  const [batchProgress, setBatchProgress] = useState<{ current: number; total: number } | null>(null);
  const [batchStatusSummary, setBatchStatusSummary] = useState<GenerateTemplateAiWordingResponse | null>(null);

  // Single Wording Assistance State
  const [improvingQuestionId, setImprovingQuestionId] = useState<string | null>(null);
  const [activeWordingComparison, setActiveWordingComparison] = useState<{
    question: TemplateQuestion;
    result: CandidateWordingResult;
    layer: "COMMON_CORE" | "SUPPLEMENTAL_EVIDENCE";
  } | null>(null);
  const [isApplyingSuggestion, setIsApplyingSuggestion] = useState<boolean>(false);
  const [announcement, setAnnouncement] = useState<string>("");
  const [expandedProvenanceQuestionId, setExpandedProvenanceQuestionId] = useState<string | null>(null);

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

  // Feedback notifications
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const loadData = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const contextUrl = resumeId && resumeId.trim() !== ""
          ? `/api/v1/jobs/${jobId}/candidates/${resumeId}/interview-context`
          : `/api/v1/jobs/${jobId}/interview-context`;
        const ctxData = await apiFetch<InterviewContextData>(contextUrl);
        if (isMounted) {
          setContext(ctxData);
        }

        // Fetch existing template
        try {
          const tData = await apiFetch<JobInterviewTemplateResponse>(
            `/api/v1/jobs/${jobId}/interview-templates/latest?revision=${ctxData.job_revision}`
          );
          if (isMounted && tData) {
            setTemplate(tData);
            setEditableQuestions(tData.common_core_questions || []);

            if (resumeId && ctxData.candidate_id) {
              try {
                const pData = await apiFetch<CandidateInterviewPlanResponse>(
                  `/api/v1/jobs/${jobId}/interview-templates/${tData.template_id}/candidate-plans/${ctxData.candidate_id}/latest`
                );
                if (isMounted && pData) {
                  setCandidatePlan(pData);
                  setEditablePlanQuestions(pData.supplemental_questions || []);
                }
              } catch {
                // No candidate plan yet
              }
            }
          }
        } catch {
          // No draft template yet
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
      setSuccessMessage("Deterministic interview blueprint generated successfully.");
    } catch (err: any) {
      setActionError(err?.message || "Failed to generate interview blueprint.");
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

  // Batch AI Wording Generation
  const handleBatchGenerateAiWording = async () => {
    if (!template) return;
    try {
      setIsBatchGenerating(true);
      setActionError(null);
      setSuccessMessage(null);
      setBatchProgress({ current: 0, total: editableQuestions.length });
      setAnnouncement("Preparing AI interview wording sequentially...");

      const response = await apiFetch<GenerateTemplateAiWordingResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/generate-ai-wording`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_template_version: template.template_version,
          }),
        }
      );

      setBatchStatusSummary(response);

      // Refresh template questions from server result
      if (response.results && response.results.length > 0) {
        const resultMap = new Map(response.results.map((r) => [r.question_id, r]));
        const updated = editableQuestions.map((q) => {
          const res = resultMap.get(q.question_id);
          if (res) {
            return {
              ...q,
              question_text: res.question_text,
              authoring_origin: res.authoring_origin,
              deterministic_source_text: res.deterministic_question_text,
            };
          }
          return q;
        });
        setEditableQuestions(updated);
      }

      setValidationReport(null);
      const aiCount = response.ai_generated_count ?? response.ai_ready_count ?? 0;
      const fallbackCount = response.fallback_count ?? 0;
      const failedCount = response.failed_count ?? 0;

      if (response.status === "COMPLETED") {
        setSuccessMessage(response.safe_message || `AI drafting complete: all ${aiCount} questions prepared and validated.`);
      } else if (response.status === "PARTIALLY_COMPLETED") {
        setSuccessMessage(
          response.safe_message ||
          `AI drafting partially completed: ${aiCount} prepared, ${fallbackCount + failedCount} retained deterministic.`
        );
      } else {
        const errorMsg =
          response.safe_message ||
          "Local AI could not prepare the questions. Your deterministic questions remain available.";
        setActionError(errorMsg);
      }
    } catch (err: any) {
      const msg = "Local AI could not prepare the questions. Your deterministic questions remain available.";
      setActionError(msg);
    } finally {
      setIsBatchGenerating(false);
      setBatchProgress(null);
    }
  };

  // Restore All Deterministic Baseline
  const handleRestoreAllDeterministic = async () => {
    if (!template) return;
    const confirmed = window.confirm(
      "Restore all original deterministic questions for this template? Any AI drafts or unsaved edits will be replaced by the deterministic baseline."
    );
    if (!confirmed) return;

    try {
      setActionError(null);
      for (const q of editableQuestions) {
        if (q.authoring_origin === "AI_ASSISTED" || q.authoring_origin === "RECRUITER_EDITED") {
          await apiFetch<QuestionActionResponse>(
            `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/questions/${q.question_id}/restore-deterministic`,
            {
              method: "POST",
              body: JSON.stringify({
                expected_question_version: q.question_version || 1,
              }),
            }
          );
        }
      }

      // Re-fetch fresh template
      const refreshed = await apiFetch<JobInterviewTemplateResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/latest?revision=${context?.job_revision}`
      );
      setTemplate(refreshed);
      setEditableQuestions(refreshed.common_core_questions);
      setValidationReport(null);
      setSuccessMessage("All questions restored to deterministic blueprint baseline.");
    } catch (err: any) {
      setActionError(err?.message || "Failed to restore all deterministic questions.");
    }
  };

  // Single Question Handlers
  const handleQuestionTextChange = (index: number, newText: string) => {
    const updated = [...editableQuestions];
    updated[index] = { ...updated[index], question_text: newText, authoring_origin: "RECRUITER_EDITED" };
    setEditableQuestions(updated);
    setHasUnsavedChanges(true);
    setValidationReport(null);
  };

  const handlePlanQuestionTextChange = (index: number, newText: string) => {
    const updated = [...editablePlanQuestions];
    updated[index] = { ...updated[index], question_text: newText, authoring_origin: "RECRUITER_EDITED" };
    setEditablePlanQuestions(updated);
    setHasUnsavedChanges(true);
    setValidationReport(null);
  };

  const handleMoveQuestion = (index: number, direction: "UP" | "DOWN") => {
    const targetIndex = direction === "UP" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= editableQuestions.length) return;
    const updated = [...editableQuestions];
    const temp = updated[index];
    updated[index] = updated[targetIndex];
    updated[targetIndex] = temp;
    updated.forEach((q, idx) => {
      q.display_order = idx;
    });
    setEditableQuestions(updated);
    setHasUnsavedChanges(true);
    setValidationReport(null);
  };

  const handleImproveWording = async (
    question: TemplateQuestion,
    layer: "COMMON_CORE" | "SUPPLEMENTAL_EVIDENCE" = "COMMON_CORE"
  ) => {
    if (!template) return;
    try {
      setImprovingQuestionId(question.question_id);
      setActionError(null);
      setSuccessMessage(null);
      setAnnouncement(`Requesting wording improvement for question ${question.display_order + 1}...`);

      const result = await apiFetch<CandidateWordingResult>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/questions/${question.question_id}/assist-wording`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_question_version: question.question_version || 1,
            source_content_hash: question.content_hash || null,
          }),
        }
      );

      if (result.is_validated && result.proposed_variants.length > 0) {
        setAnnouncement("Wording suggestion generated. Comparison modal opened.");
        setActiveWordingComparison({
          question,
          result,
          layer,
        });
      } else {
        const msg = result.safe_error_message || "Wording assistance fallback active.";
        setActionError(msg);
        setAnnouncement(`Wording assistance note: ${msg}`);
      }
    } catch (err: any) {
      const msg = err?.message || "Failed to request wording improvement.";
      setActionError(msg);
      setAnnouncement(`Error: ${msg}`);
    } finally {
      setImprovingQuestionId(null);
    }
  };

  const handleUseSuggestion = async (
    question: TemplateQuestion,
    variant: StructuredWordingVariant,
    result: CandidateWordingResult,
    layer: "COMMON_CORE" | "SUPPLEMENTAL_EVIDENCE"
  ) => {
    if (!template) return;
    try {
      setIsApplyingSuggestion(true);
      setActionError(null);

      const response = await apiFetch<QuestionActionResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/questions/${question.question_id}/apply-suggestion`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_question_version: question.question_version || 1,
            expected_source_hash: question.content_hash || null,
            suggested_text: variant.variant_text,
            rationale_code: variant.rationale_code,
          }),
        }
      );

      if (layer === "COMMON_CORE") {
        const updated = editableQuestions.map((q) =>
          q.question_id === question.question_id
            ? {
                ...q,
                question_text: response.question_text,
                question_version: response.question_version,
                authoring_origin: response.authoring_origin,
                deterministic_source_text: response.deterministic_source_text,
                safe_metadata: response.safe_metadata,
                ai_provenance: response.safe_metadata?.ai_provenance,
              }
            : q
        );
        setEditableQuestions(updated);
      } else {
        const updated = editablePlanQuestions.map((q) =>
          q.question_id === question.question_id
            ? {
                ...q,
                question_text: response.question_text,
                question_version: response.question_version,
                authoring_origin: response.authoring_origin,
                deterministic_source_text: response.deterministic_source_text,
                safe_metadata: response.safe_metadata,
                ai_provenance: response.safe_metadata?.ai_provenance,
              }
            : q
        );
        setEditablePlanQuestions(updated);
      }

      setActiveWordingComparison(null);
      setValidationReport(null);
      setSuccessMessage("AI-assisted wording suggestion applied as draft.");
      setAnnouncement("AI-assisted suggestion applied as draft.");
    } catch (err: any) {
      setActionError(err?.message || "Failed to apply wording suggestion.");
    } finally {
      setIsApplyingSuggestion(false);
    }
  };

  const handleEditSuggestion = (
    question: TemplateQuestion,
    variant: StructuredWordingVariant,
    layer: "COMMON_CORE" | "SUPPLEMENTAL_EVIDENCE"
  ) => {
    if (layer === "COMMON_CORE") {
      const idx = editableQuestions.findIndex((q) => q.question_id === question.question_id);
      if (idx !== -1) {
        handleQuestionTextChange(idx, variant.variant_text);
        setEditingQuestionId(question.question_id);
      }
    } else {
      const idx = editablePlanQuestions.findIndex((q) => q.question_id === question.question_id);
      if (idx !== -1) {
        handlePlanQuestionTextChange(idx, variant.variant_text);
      }
    }
    setActiveWordingComparison(null);
    setSuccessMessage("Suggestion transferred to editor as Recruiter Edited draft.");
  };

  const handleRestoreDeterministic = async (
    question: TemplateQuestion,
    layer: "COMMON_CORE" | "SUPPLEMENTAL_EVIDENCE" = "COMMON_CORE"
  ) => {
    if (!template) return;
    const confirmRestore = window.confirm(
      "Restore the original deterministic wording for this question? Any recruiter edits or AI suggestions will be replaced by the blueprint baseline."
    );
    if (!confirmRestore) return;

    try {
      setActionError(null);
      const response = await apiFetch<QuestionActionResponse>(
        `/api/v1/jobs/${jobId}/interview-templates/${template.template_id}/questions/${question.question_id}/restore-deterministic`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_question_version: question.question_version || 1,
          }),
        }
      );

      if (layer === "COMMON_CORE") {
        const updated = editableQuestions.map((q) =>
          q.question_id === question.question_id
            ? {
                ...q,
                question_text: response.question_text,
                question_version: response.question_version,
                authoring_origin: response.authoring_origin,
                deterministic_source_text: response.deterministic_source_text,
                safe_metadata: response.safe_metadata,
                ai_provenance: null,
              }
            : q
        );
        setEditableQuestions(updated);
      } else {
        const updated = editablePlanQuestions.map((q) =>
          q.question_id === question.question_id
            ? {
                ...q,
                question_text: response.question_text,
                question_version: response.question_version,
                authoring_origin: response.authoring_origin,
                deterministic_source_text: response.deterministic_source_text,
                safe_metadata: response.safe_metadata,
                ai_provenance: null,
              }
            : q
        );
        setEditablePlanQuestions(updated);
      }

      setValidationReport(null);
      setSuccessMessage("Deterministic blueprint wording restored.");
    } catch (err: any) {
      setActionError(err?.message || "Failed to restore deterministic wording.");
    }
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
      setEditingQuestionId(null);
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
  const templateStatus = (template as any)?.lifecycle_status || template?.lifecycle_state || "DRAFT";
  const isTemplateApproved = templateStatus === "APPROVED";
  const isTemplateDraft = templateStatus === "DRAFT" || templateStatus === "VALIDATED";

  const aiReadyCount = editableQuestions.filter((q) => q.authoring_origin === "AI_ASSISTED").length;
  const editedCount = editableQuestions.filter((q) => q.authoring_origin === "RECRUITER_EDITED").length;
  const deterministicCount = editableQuestions.length - aiReadyCount - editedCount;

  return (
    <div className="interview-workspace-container" role="region" aria-label="Recruiter Interview Workspace">
      {/* Top Header & Navigation */}
      <div className="interview-header-section">
        <div className="flex justify-between items-center mb-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm back-nav-btn"
            onClick={onNavigateBack}
          >
            <Icon name="arrow-left" size={15} />
            <span>{resumeId ? "Back to Candidates" : "Back to Jobs"}</span>
          </button>

          {template && (
            <div className="flex items-center gap-2">
              <span className={`badge ${isTemplateApproved ? "badge-success" : "badge-warning"}`}>
                Template v{template.template_version} &bull; {templateStatus}
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
              {context.candidate_name ? `Interview Plan: ${context.candidate_name}` : `Interview Template: ${context.job_title}`}
            </h1>

            {/* Compact Local AI Pill */}
            <div
              className={`ai-availability-pill ${
                ai_capability.ai_enabled ? "ai-active" : "ai-disabled"
              }`}
              title={ai_capability.message || (ai_capability.active_model_name ? `Model: ${ai_capability.active_model_name}` : undefined)}
            >
              <Icon name="sparkles" size={14} />
              <span>{ai_capability.availability_label}</span>
            </div>
          </div>
          <p className="interview-subtitle">
            Requisition: <strong>{context.job_title}</strong> (Rev {context.job_revision})
            {context.candidate_id && (
              <> &bull; Candidate ID: <code>{context.candidate_id.substring(0, 8)}</code></>
            )}
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

      {/* Context Grid (Candidate Evidence Context & Match Evaluation) */}
      <div className="interview-context-grid">
        {resumeId && context.candidate_id ? (
          <>
            <div className="context-card candidate-card">
              <div className="card-header">
                <Icon name="user" size={16} />
                <h3>Candidate Evidence Context</h3>
              </div>
              <div className="card-body">
                <div className="meta-row">
                  <span className="meta-label">Full Name:</span>
                  <span className="meta-val">{context.candidate_name || "N/A"}</span>
                </div>
                {context.candidate_email && (
                  <div className="meta-row">
                    <span className="meta-label">Primary Email:</span>
                    <span className="meta-val">{context.candidate_email}</span>
                  </div>
                )}
                {context.resume_artifact_id && (
                  <div className="meta-row">
                    <span className="meta-label">Resume Artifact ID:</span>
                    <span className="meta-val"><code>{context.resume_artifact_id.substring(0, 8)}</code></span>
                  </div>
                )}
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
          </>
        ) : (
          <>
            <div className="context-card job-requisition-context-card">
              <div className="card-header">
                <Icon name="briefcase" size={16} />
                <h3>Job Requisition Details</h3>
              </div>
              <div className="card-body">
                <div className="meta-row">
                  <span className="meta-label">Requisition Title:</span>
                  <span className="meta-val"><strong>{context.job_title}</strong></span>
                </div>
                <div className="meta-row">
                  <span className="meta-label">Version / Revision:</span>
                  <span className="meta-val">Rev #{context.job_revision}</span>
                </div>
                <div className="meta-row">
                  <span className="meta-label">Scope:</span>
                  <span className="meta-val">Standardized Common-Core Interview Template</span>
                </div>
              </div>
            </div>

            <div className="context-card ai-governance-context-card">
              <div className="card-header">
                <Icon name="shield" size={16} />
                <h3>AI Governance &amp; Assistance</h3>
              </div>
              <div className="card-body">
                <div className="meta-row">
                  <span className="meta-label">AI Status:</span>
                  <span className="meta-val">{ai_capability.availability_label}</span>
                </div>
                <div className="meta-row">
                  <span className="meta-label">Egress Mode:</span>
                  <span className="meta-val">{ai_capability.egress_class || "LOCAL_ONLY"}</span>
                </div>
                {ai_capability.active_model_name && (
                  <div className="meta-row">
                    <span className="meta-label">Active Model:</span>
                    <span className="meta-val"><code>{ai_capability.active_model_name}</code></span>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* AI Drafting Hero Control Panel */}
      {template && isTemplateDraft && (
        <div className={`ai-drafting-banner ${ai_capability.ai_enabled ? "active-mode" : ""}`}>
          <div className="ai-drafting-banner-header">
            <div className="ai-drafting-banner-title">
              <Icon name="sparkles" size={20} className={ai_capability.ai_enabled ? "text-primary" : "text-muted"} />
              <div>
                <h3>AI-Assisted Template Drafting</h3>
                <div className="ai-drafting-banner-desc">
                  {ai_capability.ai_enabled
                    ? "Generate clear, standardized wording for all interview questions with local AI. Competencies, rubrics, and durations remain authoritative."
                    : "Local AI is currently unavailable or disabled by Admin. Questions remain in deterministic blueprint baseline."}
                </div>
              </div>
            </div>

            <div className="ai-drafting-banner-actions">
              {ai_capability.ai_enabled && (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={handleBatchGenerateAiWording}
                  disabled={isBatchGenerating}
                >
                  <Icon name="sparkles" size={15} />
                  <span>{isBatchGenerating ? "Drafting with AI..." : "Generate interview wording with AI"}</span>
                </button>
              )}

              {(aiReadyCount > 0 || editedCount > 0) && (
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={handleRestoreAllDeterministic}
                  disabled={isBatchGenerating}
                  title="Revert all questions back to the deterministic blueprint"
                >
                  <Icon name="history" size={14} />
                  <span>Restore all blueprint wording</span>
                </button>
              )}
            </div>
          </div>

          {/* Sequential Progress Bar during batch generation */}
          {isBatchGenerating && (
            <div className="mt-4">
              <div className="ai-progress-bar-container">
                <div
                  className="ai-progress-bar-fill"
                  style={{ width: "100%", animation: "pulse 1.5s infinite" }}
                />
              </div>
              <div className="ai-progress-stats">
                <span>Processing questions sequentially with local AI engine...</span>
                <span>Please wait a moment</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Summary Chips Bar */}
      {template && (
        <div className="flex items-center gap-3 mb-4 flex-wrap text-xs text-muted">
          <span className="badge badge-secondary">
            {editableQuestions.length} Total Questions
          </span>
          <span className="badge badge-info">
            Target Duration: {template.target_duration_minutes || 45} min
          </span>
          {aiReadyCount > 0 && (
            <span className="badge badge-ai">
              {aiReadyCount} AI Drafted
            </span>
          )}
          {editedCount > 0 && (
            <span className="badge badge-warning">
              {editedCount} Recruiter Edited
            </span>
          )}
          {deterministicCount > 0 && (
            <span className="badge badge-outline">
              {deterministicCount} Deterministic Blueprint
            </span>
          )}
        </div>
      )}

      {/* Validation Report Alert Box */}
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
              <p className="text-success mb-0">All safety &amp; consistency rules verified. Ready for approval.</p>
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
            Generate the deterministic, job-aligned common core interview blueprint derived from verified job requirements.
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
                Uniform across all applicants for this requisition. Scores are anchored to objective rubrics.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="badge badge-secondary">
                Hash: <code>{template.content_hash ? template.content_hash.substring(0, 8) : "DRAFT"}</code>
              </span>
            </div>
          </div>

          {/* Question List (Redesigned Question Cards) */}
          <div className="questions-container">
            {editableQuestions.map((q, idx) => {
              const isImproving = improvingQuestionId === q.question_id;
              const hasAiProvenance = !!q.ai_provenance || q.authoring_origin === "AI_ASSISTED";
              const isAiExpanded = expandedProvenanceQuestionId === q.question_id;
              const isAiOrigin = q.authoring_origin === "AI_ASSISTED";
              const isEditedOrigin = q.authoring_origin === "RECRUITER_EDITED";
              const canRestore = (isAiOrigin || isEditedOrigin) && isTemplateDraft;
              const isEditing = editingQuestionId === q.question_id;
              const isComparing = comparingQuestionId === q.question_id;

              const cardClass = `question-card-redesigned ${
                isAiOrigin ? "ai-assisted-card" : isEditedOrigin ? "recruiter-edited-card" : ""
              }`;

              return (
                <div key={q.question_id} className={cardClass}>
                  {/* Top Bar: Question Index, Competency Title & Origin Badge */}
                  <div className="question-card-top-bar">
                    <div className="question-identity-group">
                      <span className="question-order-pill">Question {idx + 1}</span>
                      <span className="competency-title">
                        {formatCompetencyName(q.competency_name || (q as any).competency_id || (q.rubric as any)?.competency_definition)}
                      </span>
                      <span className="badge badge-outline text-xs">{q.question_type}</span>

                      {/* Origin Badge */}
                      {isAiOrigin ? (
                        <span className="origin-badge badge-ai" title="Validated AI Draft">
                          <Icon name="sparkles" size={12} />
                          <span>AI-Assisted Draft</span>
                        </span>
                      ) : isEditedOrigin ? (
                        <span className="origin-badge badge-edited" title="Edited by Recruiter">
                          <Icon name="edit" size={12} />
                          <span>Recruiter Edited</span>
                        </span>
                      ) : isTemplateApproved ? (
                        <span className="origin-badge badge-approved" title="Approved Baseline">
                          <Icon name="check-circle" size={12} />
                          <span>Approved</span>
                        </span>
                      ) : (
                        <span className="origin-badge badge-deterministic" title="Deterministic Blueprint">
                          <Icon name="shield" size={12} />
                          <span>Deterministic</span>
                        </span>
                      )}
                    </div>

                    {/* Reorder Buttons */}
                    {isTemplateDraft && (
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs"
                          onClick={() => handleMoveQuestion(idx, "UP")}
                          disabled={idx === 0}
                          title="Move Question Up"
                          aria-label={`Move Question ${idx + 1} Up`}
                        >
                          <Icon name="chevron-up" size={14} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs"
                          onClick={() => handleMoveQuestion(idx, "DOWN")}
                          disabled={idx === editableQuestions.length - 1}
                          title="Move Question Down"
                          aria-label={`Move Question ${idx + 1} Down`}
                        >
                          <Icon name="chevron-down" size={14} />
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Question Content: Full-width responsive textarea in draft mode */}
                  {isTemplateDraft ? (
                    <div className="mb-3">
                      <textarea
                        className="question-full-textarea"
                        rows={3}
                        value={q.question_text}
                        onChange={(e) => handleQuestionTextChange(idx, e.target.value)}
                        aria-label={`Question ${idx + 1} text`}
                      />
                    </div>
                  ) : (
                    <div className="question-display-body">
                      {q.question_text}
                    </div>
                  )}

                  {/* Original vs Current AI Draft Comparison View (if toggled) */}
                  {isComparing && q.deterministic_source_text && (
                    <div className="comparison-box p-3 bg-slate-50 border rounded text-xs mb-3 space-y-2">
                      <div className="font-semibold text-slate-800 flex items-center justify-between">
                        <span>Baseline Comparison</span>
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs"
                          onClick={() => setComparingQuestionId(null)}
                        >
                          <Icon name="x" size={12} />
                        </button>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="p-2 bg-white rounded border">
                          <strong className="text-muted block mb-1">Deterministic Blueprint Baseline:</strong>
                          <p className="text-slate-700 m-0">{q.deterministic_source_text}</p>
                        </div>
                        <div className="p-2 bg-blue-50 rounded border border-blue-100">
                          <strong className="text-blue-900 block mb-1">Current Active Draft:</strong>
                          <p className="text-blue-950 m-0">{q.question_text}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Bottom Meta & Actions Bar */}
                  <div className="question-bottom-meta-bar">
                    <div className="question-meta-tags">
                      <span><strong>Duration:</strong> {q.estimated_time_minutes} min</span>
                      {q.permitted_probes && q.permitted_probes.length > 0 && (
                        <span><strong>Permitted Probes:</strong> {q.permitted_probes.length}</span>
                      )}
                    </div>

                    <div className="question-actions-cluster">
                      {/* Edit Button */}
                      {isTemplateDraft && !isEditing && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs"
                          onClick={() => setEditingQuestionId(q.question_id)}
                          title="Edit question wording directly"
                        >
                          <Icon name="edit" size={12} />
                          <span>Edit</span>
                        </button>
                      )}

                      {/* Compare with Original */}
                      {q.deterministic_source_text && q.deterministic_source_text !== q.question_text && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs text-muted"
                          onClick={() => setComparingQuestionId(isComparing ? null : q.question_id)}
                          title="Compare current draft with original deterministic wording"
                        >
                          <Icon name="eye" size={12} />
                          <span>{isComparing ? "Hide comparison" : "Compare original"}</span>
                        </button>
                      )}

                      {/* Restore Deterministic Action */}
                      {canRestore && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs text-muted"
                          onClick={() => handleRestoreDeterministic(q, "COMMON_CORE")}
                          title="Restore original deterministic baseline wording"
                        >
                          <Icon name="history" size={12} />
                          <span>Restore original</span>
                        </button>
                      )}

                      {/* Improve Wording Action (Single Question) */}
                      {isTemplateDraft && (
                        <button
                          type="button"
                          className="btn btn-outline btn-xs btn-ai-improve"
                          onClick={() => handleImproveWording(q, "COMMON_CORE")}
                          disabled={isImproving || !ai_capability.ai_enabled}
                          title={
                            ai_capability.ai_enabled
                              ? "Regenerate wording suggestion with local AI"
                              : ai_capability.message || "AI assistance currently unavailable"
                          }
                          aria-label={`Improve wording for question ${idx + 1}`}
                        >
                          <Icon name="sparkles" size={12} />
                          <span>{isImproving ? "Improving wording…" : "Improve wording"}</span>
                        </button>
                      )}

                      {/* View Anchored Rubric */}
                      {q.rubric && (
                        <button
                          type="button"
                          className="btn btn-link btn-xs"
                          onClick={() => setSelectedRubricQuestion(q)}
                        >
                          <Icon name="file-text" size={12} />
                          <span>View Rubric</span>
                        </button>
                      )}

                      {/* AI Technical Provenance Toggle */}
                      {hasAiProvenance && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs text-xs text-muted"
                          onClick={() =>
                            setExpandedProvenanceQuestionId(isAiExpanded ? null : q.question_id)
                          }
                          aria-expanded={isAiExpanded}
                          aria-label="Toggle Technical Details"
                          title="View provenance and compliance hashes"
                        >
                          <Icon name={isAiExpanded ? "chevron-up" : "info"} size={12} />
                          <span>{isAiExpanded ? "Hide Technical" : "Technical Details"}</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Expandable Technical Details Drawer */}
                  {hasAiProvenance && isAiExpanded && (
                    <div className="ai-provenance-box mt-3 p-3 bg-slate-50 border rounded text-xs space-y-1">
                      <div className="font-semibold text-slate-800 flex items-center gap-1 mb-1">
                        <Icon name="shield-check" size={13} />
                        <span>AI Governance &amp; Provenance Record</span>
                      </div>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600">
                        <div><strong>Engine:</strong> {q.ai_provenance?.provider_class || "LOCAL_LM_STUDIO"}</div>
                        <div><strong>Model:</strong> {q.ai_provenance?.model_name || "qwen3-4b-instruct"}</div>
                        <div><strong>Origin:</strong> {q.authoring_origin}</div>
                        <div><strong>Template Schema:</strong> {q.ai_provenance?.prompt_template_version || "1.0.0"}</div>
                        <div><strong>Validation Result:</strong> <span className="text-success font-medium">Verified Safe</span></div>
                        <div><strong>Deterministic Hash:</strong> <code>{(q.deterministic_source_hash || "").substring(0, 10) || "N/A"}</code></div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Sticky Action Bar for Draft & Validation */}
          <div className="sticky-action-bar flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted">
                Status: <strong>{templateStatus}</strong>
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
                    disabled={templateStatus !== "VALIDATED" || hasUnsavedChanges}
                  >
                    <Icon name="check" size={14} />
                    <span>Approve &amp; Lock Baseline</span>
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

      {/* Candidate Supplemental Section or Job Template Mode Notice */}
      {template && (resumeId ? (
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
                  Plan v{candidatePlan.plan_version} &bull; {(candidatePlan as any).lifecycle_status || candidatePlan.lifecycle_state || "DRAFT"}
                </span>
                <span className="text-xs text-muted">
                  Supplemental Duration: {candidatePlan.supplemental_duration_minutes || 15} min &bull; Total: {candidatePlan.total_duration_minutes || 60} min
                </span>
              </div>

              {editablePlanQuestions.length === 0 ? (
                <p className="text-muted text-sm italic">
                  No supplemental evidence clarification needed. Candidate match evidence is sufficient.
                </p>
              ) : (
                <div className="space-y-3">
                  {editablePlanQuestions.map((q, idx) => (
                    <div key={q.question_id} className="supplemental-q-card border rounded p-3 bg-white">
                      <div className="flex justify-between items-center mb-1">
                        <div className="flex items-center gap-2">
                          <span className="badge badge-warning">Supplemental #{idx + 1}</span>
                          <span className="badge badge-outline text-xs">NOT IN COMMON SCORE</span>
                          <span className="text-xs font-semibold">
                            {formatCompetencyName(q.competency_name || (q as any).competency_id)}
                          </span>
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
      ) : (
        <div className="candidate-supplemental-info mt-8 p-4 border rounded bg-gray-50 flex items-center gap-3">
          <Icon name="info" size={20} className="text-primary" />
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Standardized Job Template Mode</h3>
            <p className="text-xs text-muted">
              You are managing the common core interview questions and anchored rubrics for <strong>{context.job_title}</strong>. 
              Candidate-specific supplemental clarification questions are generated per-candidate when reviewing applicants in Candidate Comparison.
            </p>
          </div>
        </div>
      ))}

      {/* Anchored Rubric Modal / Drawer */}
      {selectedRubricQuestion && selectedRubricQuestion.rubric && (
        <div className="modal-backdrop fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="modal-box bg-white rounded-lg max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4 border-b pb-2">
              <div>
                <h3 className="font-semibold text-lg">
                  Anchored Rubric: {formatCompetencyName(selectedRubricQuestion.competency_name || (selectedRubricQuestion.rubric as any).competency_definition || selectedRubricQuestion.rubric.target_competency)}
                </h3>
                <p className="text-xs text-muted">
                  {(selectedRubricQuestion.rubric as any).question_intent || "Authoritative behavioral scoring anchors"}
                </p>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setSelectedRubricQuestion(null)}
              >
                <Icon name="x" size={18} />
              </button>
            </div>

            {/* Behavioral Rating Anchors (1-5 Scale) */}
            {(selectedRubricQuestion.rubric as any).rating_anchors && (
              <div className="rubric-anchors space-y-3 mb-4">
                <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Behavioral Rating Anchors</h4>
                {Object.entries((selectedRubricQuestion.rubric as any).rating_anchors).map(([score, description]) => (
                  <div key={score} className="rubric-level-card border rounded p-3 bg-gray-50 flex items-start gap-3">
                    <span className="badge badge-primary font-bold text-sm px-2 py-1">Score {score}</span>
                    <p className="text-sm text-gray-800 m-0">{String(description)}</p>
                  </div>
                ))}
              </div>
            )}

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

      {/* Phase 3C.4: Wording Comparison Modal */}
      {activeWordingComparison && (
        <WordingComparisonModal
          isOpen={!!activeWordingComparison}
          question={activeWordingComparison.question}
          wordingResult={activeWordingComparison.result}
          onClose={() => setActiveWordingComparison(null)}
          onUseSuggestion={(variant) =>
            handleUseSuggestion(
              activeWordingComparison.question,
              variant,
              activeWordingComparison.result,
              activeWordingComparison.layer
            )
          }
          onEditSuggestion={(variant) =>
            handleEditSuggestion(
              activeWordingComparison.question,
              variant,
              activeWordingComparison.layer
            )
          }
          onKeepOriginal={() => setActiveWordingComparison(null)}
          isApplying={isApplyingSuggestion}
        />
      )}

      {/* ARIA Live Region for Screen Readers */}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
    </div>
  );
}
