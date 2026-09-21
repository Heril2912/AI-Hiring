import React from "react";
import { useCandidateAuth } from "../../context/CandidateAuthContext";
import { Icon } from "../Icon";
import { CandidatePracticeDirectory } from "./CandidatePracticeDirectory";

interface CandidateShellProps {
  onLogout?: () => void;
}

export function CandidateShell({ onLogout }: CandidateShellProps) {
  const { candidateUser, logout } = useCandidateAuth();

  const handleLogout = async () => {
    await logout();
    if (onLogout) {
      onLogout();
    }
  };

  return (
    <div className="candidate-shell-layout">
      <header className="candidate-shell-header" role="banner">
        <div className="candidate-shell-brand">
          <Icon name="briefcase" className="brand-icon" aria-hidden="true" />
          <span className="brand-title">Smart Hiring Platform</span>
          <span className="candidate-portal-chip">Candidate Practice</span>
        </div>

        <div className="candidate-shell-user-menu">
          <span className="candidate-user-name" aria-label="Authenticated candidate">
            {candidateUser?.displayName || "Candidate"}
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-sm candidate-logout-btn"
            onClick={handleLogout}
            aria-label="Sign out of Candidate Practice Portal"
          >
            <Icon name="log-out" aria-hidden="true" />
            <span>Sign Out</span>
          </button>
        </div>
      </header>

      <main className="candidate-shell-main" role="main">
        <CandidatePracticeDirectory />
      </main>
    </div>
  );
}
