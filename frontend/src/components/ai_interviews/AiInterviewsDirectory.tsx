import React, { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import { Icon } from "../Icon";
import {
  AiQuestionSetDirectory,
  AiQuestionSetDetail,
  EligibleJobItem,
  EligibleJobsResponse,
} from "../../types/ai_question_set";
import "./ai-interviews.css";

interface AiInterviewsDirectoryProps {
  onSelectTemplate: (templateId: string) => void;
  onNavigateToJobs?: () => void;
}

export function AiInterviewsDirectory({
  onSelectTemplate,
  onNavigateToJobs,
}: AiInterviewsDirectoryProps) {
  const [eligibleJobs, setEligibleJobs] = useState<EligibleJobItem[]>([]);
  const [recentDirectory, setRecentDirectory] = useState<AiQuestionSetDirectory | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isLoadingJobs, setIsLoadingJobs] = useState<boolean>(true);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [isLocalAiError, setIsLocalAiError] = useState<boolean>(false);

  const loadData = async () => {
    setIsLoadingJobs(true);
    setGenerationError(null);
    try {
      const [jobsRes, recentRes] = await Promise.allSettled([
        apiFetch<EligibleJobsResponse>("/api/v1/ai-interviews/eligible-jobs"),
        apiFetch<AiQuestionSetDirectory>("/api/v1/ai-interviews"),
      ]);

      if (jobsRes.status === "fulfilled" && jobsRes.value?.items) {
        setEligibleJobs(jobsRes.value.items);
      } else if (jobsRes.status === "rejected") {
        try {
          const altRes = await apiFetch<EligibleJobsResponse>("/api/v1/ai-question-sets/eligible-jobs");
          setEligibleJobs(altRes.items || []);
        } catch {
          setEligibleJobs([]);
        }
      }

      if (recentRes.status === "fulfilled" && recentRes.value) {
        setRecentDirectory(recentRes.value);
      }
    } catch {
      setEligibleJobs([]);
    } finally {
      setIsLoadingJobs(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Phase 3E.2 deduplication: Exclude jobs that already have an AI question set in existing work
  const existingJobIds = new Set(
    recentDirectory?.sets
      ?.filter((s) => (s.generated_question_count ?? 0) > 0)
      .map((s) => s.job_id) || []
  );
  const selectableJobs = eligibleJobs.filter(
    (job) => !existingJobIds.has(job.job_id) && !job.current_ai_set_id
  );

  // Clear selection if it becomes ineligible
  useEffect(() => {
    if (selectedJobId && !selectableJobs.some((j) => j.job_id === selectedJobId)) {
      setSelectedJobId(null);
    }
  }, [selectableJobs, selectedJobId]);

  const selectedJob = selectableJobs.find((j) => j.job_id === selectedJobId);

  const handleAction = async () => {
    if (!selectedJob || isGenerating) return;

    setIsGenerating(true);
    setGenerationError(null);
    setIsLocalAiError(false);

    try {
      const res = await apiFetch<AiQuestionSetDetail>("/api/v1/ai-interviews/generate", {
        method: "POST",
        body: JSON.stringify({ job_id: selectedJob.job_id }),
      });

      if (res && (res.ai_set_id || res.template_id)) {
        // Refresh local data so state remains perfectly in sync
        loadData();
        onSelectTemplate(res.ai_set_id || res.template_id || "");
      }
    } catch (err: any) {
      const msg = err?.message || "";
      if (
        msg.toLowerCase().includes("local ai") ||
        msg.toLowerCase().includes("model") ||
        msg.toLowerCase().includes("lm studio") ||
        msg.toLowerCase().includes("unavailable") ||
        msg.toLowerCase().includes("503")
      ) {
        setIsLocalAiError(true);
        setGenerationError("Local AI is unavailable. Start the configured local model and try again.");
      } else if (
        msg.toLowerCase().includes("requirements") ||
        msg.toLowerCase().includes("not ready") ||
        msg.toLowerCase().includes("400") ||
        msg.toLowerCase().includes("404")
      ) {
        setGenerationError("This job needs approved requirements before questions can be generated.");
      } else {
        setGenerationError("Local AI is unavailable. Start the configured local model and try again.");
        setIsLocalAiError(true);
      }
    } finally {
      setIsGenerating(false);
    }
  };

  const filteredJobs = selectableJobs.filter((job) =>
    job.job_title.toLowerCase().includes(searchQuery.toLowerCase().trim())
  );

  const formatStatus = (status: string, isStale?: boolean, isLegacy?: boolean) => {
    if (isLegacy) return "Legacy set";
    if (isStale || status === "STALE") return "Stale";
    if (status === "APPROVED") return "Approved";
    if (status === "VALIDATED") return "Ready for Review";
    return "Draft";
  };

  const formatLifecycleAction = (status: string, isStale?: boolean, isLegacy?: boolean) => {
    if (isLegacy) return "Review / Upgrade";
    if (isStale || status === "STALE") return "Update questions";
    if (status === "APPROVED") return "View questions";
    if (status === "VALIDATED") return "Review and approve";
    return "Continue review";
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "Recently";
    try {
      return new Date(dateStr).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return "Recently";
    }
  };

  const actionButtonLabel = () => {
    if (isGenerating) return "Generating questions…";
    return "Generate AI questions";
  };

  const hasRecentSets = Boolean(recentDirectory?.sets && recentDirectory.sets.length > 0);

  return (
    <div className="aiq-page">
      {/* Page Header */}
      <header className="aiq-header">
        <h1 className="aiq-title">AI interview questions</h1>
        <p className="aiq-subtitle">
          Choose a job, generate questions, and review them before approval.
        </p>
      </header>

      {/* Screen Reader Progress Announcement */}
      <div className="sr-only" aria-live="polite">
        {isGenerating ? "Generating questions for selected job..." : ""}
      </div>

      {/* Global Empty State when no jobs and no existing sets exist */}
      {!isLoadingJobs && selectableJobs.length === 0 && !hasRecentSets && (
        <div className="aiq-panel" style={{ textAlign: "center", padding: "48px 24px" }}>
          <h2 className="aiq-panel-title" style={{ marginBottom: "8px" }}>
            No jobs are ready yet
          </h2>
          <p className="aiq-panel-desc" style={{ marginBottom: "20px" }}>
            Complete a job and add approved requirements before generating interview questions.
          </p>
          {onNavigateToJobs && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onNavigateToJobs}
            >
              Go to Jobs
            </button>
          )}
        </div>
      )}

      {/* Loading State */}
      {isLoadingJobs && (
        <div className="aiq-panel" style={{ textAlign: "center", padding: "48px 24px" }}>
          <div className="loading-spinner" style={{ margin: "0 auto 12px auto" }} />
          <p className="aiq-panel-desc">Loading available jobs...</p>
        </div>
      )}

      {/* Compact Notice when all ready jobs already have question sets */}
      {!isLoadingJobs && selectableJobs.length === 0 && hasRecentSets && (
        <div
          className="aiq-panel"
          style={{
            padding: "20px 24px",
            marginBottom: "32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "16px",
            flexWrap: "wrap",
          }}
        >
          <div>
            <h2 className="aiq-panel-title" style={{ fontSize: "17px", marginBottom: "4px" }}>
              All ready jobs have AI question sets
            </h2>
            <p className="aiq-panel-desc" style={{ fontSize: "14px", margin: 0 }}>
              To generate questions for another role, create a job requisition and approve its requirements.
            </p>
          </div>
          {onNavigateToJobs && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onNavigateToJobs}
            >
              Go to Jobs
            </button>
          )}
        </div>
      )}

      {/* Two-Column Creation Workspace */}
      {!isLoadingJobs && selectableJobs.length > 0 && (
        <div className="aiq-create-layout">
          {/* Left Column: Job Panel */}
          <section className="aiq-job-panel aiq-panel" aria-labelledby="choose-job-heading">
            <div className="aiq-panel-header">
              <div className="aiq-panel-title-row">
                <h2 id="choose-job-heading" className="aiq-panel-title">
                  Choose a job
                </h2>
                <span className="aiq-panel-count">
                  {selectableJobs.length} {selectableJobs.length === 1 ? "job" : "jobs"} available
                </span>
              </div>
              <p className="aiq-panel-desc">
                Select the role you want to prepare.
              </p>
            </div>

            {/* Filter Input if > 8 jobs */}
            {selectableJobs.length > 8 && (
              <div className="aiq-search-box">
                <label htmlFor="aiq-job-search" className="aiq-search-label">
                  Search jobs
                </label>
                <input
                  id="aiq-job-search"
                  type="text"
                  className="aiq-search-input"
                  placeholder="Filter by job title..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            )}

            {/* Accessible Radio Group */}
            <fieldset className="aiq-job-fieldset">
              <legend className="aiq-job-legend">Choose a job</legend>

              <div className="aiq-job-list" role="radiogroup">
                {filteredJobs.length === 0 ? (
                  <p className="aiq-panel-desc" style={{ padding: "16px 0" }}>
                    No jobs matching &ldquo;{searchQuery}&rdquo;.
                  </p>
                ) : (
                  filteredJobs.map((job) => {
                    const isSelected = selectedJobId === job.job_id;
                    return (
                      <label
                        key={job.job_id}
                        htmlFor={`aiq-job-${job.job_id}`}
                        className={`aiq-job-row ${isSelected ? "aiq-selected" : ""}`}
                        onClick={() => {
                          setSelectedJobId(job.job_id);
                          setGenerationError(null);
                        }}
                      >
                        <div className="aiq-job-left">
                          <input
                            type="radio"
                            id={`aiq-job-${job.job_id}`}
                            name="selected_job"
                            value={job.job_id}
                            checked={isSelected}
                            onChange={() => {
                              setSelectedJobId(job.job_id);
                              setGenerationError(null);
                            }}
                            className="aiq-radio-input"
                          />
                          <span className="aiq-job-name">{job.job_title}</span>
                        </div>
                        <span className="aiq-job-req-count">
                          {job.requirement_count}{" "}
                          {job.requirement_count === 1 ? "requirement" : "requirements"}
                        </span>
                      </label>
                    );
                  })
                )}
              </div>
            </fieldset>
          </section>

          {/* Right Column: Generation Panel */}
          <aside className="aiq-generation-panel aiq-panel" aria-labelledby="generate-panel-heading">
            <div className="aiq-panel-header">
              <h2 id="generate-panel-heading" className="aiq-panel-title">
                Generate AI questions
              </h2>
              <p className="aiq-panel-desc">
                The approved requirements will guide the local AI.
              </p>
            </div>

            {/* Selection Summary or Placeholder */}
            {selectedJob ? (
              <div className="aiq-selection-summary">
                <div className="aiq-selection-label">Selected job</div>
                <div className="aiq-selection-job-title">{selectedJob.job_title}</div>
                <div className="aiq-selection-reqs">
                  {selectedJob.requirement_count}{" "}
                  {selectedJob.requirement_count === 1 ? "requirement" : "requirements"}
                </div>
              </div>
            ) : (
              <div className="aiq-unselected-placeholder">
                Select a job on the left to start generating interview questions.
              </div>
            )}

            {/* Error Alert */}
            {generationError && (
              <div className="feedback-box error" role="alert" style={{ margin: "0" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: "8px", flex: 1 }}>
                  <Icon name="alert-triangle" size={16} />
                  <span>{generationError}</span>
                </div>
                {isLocalAiError && (
                  <div style={{ display: "flex", gap: "6px", marginLeft: "auto" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={handleAction}
                      disabled={isGenerating}
                    >
                      Try again
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={() => {
                        setGenerationError(null);
                        setIsLocalAiError(false);
                      }}
                      disabled={isGenerating}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Action Section */}
            <div className="aiq-action-container">
              <button
                type="button"
                className="aiq-generate-btn"
                disabled={!selectedJobId || isGenerating}
                onClick={handleAction}
              >
                {isGenerating ? (
                  <>
                    <span className="loading-spinner" style={{ width: "16px", height: "16px" }} />
                    <span>Generating questions…</span>
                  </>
                ) : (
                  <span>{actionButtonLabel()}</span>
                )}
              </button>

              <p className="aiq-reassurance-text">
                You’ll review every question before approval.
              </p>
            </div>
          </aside>
        </div>
      )}

      {/* Recent Sets: "Continue Reviewing" Section */}
      {!isLoadingJobs && hasRecentSets && recentDirectory && (
        <section className="aiq-recent-section" aria-labelledby="continue-reviewing-heading">
          <h2 id="continue-reviewing-heading" className="aiq-recent-heading">
            Continue reviewing
          </h2>

          <div className="aiq-recent-list">
            {recentDirectory.sets.map((set) => {
              const isLegacy = set.is_legacy;
              const status = formatStatus(set.lifecycle_status, set.is_source_stale, isLegacy);
              const actionLabel = formatLifecycleAction(set.lifecycle_status, set.is_source_stale, isLegacy);
              const badgeClass =
                isLegacy
                  ? "legacy"
                  : status === "Approved"
                  ? "approved"
                  : status === "Ready for Review"
                  ? "validated"
                  : status === "Stale"
                  ? "stale"
                  : "draft";

              return (
                <div key={set.ai_set_id} className="aiq-recent-row">
                  <div className="aiq-recent-info">
                    <span className="aiq-recent-job-title">{set.job_title}</span>
                    <div className="aiq-recent-meta">
                      <span>
                        {set.generated_question_count}{" "}
                        {set.generated_question_count === 1 ? "question" : "questions"}
                      </span>
                      <span className="aiq-dot">·</span>
                      <span className={`aiq-status-badge ${badgeClass}`}>{status}</span>
                      <span className="aiq-dot">·</span>
                      <span>Updated {formatDate(set.updated_at)}</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => onSelectTemplate(set.ai_set_id || set.template_id || "")}
                    aria-label={`${actionLabel} for ${set.job_title}`}
                  >
                    {actionLabel}
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
