import React from "react";
import { Icon } from "../Icon";

export function ReviewerWorkspace() {
  return (
    <div className="reviewer-workspace-container" role="region" aria-label="Reviewer Workspace">
      <div className="empty-state-card">
        <div className="empty-state-icon-wrapper" aria-hidden="true">
          <Icon name="award" size={36} />
        </div>
        <h2 className="empty-state-title">Candidate Evaluation Queue</h2>
        <p className="empty-state-description">
          You are signed in as an authenticated <strong>Reviewer</strong>. Job assignment queues and scorecards are being introduced in Phase 2B.
        </p>
        <div className="empty-state-guidelines">
          <div className="guideline-item">
            <Icon name="check" size={16} className="guideline-check" />
            <span>Multi-factor candidate assessment rubrics</span>
          </div>
          <div className="guideline-item">
            <Icon name="check" size={16} className="guideline-check" />
            <span>Assigned requisition review pipelines</span>
          </div>
          <div className="guideline-item">
            <Icon name="check" size={16} className="guideline-check" />
            <span>Audited consensus decision-making</span>
          </div>
        </div>
      </div>
    </div>
  );
}
