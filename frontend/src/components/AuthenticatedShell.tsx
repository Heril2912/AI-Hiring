import React, { useState, useRef, useEffect, ReactNode } from "react";
import { useAuth } from "../context/AuthContext";
import { Icon } from "./Icon";
import { getPortalContext, getCrossPortalUrl } from "../utils/portal";

interface AuthenticatedShellProps {
  children: ReactNode;
  activeNavTab?: string;
  onNavigateTab?: (tab: string) => void;
  candidateCount?: number;
  jobsCount?: number;
  aiQuestionsCount?: number;
  connectionState?: "checking" | "connected" | "unavailable";
}

export function AuthenticatedShell({
  children,
  activeNavTab,
  onNavigateTab,
  candidateCount = 0,
  jobsCount = 0,
  aiQuestionsCount = 0,
  connectionState = "connected",
}: AuthenticatedShellProps) {
  const { user, logout } = useAuth();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const portalContext = getPortalContext();

  // Close menu on outside click or Escape key
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isMenuOpen) {
        setIsMenuOpen(false);
        triggerRef.current?.focus();
      }
    }

    if (isMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMenuOpen]);

  const handleLogout = async () => {
    try {
      setIsLoggingOut(true);
      await logout();
    } finally {
      setIsLoggingOut(false);
    }
  };

  const role = user?.role || "REVIEWER";
  const displayedWorkspaceLabel =
    portalContext === "admin"
      ? "Admin workspace"
      : portalContext === "recruiter"
      ? "Recruiter workspace"
      : role === "ADMIN"
      ? "Admin workspace"
      : role === "RECRUITER"
      ? "Recruiter workspace"
      : "Reviewer workspace";

  return (
    <div className="dashboard-app-container">
      {/* Skip to Main Content Link for Keyboard Navigation */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* Top Application Navigation Bar */}
      <header className="dashboard-top-nav" role="banner">
        <div className="nav-brand-section">
          <div className="brand-logo-icon" aria-hidden="true">
            <Icon name="sparkles" size={18} />
          </div>
          <div className="brand-title-group">
            <div className="brand-title-row">
              <h1 className="brand-title">Smart Hiring Platform</h1>
              <span
                className="portal-workspace-label"
                aria-label={`Current Workspace: ${displayedWorkspaceLabel}`}
              >
                {displayedWorkspaceLabel}
              </span>
            </div>
            <span className="brand-subtitle">
              {role === "ADMIN" && "Administration & User Governance"}
              {role === "RECRUITER" && "Evidence-Based Parsing & Audited Profiles"}
              {role === "REVIEWER" && "Candidate Review & Evaluation"}
            </span>
          </div>
        </div>

        {/* Role-Specific Navigation Tabs */}
        <nav className="nav-links-group" aria-label="Role Navigation">
          {role === "RECRUITER" && (
            <>
              <button
                type="button"
                className={`nav-tab-btn ${
                  activeNavTab === "jobs" || activeNavTab === "new_job" || activeNavTab === "edit_job"
                    ? "tab-active"
                    : ""
                }`}
                aria-current={
                  activeNavTab === "jobs" || activeNavTab === "new_job" || activeNavTab === "edit_job"
                    ? "page"
                    : undefined
                }
                onClick={() => onNavigateTab?.("jobs")}
              >
                <Icon name="briefcase" size={15} />
                <span>Jobs</span>
                {jobsCount > 0 && <span className="nav-count-pill">{jobsCount}</span>}
              </button>

              <button
                type="button"
                className={`nav-tab-btn ${
                  activeNavTab === "candidates" || activeNavTab === "profile" || activeNavTab === "extraction"
                    ? "tab-active"
                    : ""
                }`}
                aria-current={
                  activeNavTab === "candidates" || activeNavTab === "profile" || activeNavTab === "extraction"
                    ? "page"
                    : undefined
                }
                onClick={() => onNavigateTab?.("candidates")}
              >
                <Icon name="user" size={15} />
                <span>Candidates</span>
                {candidateCount > 0 && (
                  <span className="nav-count-pill">{candidateCount}</span>
                )}
              </button>

              <button
                type="button"
                className={`nav-tab-btn ${activeNavTab === "upload" ? "tab-active" : ""}`}
                aria-current={activeNavTab === "upload" ? "page" : undefined}
                onClick={() => onNavigateTab?.("upload")}
              >
                <Icon name="upload" size={15} />
                <span>Upload Resume</span>
              </button>

              <button
                type="button"
                className={`nav-tab-btn ${
                  activeNavTab === "ai_interviews" || activeNavTab === "ai-interviews"
                    ? "tab-active"
                    : ""
                }`}
                aria-current={
                  activeNavTab === "ai_interviews" || activeNavTab === "ai-interviews"
                    ? "page"
                    : undefined
                }
                aria-label="AI-generated interviews and question sets"
                onClick={() => onNavigateTab?.("ai_interviews")}
              >
                <Icon name="sparkles" size={15} />
                <span>AI Interviews</span>
                {aiQuestionsCount !== undefined && aiQuestionsCount > 0 && (
                  <span className="nav-count-pill">{aiQuestionsCount}</span>
                )}
              </button>
            </>
          )}

          {role === "ADMIN" && (
            <>
              <button
                type="button"
                className={`nav-tab-btn ${
                  activeNavTab === "jobs" || activeNavTab === "new_job" || activeNavTab === "edit_job"
                    ? "tab-active"
                    : ""
                }`}
                aria-current={
                  activeNavTab === "jobs" || activeNavTab === "new_job" || activeNavTab === "edit_job"
                    ? "page"
                    : undefined
                }
                onClick={() => onNavigateTab?.("jobs")}
              >
                <Icon name="briefcase" size={15} />
                <span>Jobs</span>
                {jobsCount > 0 && <span className="nav-count-pill">{jobsCount}</span>}
              </button>
              <button
                type="button"
                className={`nav-tab-btn ${activeNavTab === "users" ? "tab-active" : ""}`}
                aria-current={activeNavTab === "users" ? "page" : undefined}
                onClick={() => onNavigateTab?.("users")}
              >
                <Icon name="user" size={15} />
                <span>User Management</span>
              </button>
              <button
                type="button"
                className={`nav-tab-btn ${activeNavTab === "events" ? "tab-active" : ""}`}
                aria-current={activeNavTab === "events" ? "page" : undefined}
                onClick={() => onNavigateTab?.("events")}
              >
                <Icon name="shield" size={15} />
                <span>Security Events</span>
              </button>
              <button
                type="button"
                className={`nav-tab-btn ${activeNavTab === "ai_providers" ? "tab-active" : ""}`}
                aria-current={activeNavTab === "ai_providers" ? "page" : undefined}
                onClick={() => onNavigateTab?.("ai_providers")}
              >
                <Icon name="sparkles" size={15} />
                <span>AI Providers</span>
              </button>
              <button
                type="button"
                className={`nav-tab-btn ${activeNavTab === "ats_integrations" ? "tab-active" : ""}`}
                aria-current={activeNavTab === "ats_integrations" ? "page" : undefined}
                onClick={() => onNavigateTab?.("ats_integrations")}
              >
                <Icon name="external-link" size={15} />
                <span>ATS Integrations</span>
              </button>
            </>
          )}

          {role === "REVIEWER" && (
            <button
              type="button"
              className={`nav-tab-btn tab-active`}
              aria-current="page"
              onClick={() => onNavigateTab?.("reviews")}
            >
              <Icon name="award" size={15} />
              <span>Assigned Reviews</span>
            </button>
          )}
        </nav>

        {/* User Profile & System Status Area */}
        <div className="nav-user-actions-section">
          <div className="nav-system-status" aria-label="Database Health">
            <span className={`status-indicator-dot ${connectionState}`} />
            <span className="status-indicator-text">
              {connectionState === "checking" && "Connecting..."}
              {connectionState === "connected" && "System Connected"}
              {connectionState === "unavailable" && "Service Unavailable"}
            </span>
          </div>

          {/* User Profile Menu */}
          <div className="user-profile-menu-container" ref={menuRef}>
            <button
              ref={triggerRef}
              type="button"
              className="user-profile-btn"
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              aria-expanded={isMenuOpen}
              aria-haspopup="true"
              aria-label="User profile and account settings"
            >
              <div className="user-avatar-circle" aria-hidden="true">
                {user?.displayName ? user.displayName.charAt(0).toUpperCase() : "U"}
              </div>
              <div className="user-info-text">
                <span className="user-display-name">{user?.displayName || "User"}</span>
                <span className={`user-role-badge badge-${role.toLowerCase()}`}>
                  {role}
                </span>
              </div>
              <Icon name="chevron-down" size={14} className="menu-arrow-icon" />
            </button>

            {isMenuOpen && (
              <div className="user-dropdown-card" role="menu" aria-label="User options">
                <div className="dropdown-user-header">
                  <p className="dropdown-name">{user?.displayName}</p>
                  <p className="dropdown-email">{user?.email}</p>
                </div>
                <div className="dropdown-divider" />
                <a
                  href={getCrossPortalUrl(portalContext === "admin" || role === "ADMIN" ? "recruiter" : "admin")}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="dropdown-menu-item"
                  role="menuitem"
                  onClick={() => setIsMenuOpen(false)}
                >
                  <Icon name="external-link" size={15} />
                  <span>
                    {portalContext === "admin" || role === "ADMIN"
                      ? "Open Recruiter workspace"
                      : "Open Admin workspace"}
                  </span>
                </a>
                <button
                  type="button"
                  className="dropdown-menu-item logout-btn"
                  role="menuitem"
                  onClick={handleLogout}
                  disabled={isLoggingOut}
                >
                  <Icon name="arrow-left" size={15} />
                  <span>{isLoggingOut ? "Signing Out..." : "Sign Out"}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Viewport */}
      <main id="main-content" className="dashboard-main-viewport" role="main">
        {children}
      </main>
    </div>
  );
}
