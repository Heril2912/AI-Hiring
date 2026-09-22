import React, { useEffect, useRef, useState } from "react";
import {
  PracticeMessageDto,
  PracticeSessionDetailResponse,
  abandonPracticeSession,
  getPracticeSessionState,
  submitConversationalAnswer,
  submitMcqAnswer,
} from "../../api/candidatePracticeSession";
import { Icon } from "../Icon";

interface CandidatePracticeRoomProps {
  sessionId: string;
  onExit: () => void;
}

export function CandidatePracticeRoom({ sessionId, onExit }: CandidatePracticeRoomProps) {
  const [session, setSession] = useState<PracticeSessionDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Conversational response state
  const [answerText, setAnswerText] = useState<string>("");

  // MCQ response state
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);

  // Timer countdown
  const [timeRemaining, setTimeRemaining] = useState<number>(0);

  // Auto-scroll ref
  const chatStreamEndRef = useRef<HTMLDivElement>(null);

  const fetchSessionState = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getPracticeSessionState(sessionId);
      setSession(data);
      setTimeRemaining(data.time_remaining_seconds || 0);
    } catch (err: any) {
      setError(err?.message || "Failed to load practice session.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSessionState();
  }, [sessionId]);

  // Scroll to bottom when messages update
  useEffect(() => {
    if (chatStreamEndRef.current) {
      chatStreamEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [session?.messages]);

  // Countdown timer effect
  useEffect(() => {
    if (timeRemaining <= 0 || session?.lifecycle_status !== "IN_PROGRESS") return;

    const timer = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          // Refresh state on expiration
          fetchSessionState();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [timeRemaining, session?.lifecycle_status]);

  const formatTimer = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hrs > 0) {
      return `${hrs}h ${mins.toString().padStart(2, "0")}m`;
    }
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const handleConversationalSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!session || !session.active_question || isSubmitting) return;

    const trimmed = answerText.trim();
    if (!trimmed) {
      setError("Please enter your answer before submitting.");
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      const updated = await submitConversationalAnswer(
        session.session_id,
        session.active_question.question_id,
        trimmed
      );
      setSession(updated);
      setTimeRemaining(updated.time_remaining_seconds || 0);
      setAnswerText("");
    } catch (err: any) {
      setError(err?.message || "Failed to submit your response.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleMcqSubmit = async () => {
    if (!session || !session.active_question || !selectedOptionId || isSubmitting) return;

    try {
      setIsSubmitting(true);
      setError(null);
      const updated = await submitMcqAnswer(
        session.session_id,
        session.active_question.question_id,
        selectedOptionId
      );
      setSession(updated);
      setTimeRemaining(updated.time_remaining_seconds || 0);
      setSelectedOptionId(null);
    } catch (err: any) {
      setError(err?.message || "Failed to submit your selection.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAbandon = async () => {
    if (!session) return;
    const confirm = window.confirm(
      "Are you sure you want to exit and abandon this practice interview? Incomplete sessions will not be saved."
    );
    if (!confirm) return;

    try {
      setIsLoading(true);
      await abandonPracticeSession(session.session_id);
      onExit();
    } catch (err: any) {
      setError(err?.message || "Failed to abandon session.");
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleConversationalSubmit();
    }
  };

  if (isLoading && !session) {
    return (
      <div className="candidate-home-container" style={{ padding: "60px 20px" }}>
        <div style={{ textAlign: "center" }}>
          <div className="loading-spinner" style={{ margin: "0 auto 16px auto" }} />
          <p style={{ color: "var(--text-secondary, #64748b)", fontSize: "15px" }}>
            Preparing your practice interview room...
          </p>
        </div>
      </div>
    );
  }

  if (error && !session) {
    return (
      <div className="candidate-home-container" style={{ padding: "40px 20px" }}>
        <div className="feedback-box error" role="alert" style={{ marginBottom: "20px" }}>
          <Icon name="alert-triangle" size={16} />
          <span>{error}</span>
        </div>
        <button type="button" className="btn btn-secondary" onClick={onExit}>
          Back to Directory
        </button>
      </div>
    );
  }

  if (!session) return null;

  // Calculate Progress Percentage
  const totalQuestions = (session.total_conv_count || 0) + (session.total_mcq_count || 0);
  let completedCount = session.total_response_count || 0;
  if (session.lifecycle_status === "COMPLETED") {
    completedCount = totalQuestions;
  }
  const progressPercent =
    totalQuestions > 0 ? Math.min(100, Math.round((completedCount / totalQuestions) * 100)) : 0;

  return (
    <div className="practice-room-layout">
      {/* Header */}
      <header className="practice-room-header">
        <div className="practice-header-meta">
          <h1 className="practice-header-title">
            <span>Role Practice Interview</span>
            <span
              className="badge"
              style={{
                backgroundColor: "#f0fdf4",
                color: "#166534",
                fontSize: "11px",
                border: "1px solid #bbf7d0",
              }}
            >
              Private Session
            </span>
          </h1>
          <div className="practice-header-subtitle">
            {session.current_section === "CONVERSATION" && (
              <span>
                Conversational Section • Question {session.current_conv_index + 1} of{" "}
                {session.total_conv_count}
              </span>
            )}
            {session.current_section === "MCQ" && (
              <span>
                Multiple Choice Section • Question {session.current_mcq_index + 1} of{" "}
                {session.total_mcq_count}
              </span>
            )}
            {session.current_section === "COMPLETE" && (
              <span>Practice Completed • All Sections Finished</span>
            )}
          </div>
        </div>

        <div className="practice-header-actions">
          {session.lifecycle_status === "IN_PROGRESS" && (
            <div className="practice-timer-badge" title="Session expires in 24 hours">
              <Icon name="clock" size={13} />
              <span>{formatTimer(timeRemaining)}</span>
            </div>
          )}

          {session.lifecycle_status === "IN_PROGRESS" ? (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleAbandon}
              title="Abandon practice session"
            >
              Exit Session
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={onExit}
            >
              Back to Directory
            </button>
          )}
        </div>
      </header>

      {/* Progress Strip */}
      <div className="practice-progress-strip">
        <div className="practice-progress-fill" style={{ width: `${progressPercent}%` }} />
      </div>

      {/* Optional Safe Fallback Banner */}
      {session.safe_fallback_notice && (
        <div className="practice-fallback-banner" role="status">
          <Icon name="info" size={14} />
          <span>{session.safe_fallback_notice}</span>
        </div>
      )}

      {/* Chat Stream Transcript */}
      <div className="practice-chat-stream" role="log" aria-label="Practice transcript">
        {session.messages.map((msg: PracticeMessageDto) => {
          const isInterviewer = msg.role === "INTERVIEWER";
          const isCandidate = msg.role === "CANDIDATE";

          let kindLabel = "";
          let kindClass = "primary";
          if (msg.message_kind === "GREETING") {
            kindLabel = "Welcome";
            kindClass = "ack";
          } else if (msg.message_kind === "PRIMARY_QUESTION") {
            kindLabel = "Primary Prompt";
            kindClass = "primary";
          } else if (msg.message_kind === "FOLLOW_UP") {
            kindLabel = "Follow-up Prompt";
            kindClass = "follow-up";
          } else if (msg.message_kind === "ACKNOWLEDGEMENT") {
            kindLabel = "Interviewer Note";
            kindClass = "ack";
          } else if (msg.message_kind === "ANSWER") {
            kindLabel = "Your Answer";
            kindClass = "answer";
          }

          return (
            <div
              key={msg.message_id}
              className={`practice-message-bubble ${
                isInterviewer ? "interviewer" : isCandidate ? "candidate" : "system"
              }`}
            >
              <div className={`practice-avatar ${isInterviewer ? "interviewer" : "candidate"}`}>
                {isInterviewer ? <Icon name="sparkles" size={16} /> : <Icon name="user" size={16} />}
              </div>

              <div className="practice-bubble-content-card">
                <div className="practice-bubble-header">
                  <span className="practice-bubble-sender">
                    {isInterviewer ? "AI Practice Interviewer" : "You"}
                  </span>
                  {kindLabel && (
                    <span className={`practice-bubble-kind-chip ${kindClass}`}>{kindLabel}</span>
                  )}
                </div>
                <div className="practice-bubble-text">{msg.text}</div>
              </div>
            </div>
          );
        })}
        <div ref={chatStreamEndRef} />
      </div>

      {/* Error banner if submission failed */}
      {error && (
        <div style={{ padding: "0 24px" }}>
          <div className="feedback-box error" role="alert" style={{ margin: "12px 0 0 0" }}>
            <Icon name="alert-triangle" size={14} />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Input / Composer Area */}
      {session.lifecycle_status === "IN_PROGRESS" && (
        <div className="practice-composer-panel">
          {session.current_section === "CONVERSATION" && session.active_question && (
            <form onSubmit={handleConversationalSubmit}>
              <div style={{ marginBottom: "8px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary, #475569)" }}>
                  Competency: {session.active_question.competency_name}
                </span>
                {session.active_question.turn_count_for_question === 0 ? (
                  <span style={{ fontSize: "11px", color: "var(--text-muted, #64748b)" }}>
                    Initial Response (1 follow-up possible)
                  </span>
                ) : (
                  <span style={{ fontSize: "11px", color: "#92400e", fontWeight: 600 }}>
                    Final Turn on this Question
                  </span>
                )}
              </div>

              <textarea
                className="practice-composer-textarea"
                placeholder="Type your structured response here... (Press Ctrl+Enter or Cmd+Enter to submit)"
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value.slice(0, 2000))}
                onKeyDown={handleKeyDown}
                disabled={isSubmitting}
                rows={4}
                aria-label="Your response"
              />

              <div className="practice-composer-footer">
                <span>
                  {answerText.length} / 2000 characters
                </span>

                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isSubmitting || answerText.trim().length === 0}
                >
                  {isSubmitting ? (
                    <>
                      <div className="loading-spinner-sm" style={{ marginRight: "6px" }} />
                      <span>Submitting...</span>
                    </>
                  ) : (
                    <>
                      <span>Submit Response</span>
                      <Icon name="chevron-right" size={14} />
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {session.current_section === "MCQ" && session.active_question && (
            <div className="practice-mcq-container">
              <div className="practice-mcq-question-box">
                <div style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", color: "#4f46e5", marginBottom: "4px" }}>
                  Knowledge Check • {session.active_question.competency_name}
                </div>
                <h3 className="practice-mcq-question-wording">
                  {session.active_question.wording}
                </h3>
              </div>

              <div className="practice-mcq-options-grid" role="radiogroup" aria-label="Multiple choice options">
                {(session.active_question.options || []).map((opt, index) => {
                  const letter = String.fromCharCode(65 + index);
                  const isSelected = selectedOptionId === opt.option_id;

                  return (
                    <div
                      key={opt.option_id}
                      className={`practice-mcq-option-item ${isSelected ? "selected" : ""}`}
                      onClick={() => !isSubmitting && setSelectedOptionId(opt.option_id)}
                      role="radio"
                      aria-checked={isSelected}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === " " || e.key === "Enter") {
                          e.preventDefault();
                          setSelectedOptionId(opt.option_id);
                        }
                      }}
                    >
                      <span className="practice-mcq-option-letter">{letter}</span>
                      <span className="practice-mcq-option-label">{opt.text}</span>
                    </div>
                  );
                })}
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "14px" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleMcqSubmit}
                  disabled={isSubmitting || !selectedOptionId}
                >
                  {isSubmitting ? (
                    <>
                      <div className="loading-spinner-sm" style={{ marginRight: "6px" }} />
                      <span>Saving Selection...</span>
                    </>
                  ) : (
                    <>
                      <span>Submit Answer & Continue</span>
                      <Icon name="chevron-right" size={14} />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Completion View */}
      {session.lifecycle_status === "COMPLETED" && (
        <div className="practice-completed-view">
          <div className="practice-completed-icon">
            <Icon name="check-circle" size={32} />
          </div>
          <div>
            <h2 style={{ fontSize: "20px", fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>
              Practice Interview Completed!
            </h2>
            <p style={{ fontSize: "14px", color: "#64748b", maxWidth: "480px", margin: "0 auto", lineHeight: 1.5 }}>
              You have completed all conversational questions and multiple-choice knowledge checks for this session.
            </p>
          </div>

          <div
            style={{
              display: "flex",
              gap: "24px",
              backgroundColor: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: "8px",
              padding: "16px 24px",
            }}
          >
            <div>
              <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase", fontWeight: 600, display: "block" }}>
                Conversational Turns
              </span>
              <span style={{ fontSize: "18px", fontWeight: 700, color: "#0f172a" }}>
                {session.total_conv_count} Questions
              </span>
            </div>
            <div style={{ borderLeft: "1px solid #e2e8f0", paddingLeft: "24px" }}>
              <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase", fontWeight: 600, display: "block" }}>
                MCQ Checks
              </span>
              <span style={{ fontSize: "18px", fontWeight: 700, color: "#0f172a" }}>
                {session.total_mcq_count} Questions
              </span>
            </div>
          </div>

          <button
            type="button"
            className="btn btn-primary"
            onClick={onExit}
            style={{ marginTop: "12px" }}
          >
            Return to Practice Directory
          </button>
        </div>
      )}

      {/* Abandoned or Expired View */}
      {(session.lifecycle_status === "ABANDONED" || session.lifecycle_status === "EXPIRED") && (
        <div className="practice-completed-view">
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "50%",
              backgroundColor: "#f1f5f9",
              color: "#475569",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Icon name="alert-circle" size={28} />
          </div>
          <div>
            <h2 style={{ fontSize: "18px", fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>
              {session.lifecycle_status === "ABANDONED" ? "Session Abandoned" : "Session Expired"}
            </h2>
            <p style={{ fontSize: "14px", color: "#64748b", maxWidth: "440px", margin: "0 auto", lineHeight: 1.5 }}>
              This practice session is closed. You can start a fresh session from your practice directory at any time (up to 3 attempts per 24 hours).
            </p>
          </div>
          <button type="button" className="btn btn-secondary" onClick={onExit}>
            Return to Directory
          </button>
        </div>
      )}
    </div>
  );
}
