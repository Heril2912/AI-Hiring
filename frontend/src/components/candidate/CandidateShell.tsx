import React, { useState } from "react";
import { useCandidateAuth } from "../../context/CandidateAuthContext";
import { Icon } from "../Icon";
import { CandidatePracticeDirectory } from "./CandidatePracticeDirectory";
import { CandidateOpenJobs } from "./CandidateOpenJobs";
import { CandidateJobDetailView } from "./CandidateJobDetail";

interface CandidateShellProps {
  onLogout?: () => void;
  initialTab?: "jobs" | "practice";
}

export function CandidateShell({ onLogout, initialTab = "jobs" }: CandidateShellProps) {
  const { candidateUser, logout } = useCandidateAuth();
  const [activeTab, setActiveTab] = useState<"jobs" | "practice">(initialTab);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | undefined>(undefined);

  const handleLogout = async () => {
    await logout();
    if (onLogout) {
      onLogout();
    }
  };

  const handleSelectJob = (jobId: string, versionId?: string) => {
    setSelectedJobId(jobId);
    setSelectedVersionId(versionId);
  };

  const handleBackToJobs = () => {
    setSelectedJobId(null);
    setSelectedVersionId(undefined);
  };

  return (
    <div className="candidate-shell-layout">
      <header className="candidate-shell-header" role="banner">
        <div className="candidate-shell-brand">
          <Icon name="briefcase" className="brand-icon" aria-hidden="true" />
          <span className="brand-title">Smart Hiring Platform</span>
          <span className="candidate-portal-chip">Candidate Portal</span>
        </div>

        <nav
          className="candidate-shell-nav"
          role="navigation"
          aria-label="Candidate Portal Navigation"
          style={{ display: "flex", gap: "8px", margin: "0 auto" }}
        >
          <button
            type="button"
            className={`btn btn-sm ${activeTab === "jobs" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              setActiveTab("jobs");
              handleBackToJobs();
            }}
            style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
            aria-current={activeTab === "jobs" ? "page" : undefined}
          >
            <Icon name="briefcase" size={14} aria-hidden="true" />
            <span>Open Jobs</span>
          </button>

          <button
            type="button"
            className={`btn btn-sm ${activeTab === "practice" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              setActiveTab("practice");
              handleBackToJobs();
            }}
            style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
            aria-current={activeTab === "practice" ? "page" : undefined}
          >
            <Icon name="message-square" size={14} aria-hidden="true" />
            <span>Practice Interviews</span>
          </button>
        </nav>

        <div className="candidate-shell-user-menu">
          <span className="candidate-user-name" aria-label="Authenticated candidate">
            {candidateUser?.displayName || "Candidate"}
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-sm candidate-logout-btn"
            onClick={handleLogout}
            aria-label="Sign out of Candidate Portal"
          >
            <Icon name="log-out" aria-hidden="true" />
            <span>Sign Out</span>
          </button>
        </div>
      </header>

      <main className="candidate-shell-main" role="main">
        {activeTab === "jobs" && (
          selectedJobId ? (
            <CandidateJobDetailView
              jobId={selectedJobId}
              versionId={selectedVersionId}
              onBack={handleBackToJobs}
            />
          ) : (
            <CandidateOpenJobs onSelectJob={handleSelectJob} />
          )
        )}

        {activeTab === "practice" && (
          <CandidatePracticeDirectory />
        )}
      </main>
    </div>
  );
}
