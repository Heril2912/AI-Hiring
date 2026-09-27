import React, { useState, useEffect } from "react";
import { useCandidateAuth } from "../../context/CandidateAuthContext";
import { Icon } from "../Icon";
import { CandidatePracticeDirectory } from "./CandidatePracticeDirectory";
import { CandidateOpenJobs } from "./CandidateOpenJobs";
import { CandidateJobDetailView } from "./CandidateJobDetail";
import { CandidateMyApplications } from "./CandidateMyApplications";
import { CandidateApplicationDetailView } from "./CandidateApplicationDetail";

export type CandidateTab = "jobs" | "applications" | "interviews" | "profile";

interface CandidateShellProps {
  onLogout?: () => void;
  initialTab?: CandidateTab;
}

export function CandidateShell({ onLogout, initialTab }: CandidateShellProps) {
  const { candidateUser, logout } = useCandidateAuth();

  const getTabFromPath = (): CandidateTab => {
    if (typeof window === "undefined") return initialTab || "jobs";
    const path = window.location.pathname.toLowerCase();
    if (path.startsWith("/candidate/applications")) return "applications";
    if (path.startsWith("/candidate/interviews")) return "interviews";
    if (path.startsWith("/candidate/profile")) return "profile";
    if (path.startsWith("/candidate/jobs")) return "jobs";
    return initialTab || "jobs";
  };

  const [activeTab, setActiveTab] = useState<CandidateTab>(getTabFromPath);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | undefined>(undefined);
  const [selectedApplicationId, setSelectedApplicationId] = useState<string | null>(null);

  // Sync tab with popstate (Back / Forward)
  useEffect(() => {
    const handlePopState = () => {
      const tab = getTabFromPath();
      setActiveTab(tab);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigateToTab = (tab: CandidateTab) => {
    setActiveTab(tab);
    const targetUrl = `/candidate/${tab}`;
    if (typeof window !== "undefined" && window.location.pathname !== targetUrl && window.history?.pushState) {
      window.history.pushState(null, "", targetUrl);
    }
  };

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

  const handleSelectApplication = (applicationId: string) => {
    setSelectedApplicationId(applicationId);
    navigateToTab("applications");
  };

  const handleBackToApplications = () => {
    setSelectedApplicationId(null);
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
              navigateToTab("jobs");
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
            className={`btn btn-sm ${activeTab === "applications" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              navigateToTab("applications");
              handleBackToApplications();
            }}
            style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
            aria-current={activeTab === "applications" ? "page" : undefined}
          >
            <Icon name="file-text" size={14} aria-hidden="true" />
            <span>My Applications</span>
          </button>

          <button
            type="button"
            className={`btn btn-sm ${activeTab === "interviews" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              navigateToTab("interviews");
              handleBackToJobs();
              handleBackToApplications();
            }}
            style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
            aria-current={activeTab === "interviews" ? "page" : undefined}
            aria-label="Practice Interviews"
          >
            <Icon name="message-square" size={14} aria-hidden="true" />
            <span>Interviews</span>
          </button>

          <button
            type="button"
            className={`btn btn-sm ${activeTab === "profile" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => {
              navigateToTab("profile");
              handleBackToJobs();
              handleBackToApplications();
            }}
            style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
            aria-current={activeTab === "profile" ? "page" : undefined}
          >
            <Icon name="user" size={14} aria-hidden="true" />
            <span>Profile</span>
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
              onNavigateApplication={handleSelectApplication}
            />
          ) : (
            <CandidateOpenJobs onSelectJob={handleSelectJob} />
          )
        )}

        {activeTab === "applications" && (
          selectedApplicationId ? (
            <CandidateApplicationDetailView
              applicationId={selectedApplicationId}
              onBack={handleBackToApplications}
              onNavigateJobs={() => {
                navigateToTab("jobs");
                handleBackToJobs();
              }}
            />
          ) : (
            <CandidateMyApplications
              onSelectApplication={handleSelectApplication}
              onNavigateJobs={() => {
                navigateToTab("jobs");
                handleBackToJobs();
              }}
            />
          )
        )}

        {activeTab === "interviews" && (
          <CandidatePracticeDirectory />
        )}

        {activeTab === "profile" && (
          <div className="candidate-profile-container" style={{ maxWidth: "800px", margin: "0 auto", padding: "24px" }}>
            <div className="card" style={{ padding: "24px", backgroundColor: "#ffffff", borderRadius: "8px", border: "1px solid var(--border-subtle, #e2e8f0)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
                <div
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "50%",
                    backgroundColor: "#e0e7ff",
                    color: "#4338ca",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "18px",
                    fontWeight: 700,
                  }}
                >
                  {(candidateUser?.displayName || "C").charAt(0).toUpperCase()}
                </div>
                <div>
                  <h2 style={{ fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--text-primary, #0f172a)" }}>
                    {candidateUser?.displayName || "Candidate Profile"}
                  </h2>
                  <p style={{ fontSize: "13px", color: "var(--text-secondary, #64748b)", margin: 0 }}>
                    {candidateUser?.email}
                  </p>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", borderTop: "1px solid var(--border-subtle, #e2e8f0)", paddingTop: "16px", fontSize: "13px" }}>
                <div>
                  <span style={{ color: "var(--text-muted, #64748b)", display: "block", fontSize: "11px", textTransform: "uppercase" }}>Account Role</span>
                  <strong>Candidate</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted, #64748b)", display: "block", fontSize: "11px", textTransform: "uppercase" }}>Portal Access</span>
                  <span className="badge badge-success" style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                    <Icon name="check-circle" size={11} />
                    <span>Active Candidate Account</span>
                  </span>
                </div>
              </div>

              <div style={{ marginTop: "24px", padding: "16px", backgroundColor: "#f8fafc", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
                <h3 style={{ fontSize: "14px", fontWeight: 600, margin: "0 0 6px", color: "#0f172a" }}>
                  Candidate Workspace
                </h3>
                <p style={{ fontSize: "13px", color: "#64748b", margin: 0, lineHeight: 1.5 }}>
                  You can browse and apply for verified job postings, view your submitted applications, and take scheduled AI interviews directly from this portal.
                </p>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
