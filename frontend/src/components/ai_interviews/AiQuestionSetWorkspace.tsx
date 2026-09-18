import React, { useEffect, useRef, useState } from "react";
import { apiFetch } from "../../api/client";
import { Icon } from "../Icon";
import {
  AiQuestionSetDetail,
  AiQuestionSlotItem,
  AiQuestionSetValidateResult,
  AiQuestionSetApproveResult,
  SafeRubricDto,
} from "../../types/ai_question_set";
import { SafeRubricModal } from "./SafeRubricModal";
import "./ai-interviews.css";

interface AiQuestionSetWorkspaceProps {
  templateId: string;
  onNavigateBack: () => void;
}

export function AiQuestionSetWorkspace({
  templateId,
  onNavigateBack,
}: AiQuestionSetWorkspaceProps) {
  const [detail, setDetail] = useState<AiQuestionSetDetail | null>(null);
  const [activeSlotIndex, setActiveSlotIndex] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isRegenerating, setIsRegenerating] = useState<boolean>(false);
  const [isUpdatingSlot, setIsUpdatingSlot] = useState<boolean>(false);
  const [isApproving, setIsApproving] = useState<boolean>(false);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [validationResult, setValidationResult] = useState<AiQuestionSetValidateResult | null>(null);
  const [activeRubric, setActiveRubric] = useState<{ rubric: SafeRubricDto; competencyName: string } | null>(null);

  // Edit wording state
  const [isEditingWording, setIsEditingWording] = useState<boolean>(false);
  const [editedWordingText, setEditedWordingText] = useState<string>("");
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  // Ref to return focus to rubric button after closing modal
  const viewRubricBtnRef = useRef<HTMLButtonElement>(null);

  // Humanize helpers
  const humanizeCompetency = (raw: string) => {
    return raw
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const humanizeReviewState = (state: string) => {
    switch (state) {
      case "KEPT":
        return "Reviewed";
      case "EDITED":
        return "Edited";
      case "REVISED":
        return "Regenerated";
      case "RECRUITER_AUTHORED":
        return "Written by recruiter";
      case "UNREVIEWED":
      default:
        return "To review";
    }
  };

  const humanizeType = (type: string) => {
    return type
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const loadQuestionSet = async (isInitial = false) => {
    try {
      if (isInitial) setIsLoading(true);
      setError(null);
      const res = await apiFetch<AiQuestionSetDetail>(`/api/v1/ai-interviews/${templateId}`);
      setDetail(res);
      if (res.slots && res.slots.length > 0) {
        setEditedWordingText(res.slots[activeSlotIndex]?.ai_wording || "");
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load AI question set.");
    } finally {
      if (isInitial) setIsLoading(false);
    }
  };

  useEffect(() => {
    loadQuestionSet(true);
  }, [templateId]);

  const activeSlot: AiQuestionSlotItem | undefined = detail?.slots?.[activeSlotIndex];

  useEffect(() => {
    if (activeSlot) {
      setEditedWordingText(activeSlot.ai_wording || "");
      setIsEditingWording(false);
    }
  }, [activeSlotIndex]);

  const handleDecision = async (
    decision: "KEEP" | "EDIT" | "RECRUITER_AUTHORED" | "REVISE",
    wording?: string
  ) => {
    if (!activeSlot || detail?.is_immutable) return;

    try {
      setIsUpdatingSlot(true);
      setActionFeedback(null);
      const updatedDetail = await apiFetch<AiQuestionSetDetail>(
        `/api/v1/ai-interviews/${templateId}/items/${activeSlot.slot_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            decision,
            wording: wording !== undefined ? wording : activeSlot.ai_wording,
          }),
        }
      );
      setDetail(updatedDetail);
      setIsEditingWording(false);

      const feedbackMsg =
        decision === "KEEP"
          ? "Question wording marked as reviewed."
          : decision === "EDIT"
          ? "Custom question wording saved."
          : "Question slot updated.";
      setActionFeedback(feedbackMsg);

      // Advance to the next unreviewed slot if available
      if (decision === "KEEP" && updatedDetail.slots) {
        const nextUnreviewedIdx = updatedDetail.slots.findIndex(
          (s, idx) => idx > activeSlotIndex && s.review_state === "UNREVIEWED"
        );
        if (nextUnreviewedIdx !== -1) {
          setActiveSlotIndex(nextUnreviewedIdx);
        }
      }
    } catch (err: any) {
      setError(err?.message || "Failed to update slot decision.");
    } finally {
      setIsUpdatingSlot(false);
    }
  };

  const handleRegenerateSlot = async () => {
    if (!activeSlot || detail?.is_immutable) return;

    try {
      setIsRegenerating(true);
      setError(null);
      setActionFeedback(null);
      const updatedDetail = await apiFetch<AiQuestionSetDetail>(
        `/api/v1/ai-interviews/${templateId}/regenerate-slot/${activeSlot.slot_id}`,
        { method: "POST" }
      );
      setDetail(updatedDetail);
      setActionFeedback("Slot question wording regenerated via local model.");
    } catch (err: any) {
      setError(err?.message || "Slot regeneration failed. Ensure local AI provider is active.");
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleValidateSet = async () => {
    try {
      setIsValidating(true);
      setError(null);
      const res = await apiFetch<AiQuestionSetValidateResult>(
        `/api/v1/ai-interviews/${templateId}/validate`,
        { method: "POST" }
      );
      setValidationResult(res);
    } catch (err: any) {
      setError(err?.message || "Validation failed.");
    } finally {
      setIsValidating(false);
    }
  };

  const handleApproveSet = async () => {
    if (detail?.is_immutable) return;

    try {
      setIsApproving(true);
      setError(null);
      const res = await apiFetch<AiQuestionSetApproveResult>(
        `/api/v1/ai-interviews/${templateId}/approve`,
        { method: "POST" }
      );
      await loadQuestionSet();
      setActionFeedback(`AI question set approved and sealed.`);
    } catch (err: any) {
      setError(err?.message || "Approval failed. Please resolve review items and retry.");
    } finally {
      setIsApproving(false);
    }
  };

  const handleCloseRubric = () => {
    setActiveRubric(null);
    // Return focus to View Rubric button for keyboard accessibility
    setTimeout(() => {
      viewRubricBtnRef.current?.focus();
    }, 50);
  };

  if (isLoading) {
    return (
      <div className="aiq-workspace-page">
        <div className="aiq-panel" style={{ textAlign: "center", padding: "48px 24px" }}>
          <div className="loading-spinner" style={{ margin: "0 auto 12px auto" }} />
          <p className="aiq-panel-desc">Loading AI question set...</p>
        </div>
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="aiq-workspace-page">
        <div className="feedback-box error" role="alert" style={{ marginBottom: "16px" }}>
          <Icon name="alert-triangle" size={16} />
          <span>{error}</span>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onNavigateBack}>
          <Icon name="arrow-left" size={14} />
          <span>Back to AI Questions</span>
        </button>
      </div>
    );
  }

  if (!detail) return null;

  const isApproved = detail.lifecycle_status === "APPROVED" || detail.is_immutable;
  const isStale = detail.is_source_stale || detail.lifecycle_status === "STALE";
  const reviewedCount = detail.reviewed_slots_count || 0;
  const totalCount = detail.total_slots_count || detail.slots.length;
  const progressPercent = totalCount > 0 ? Math.round((reviewedCount / totalCount) * 100) : 0;
  const allReviewed = totalCount > 0 && reviewedCount === totalCount;
  const canApprove = !isApproved && !isStale && (validationResult?.is_valid || allReviewed);

  return (
    <div className="aiq-workspace-page">
      {/* Live Region for Screen Readers */}
      <div className="sr-only" aria-live="polite">
        {actionFeedback || (isRegenerating ? "Regenerating question wording..." : "")}
      </div>

      {/* Back Button */}
      <button
        type="button"
        className="aiq-back-btn"
        onClick={onNavigateBack}
        aria-label="Back to AI Questions"
      >
        <Icon name="arrow-left" size={16} />
        <span>Back to AI Questions</span>
      </button>

      {/* Workspace Header */}
      <header className="aiq-workspace-header">
        <div className="aiq-header-left">
          <div className="aiq-workspace-title-row">
            <h1 className="aiq-workspace-title">{detail.job_title}</h1>
            <span
              className={`aiq-status-badge ${
                isApproved
                  ? "approved"
                  : isStale
                  ? "stale"
                  : detail.lifecycle_status === "VALIDATED"
                  ? "validated"
                  : "draft"
              }`}
            >
              {isApproved && <Icon name="lock" size={11} />}
              {isApproved
                ? "Approved & Sealed"
                : isStale
                ? "Blueprint Stale"
                : detail.lifecycle_status === "VALIDATED"
                ? "Ready for Approval"
                : "Draft"}
            </span>
          </div>

          <div className="aiq-progress-group">
            <span className="aiq-progress-text">
              {reviewedCount} of {totalCount} reviewed
            </span>
            <div className="aiq-progress-track">
              <div
                className={`aiq-progress-fill ${progressPercent === 100 ? "complete" : ""}`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* Header Actions */}
        <div className="aiq-header-actions">
          {!isApproved && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleValidateSet}
              disabled={isValidating}
            >
              <Icon name="check-circle" size={15} />
              <span>{isValidating ? "Validating…" : "Validate questions"}</span>
            </button>
          )}

          {canApprove && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleApproveSet}
              disabled={isApproving}
            >
              <Icon name="shield-check" size={15} />
              <span>{isApproving ? "Sealing…" : "Approve & Seal"}</span>
            </button>
          )}
        </div>
      </header>

      {/* Stale Blueprint Warning */}
      {isStale && (
        <div
          className="aiq-panel"
          style={{
            backgroundColor: "var(--status-warn-bg, #fffbeb)",
            borderColor: "var(--status-warn-border, #fde68a)",
            marginBottom: "20px",
            display: "flex",
            alignItems: "flex-start",
            gap: "12px",
          }}
        >
          <Icon name="alert-triangle" size={18} style={{ color: "var(--status-warn, #d97706)", flexShrink: 0, marginTop: "2px" }} />
          <div>
            <strong style={{ display: "block", color: "#92400e", marginBottom: "2px", fontSize: "15px" }}>
              Job Requirements Modified
            </strong>
            <p style={{ color: "#78350f", fontSize: "14px", margin: 0 }}>
              {detail.stale_reason || "The approved job requirements have changed. Please regenerate or re-verify questions."}
            </p>
          </div>
        </div>
      )}

      {/* Validation Result Box */}
      {validationResult && (
        <div
          className={`aiq-panel ${validationResult.is_valid ? "" : "feedback-box error"}`}
          style={{
            backgroundColor: validationResult.is_valid ? "#ecfdf5" : undefined,
            borderColor: validationResult.is_valid ? "#a7f3d0" : undefined,
            color: validationResult.is_valid ? "#065f46" : undefined,
            marginBottom: "20px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 600 }}>
            <Icon name={validationResult.is_valid ? "check-circle" : "alert-circle"} size={16} />
            <span>{validationResult.safe_message}</span>
          </div>
          {validationResult.blocking_errors && validationResult.blocking_errors.length > 0 && (
            <ul style={{ paddingLeft: "20px", marginTop: "8px", fontSize: "14px" }}>
              {validationResult.blocking_errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Action Notification */}
      {actionFeedback && (
        <div
          className="aiq-panel"
          style={{
            backgroundColor: "var(--accent-subtle, #eef1fc)",
            borderColor: "var(--accent-border, #d4dbf8)",
            color: "var(--accent-primary, #4f5bd5)",
            padding: "12px 16px",
            marginBottom: "20px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "14px",
            fontWeight: 500,
          }}
        >
          <Icon name="check" size={16} />
          <span>{actionFeedback}</span>
        </div>
      )}

      {/* Workspace 2-Column Layout */}
      <div className="aiq-workspace-layout">
        {/* Left: Question Navigator */}
        <nav className="aiq-question-navigation" aria-label="Question slots navigator">
          <div className="aiq-nav-header">
            <span>Questions</span>
            <span>{reviewedCount}/{totalCount} Reviewed</span>
          </div>

          {detail.slots.map((slot, index) => {
            const isActive = index === activeSlotIndex;
            const isReviewed = slot.review_state !== "UNREVIEWED";
            const numStr = String(index + 1).padStart(2, "0");
            const badgeClass = isReviewed ? (slot.review_state === "EDITED" ? "edited" : "reviewed") : "to-review";

            return (
              <button
                key={slot.slot_id}
                type="button"
                className={`aiq-nav-item ${isActive ? "aiq-active" : ""}`}
                onClick={() => setActiveSlotIndex(index)}
              >
                <span className="aiq-nav-num">{numStr}</span>
                <div className="aiq-nav-content">
                  <div className="aiq-nav-title">{humanizeCompetency(slot.competency_name)}</div>
                  <div className="aiq-nav-sub">
                    {humanizeType(slot.question_type)} · {slot.estimated_time_minutes} min
                  </div>
                  <span className={`aiq-nav-state-badge ${badgeClass}`}>
                    {humanizeReviewState(slot.review_state)}
                  </span>
                </div>
              </button>
            );
          })}
        </nav>

        {/* Right: Question Editor */}
        <main className="aiq-question-editor">
          {activeSlot ? (
            <>
              {/* Editor Header */}
              <div className="aiq-editor-header">
                <div>
                  <div className="aiq-editor-slot-meta">
                    Question {activeSlotIndex + 1} of {totalCount} · {humanizeType(activeSlot.question_type)} · {activeSlot.estimated_time_minutes} minutes
                  </div>
                  <h2 className="aiq-editor-competency">
                    {humanizeCompetency(activeSlot.competency_name)}
                  </h2>
                </div>

                {activeSlot.rubric && (
                  <button
                    ref={viewRubricBtnRef}
                    type="button"
                    className="aiq-rubric-btn"
                    onClick={() =>
                      setActiveRubric({
                        rubric: activeSlot.rubric!,
                        competencyName: activeSlot.competency_name,
                      })
                    }
                  >
                    <Icon name="file-text" size={15} />
                    <span>View rubric</span>
                  </button>
                )}
              </div>

              {/* Question Wording Surface */}
              <section className="aiq-wording-section" aria-label="Question text">
                {isEditingWording ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    <label htmlFor="aiq-wording-editor" className="sr-only">
                      Edit interview question wording
                    </label>
                    <textarea
                      id="aiq-wording-editor"
                      className="aiq-wording-textarea"
                      value={editedWordingText}
                      onChange={(e) => setEditedWordingText(e.target.value)}
                      placeholder="Enter tailored question wording for this competency slot..."
                      rows={4}
                    />
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setEditedWordingText(activeSlot.ai_wording || "");
                          setIsEditingWording(false);
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => handleDecision("EDIT", editedWordingText)}
                        disabled={!editedWordingText.trim() || isUpdatingSlot}
                      >
                        Save question
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="aiq-wording-display">
                      {activeSlot.ai_wording ? (
                        activeSlot.ai_wording
                      ) : (
                        <span className="aiq-wording-empty">No question generated yet for this slot.</span>
                      )}
                    </div>

                    {!isApproved && (
                      <div className="aiq-wording-tools">
                        <button
                          type="button"
                          className="aiq-tool-btn"
                          onClick={() => setIsEditingWording(true)}
                        >
                          <Icon name="edit" size={14} />
                          <span>Edit question</span>
                        </button>

                        <button
                          type="button"
                          className="aiq-tool-btn"
                          onClick={handleRegenerateSlot}
                          disabled={isRegenerating || isUpdatingSlot}
                        >
                          <Icon name="refresh" size={14} className={isRegenerating ? "animate-spin" : ""} />
                          <span>{isRegenerating ? "Regenerating…" : "Regenerate"}</span>
                        </button>
                      </div>
                    )}
                  </>
                )}
              </section>

              {/* Permitted Probes */}
              {activeSlot.permitted_probes && activeSlot.permitted_probes.length > 0 && (
                <section className="aiq-probes-section">
                  <h3 className="aiq-probes-title">Permitted follow-up probes</h3>
                  <ul className="aiq-probes-list">
                    {activeSlot.permitted_probes.map((probe, i) => (
                      <li key={i}>{probe}</li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Decision Bottom Bar */}
              {!isApproved && (
                <div className="aiq-decision-bar">
                  <span className="aiq-decision-prompt">
                    Confirm this question is suitable for the interview.
                  </span>

                  {activeSlot.ai_wording ? (
                    <button
                      type="button"
                      className={`aiq-review-btn ${activeSlot.review_state === "KEPT" ? "is-reviewed" : ""}`}
                      onClick={() => handleDecision("KEEP")}
                      disabled={isUpdatingSlot}
                    >
                      <Icon name="check" size={16} />
                      <span>{activeSlot.review_state === "KEPT" ? "Reviewed" : "Mark as reviewed"}</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="aiq-review-btn"
                      onClick={handleRegenerateSlot}
                      disabled={isRegenerating}
                    >
                      <Icon name="sparkles" size={16} />
                      <span>Generate this question</span>
                    </button>
                  )}
                </div>
              )}
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "48px 0", color: "var(--text-muted, #64748b)" }}>
              Select a question from the left navigation to view and review.
            </div>
          )}
        </main>
      </div>

      {/* Rubric Modal Dialog */}
      {activeRubric && (
        <SafeRubricModal
          rubric={activeRubric.rubric}
          competencyName={activeRubric.competencyName}
          onClose={handleCloseRubric}
        />
      )}
    </div>
  );
}
