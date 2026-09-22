import React, { useEffect, useState } from "react";
import { getCandidatePracticeDiscovery } from "../../api/candidatePractice";
import { startOrResumePracticeSession } from "../../api/candidatePracticeSession";
import { CandidatePracticeJobSummary } from "../../types/ai_question_set";
import { Icon } from "../Icon";
import { CandidatePracticeRoom } from "./CandidatePracticeRoom";

export function CandidatePracticeDirectory() {
  const [practiceJobs, setPracticeJobs] = useState<CandidatePracticeJobSummary[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [launchingReleaseId, setLaunchingReleaseId] = useState<string | null>(null);

  const fetchDiscovery = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await getCandidatePracticeDiscovery();
      setPracticeJobs(res.items || []);
    } catch (err: any) {
      setError(err?.message || "Failed to load practice interviews.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDiscovery();
  }, []);

  const handleStartSession = async (releaseId: string) => {
    try {
      setLaunchingReleaseId(releaseId);
      setError(null);
      const session = await startOrResumePracticeSession(releaseId);
      setActiveSessionId(session.session_id);
    } catch (err: any) {
      setError(err?.message || "Failed to start practice interview.");
    } finally {
      setLaunchingReleaseId(null);
    }
  };

  if (activeSessionId) {
    return (
      <CandidatePracticeRoom
        sessionId={activeSessionId}
        onExit={() => {
          setActiveSessionId(null);
          fetchDiscovery();
        }}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="candidate-home-container" style={{ padding: "40px 20px" }}>
        <div style={{ textAlign: "center" }}>
          <div className="loading-spinner" style={{ margin: "0 auto 12px auto" }} />
          <p style={{ color: "var(--text-secondary, #64748b)", fontSize: "14px" }}>
            Loading your practice interviews...
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="candidate-home-container" style={{ padding: "40px 20px" }}>
        <div className="feedback-box error" role="alert" style={{ marginBottom: "16px" }}>
          <Icon name="alert-triangle" size={16} />
          <span>{error}</span>
        </div>
        <button type="button" className="btn btn-secondary" onClick={fetchDiscovery}>
          Retry
        </button>
      </div>
    );
  }

  if (practiceJobs.length === 0) {
    return (
      <div className="candidate-home-container">
        <div className="candidate-welcome-card">
          <div className="candidate-welcome-icon-box">
            <Icon name="message-square" className="welcome-icon" aria-hidden="true" />
          </div>
          <h1 className="candidate-welcome-title">Practice interviews will appear here</h1>
          <p className="candidate-welcome-description">
            Your recruiting team will release personalized practice interview sessions to your portal. Once assigned, you will be able to prepare, test your skills, and receive structured feedback.
          </p>
          <div className="candidate-status-indicator">
            <span className="status-dot" aria-hidden="true" />
            <span className="status-text">Practice portal is active and connected</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="candidate-home-container" style={{ maxWidth: "960px", margin: "0 auto", padding: "32px 20px" }}>
      <div style={{ marginBottom: "28px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
          <h1 style={{ fontSize: "24px", fontWeight: 700, color: "var(--text-primary, #0f172a)", margin: 0 }}>
            Assigned Practice Interviews
          </h1>
          <span
            className="badge badge-info"
            style={{ fontSize: "12px", padding: "3px 8px" }}
          >
            {practiceJobs.length} {practiceJobs.length === 1 ? "Session" : "Sessions"} Available
          </span>
        </div>
        <p style={{ fontSize: "14px", color: "var(--text-secondary, #64748b)", margin: 0 }}>
          Review the roles assigned by your recruiting team below. Each session combines conversational interview questions and practical multiple-choice knowledge checks.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: "20px" }}>
        {practiceJobs.map((job) => {
          const isLaunching = launchingReleaseId === job.release_id;

          return (
            <div
              key={job.release_id}
              className="aiq-panel"
              style={{
                backgroundColor: "var(--surface-base, #ffffff)",
                border: "1px solid var(--border-subtle, #e2e8f0)",
                borderRadius: "10px",
                padding: "24px",
                display: "flex",
                flexDirection: "column",
                gap: "16px",
                boxShadow: "0 1px 3px rgba(0, 0, 0, 0.05)",
              }}
            >
              {/* Card Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: "var(--accent-primary, #3b82f6)",
                      letterSpacing: "0.5px",
                      display: "block",
                      marginBottom: "4px",
                    }}
                  >
                    Role Practice Interview
                  </span>
                  <h2 style={{ fontSize: "18px", fontWeight: 700, color: "var(--text-primary, #0f172a)", margin: 0 }}>
                    {job.job_title}
                  </h2>
                </div>
                <span
                  className="badge"
                  style={{
                    backgroundColor: "#ecfdf5",
                    color: "#065f46",
                    fontSize: "12px",
                    fontWeight: 600,
                    padding: "4px 8px",
                    borderRadius: "6px",
                    border: "1px solid #a7f3d0",
                  }}
                >
                  Ready
                </span>
              </div>

              {/* Questions Composition */}
              <div
                style={{
                  backgroundColor: "var(--surface-muted, #f8fafc)",
                  borderRadius: "8px",
                  padding: "12px 16px",
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "12px",
                }}
              >
                <div>
                  <span style={{ fontSize: "11px", color: "var(--text-muted, #64748b)", display: "block", textTransform: "uppercase", fontWeight: 600 }}>
                    Conversational
                  </span>
                  <span style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
                    {job.conversation_count} Questions
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: "11px", color: "var(--text-muted, #64748b)", display: "block", textTransform: "uppercase", fontWeight: 600 }}>
                    Multiple Choice
                  </span>
                  <span style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
                    {job.mcq_count} Questions
                  </span>
                </div>
              </div>

              {/* Card Information */}
              <div style={{ fontSize: "13px", color: "var(--text-secondary, #475569)", lineHeight: 1.5 }}>
                This practice session covers foundational competencies for the role. Once started, you will respond to structured scenario prompts followed by multiple-choice knowledge assessments.
              </div>

              {/* Launch Action */}
              <div style={{ marginTop: "4px" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ width: "100%", justifyContent: "center" }}
                  onClick={() => handleStartSession(job.release_id)}
                  disabled={isLaunching}
                >
                  {isLaunching ? (
                    <>
                      <div className="loading-spinner-sm" style={{ marginRight: "6px" }} />
                      <span>Starting Practice Session...</span>
                    </>
                  ) : (
                    <>
                      <Icon name="play" size={14} />
                      <span>Start Practice Interview</span>
                    </>
                  )}
                </button>
              </div>

              {/* Card Footer */}
              <div
                style={{
                  marginTop: "auto",
                  paddingTop: "12px",
                  borderTop: "1px solid var(--border-subtle, #f1f5f9)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  fontSize: "12px",
                  color: "var(--text-muted, #64748b)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <Icon name="calendar" size={13} />
                  <span>Released {new Date(job.released_at).toLocaleDateString()}</span>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "4px", color: "var(--accent-primary, #3b82f6)", fontWeight: 500 }}>
                  <Icon name="check-circle" size={13} />
                  <span>Private Session</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

