import React, { useState } from "react";
import { JobSummary } from "../../api/jobs";
import { Icon } from "../Icon";

interface JobsDirectoryProps {
  jobs: JobSummary[];
  isLoading: boolean;
  error?: string | null;
  onSelectJob: (jobId: string) => void;
  onCreateJob: () => void;
  onRefresh: () => void;
}

export function JobsDirectory({
  jobs = [],
  isLoading,
  error,
  onSelectJob,
  onCreateJob,
  onRefresh,
}: JobsDirectoryProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const safeJobs = Array.isArray(jobs) ? jobs : [];
  const filteredJobs = safeJobs.filter((j) => {

    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const v = j.currentVersion;
    const titleMatch = v.title.toLowerCase().includes(q);
    const deptMatch = v.department?.toLowerCase().includes(q);
    const locMatch = v.location?.toLowerCase().includes(q);
    const refMatch = v.internalReference?.toLowerCase().includes(q);
    return Boolean(titleMatch || deptMatch || locMatch || refMatch);
  });

  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="jobs-directory-container" role="region" aria-label="Jobs Directory">
      {/* Directory Header Bar */}
      <div className="directory-header-row">
        <div>
          <h2 className="directory-title">Job Requisitions</h2>
          <p className="directory-subtitle">
            Manage structured job requisitions, versioned drafts, and defensible criteria.
          </p>
        </div>

        <button
          type="button"
          onClick={onCreateJob}
          className="btn btn-primary btn-md"
        >
          <Icon name="plus" size={15} />
          <span>Create Job</span>
        </button>
      </div>

      {/* Toolbar / Search & Filter */}
      <div className="directory-toolbar">
        <div className="search-input-wrapper">
          <Icon name="search" size={16} className="search-icon" />
          <input
            type="text"
            className="search-input"
            placeholder="Search jobs by title, department, location, or reference code..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search jobs"
          />
          {searchQuery && (
            <button
              type="button"
              className="search-clear-btn"
              onClick={() => setSearchQuery("")}
              aria-label="Clear job search"
            >
              <Icon name="x" size={14} />
            </button>
          )}
        </div>

        <div className="directory-count-badge">
          {filteredJobs.length} job{filteredJobs.length === 1 ? "" : "s"}
        </div>
      </div>

      {/* Directory Content */}
      {error && (
        <div className="feedback-box error" role="alert" style={{ marginBottom: "16px" }}>
          <Icon name="alert-triangle" size={16} />
          <p className="feedback-text error">{error}</p>
          <button type="button" onClick={onRefresh} className="btn btn-secondary btn-sm" style={{ marginLeft: "auto" }}>
            Retry
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="loading-state-card">
          <div className="loading-spinner" />
          <p className="loading-text">Loading accessible job requisitions...</p>
        </div>
      ) : jobs.length === 0 ? (
        <div className="empty-state-card">
          <div className="empty-icon-circle">
            <Icon name="briefcase" size={32} />
          </div>
          <h3 className="empty-title">No job requisitions created yet</h3>
          <p className="empty-description">
            Create your first job requisition to define structured technical requirements, qualifications, and evidence criteria.
          </p>
          <button
            type="button"
            onClick={onCreateJob}
            className="btn btn-primary btn-md"
          >
            <Icon name="plus" size={15} />
            <span>Create Job</span>
          </button>
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="empty-state-card">
          <Icon name="search" size={28} className="text-muted" />
          <h3 className="empty-title">No jobs match your search</h3>
          <p className="empty-description">Try adjusting your search terms or clearing the filter.</p>
          <button
            type="button"
            onClick={() => setSearchQuery("")}
            className="btn btn-secondary btn-sm"
          >
            Clear Search
          </button>
        </div>
      ) : (
        <div className="jobs-grid">
          {filteredJobs.map((j) => {
            const v = j.currentVersion;
            return (
              <div
                key={j.jobId}
                className="job-requisition-card"
                onClick={() => onSelectJob(j.jobId)}
                tabIndex={0}
                role="button"
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelectJob(j.jobId);
                  }
                }}
              >
                <div className="job-card-header">
                  <div className="job-card-main-title">
                    <h3 className="job-title-text">{v.title}</h3>
                    {v.internalReference && (
                      <span className="job-ref-tag">{v.internalReference}</span>
                    )}
                  </div>
                  <span className={`badge badge-job-status-${v.versionStatus.toLowerCase()}`}>
                    {v.versionStatus === "DRAFT" ? "Draft" : "Approved"}
                  </span>
                </div>

                <div className="job-card-sub-info">
                  {v.department && (
                    <span className="job-meta-pill">
                      <Icon name="building" size={13} /> {v.department}
                    </span>
                  )}
                  {v.location && (
                    <span className="job-meta-pill">
                      <Icon name="map-pin" size={13} /> {v.location}
                    </span>
                  )}
                  {v.workplaceType && (
                    <span className="job-meta-pill">
                      {v.workplaceType.replace("_", " ")}
                    </span>
                  )}
                </div>

                <div className="job-card-meta-row">
                  <div className="job-badges-group">
                    <span className="badge badge-version">v{v.versionNumber}</span>
                    <span className="badge badge-revision">Rev #{v.revision}</span>
                    <span className="badge badge-req-count">{v.requirementsCount} Requirements</span>
                  </div>
                  <span className="job-date-text">Updated {formatDate(v.updatedAt)}</span>
                </div>

                <div className="job-card-footer">
                  <span className="job-action-link">
                    Edit Draft &amp; Requirements <Icon name="chevron-right" size={14} />
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
