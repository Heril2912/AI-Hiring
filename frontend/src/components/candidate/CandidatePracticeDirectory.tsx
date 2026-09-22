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

  const fetchData = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const assignedRes = await getCandidatePracticeDiscovery().catch(() => ({ items: [] }));
      setPracticeJobs(assignedRes.items || []);
    } catch (err: any) {
      setError(err?.message || "Failed to load assigned practice interviews.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
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
          fetchData();
        }}
      />
    );
  }

  return (
    <div className="candidate-home-container" style={{ maxWidth: "960px", margin: "0 auto", padding: "16px 20px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "28px" }}>
        <div>
          <h1 style={{ fontSize: "24px", fontWeight: 700, color: "var(--text-primary, #0f172a)", margin: "0 0 8px 0" }}>
            Interactive Practice Interviews
          </h1>
          <p style={{ fontSize: "14px", color: "var(--text-secondary, #64748b)", margin: 0, lineHeight: 1.5 }}>
            Prepare for real interviews with AI-guided conversational scenarios and competency assessments released by your recruiter.
          </p>
        </div>

        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={fetchData}
          disabled={isLoading}
          title="Refresh assigned practice interviews"
          style={{ display: "inline-flex", alignItems: "center", gap: "6px", flexShrink: 0 }}
        >
          <Icon name="refresh" size={14} aria-hidden="true" />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="feedback-box error" role="alert" style={{ marginBottom: "20px" }}>
          <Icon name="alert-triangle" size={16} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: "center", padding: "60px 20px" }}>
          <div className="loading-spinner" style={{ margin: "0 auto 16px auto" }} />
          <p style={{ color: "var(--text-secondary, #64748b)", fontSize: "14px" }}>
            Loading assigned practice interviews...
          </p>
        </div>
      ) : practiceJobs.length === 0 ? (
        /* Case 0: No Practice Jobs Released Yet */
        <div className="candidate-welcome-card" style={{ marginTop: "20px" }}>
          <div className="candidate-welcome-icon-box">
            <Icon name="message-square" className="welcome-icon" aria-hidden="true" />
          </div>
          <h2 className="candidate-welcome-title">No assigned practice sessions yet</h2>
          <p className="candidate-welcome-description">
            Your recruiter has not released an interview practice module for your account yet. Once your recruiter assigns an interview session, it will automatically appear here ready for you to practice.
          </p>
          <div style={{ display: "flex", justifyContent: "center", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
            <span
              className="candidate-status-indicator"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                backgroundColor: "#f0fdf4",
                border: "1px solid #bbf7d0",
                color: "#166534",
                padding: "6px 14px",
                borderRadius: "9999px",
                fontSize: "12px",
                fontWeight: 600,
              }}
            >
              <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#22c55e" }} />
              Candidate Account Active
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchData}
            >
              <Icon name="refresh" size={13} aria-hidden="true" />
              <span>Check for Updates</span>
            </button>
          </div>
        </div>
      ) : practiceJobs.length === 1 ? (
        /* Case 1: Single Assigned Practice Interview - Dedicated Spotlight Card */
        (() => {
          const singleJob = practiceJobs[0];
          const isLaunching = launchingReleaseId === singleJob.release_id;
          const convCount = singleJob.conversation_question_count ?? singleJob.conversation_count ?? 0;
          const mcqCount = singleJob.mcq_count ?? 0;
          const revNum = singleJob.job_revision ?? 1;
          const estMinutes = (convCount * 5) + (mcqCount * 2) || 15;

          return (
            <div
              className="aiq-panel"
              style={{
                backgroundColor: "var(--surface-base, #ffffff)",
                border: "1px solid var(--border-subtle, #e2e8f0)",
                borderRadius: "12px",
                padding: "32px",
                boxShadow: "0 2px 8px rgba(0, 0, 0, 0.04)",
                display: "flex",
                flexDirection: "column",
                gap: "24px",
              }}
            >
              {/* Card Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        color: "#2563eb",
                        letterSpacing: "0.5px",
                        backgroundColor: "#eff6ff",
                        padding: "3px 8px",
                        borderRadius: "4px",
                        border: "1px solid #bfdbfe",
                      }}
                    >
                      Assigned Role Practice
                    </span>
                    <span style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)" }}>
                      Revision #{revNum}
                    </span>
                  </div>
                  <h2 style={{ fontSize: "22px", fontWeight: 700, color: "var(--text-primary, #0f172a)", margin: 0 }}>
                    {singleJob.job_title}
                  </h2>
                </div>

                <span
                  style={{
                    backgroundColor: "#f0fdf4",
                    color: "#166534",
                    fontSize: "12px",
                    fontWeight: 600,
                    padding: "6px 12px",
                    borderRadius: "16px",
                    border: "1px solid #bbf7d0",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#22c55e" }} />
                  Ready to Practice
                </span>
              </div>

              {/* Assessment Breakdown Blocks */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px" }}>
                <div
                  style={{
                    backgroundColor: "var(--surface-muted, #f8fafc)",
                    border: "1px solid var(--border-subtle, #e2e8f0)",
                    borderRadius: "8px",
                    padding: "16px 20px",
                  }}
                >
                  <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px", marginBottom: "4px" }}>
                    Conversational Questions
                  </span>
                  <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
                    {convCount} Questions
                  </div>
                  <span style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)", marginTop: "2px", display: "block" }}>
                    AI-evaluated interactive voice/text dialogue
                  </span>
                </div>

                <div
                  style={{
                    backgroundColor: "var(--surface-muted, #f8fafc)",
                    border: "1px solid var(--border-subtle, #e2e8f0)",
                    borderRadius: "8px",
                    padding: "16px 20px",
                  }}
                >
                  <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px", marginBottom: "4px" }}>
                    Multiple Choice Check
                  </span>
                  <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
                    {mcqCount} Questions
                  </div>
                  <span style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)", marginTop: "2px", display: "block" }}>
                    Timed technical concept verification
                  </span>
                </div>

                <div
                  style={{
                    backgroundColor: "var(--surface-muted, #f8fafc)",
                    border: "1px solid var(--border-subtle, #e2e8f0)",
                    borderRadius: "8px",
                    padding: "16px 20px",
                  }}
                >
                  <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px", marginBottom: "4px" }}>
                    Estimated Duration
                  </span>
                  <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
                    ~{estMinutes} Minutes
                  </div>
                  <span style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)", marginTop: "2px", display: "block" }}>
                    Self-paced practice session
                  </span>
                </div>
              </div>

              {/* Guidance Info Box */}
              <div
                style={{
                  padding: "14px 18px",
                  backgroundColor: "#eff6ff",
                  borderRadius: "8px",
                  border: "1px solid #bfdbfe",
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                }}
              >
                <Icon name="info" size={18} style={{ color: "#2563eb", flexShrink: 0 }} aria-hidden="true" />
                <p style={{ fontSize: "13px", color: "#1e40af", margin: 0, lineHeight: 1.5 }}>
                  This is a confidential practice interview tailored for your role. You can complete it at your own pace with instant rubric scoring and guidance.
                </p>
              </div>

              {/* Launch CTA */}
              <div>
                <button
                  type="button"
                  className="btn btn-primary btn-lg"
                  style={{
                    width: "100%",
                    justifyContent: "center",
                    padding: "14px 24px",
                    fontSize: "15px",
                    fontWeight: 600,
                  }}
                  onClick={() => handleStartSession(singleJob.release_id)}
                  disabled={isLaunching}
                >
                  {isLaunching ? (
                    <>
                      <div className="loading-spinner-sm" style={{ marginRight: "8px" }} />
                      <span>Starting Practice Interview...</span>
                    </>
                  ) : (
                    <>
                      <Icon name="play" size={16} aria-hidden="true" />
                      <span>Start Practice Interview</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })()
      ) : (
        /* Case >1: Multiple Practice Interviews Provided - Choice Mode */
        <div>
          <div
            style={{
              padding: "12px 16px",
              backgroundColor: "var(--surface-muted, #f8fafc)",
              border: "1px solid var(--border-subtle, #e2e8f0)",
              borderRadius: "8px",
              marginBottom: "20px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "14px",
              color: "var(--text-secondary, #475569)",
            }}
          >
            <Icon name="info" size={16} style={{ color: "#2563eb" }} aria-hidden="true" />
            <span>
              Your recruiter has provided <strong>{practiceJobs.length} practice interviews</strong>. Select a role below to start practicing:
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: "20px" }}>
            {practiceJobs.map((job) => {
              const isLaunching = launchingReleaseId === job.release_id;
              const convCount = job.conversation_question_count ?? job.conversation_count ?? 0;
              const mcqCount = job.mcq_count ?? 0;
              const revNum = job.job_revision ?? 1;
              const estMinutes = (convCount * 5) + (mcqCount * 2) || 15;

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
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "8px" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
                        <span style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", color: "#2563eb", letterSpacing: "0.5px" }}>
                          Practice Interview
                        </span>
                        <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)" }}>
                          • Rev #{revNum}
                        </span>
                      </div>
                      <h2 style={{ fontSize: "18px", fontWeight: 700, color: "var(--text-primary, #0f172a)", margin: 0 }}>
                        {job.job_title}
                      </h2>
                    </div>

                    <span
                      style={{
                        backgroundColor: "#f0fdf4",
                        color: "#166534",
                        fontSize: "11px",
                        fontWeight: 600,
                        padding: "3px 8px",
                        borderRadius: "12px",
                        border: "1px solid #bbf7d0",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Ready
                    </span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                    <div style={{ backgroundColor: "var(--surface-muted, #f8fafc)", padding: "10px 12px", borderRadius: "6px" }}>
                      <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block" }}>Conversational</span>
                      <strong style={{ fontSize: "14px", color: "var(--text-primary, #0f172a)" }}>{convCount} Questions</strong>
                    </div>
                    <div style={{ backgroundColor: "var(--surface-muted, #f8fafc)", padding: "10px 12px", borderRadius: "6px" }}>
                      <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", display: "block" }}>Multiple Choice</span>
                      <strong style={{ fontSize: "14px", color: "var(--text-primary, #0f172a)" }}>{mcqCount} Questions</strong>
                    </div>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: "8px", borderTop: "1px solid var(--border-subtle, #f1f5f9)" }}>
                    <span style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)" }}>
                      ~{estMinutes} Mins · Self-paced
                    </span>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => handleStartSession(job.release_id)}
                      disabled={isLaunching}
                    >
                      {isLaunching ? (
                        <>
                          <div className="loading-spinner-sm" style={{ marginRight: "6px" }} />
                          <span>Starting...</span>
                        </>
                      ) : (
                        <>
                          <Icon name="play" size={13} aria-hidden="true" />
                          <span>Start Practice</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
