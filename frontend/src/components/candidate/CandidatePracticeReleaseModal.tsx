import React, { useState, useEffect, useCallback } from "react";
import {
  listEligibleJobsForPracticeRelease,
  listCandidatePracticeReleases,
  releasePracticeToCandidate,
  revokeCandidatePracticeRelease,
  PracticeEligibleJob,
} from "../../api/candidatePractice";
import { RecruiterPracticeReleaseSummary } from "../../types/ai_question_set";
import { Icon } from "../Icon";

interface CandidatePracticeReleaseModalProps {
  candidateId: string;
  candidateName: string;
  isOpen: boolean;
  onClose: () => void;
}

export function CandidatePracticeReleaseModal({
  candidateId,
  candidateName,
  isOpen,
  onClose,
}: CandidatePracticeReleaseModalProps) {
  const [eligibleJobs, setEligibleJobs] = useState<PracticeEligibleJob[]>([]);
  const [releases, setReleases] = useState<RecruiterPracticeReleaseSummary[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isReleasing, setIsReleasing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!candidateId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [jobsRes, releasesRes] = await Promise.all([
        listEligibleJobsForPracticeRelease(candidateId),
        listCandidatePracticeReleases(candidateId),
      ]);
      setEligibleJobs(jobsRes.items || []);
      setReleases(releasesRes || []);
      const firstUnreleased = (jobsRes.items || []).find((j) => !j.already_released);
      if (firstUnreleased) {
        setSelectedJobId(firstUnreleased.job_id);
      } else if (jobsRes.items && jobsRes.items.length > 0) {
        setSelectedJobId(jobsRes.items[0].job_id);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load practice release data.");
    } finally {
      setIsLoading(false);
    }
  }, [candidateId]);

  useEffect(() => {
    if (isOpen) {
      fetchData();
      setSuccessMessage(null);
      setError(null);
    }
  }, [isOpen, fetchData]);

  if (!isOpen) return null;

  const handleRelease = async () => {
    if (!selectedJobId) return;
    setIsReleasing(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const res = await releasePracticeToCandidate(candidateId, selectedJobId);
      setSuccessMessage(`Practice interview for "${res.job_title}" successfully released to ${candidateName}.`);
      await fetchData();
    } catch (err: any) {
      setError(err?.message || "Failed to release practice interview.");
    } finally {
      setIsReleasing(false);
    }
  };

  const handleRevoke = async (releaseId: string) => {
    setError(null);
    setSuccessMessage(null);
    try {
      await revokeCandidatePracticeRelease(releaseId);
      setSuccessMessage("Practice interview release revoked.");
      await fetchData();
    } catch (err: any) {
      setError(err?.message || "Failed to revoke practice release.");
    }
  };

  const selectedJob = eligibleJobs.find((j) => j.job_id === selectedJobId);

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="practice-release-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-container candidate-invitation-modal" style={{ maxWidth: "680px" }}>
        <header className="modal-header">
          <div className="modal-title-group">
            <Icon name="briefcase" className="modal-title-icon" aria-hidden="true" />
            <h2 id="practice-release-modal-title" className="modal-title">
              Release Practice Interview: {candidateName}
            </h2>
          </div>
          <button
            type="button"
            className="btn-icon-close"
            onClick={onClose}
            aria-label="Close modal"
          >
            <Icon name="x" aria-hidden="true" />
          </button>
        </header>

        <div className="modal-body">
          <p className="modal-description">
            Release an approved, sealed interview practice set to {candidateName}. The candidate will discover this practice session in their portal. Correct answers and scoring rubrics are never exposed.
          </p>

          {error && (
            <div className="modal-alert modal-alert-error" role="alert">
              <Icon name="alert-triangle" aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div
              className="feedback-box success"
              role="status"
              style={{
                marginBottom: "16px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                backgroundColor: "#ecfdf5",
                borderColor: "#a7f3d0",
                color: "#065f46",
                padding: "10px 14px",
                borderRadius: "6px",
              }}
            >
              <Icon name="check" aria-hidden="true" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Release Action Section */}
          <div className="invitation-create-section">
            <div className="create-controls" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div className="form-group-inline" style={{ width: "100%", justifyContent: "space-between" }}>
                <label htmlFor="practice-job-select" style={{ fontWeight: 600 }}>
                  Approved Practice Job
                </label>
                <select
                  id="practice-job-select"
                  className="form-select form-select-sm"
                  value={selectedJobId}
                  onChange={(e) => setSelectedJobId(e.target.value)}
                  disabled={isReleasing || eligibleJobs.length === 0}
                  style={{ minWidth: "280px" }}
                >
                  {eligibleJobs.length === 0 ? (
                    <option value="">No approved interview sets available</option>
                  ) : (
                    eligibleJobs.map((job) => (
                      <option key={job.job_id} value={job.job_id}>
                        {job.job_title} ({job.conversation_count} Conv, {job.mcq_count} MCQ){job.already_released ? " [Released]" : ""}
                      </option>
                    ))
                  )}
                </select>
              </div>

              {selectedJob && (
                <div
                  style={{
                    backgroundColor: "var(--surface-muted, #f8fafc)",
                    padding: "10px 14px",
                    borderRadius: "6px",
                    fontSize: "13px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span>
                    Questions: <strong>{selectedJob.conversation_count}</strong> Conversational · <strong>{selectedJob.mcq_count}</strong> MCQs
                  </span>
                  {selectedJob.already_released ? (
                    <span className="badge badge-info">Currently Active for Candidate</span>
                  ) : (
                    <span className="badge badge-success">Ready to Release</span>
                  )}
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleRelease}
                  disabled={isReleasing || !selectedJobId || selectedJob?.already_released}
                >
                  <Icon name="check-circle" aria-hidden="true" />
                  <span>{isReleasing ? "Releasing..." : "Release to Candidate"}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Release History Table */}
          <section className="invitation-history-section" aria-label="Practice Release History">
            <h3 className="section-subtitle">Practice Release History</h3>

            {isLoading ? (
              <div className="loading-state-inline" role="status">
                <div className="spinner-inline" />
                <span>Loading releases...</span>
              </div>
            ) : releases.length === 0 ? (
              <div className="empty-history-text">
                No practice interviews have been released to this candidate yet.
              </div>
            ) : (
              <div className="invitation-table-wrapper">
                <table className="invitation-table">
                  <thead>
                    <tr>
                      <th scope="col">Job Title</th>
                      <th scope="col">Questions</th>
                      <th scope="col">Released At</th>
                      <th scope="col">Status</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {releases.map((rel) => {
                      const isRevocable = rel.status === "RELEASED";
                      return (
                        <tr key={rel.release_id}>
                          <td style={{ fontWeight: 600 }}>{rel.job_title}</td>
                          <td>
                            {rel.conversation_count} Conv, {rel.mcq_count} MCQ
                          </td>
                          <td>{new Date(rel.released_at).toLocaleDateString()}</td>
                          <td>
                            <span
                              className="badge"
                              style={{
                                backgroundColor: isRevocable ? "#ecfdf5" : "#f1f5f9",
                                color: isRevocable ? "#065f46" : "#64748b",
                                textTransform: "uppercase",
                                fontSize: "11px",
                              }}
                            >
                              {rel.status}
                            </span>
                          </td>
                          <td>
                            {isRevocable ? (
                              <button
                                type="button"
                                className="btn btn-secondary btn-xs"
                                onClick={() => handleRevoke(rel.release_id)}
                                aria-label={`Revoke release for ${rel.job_title}`}
                              >
                                <Icon name="slash" aria-hidden="true" />
                                <span>Revoke</span>
                              </button>
                            ) : (
                              <span className="text-muted">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <footer className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  );
}
