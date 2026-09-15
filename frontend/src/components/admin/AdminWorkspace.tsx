import React, { useState, useEffect, FormEvent } from "react";
import { apiFetch, ApiError } from "../../api/client";
import { Icon } from "../Icon";

interface UserItem {
  userId: string;
  email: string;
  displayName: string;
  role: "ADMIN" | "RECRUITER" | "REVIEWER";
  isActive: boolean;
  mustChangePassword: boolean;
  lastLoginAt?: string | null;
  createdAt: string;
}

interface SecurityEventItem {
  eventId: string;
  actorUserId?: string | null;
  eventType: string;
  resourceType?: string | null;
  resourceId?: string | null;
  result: string;
  reasonCode: string;
  safeMetadata: Record<string, any>;
  occurredAt: string;
}

interface PaginatedEvents {
  items: SecurityEventItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminProviderProfileItem {
  profileId: string;
  organizationId?: string | null;
  displayName: string;
  providerType: string;
  apiMode: string;
  baseUrlMasked?: string | null;
  modelIdentifier?: string | null;
  secretStatus: "CONFIGURED" | "MISSING" | "NOT_REQUIRED";
  secretRefName?: string | null;
  supportedOperations: string[];
  connectTimeoutSeconds: number;
  requestTimeoutSeconds: number;
  maxInputTokens: number;
  maxOutputTokens: number;
  maxResponseBytes: number;
  maxConcurrency: number;
  retryLimit: number;
  egressClass: "LOCAL_ONLY" | "APPROVED_REMOTE";
  privacyReviewStatus: "APPROVED" | "PENDING_REVIEW" | "REJECTED";
  enabled: boolean;
  compatibilityStatus: "COMPATIBLE" | "INCOMPATIBLE" | "NOT_TESTED";
  testedAt?: string | null;
  version: number;
  createdAt: string;
  updatedAt: string;
}

export function AdminWorkspace({ activeTab = "users" }: { activeTab?: string }) {
  // Users state
  const [users, setUsers] = useState<UserItem[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [userError, setUserError] = useState<string | null>(null);

  // Modals
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createEmail, setCreateEmail] = useState("");
  const [createDisplayName, setCreateDisplayName] = useState("");
  const [createRole, setCreateRole] = useState<"ADMIN" | "RECRUITER" | "REVIEWER">("RECRUITER");
  const [createTempPassword, setCreateTempPassword] = useState("");
  const [createModalError, setCreateModalError] = useState<string | null>(null);
  const [isCreatingUser, setIsCreatingUser] = useState(false);

  // Edit / Reset Modal
  const [selectedUser, setSelectedUser] = useState<UserItem | null>(null);
  const [isResetModalOpen, setIsResetModalOpen] = useState(false);
  const [resetTempPassword, setResetTempPassword] = useState("");
  const [resetModalError, setResetModalError] = useState<string | null>(null);
  const [isResetting, setIsResetting] = useState(false);

  // Status feedback toast/banner
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Security Events state
  const [events, setEvents] = useState<SecurityEventItem[]>([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsOffset, setEventsOffset] = useState(0);
  const [isLoadingEvents, setIsLoadingEvents] = useState(false);

  // AI Providers state
  const [providers, setProviders] = useState<AdminProviderProfileItem[]>([]);
  const [isLoadingProviders, setIsLoadingProviders] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [isTogglingProvider, setIsTogglingProvider] = useState<string | null>(null);

  // Create Provider Modal
  const [isCreateProviderModalOpen, setIsCreateProviderModalOpen] = useState(false);
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newProviderType, setNewProviderType] = useState<"LOCAL_OPENAI_COMPATIBLE" | "REMOTE_OPENAI_COMPATIBLE">("LOCAL_OPENAI_COMPATIBLE");
  const [newEgressClass, setNewEgressClass] = useState<"LOCAL_ONLY" | "APPROVED_REMOTE">("LOCAL_ONLY");
  const [newBaseUrl, setNewBaseUrl] = useState("");
  const [newModelId, setNewModelId] = useState("");
  const [newSecretRef, setNewSecretRef] = useState("");
  const [createProviderModalError, setCreateProviderModalError] = useState<string | null>(null);
  const [isCreatingProvider, setIsCreatingProvider] = useState(false);

  // Activate Provider Modal
  const [targetActivateProfile, setTargetActivateProfile] = useState<AdminProviderProfileItem | null>(null);
  const [isActivateModalOpen, setIsActivateModalOpen] = useState(false);
  const [confirmRemoteEgress, setConfirmRemoteEgress] = useState(false);
  const [activateReason, setActivateReason] = useState("");
  const [activateModalError, setActivateModalError] = useState<string | null>(null);

  const fetchProviders = async () => {
    try {
      setIsLoadingProviders(true);
      setProviderError(null);
      const data = await apiFetch<AdminProviderProfileItem[]>("/api/v1/admin/provider-profiles");
      setProviders(data || []);
    } catch (err: any) {
      setProviderError(err?.message || "Failed to load AI provider profiles.");
    } finally {
      setIsLoadingProviders(false);
    }
  };

  const handleCreateProvider = async (e: FormEvent) => {
    e.preventDefault();
    setCreateProviderModalError(null);

    if (!newDisplayName.trim()) {
      setCreateProviderModalError("Display Name is required.");
      return;
    }

    try {
      setIsCreatingProvider(true);
      const payload = {
        displayName: newDisplayName.trim(),
        providerType: newProviderType,
        egressClass: newEgressClass,
        baseUrl: newBaseUrl.trim() || undefined,
        modelIdentifier: newModelId.trim() || undefined,
        secretRef: newSecretRef.trim() || undefined,
      };

      await apiFetch("/api/v1/admin/provider-profiles", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setIsCreateProviderModalOpen(false);
      setNewDisplayName("");
      setNewBaseUrl("");
      setNewModelId("");
      setNewSecretRef("");
      setActionSuccess(`Provider profile '${newDisplayName.trim()}' created successfully.`);
      fetchProviders();
    } catch (err: any) {
      setCreateProviderModalError(err?.message || "Failed to create provider profile.");
    } finally {
      setIsCreatingProvider(false);
    }
  };

  const handleOpenActivateModal = (profile: AdminProviderProfileItem) => {
    setTargetActivateProfile(profile);
    setConfirmRemoteEgress(false);
    setActivateReason("");
    setActivateModalError(null);
    setIsActivateModalOpen(true);
  };

  const handleConfirmActivate = async (e: FormEvent) => {
    e.preventDefault();
    if (!targetActivateProfile) return;
    setActivateModalError(null);

    if (targetActivateProfile.egressClass === "APPROVED_REMOTE" && !confirmRemoteEgress) {
      setActivateModalError("Explicit confirmation of remote data egress is required.");
      return;
    }

    try {
      setIsTogglingProvider(targetActivateProfile.profileId);
      await apiFetch(`/api/v1/admin/provider-profiles/${targetActivateProfile.profileId}/activate`, {
        method: "POST",
        body: JSON.stringify({
          version: targetActivateProfile.version,
          confirmRemoteEgress: confirmRemoteEgress,
          reason: activateReason.trim() || undefined,
        }),
      });

      setIsActivateModalOpen(false);
      setActionSuccess(`Provider profile '${targetActivateProfile.displayName}' activated successfully.`);
      fetchProviders();
    } catch (err: any) {
      setActivateModalError(err?.message || "Failed to activate provider profile.");
    } finally {
      setIsTogglingProvider(null);
    }
  };

  const handleDisableProvider = async (profile: AdminProviderProfileItem) => {
    try {
      setIsTogglingProvider(profile.profileId);
      await apiFetch(`/api/v1/admin/provider-profiles/${profile.profileId}/disable`, {
        method: "POST",
        body: JSON.stringify({
          version: profile.version,
          reason: "Disabled via Admin Workspace",
        }),
      });
      setActionSuccess(`Provider profile '${profile.displayName}' disabled successfully.`);
      fetchProviders();
    } catch (err: any) {
      setProviderError(err?.message || "Failed to disable provider profile.");
    } finally {
      setIsTogglingProvider(null);
    }
  };

  const fetchUsers = async () => {
    try {
      setIsLoadingUsers(true);
      setUserError(null);
      const data = await apiFetch<UserItem[]>("/api/v1/admin/users");
      setUsers(data || []);
    } catch (err: any) {
      setUserError(err?.message || "Failed to load platform users.");
    } finally {
      setIsLoadingUsers(false);
    }
  };

  const fetchSecurityEvents = async (offset = 0) => {
    try {
      setIsLoadingEvents(true);
      const data = await apiFetch<PaginatedEvents>(
        `/api/v1/admin/security-events?limit=25&offset=${offset}`
      );
      setEvents(data.items || []);
      setEventsTotal(data.total || 0);
      setEventsOffset(data.offset || 0);
    } catch (err: any) {
      console.error("Failed to load security audit events", err);
    } finally {
      setIsLoadingEvents(false);
    }
  };

  useEffect(() => {
    if (activeTab === "users") {
      fetchUsers();
    } else if (activeTab === "events") {
      fetchSecurityEvents(0);
    } else if (activeTab === "ai_providers") {
      fetchProviders();
    }
  }, [activeTab]);

  const handleCreateUser = async (e: FormEvent) => {
    e.preventDefault();
    setCreateModalError(null);

    if (!createEmail.trim() || !createDisplayName.trim() || !createTempPassword) {
      setCreateModalError("All fields are required.");
      return;
    }
    if (createTempPassword.length < 8) {
      setCreateModalError("Temporary password must be at least 8 characters.");
      return;
    }

    try {
      setIsCreatingUser(true);
      await apiFetch("/api/v1/admin/users", {
        method: "POST",
        body: JSON.stringify({
          email: createEmail.trim(),
          displayName: createDisplayName.trim(),
          role: createRole,
          temporaryPassword: createTempPassword,
        }),
      });

      setIsCreateModalOpen(false);
      setCreateEmail("");
      setCreateDisplayName("");
      setCreateTempPassword("");
      setActionSuccess(`User '${createEmail.trim()}' created successfully with forced password change.`);
      fetchUsers();
    } catch (err: any) {
      if (err?.code === "USER_ALREADY_EXISTS") {
        setCreateModalError(`A user with email '${createEmail.trim()}' already exists.`);
      } else {
        setCreateModalError(err?.message || "Failed to create user.");
      }
    } finally {
      setIsCreatingUser(false);
    }
  };

  const handleToggleUserActive = async (user: UserItem) => {
    const newActiveState = !user.isActive;
    const confirmMsg = newActiveState
      ? `Activate user '${user.displayName}'?`
      : `Deactivate user '${user.displayName}'? All active sessions will be terminated immediately.`;

    if (!window.confirm(confirmMsg)) return;

    try {
      await apiFetch(`/api/v1/admin/users/${user.userId}`, {
        method: "PATCH",
        body: JSON.stringify({ isActive: newActiveState }),
      });
      setActionSuccess(
        `User '${user.displayName}' ${newActiveState ? "activated" : "deactivated"} successfully.`
      );
      fetchUsers();
    } catch (err: any) {
      alert(err?.message || "Failed to update user status.");
    }
  };

  const handleChangeRole = async (user: UserItem, newRole: "ADMIN" | "RECRUITER" | "REVIEWER") => {
    if (user.role === newRole) return;
    if (!window.confirm(`Change role of '${user.displayName}' from ${user.role} to ${newRole}? Target sessions will be revoked.`)) {
      return;
    }

    try {
      await apiFetch(`/api/v1/admin/users/${user.userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole }),
      });
      setActionSuccess(`Role for '${user.displayName}' updated to ${newRole}.`);
      fetchUsers();
    } catch (err: any) {
      alert(err?.message || "Failed to update user role.");
    }
  };

  const handleResetPassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;
    setResetModalError(null);

    if (resetTempPassword.length < 8) {
      setResetModalError("Temporary password must be at least 8 characters.");
      return;
    }

    try {
      setIsResetting(true);
      await apiFetch(`/api/v1/admin/users/${selectedUser.userId}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ temporaryPassword: resetTempPassword }),
      });

      setIsResetModalOpen(false);
      setResetTempPassword("");
      setActionSuccess(
        `Password reset successfully for '${selectedUser.displayName}'. Sessions revoked.`
      );
      fetchUsers();
    } catch (err: any) {
      setResetModalError(err?.message || "Failed to reset password.");
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div className="admin-workspace-container" role="region" aria-label="Administrator Workspace">
      {/* Action Notification Toast */}
      {actionSuccess && (
        <div className="feedback-box success admin-toast" role="status" aria-live="polite">
          <Icon name="check" size={16} />
          <p className="feedback-text">{actionSuccess}</p>
          <button
            type="button"
            className="toast-close-btn"
            onClick={() => setActionSuccess(null)}
            aria-label="Dismiss message"
          >
            <Icon name="x" size={14} />
          </button>
        </div>
      )}

      {activeTab === "users" && (
        <div className="admin-section-card">
          <div className="admin-section-header">
            <div>
              <h2 className="admin-section-title">Platform Users</h2>
              <p className="admin-section-subtitle">
                Manage accounts, roles, access states, and temporary credentials.
              </p>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setIsCreateModalOpen(true)}
            >
              <Icon name="plus" size={16} />
              <span>Create New User</span>
            </button>
          </div>

          {userError && (
            <div className="feedback-box error" role="alert">
              <Icon name="alert-triangle" size={16} />
              <p className="feedback-text error">{userError}</p>
            </div>
          )}

          {isLoadingUsers ? (
            <div className="admin-table-loading">
              <div className="loading-spinner-sm" />
              <span>Loading internal accounts...</span>
            </div>
          ) : (
            <div className="admin-table-wrapper">
              <table className="admin-data-table" aria-label="Users Table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Password Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="table-empty-cell">
                        No internal users found.
                      </td>
                    </tr>
                  ) : (
                    users.map((u) => (
                      <tr key={u.userId}>
                        <td>
                          <div className="table-user-cell">
                            <span className="table-user-name">{u.displayName}</span>
                            <span className="table-user-email">{u.email}</span>
                          </div>
                        </td>
                        <td>
                          <select
                            className="role-selector-inline"
                            value={u.role}
                            onChange={(e) =>
                              handleChangeRole(u, e.target.value as any)
                            }
                            aria-label={`Change role for ${u.displayName}`}
                          >
                            <option value="ADMIN">ADMIN</option>
                            <option value="RECRUITER">RECRUITER</option>
                            <option value="REVIEWER">REVIEWER</option>
                          </select>
                        </td>
                        <td>
                          <span
                            className={`status-pill ${
                              u.isActive ? "status-active" : "status-inactive"
                            }`}
                          >
                            {u.isActive ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td>
                          {u.mustChangePassword ? (
                            <span className="status-pill status-warn">
                              Change Required
                            </span>
                          ) : (
                            <span className="status-pill status-neutral">
                              Set
                            </span>
                          )}
                        </td>
                        <td className="table-date-cell">
                          {new Date(u.createdAt).toLocaleDateString()}
                        </td>
                        <td>
                          <div className="table-actions-group">
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => {
                                setSelectedUser(u);
                                setIsResetModalOpen(true);
                                setResetModalError(null);
                              }}
                              title="Reset temporary password"
                            >
                              Reset Password
                            </button>
                            <button
                              type="button"
                              className={`btn btn-sm ${
                                u.isActive ? "btn-secondary" : "btn-primary"
                              }`}
                              onClick={() => handleToggleUserActive(u)}
                            >
                              {u.isActive ? "Deactivate" : "Activate"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === "events" && (
        <div className="admin-section-card">
          <div className="admin-section-header">
            <div>
              <h2 className="admin-section-title">Security &amp; Audit Logs</h2>
              <p className="admin-section-subtitle">
                Immutable, privacy-safe record of authentication and administrative actions.
              </p>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => fetchSecurityEvents(eventsOffset)}
            >
              <Icon name="refresh" size={14} />
              <span>Refresh Logs</span>
            </button>
          </div>

          {isLoadingEvents ? (
            <div className="admin-table-loading">
              <div className="loading-spinner-sm" />
              <span>Loading audit logs...</span>
            </div>
          ) : (
            <div className="admin-table-wrapper">
              <table className="admin-data-table" aria-label="Security Events Table">
                <thead>
                  <tr>
                    <th>Occurred At</th>
                    <th>Event Type</th>
                    <th>Result</th>
                    <th>Reason Code</th>
                    <th>Resource</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="table-empty-cell">
                        No security events recorded.
                      </td>
                    </tr>
                  ) : (
                    events.map((ev) => (
                      <tr key={ev.eventId}>
                        <td className="table-date-cell">
                          {new Date(ev.occurredAt).toLocaleString()}
                        </td>
                        <td>
                          <code className="event-type-tag">{ev.eventType}</code>
                        </td>
                        <td>
                          <span
                            className={`status-pill ${
                              ev.result === "SUCCESS"
                                ? "status-active"
                                : "status-inactive"
                            }`}
                          >
                            {ev.result}
                          </span>
                        </td>
                        <td>
                          <span className="reason-code-text">{ev.reasonCode}</span>
                        </td>
                        <td>
                          <span className="resource-ref-text">
                            {ev.resourceType || "system"}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>

              {eventsTotal > 25 && (
                <div className="admin-pagination-bar">
                  <span className="pagination-summary">
                    Showing {eventsOffset + 1} - {Math.min(eventsOffset + 25, eventsTotal)} of {eventsTotal} events
                  </span>
                  <div className="pagination-controls">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={eventsOffset === 0}
                      onClick={() => fetchSecurityEvents(Math.max(0, eventsOffset - 25))}
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={eventsOffset + 25 >= eventsTotal}
                      onClick={() => fetchSecurityEvents(eventsOffset + 25)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Create User Modal Dialog */}
      {isCreateModalOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="create-user-title">
          <div className="modal-card">
            <div className="modal-header">
              <h3 id="create-user-title" className="modal-title">Create Internal User</h3>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setIsCreateModalOpen(false)}
                aria-label="Close dialog"
              >
                <Icon name="x" size={16} />
              </button>
            </div>

            {createModalError && (
              <div className="feedback-box error" role="alert">
                <Icon name="alert-triangle" size={16} />
                <p className="feedback-text error">{createModalError}</p>
              </div>
            )}

            <form onSubmit={handleCreateUser} className="modal-form" noValidate>
              <div className="form-group">
                <label htmlFor="create-email" className="form-label">
                  Email Address
                </label>
                <input
                  id="create-email"
                  type="email"
                  className="form-input"
                  placeholder="recruiter@company.com"
                  value={createEmail}
                  onChange={(e) => setCreateEmail(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="create-display-name" className="form-label">
                  Display Name
                </label>
                <input
                  id="create-display-name"
                  type="text"
                  className="form-input"
                  placeholder="Jane Recruiter"
                  value={createDisplayName}
                  onChange={(e) => setCreateDisplayName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="create-role" className="form-label">
                  Platform Role
                </label>
                <select
                  id="create-role"
                  className="form-input"
                  value={createRole}
                  onChange={(e) => setCreateRole(e.target.value as any)}
                >
                  <option value="RECRUITER">RECRUITER (Candidate Directory, Resumes, Profiles)</option>
                  <option value="REVIEWER">REVIEWER (Evaluation &amp; Scorecards)</option>
                  <option value="ADMIN">ADMIN (User Management &amp; Audit Logs)</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="create-temp-password" className="form-label">
                  Temporary Password (min. 8 characters)
                </label>
                <input
                  id="create-temp-password"
                  type="password"
                  className="form-input"
                  placeholder="TemporaryPass123!"
                  value={createTempPassword}
                  onChange={(e) => setCreateTempPassword(e.target.value)}
                  required
                />
                <span className="form-hint-text">
                  User will be forced to change this password upon first sign-in.
                </span>
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsCreateModalOpen(false)}
                  disabled={isCreatingUser}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isCreatingUser}
                >
                  {isCreatingUser ? "Creating..." : "Create Account"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reset Password Modal Dialog */}
      {isResetModalOpen && selectedUser && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="reset-user-title">
          <div className="modal-card">
            <div className="modal-header">
              <h3 id="reset-user-title" className="modal-title">
                Reset Password for {selectedUser.displayName}
              </h3>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setIsResetModalOpen(false)}
                aria-label="Close dialog"
              >
                <Icon name="x" size={16} />
              </button>
            </div>

            {resetModalError && (
              <div className="feedback-box error" role="alert">
                <Icon name="alert-triangle" size={16} />
                <p className="feedback-text error">{resetModalError}</p>
              </div>
            )}

            <form onSubmit={handleResetPassword} className="modal-form" noValidate>
              <p className="modal-description">
                Setting a new temporary password will invalidate all current active sessions for <strong>{selectedUser.email}</strong> and require a password change on next login.
              </p>

              <div className="form-group">
                <label htmlFor="reset-temp-pw" className="form-label">
                  New Temporary Password
                </label>
                <input
                  id="reset-temp-pw"
                  type="password"
                  className="form-input"
                  placeholder="NewTemporaryPass123!"
                  value={resetTempPassword}
                  onChange={(e) => setResetTempPassword(e.target.value)}
                  required
                />
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsResetModalOpen(false)}
                  disabled={isResetting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isResetting}
                >
                  {isResetting ? "Resetting..." : "Reset & Invalidate Sessions"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AI Providers Section */}
      {activeTab === "ai_providers" && (
        <div className="admin-section-card">
          <div className="admin-section-header">
            <div>
              <h2 className="admin-section-title">AI Provider Profiles</h2>
              <p className="admin-section-subtitle">
                Configure provider backends, egress boundaries, and optimistic activation controls.
              </p>
            </div>
            <div className="admin-header-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={fetchProviders}
                disabled={isLoadingProviders}
              >
                <Icon name="refresh" size={16} />
                <span>Refresh</span>
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setIsCreateProviderModalOpen(true)}
              >
                <Icon name="plus" size={16} />
                <span>Add Provider Profile</span>
              </button>
            </div>
          </div>

          {providerError && (
            <div className="feedback-box error admin-error-banner" role="alert">
              <Icon name="alert-triangle" size={16} />
              <p className="feedback-text">{providerError}</p>
            </div>
          )}

          {isLoadingProviders ? (
            <div className="admin-table-loading">
              <div className="loading-spinner-sm" />
              <span>Loading provider profiles...</span>
            </div>
          ) : (
            <div className="admin-table-wrapper">
              <table className="admin-data-table" aria-label="AI Providers Table">
                <thead>
                  <tr>
                    <th>Display Name</th>
                    <th>Type & Model</th>
                    <th>Egress Class</th>
                    <th>Base URL</th>
                    <th>Secret Status</th>
                    <th>Compatibility</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="table-empty-cell">
                        No provider profiles configured. Click "Add Provider Profile" to create one.
                      </td>
                    </tr>
                  ) : (
                    providers.map((p) => (
                      <tr key={p.profileId} className={p.enabled ? "row-active-provider" : ""}>
                        <td>
                          <div className="provider-name-cell">
                            <strong>{p.displayName}</strong>
                            <span className="profile-version-tag">v{p.version}</span>
                          </div>
                        </td>
                        <td>
                          <div className="provider-type-cell">
                            <code>{p.providerType}</code>
                            {p.modelIdentifier && (
                              <span className="model-id-tag">{p.modelIdentifier}</span>
                            )}
                          </div>
                        </td>
                        <td>
                          <span
                            className={`status-pill ${
                              p.egressClass === "LOCAL_ONLY"
                                ? "status-active"
                                : "status-badge-remote"
                            }`}
                          >
                            {p.egressClass === "LOCAL_ONLY" ? "Local Only" : "Approved Remote"}
                          </span>
                        </td>
                        <td>
                          <span className="base-url-text">
                            {p.baseUrlMasked || <em className="text-muted">Standard / Local Default</em>}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`secret-status-tag ${
                              p.secretStatus === "CONFIGURED"
                                ? "secret-ok"
                                : p.secretStatus === "MISSING"
                                ? "secret-missing"
                                : "secret-none"
                            }`}
                          >
                            {p.secretStatus === "CONFIGURED" && "✓ Configured"}
                            {p.secretStatus === "MISSING" && "⚠ Missing Secret"}
                            {p.secretStatus === "NOT_REQUIRED" && "Not Required"}
                          </span>
                        </td>
                        <td>
                          <span className="compat-status-tag">
                            {p.compatibilityStatus === "COMPATIBLE" ? "Compatible" : "Not Tested"}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`status-pill ${
                              p.enabled ? "status-active" : "status-inactive"
                            }`}
                          >
                            {p.enabled ? "Active" : "Disabled"}
                          </span>
                        </td>
                        <td>
                          <div className="table-actions-cell">
                            {p.enabled ? (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleDisableProvider(p)}
                                disabled={isTogglingProvider === p.profileId}
                              >
                                {isTogglingProvider === p.profileId ? "Disabling..." : "Disable"}
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={() => handleOpenActivateModal(p)}
                                disabled={isTogglingProvider === p.profileId}
                              >
                                Activate
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Create Provider Modal */}
      {isCreateProviderModalOpen && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="create-provider-title">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3 id="create-provider-title" className="modal-title">
                Add AI Provider Profile
              </h3>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setIsCreateProviderModalOpen(false)}
                aria-label="Close modal"
              >
                <Icon name="x" size={18} />
              </button>
            </div>

            {createProviderModalError && (
              <div className="feedback-box error" role="alert">
                <Icon name="alert-triangle" size={16} />
                <p className="feedback-text error">{createProviderModalError}</p>
              </div>
            )}

            <form onSubmit={handleCreateProvider} className="modal-form" noValidate>
              <div className="form-group">
                <label htmlFor="provider-display-name" className="form-label">
                  Display Name *
                </label>
                <input
                  id="provider-display-name"
                  type="text"
                  className="form-input"
                  placeholder="e.g. Local llama.cpp Qwen3 / OpenAI Production"
                  value={newDisplayName}
                  onChange={(e) => setNewDisplayName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="provider-type-select" className="form-label">
                  Provider Backend Type *
                </label>
                <select
                  id="provider-type-select"
                  className="form-select"
                  value={newProviderType}
                  onChange={(e) => setNewProviderType(e.target.value as any)}
                >
                  <option value="LOCAL_OPENAI_COMPATIBLE">Local OpenAI-Compatible (e.g. llama.cpp / Ollama)</option>
                  <option value="REMOTE_OPENAI_COMPATIBLE">Remote OpenAI-Compatible (e.g. OpenAI / Azure)</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="provider-egress-class" className="form-label">
                  Egress Boundary Class *
                </label>
                <select
                  id="provider-egress-class"
                  className="form-select"
                  value={newEgressClass}
                  onChange={(e) => setNewEgressClass(e.target.value as any)}
                >
                  <option value="LOCAL_ONLY">LOCAL_ONLY (Enforces loopback / local boundary)</option>
                  <option value="APPROVED_REMOTE">APPROVED_REMOTE (Requires HTTPS & Host Allowlist)</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="provider-base-url" className="form-label">
                  Base URL (optional for standard loopback)
                </label>
                <input
                  id="provider-base-url"
                  type="url"
                  className="form-input"
                  placeholder={
                    newEgressClass === "LOCAL_ONLY"
                      ? "http://127.0.0.1:8080/v1"
                      : "https://api.openai.com/v1"
                  }
                  value={newBaseUrl}
                  onChange={(e) => setNewBaseUrl(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="provider-model-id" className="form-label">
                  Model Identifier (optional)
                </label>
                <input
                  id="provider-model-id"
                  type="text"
                  className="form-input"
                  placeholder="e.g. qwen2.5:7b or gpt-4o-mini"
                  value={newModelId}
                  onChange={(e) => setNewModelId(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label htmlFor="provider-secret-ref" className="form-label">
                  Secret Reference (Controlled Format: env:VAR_NAME)
                </label>
                <input
                  id="provider-secret-ref"
                  type="text"
                  className="form-input"
                  placeholder="e.g. env:LLM_OPENAI_API_KEY"
                  value={newSecretRef}
                  onChange={(e) => setNewSecretRef(e.target.value)}
                />
                <span className="form-help-text">
                  Plaintext credentials are never accepted. Specify an environment variable reference.
                </span>
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsCreateProviderModalOpen(false)}
                  disabled={isCreatingProvider}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isCreatingProvider}
                >
                  {isCreatingProvider ? "Saving Profile..." : "Create Provider Profile"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Activate Provider Confirmation Modal */}
      {isActivateModalOpen && targetActivateProfile && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="activate-provider-title">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3 id="activate-provider-title" className="modal-title">
                Activate Provider: {targetActivateProfile.displayName}
              </h3>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setIsActivateModalOpen(false)}
                aria-label="Close modal"
              >
                <Icon name="x" size={18} />
              </button>
            </div>

            {activateModalError && (
              <div className="feedback-box error" role="alert">
                <Icon name="alert-triangle" size={16} />
                <p className="feedback-text error">{activateModalError}</p>
              </div>
            )}

            <form onSubmit={handleConfirmActivate} className="modal-form" noValidate>
              <p className="modal-description">
                Activating this provider will immediately route all future AI interview and assistance requests to <strong>{targetActivateProfile.displayName}</strong>. Any currently active provider in this organization will be disabled.
              </p>

              {targetActivateProfile.egressClass === "APPROVED_REMOTE" && (
                <div className="remote-egress-warning-box">
                  <div className="warning-box-header">
                    <Icon name="shield" size={18} />
                    <strong>Remote Data Egress Confirmation Required</strong>
                  </div>
                  <p className="warning-box-body">
                    This profile is configured as an <strong>APPROVED_REMOTE</strong> provider ({targetActivateProfile.baseUrlMasked}). Activating it means prompt payloads and bounded interview requests may egress across the approved network boundary.
                  </p>
                  <label className="checkbox-label" htmlFor="confirm-remote-egress-cb">
                    <input
                      id="confirm-remote-egress-cb"
                      type="checkbox"
                      checked={confirmRemoteEgress}
                      onChange={(e) => setConfirmRemoteEgress(e.target.checked)}
                      required
                    />
                    <span>I confirm and authorize remote data egress for this provider profile.</span>
                  </label>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="activate-reason-input" className="form-label">
                  Activation Audit Reason (optional)
                </label>
                <input
                  id="activate-reason-input"
                  type="text"
                  className="form-input"
                  placeholder="e.g. Switched to local Qwen3 instance for testing"
                  value={activateReason}
                  onChange={(e) => setActivateReason(e.target.value)}
                />
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsActivateModalOpen(false)}
                  disabled={isTogglingProvider !== null}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={
                    isTogglingProvider !== null ||
                    (targetActivateProfile.egressClass === "APPROVED_REMOTE" && !confirmRemoteEgress)
                  }
                >
                  {isTogglingProvider ? "Activating..." : "Confirm Activation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
