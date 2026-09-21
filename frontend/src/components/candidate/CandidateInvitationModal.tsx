import React, { useState, useEffect, useCallback } from "react";
import {
  createCandidateInvitation,
  listCandidateInvitations,
  revokeCandidateInvitation,
  CandidateInvitationSummary,
  CreateInvitationResponse,
} from "../../api/candidateAuth";
import { Icon } from "../Icon";

interface CandidateInvitationModalProps {
  candidateId: string;
  candidateName: string;
  isOpen: boolean;
  onClose: () => void;
}

export function CandidateInvitationModal({
  candidateId,
  candidateName,
  isOpen,
  onClose,
}: CandidateInvitationModalProps) {
  const [invitations, setInvitations] = useState<CandidateInvitationSummary[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [createdResult, setCreatedResult] = useState<CreateInvitationResponse | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [validHours, setValidHours] = useState<number>(24);

  const fetchInvitations = useCallback(async () => {
    if (!candidateId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await listCandidateInvitations(candidateId);
      setInvitations(data || []);
    } catch (err: any) {
      setError(err.message || "Failed to load candidate invitations.");
    } finally {
      setIsLoading(false);
    }
  }, [candidateId]);

  useEffect(() => {
    if (isOpen) {
      fetchInvitations();
      setCreatedResult(null);
      setCopied(false);
      setError(null);
    }
  }, [isOpen, fetchInvitations]);

  if (!isOpen) return null;

  const handleCreateInvitation = async () => {
    setIsCreating(true);
    setError(null);
    setCreatedResult(null);
    try {
      const result = await createCandidateInvitation(candidateId, validHours);
      setCreatedResult(result);
      await fetchInvitations();
    } catch (err: any) {
      setError(err.message || "Failed to create invitation link.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleRevoke = async (invitationId: string) => {
    setError(null);
    try {
      await revokeCandidateInvitation(invitationId);
      await fetchInvitations();
    } catch (err: any) {
      setError(err.message || "Failed to revoke invitation.");
    }
  };

  const handleCopyLink = async () => {
    if (!createdResult?.activationUrl) return;
    try {
      await navigator.clipboard.writeText(createdResult.activationUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      // Fallback
      setCopied(true);
    }
  };

  const activeInvitation = invitations.find((i) => i.status === "ACTIVE");

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="invitation-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-container candidate-invitation-modal">
        <header className="modal-header">
          <div className="modal-title-group">
            <Icon name="key" className="modal-title-icon" aria-hidden="true" />
            <h2 id="invitation-modal-title" className="modal-title">
              Candidate Practice Access: {candidateName}
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
            Generate a secure, single-use activation link granting {candidateName} access to their candidate practice interview portal.
          </p>

          {error && (
            <div className="modal-alert modal-alert-error" role="alert">
              <Icon name="alert-triangle" aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          {createdResult && (
            <div className="invitation-created-banner" role="region" aria-label="Newly generated invitation link">
              <div className="banner-header">
                <Icon name="check-circle" className="success-icon" aria-hidden="true" />
                <span className="banner-title">Activation Link Ready</span>
              </div>
              <p className="banner-instructions">
                Share this link directly with the candidate. The link expires in {validHours} hours and can only be used once.
              </p>
              <div className="link-copy-box">
                <input
                  type="text"
                  readOnly
                  className="link-input"
                  value={createdResult.activationUrl}
                  aria-label="Activation URL"
                />
                <button
                  type="button"
                  className={`btn ${copied ? "btn-success" : "btn-primary"} btn-sm`}
                  onClick={handleCopyLink}
                >
                  <Icon name={copied ? "check" : "copy"} aria-hidden="true" />
                  <span>{copied ? "Copied!" : "Copy Link"}</span>
                </button>
              </div>
            </div>
          )}

          <div className="invitation-create-section">
            <div className="create-controls">
              <div className="form-group-inline">
                <label htmlFor="invitation-expiry">Link Expiry Duration</label>
                <select
                  id="invitation-expiry"
                  className="form-select form-select-sm"
                  value={validHours}
                  onChange={(e) => setValidHours(Number(e.target.value))}
                  disabled={isCreating}
                >
                  <option value={12}>12 hours</option>
                  <option value={24}>24 hours (Default)</option>
                  <option value={48}>48 hours</option>
                  <option value={72}>3 days</option>
                  <option value={168}>7 days</option>
                </select>
              </div>

              <button
                type="button"
                className="btn btn-primary"
                onClick={handleCreateInvitation}
                disabled={isCreating}
              >
                <Icon name="plus" aria-hidden="true" />
                <span>{isCreating ? "Generating Link..." : "Create Candidate Access"}</span>
              </button>
            </div>
          </div>

          <section className="invitation-history-section" aria-label="Invitation History">
            <h3 className="section-subtitle">Invitation History</h3>

            {isLoading ? (
              <div className="loading-state-inline" role="status">
                <div className="spinner-inline" />
                <span>Loading invitation records...</span>
              </div>
            ) : invitations.length === 0 ? (
              <div className="empty-history-text">
                No previous invitations generated for this candidate.
              </div>
            ) : (
              <div className="invitation-table-wrapper">
                <table className="invitation-table">
                  <thead>
                    <tr>
                      <th scope="col">Status</th>
                      <th scope="col">Created At</th>
                      <th scope="col">Expires At</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invitations.map((inv) => {
                      const isRevocable = (inv.status || "").toUpperCase() === "ACTIVE";
                      return (
                        <tr key={inv.invitationId}>
                          <td>
                            <span className={`status-pill status-${inv.status?.toLowerCase()}`}>
                              {inv.status}
                            </span>
                          </td>
                          <td>{new Date(inv.createdAt).toLocaleString()}</td>
                          <td>{new Date(inv.expiresAt).toLocaleString()}</td>
                          <td>
                            {isRevocable ? (
                              <button
                                type="button"
                                className="btn btn-secondary btn-xs"
                                onClick={() => handleRevoke(inv.invitationId)}
                                aria-label="Revoke unused invitation"
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
