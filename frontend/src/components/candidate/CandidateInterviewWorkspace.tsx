import React, { useEffect, useState, useRef } from "react";
import {
  CandidateInterviewQuestionDto,
  CandidateInterviewSessionResponse,
  getInterviewSession,
  saveInterviewAnswer,
  startOrResumeInterview,
  submitInterview,
} from "../../api/candidateInterviews";
import { Icon } from "../Icon";

interface CandidateInterviewWorkspaceProps {
  releaseId: string;
  onExit: () => void;
}

type WorkspaceView = "landing" | "question" | "review" | "submitted";
type SaveState = "idle" | "saving" | "saved" | "error";

export function CandidateInterviewWorkspace({
  releaseId,
  onExit,
}: CandidateInterviewWorkspaceProps) {
  const [session, setSession] = useState<CandidateInterviewSessionResponse | null>(null);
  const [currentView, setCurrentView] = useState<WorkspaceView>("landing");
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Edit buffer state for the active question
  const [textDraft, setTextDraft] = useState<string>("");
  const [mcqDraft, setMcqDraft] = useState<string>("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [lastSavedTimestamp, setLastSavedTimestamp] = useState<string | null>(null);

  // Incomplete confirmation dialog state
  const [showIncompleteModal, setShowIncompleteModal] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitReceipt, setSubmitReceipt] = useState<{
    submittedAt: string;
    message: string;
  } | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);

  // Sync draft buffers whenever currentQuestion changes
  const activeQuestion: CandidateInterviewQuestionDto | undefined =
    session?.questions[currentQuestionIndex];

  useEffect(() => {
    if (activeQuestion) {
      setTextDraft(activeQuestion.saved_text_answer || "");
      setMcqDraft(activeQuestion.saved_selected_option_id || "");
      setSaveState("idle");
    }
  }, [currentQuestionIndex, session?.questions]);

  // Initial load / fetch
  useEffect(() => {
    let isMounted = true;
    async function init() {
      try {
        setIsLoading(true);
        setError(null);
        // Start or resume
        const data = await startOrResumeInterview(releaseId);
        if (!isMounted) return;
        setSession(data);
        if (data.status === "SUBMITTED") {
          setCurrentView("submitted");
          setSubmitReceipt({
            submittedAt: data.submitted_at || new Date().toISOString(),
            message: "Your interview responses have been submitted.",
          });
        } else {
          // If already started and has answers, find first unanswered or start at 0
          const firstUnansweredIndex = data.questions.findIndex((q) => !q.is_answered);
          if (firstUnansweredIndex >= 0) {
            setCurrentQuestionIndex(firstUnansweredIndex);
          } else {
            setCurrentQuestionIndex(0);
          }
        }
      } catch (err: any) {
        if (!isMounted) return;
        setError(err?.message || "Failed to start or resume interview.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    init();
    return () => {
      isMounted = false;
    };
  }, [releaseId]);

  // Handle modal keyboard trap / escape
  useEffect(() => {
    if (showIncompleteModal && modalRef.current) {
      modalRef.current.focus();
    }
  }, [showIncompleteModal]);

  const handleKeyDownModal = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setShowIncompleteModal(false);
    }
  };

  const handleSaveAnswer = async (
    customText?: string,
    customMcq?: string
  ): Promise<boolean> => {
    if (!session || !activeQuestion || session.status === "SUBMITTED") return false;

    const t = customText !== undefined ? customText : textDraft;
    const m = customMcq !== undefined ? customMcq : mcqDraft;

    const payload = {
      text_answer: activeQuestion.question_format === "CONVERSATIONAL" ? t : undefined,
      selected_option_id: activeQuestion.question_format === "MCQ" ? m : undefined,
    };

    try {
      setSaveState("saving");
      const res = await saveInterviewAnswer(session.session_id, activeQuestion.slot_id, payload);
      setSaveState("saved");
      setLastSavedTimestamp(new Date(res.saved_at).toLocaleTimeString());

      // Update local session state without reloading all
      setSession((prev) => {
        if (!prev) return null;
        const updatedQuestions = prev.questions.map((q) => {
          if (q.slot_id === activeQuestion.slot_id) {
            return {
              ...q,
              saved_text_answer: payload.text_answer ?? null,
              saved_selected_option_id: payload.selected_option_id ?? null,
              is_answered: res.is_answered,
              saved_at: res.saved_at,
            };
          }
          return q;
        });
        return {
          ...prev,
          answered_questions: res.answered_questions,
          last_saved_at: res.saved_at,
          questions: updatedQuestions,
        };
      });
      return true;
    } catch (err: any) {
      setSaveState("error");
      setError(err?.message || "Could not save answer. Please retry.");
      return false;
    }
  };

  const handleSaveAndContinue = async () => {
    if (!session) return;
    await handleSaveAnswer();
    if (currentQuestionIndex < session.questions.length - 1) {
      setCurrentQuestionIndex((prev) => prev + 1);
    } else {
      setCurrentView("review");
    }
  };

  const handlePrevious = () => {
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex((prev) => prev - 1);
    }
  };

  const handleGoToQuestion = (index: number) => {
    setCurrentQuestionIndex(index);
    setCurrentView("question");
  };

  const handleReviewClick = async () => {
    // Optionally save current question first if modified
    if (
      activeQuestion &&
      ((activeQuestion.question_format === "CONVERSATIONAL" &&
        textDraft !== (activeQuestion.saved_text_answer || "")) ||
        (activeQuestion.question_format === "MCQ" &&
          mcqDraft !== (activeQuestion.saved_selected_option_id || "")))
    ) {
      await handleSaveAnswer();
    }
    setCurrentView("review");
  };

  const executeFinalSubmit = async (confirmedIncomplete: boolean = false) => {
    if (!session) return;
    try {
      setIsSubmitting(true);
      setError(null);
      const res = await submitInterview(session.session_id, {
        confirmed_incomplete: confirmedIncomplete,
      });
      setSubmitReceipt({
        submittedAt: res.submitted_at,
        message: res.message,
      });
      setSession((prev) => (prev ? { ...prev, status: "SUBMITTED", submitted_at: res.submitted_at } : null));
      setShowIncompleteModal(false);
      setCurrentView("submitted");
    } catch (err: any) {
      setError(err?.message || "Failed to submit interview.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitAttempt = () => {
    if (!session) return;
    const unansweredCount = session.total_questions - session.answered_questions;
    if (unansweredCount > 0) {
      setShowIncompleteModal(true);
    } else {
      executeFinalSubmit(false);
    }
  };

  if (isLoading) {
    return (
      <div className="candidate-home-container" style={{ maxWidth: "800px", margin: "40px auto", padding: "20px", textAlign: "center" }}>
        <div className="loading-spinner" style={{ margin: "0 auto 16px auto" }} />
        <p style={{ color: "var(--text-secondary, #64748b)", fontSize: "15px" }}>
          Loading official interview session...
        </p>
      </div>
    );
  }

  if (error && !session) {
    return (
      <div className="candidate-home-container" style={{ maxWidth: "800px", margin: "40px auto", padding: "20px" }}>
        <div className="feedback-box error" role="alert" style={{ marginBottom: "20px" }}>
          <Icon name="alert-triangle" size={18} aria-hidden="true" />
          <span>{error}</span>
        </div>
        <button type="button" className="btn btn-secondary" onClick={onExit}>
          Return to Interviews
        </button>
      </div>
    );
  }

  if (!session) return null;

  // -------------------------------------------------------------
  // 1. SUBMITTED STATE
  // -------------------------------------------------------------
  if (currentView === "submitted" || session.status === "SUBMITTED") {
    const formattedDate = session.submitted_at
      ? new Date(session.submitted_at).toLocaleString()
      : submitReceipt?.submittedAt
      ? new Date(submitReceipt.submittedAt).toLocaleString()
      : new Date().toLocaleString();

    return (
      <div
        className="candidate-home-container"
        style={{ maxWidth: "760px", margin: "32px auto", padding: "20px" }}
      >
        <div
          tabIndex={-1}
          role="region"
          aria-label="Interview Submitted Receipt"
          style={{
            backgroundColor: "var(--surface-base, #ffffff)",
            border: "1px solid var(--border-subtle, #e2e8f0)",
            borderRadius: "12px",
            padding: "36px 32px",
            textAlign: "center",
            boxShadow: "0 1px 4px rgba(0, 0, 0, 0.05)",
          }}
        >
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "50%",
              backgroundColor: "#f0fdf4",
              border: "1px solid #bbf7d0",
              color: "#166534",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: "20px",
            }}
          >
            <Icon name="check-circle" size={30} aria-hidden="true" />
          </div>

          <span
            style={{
              fontSize: "12px",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              color: "#059669",
              display: "block",
              marginBottom: "8px",
            }}
          >
            Official Submission Receipt
          </span>

          <h1
            style={{
              fontSize: "24px",
              fontWeight: 700,
              color: "var(--text-primary, #0f172a)",
              margin: "0 0 12px 0",
            }}
          >
            Interview Submitted Successfully
          </h1>

          <p
            style={{
              fontSize: "15px",
              color: "var(--text-secondary, #475569)",
              maxWidth: "540px",
              margin: "0 auto 24px auto",
              lineHeight: 1.6,
            }}
          >
            Your answers for <strong>{session.job_title}</strong> (Rev #{session.job_revision}) have been locked and submitted to the hiring team.
          </p>

          <div
            style={{
              backgroundColor: "var(--surface-muted, #f8fafc)",
              border: "1px solid var(--border-subtle, #e2e8f0)",
              borderRadius: "8px",
              padding: "16px 20px",
              maxWidth: "480px",
              margin: "0 auto 28px auto",
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "12px",
              textAlign: "left",
            }}
          >
            <div>
              <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block" }}>
                Submission Time
              </span>
              <strong style={{ fontSize: "13px", color: "var(--text-primary, #0f172a)" }}>
                {formattedDate}
              </strong>
            </div>
            <div>
              <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block" }}>
                Answers Recorded
              </span>
              <strong style={{ fontSize: "13px", color: "var(--text-primary, #0f172a)" }}>
                {session.answered_questions} of {session.total_questions} Questions
              </strong>
            </div>
          </div>

          <p
            style={{
              fontSize: "13px",
              color: "var(--text-secondary, #64748b)",
              marginBottom: "28px",
            }}
          >
            The hiring team will review your application and interview submission.
          </p>

          <button
            type="button"
            className="btn btn-primary"
            onClick={onExit}
            style={{ minWidth: "180px" }}
          >
            Return to Interviews
          </button>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------
  // 2. LANDING STATE
  // -------------------------------------------------------------
  if (currentView === "landing") {
    const isResuming = session.answered_questions > 0;

    return (
      <div
        className="candidate-home-container"
        style={{ maxWidth: "760px", margin: "32px auto", padding: "20px" }}
      >
        <div
          style={{
            backgroundColor: "var(--surface-base, #ffffff)",
            border: "1px solid var(--border-subtle, #e2e8f0)",
            borderRadius: "12px",
            padding: "32px",
            boxShadow: "0 1px 3px rgba(0, 0, 0, 0.05)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.5px",
                color: "#2563eb",
                backgroundColor: "#eff6ff",
                padding: "2px 8px",
                borderRadius: "4px",
                border: "1px solid #bfdbfe",
              }}
            >
              Official Interview
            </span>
            <span style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)" }}>
              Job Revision #{session.job_revision}
            </span>
          </div>

          <h1
            style={{
              fontSize: "24px",
              fontWeight: 700,
              color: "var(--text-primary, #0f172a)",
              margin: "0 0 16px 0",
            }}
          >
            {session.job_title}
          </h1>

          <p
            style={{
              fontSize: "14px",
              color: "var(--text-secondary, #475569)",
              lineHeight: 1.6,
              marginBottom: "24px",
            }}
          >
            Welcome to your official interview workspace. Your responses will be saved directly to the system as you progress. You can review and revise any answer before final submission.
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: "14px",
              marginBottom: "28px",
            }}
          >
            <div
              style={{
                backgroundColor: "var(--surface-muted, #f8fafc)",
                padding: "14px 16px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle, #e2e8f0)",
              }}
            >
              <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block" }}>
                Total Questions
              </span>
              <strong style={{ fontSize: "18px", color: "var(--text-primary, #0f172a)" }}>
                {session.total_questions}
              </strong>
            </div>

            <div
              style={{
                backgroundColor: "var(--surface-muted, #f8fafc)",
                padding: "14px 16px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle, #e2e8f0)",
              }}
            >
              <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block" }}>
                Saved Progress
              </span>
              <strong style={{ fontSize: "18px", color: "var(--text-primary, #0f172a)" }}>
                {session.answered_questions} of {session.total_questions} answered
              </strong>
            </div>
          </div>

          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setCurrentView("question")}
              style={{ minWidth: "160px" }}
            >
              {isResuming ? "Resume Interview" : "Begin Interview"}
            </button>

            <button type="button" className="btn btn-secondary" onClick={onExit}>
              Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------
  // 3. REVIEW STATE
  // -------------------------------------------------------------
  if (currentView === "review") {
    const unansweredCount = session.total_questions - session.answered_questions;

    return (
      <div
        className="candidate-home-container"
        style={{ maxWidth: "840px", margin: "28px auto", padding: "20px" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: 700, color: "var(--text-primary, #0f172a)", margin: "0 0 4px 0" }}>
              Review Interview Answers
            </h1>
            <p style={{ fontSize: "14px", color: "var(--text-secondary, #64748b)", margin: 0 }}>
              {session.job_title} · Revision #{session.job_revision}
            </p>
          </div>

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setCurrentView("question")}
          >
            Back to Workspace
          </button>
        </div>

        {error && (
          <div className="feedback-box error" role="alert" style={{ marginBottom: "16px" }}>
            <Icon name="alert-triangle" size={16} aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        {/* Summary Card */}
        <div
          style={{
            backgroundColor: "var(--surface-base, #ffffff)",
            border: "1px solid var(--border-subtle, #e2e8f0)",
            borderRadius: "10px",
            padding: "20px",
            marginBottom: "24px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "16px",
          }}
        >
          <div style={{ display: "flex", gap: "24px" }}>
            <div>
              <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block" }}>
                Answered
              </span>
              <strong style={{ fontSize: "20px", color: "#166534" }}>
                {session.answered_questions} / {session.total_questions}
              </strong>
            </div>
            {unansweredCount > 0 && (
              <div>
                <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block" }}>
                  Unanswered
                </span>
                <strong style={{ fontSize: "20px", color: "#b45309" }}>
                  {unansweredCount}
                </strong>
              </div>
            )}
          </div>

          <div style={{ textAlign: "right" }}>
            <span style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)", display: "block", marginBottom: "6px" }}>
              Submission is final and cannot be edited.
            </span>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSubmitAttempt}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Submitting..." : "Submit Interview"}
            </button>
          </div>
        </div>

        {/* Questions Compact List */}
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {session.questions.map((q, idx) => {
            const hasAnswer = q.is_answered;
            let previewText = "No answer recorded";
            if (q.question_format === "CONVERSATIONAL" && q.saved_text_answer) {
              previewText = q.saved_text_answer;
            } else if (q.question_format === "MCQ" && q.saved_selected_option_id) {
              const opt = q.options.find((o) => o.option_id === q.saved_selected_option_id);
              previewText = opt ? `Selected: ${opt.label}` : "Option selected";
            }

            return (
              <div
                key={q.slot_id}
                style={{
                  backgroundColor: "var(--surface-base, #ffffff)",
                  border: "1px solid var(--border-subtle, #e2e8f0)",
                  borderRadius: "8px",
                  padding: "16px 20px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "16px",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                    <span style={{ fontSize: "12px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
                      Question {idx + 1}
                    </span>
                    <span
                      style={{
                        fontSize: "11px",
                        padding: "2px 6px",
                        borderRadius: "4px",
                        backgroundColor: hasAnswer ? "#f0fdf4" : "#fef3c7",
                        color: hasAnswer ? "#166534" : "#92400e",
                        fontWeight: 600,
                      }}
                    >
                      {hasAnswer ? "Answered" : "Unanswered"}
                    </span>
                    {q.is_supplemental && (
                      <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)" }}>
                        (Supplemental)
                      </span>
                    )}
                  </div>
                  <p
                    style={{
                      fontSize: "13px",
                      color: "var(--text-secondary, #475569)",
                      margin: "0 0 6px 0",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {q.question_text}
                  </p>
                  <p
                    style={{
                      fontSize: "12px",
                      color: hasAnswer ? "var(--text-primary, #0f172a)" : "var(--text-secondary, #94a3b8)",
                      margin: 0,
                      fontStyle: hasAnswer ? "normal" : "italic",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {previewText}
                  </p>
                </div>

                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleGoToQuestion(idx)}
                >
                  Edit
                </button>
              </div>
            );
          })}
        </div>

        {/* Incomplete Submission Confirmation Modal */}
        {showIncompleteModal && (
          <div
            className="modal-backdrop"
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(15, 23, 42, 0.6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
              padding: "16px",
            }}
            onKeyDown={handleKeyDownModal}
          >
            <div
              ref={modalRef}
              tabIndex={-1}
              role="dialog"
              aria-modal="true"
              aria-labelledby="incomplete-dialog-title"
              style={{
                backgroundColor: "var(--surface-base, #ffffff)",
                borderRadius: "12px",
                maxWidth: "480px",
                width: "100%",
                padding: "28px",
                boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
                <Icon name="alert-triangle" size={22} style={{ color: "#d97706" }} aria-hidden="true" />
                <h2
                  id="incomplete-dialog-title"
                  style={{ fontSize: "18px", fontWeight: 700, color: "var(--text-primary, #0f172a)", margin: 0 }}
                >
                  Incomplete Interview
                </h2>
              </div>

              <p style={{ fontSize: "14px", color: "var(--text-secondary, #475569)", lineHeight: 1.5, margin: "0 0 20px 0" }}>
                You have <strong>{unansweredCount} unanswered question{unansweredCount === 1 ? "" : "s"}</strong>. Once submitted, you will not be able to return or change your answers. Are you sure you want to submit now?
              </p>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowIncompleteModal(false)}
                  disabled={isSubmitting}
                >
                  Continue Answering
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => executeFinalSubmit(true)}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Submitting..." : "Yes, Submit Incomplete"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // -------------------------------------------------------------
  // 4. QUESTION WORKSPACE STATE
  // -------------------------------------------------------------
  if (!activeQuestion) return null;

  const progressPercentage = Math.round(
    (session.answered_questions / session.total_questions) * 100
  );

  return (
    <div
      className="candidate-home-container"
      style={{ maxWidth: "800px", margin: "24px auto", padding: "16px 20px" }}
    >
      {/* Top Bar with Header, Progress & Review Nav */}
      <div style={{ marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <div>
            <span style={{ fontSize: "12px", fontWeight: 700, color: "#2563eb", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Official Interview · {session.job_title}
            </span>
            <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary, #0f172a)" }}>
              Question {currentQuestionIndex + 1} of {session.total_questions}
            </div>
          </div>

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleReviewClick}
          >
            Review all ({session.answered_questions}/{session.total_questions})
          </button>
        </div>

        {/* Accessible Progress Bar */}
        <div
          role="progressbar"
          aria-valuenow={session.answered_questions}
          aria-valuemin={0}
          aria-valuemax={session.total_questions}
          aria-label={`Interview progress: ${session.answered_questions} of ${session.total_questions} questions answered`}
          style={{
            height: "6px",
            backgroundColor: "var(--border-subtle, #e2e8f0)",
            borderRadius: "3px",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${progressPercentage}%`,
              backgroundColor: "#2563eb",
              transition: "width 0.3s ease",
            }}
          />
        </div>
      </div>

      {error && (
        <div className="feedback-box error" role="alert" style={{ marginBottom: "16px" }}>
          <Icon name="alert-triangle" size={16} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Question Card */}
      <div
        style={{
          backgroundColor: "var(--surface-base, #ffffff)",
          border: "1px solid var(--border-subtle, #e2e8f0)",
          borderRadius: "12px",
          padding: "28px",
          marginBottom: "20px",
          boxShadow: "0 1px 3px rgba(0, 0, 0, 0.05)",
        }}
      >
        {activeQuestion.is_supplemental && (
          <span
            style={{
              display: "inline-block",
              fontSize: "11px",
              fontWeight: 700,
              backgroundColor: "#f1f5f9",
              color: "#475569",
              padding: "2px 8px",
              borderRadius: "4px",
              marginBottom: "10px",
            }}
          >
            Supplemental Question
          </span>
        )}

        <h2
          style={{
            fontSize: "18px",
            fontWeight: 600,
            color: "var(--text-primary, #0f172a)",
            lineHeight: 1.5,
            margin: "0 0 24px 0",
          }}
        >
          {activeQuestion.question_text}
        </h2>

        {/* Answer Input depending on Question Format */}
        {activeQuestion.question_format === "CONVERSATIONAL" ? (
          <div>
            <label
              htmlFor={`answer-text-${activeQuestion.slot_id}`}
              style={{
                display: "block",
                fontSize: "13px",
                fontWeight: 600,
                color: "var(--text-secondary, #475569)",
                marginBottom: "8px",
              }}
            >
              Your Answer
            </label>
            <textarea
              id={`answer-text-${activeQuestion.slot_id}`}
              rows={6}
              value={textDraft}
              onChange={(e) => setTextDraft(e.target.value)}
              placeholder="Type your response here..."
              style={{
                width: "100%",
                padding: "12px 14px",
                fontSize: "14px",
                lineHeight: 1.5,
                border: "1px solid var(--border-subtle, #cbd5e1)",
                borderRadius: "8px",
                boxSizing: "border-box",
                fontFamily: "inherit",
              }}
            />
          </div>
        ) : (
          <div>
            <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
              <legend
                style={{
                  fontSize: "13px",
                  fontWeight: 600,
                  color: "var(--text-secondary, #475569)",
                  marginBottom: "12px",
                }}
              >
                Select an option
              </legend>

              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {activeQuestion.options.map((option) => {
                  const isChecked = mcqDraft === option.option_id;
                  return (
                    <label
                      key={option.option_id}
                      htmlFor={`opt-${option.option_id}`}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "12px",
                        padding: "12px 16px",
                        borderRadius: "8px",
                        border: isChecked
                          ? "1.5px solid #2563eb"
                          : "1px solid var(--border-subtle, #e2e8f0)",
                        backgroundColor: isChecked ? "#eff6ff" : "var(--surface-base, #ffffff)",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <input
                        type="radio"
                        id={`opt-${option.option_id}`}
                        name={`question-mcq-${activeQuestion.slot_id}`}
                        value={option.option_id}
                        checked={isChecked}
                        onChange={() => setMcqDraft(option.option_id)}
                        style={{ accentColor: "#2563eb" }}
                      />
                      <span style={{ fontSize: "14px", color: "var(--text-primary, #0f172a)" }}>
                        {option.label}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          </div>
        )}

        {/* Live Saving Status Feedback */}
        <div
          aria-live="polite"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: "16px",
            fontSize: "12px",
            color: "var(--text-secondary, #64748b)",
          }}
        >
          <div>
            {saveState === "saving" && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", color: "#2563eb" }}>
                <Icon name="refresh" size={12} className="spinning" aria-hidden="true" />
                Saving answer...
              </span>
            )}
            {saveState === "saved" && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", color: "#166534" }}>
                <Icon name="check" size={12} aria-hidden="true" />
                Saved {lastSavedTimestamp ? `at ${lastSavedTimestamp}` : ""}
              </span>
            )}
            {saveState === "error" && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: "4px", color: "#b45309" }}>
                <Icon name="alert-triangle" size={12} aria-hidden="true" />
                Could not save
              </span>
            )}
            {saveState === "idle" && activeQuestion.saved_at && (
              <span>Last saved: {new Date(activeQuestion.saved_at).toLocaleTimeString()}</span>
            )}
          </div>

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => handleSaveAnswer()}
            disabled={saveState === "saving"}
            style={{ fontSize: "12px" }}
          >
            Save answer
          </button>
        </div>
      </div>

      {/* Navigation Controls */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handlePrevious}
          disabled={currentQuestionIndex === 0}
        >
          Previous
        </button>

        <div style={{ display: "flex", gap: "10px" }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSaveAndContinue}
            disabled={saveState === "saving"}
          >
            {currentQuestionIndex < session.questions.length - 1
              ? "Save and continue"
              : "Save & Review answers"}
          </button>
        </div>
      </div>
    </div>
  );
}
