import React from "react";
import { useCandidateAuth } from "../../context/CandidateAuthContext";
import { Icon } from "../Icon";

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
      </main>
    </div>
  );
}
