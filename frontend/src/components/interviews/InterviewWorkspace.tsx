import React, { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import { Icon } from "../Icon";

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

  useEffect(() => {
    let isMounted = true;
    const loadContext = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const data = await apiFetch<InterviewContextData>(
          `/api/v1/jobs/${jobId}/candidates/${resumeId}/interview-context`
        );
        if (isMounted) {
          setContext(data);
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

    loadContext();
    return () => {
      isMounted = false;
    };
  }, [jobId, resumeId]);

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

  return (
    <div className="interview-workspace-container" role="region" aria-label="Recruiter Interview Workspace">
      {/* Top Header & Navigation */}
      <div className="interview-header-section">
        <button
          type="button"
          className="btn btn-secondary btn-sm back-nav-btn"
          onClick={onNavigateBack}
        >
          <Icon name="arrow-left" size={15} />
          <span>Back to Candidate Comparison</span>
        </button>

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

      {/* Plan State & Guidance Banner */}
      <div className="interview-plan-section">
        <div className="plan-section-header">
          <h2>Standardized Interview Structure</h2>
          <span className="plan-state-badge">EMPTY PLAN (PHASE 3A SHELL)</span>
        </div>

        {/* Structured explanation of Phase 3B contract expectations */}
        <div className="interview-guidance-card">
          <div className="guidance-icon-col">
            <Icon name="info" size={24} />
          </div>
          <div className="guidance-content">
            <h4>Structured Behavioral &amp; Technical Interview Methodology</h4>
            <p>
              This workspace enforces the platform's standardized interviewing protocol. Standard core competencies
              derived directly from verified job requirements form the immutable baseline, ensuring consistent, unbiased evaluation
              across all candidates.
            </p>
            <ul className="guidance-list">
              <li>
                <strong>Standard Core Competencies:</strong> Uniform across all applicants for this requisition revision to prevent disparate questioning.
              </li>
              <li>
                <strong>Supplemental Probes:</strong> Targeted, evidence-bounded questions addressing specific requirement gaps or credential verifications.
              </li>
              <li>
                <strong>AI Assistance:</strong> When active, bounded question rewording and probe generation remain subject to recruiter review and approval.
              </li>
            </ul>
          </div>
        </div>

        {/* Empty State Card */}
        <div className="empty-plan-placeholder">
          <div className="empty-icon-wrap">
            <Icon name="sparkles" size={32} />
          </div>
          <h3>Interview Plan Ready for Generation</h3>
          <p>
            The interview workspace shell has established authorized access to the job requisition and candidate evidence.
            Standardized question generation, bounded probe formulation, and dynamic interview templates will be activated in Phase 3B.
          </p>
        </div>
      </div>
    </div>
  );
}
