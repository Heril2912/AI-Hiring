import React, { useState, FormEvent } from "react";
import { useAuth } from "../../context/AuthContext";
import { Icon } from "../Icon";

export function ChangePasswordPage() {
  const { user, changePassword, logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setValidationError(null);
    setServerError(null);

    if (!currentPassword) {
      setValidationError("Please enter your current or temporary password.");
      return;
    }
    if (newPassword.length < 8) {
      setValidationError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setValidationError("New password confirmation does not match.");
      return;
    }
    if (currentPassword === newPassword) {
      setValidationError("New password cannot be the same as your current temporary password.");
      return;
    }

    try {
      setIsSubmitting(true);
      await changePassword(currentPassword, newPassword, confirmPassword);
    } catch (err: any) {
      if (err?.code === "INVALID_CURRENT_PASSWORD") {
        setServerError("The current password provided is incorrect.");
      } else if (err?.code === "PASSWORD_REUSE_FORBIDDEN") {
        setServerError("You cannot reuse your previous password. Please choose a new one.");
      } else {
        setServerError(err?.message || "Failed to update password. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="auth-page-container">
      <div className="auth-card" role="region" aria-label="Password Change Required">
        <div className="auth-header">
          <div className="auth-logo-badge warn" aria-hidden="true">
            <Icon name="shield" size={24} />
          </div>
          <h1 className="auth-title">Password Update Required</h1>
          <p className="auth-subtitle">
            Welcome, <strong>{user?.displayName || "User"}</strong>. For platform security, please set a new permanent password before proceeding.
          </p>
        </div>

        {(validationError || serverError) && (
          <div className="feedback-box error" role="alert" aria-live="polite">
            <Icon name="alert-triangle" size={16} />
            <p className="feedback-text error">
              {validationError || serverError}
            </p>
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="current-pw" className="form-label">
              Current / Temporary Password
            </label>
            <div className="input-with-icon">
              <span className="input-icon-prefix" aria-hidden="true">
                <Icon name="shield" size={16} />
              </span>
              <input
                id="current-pw"
                type={showCurrent ? "text" : "password"}
                className="form-input"
                value={currentPassword}
                onChange={(e) => {
                  setCurrentPassword(e.target.value);
                  if (validationError) setValidationError(null);
                }}
                disabled={isSubmitting}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowCurrent(!showCurrent)}
                aria-label={showCurrent ? "Hide current password" : "Show current password"}
                title={showCurrent ? "Hide current password" : "Show current password"}
              >
                <Icon name="eye" size={16} />
              </button>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="new-pw" className="form-label">
              New Password (min. 8 characters)
            </label>
            <div className="input-with-icon">
              <span className="input-icon-prefix" aria-hidden="true">
                <Icon name="shield" size={16} />
              </span>
              <input
                id="new-pw"
                type={showNew ? "text" : "password"}
                className="form-input"
                value={newPassword}
                onChange={(e) => {
                  setNewPassword(e.target.value);
                  if (validationError) setValidationError(null);
                }}
                disabled={isSubmitting}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowNew(!showNew)}
                aria-label={showNew ? "Hide new password" : "Show new password"}
                title={showNew ? "Hide new password" : "Show new password"}
              >
                <Icon name="eye" size={16} />
              </button>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="confirm-pw" className="form-label">
              Confirm New Password
            </label>
            <div className="input-with-icon">
              <span className="input-icon-prefix" aria-hidden="true">
                <Icon name="shield" size={16} />
              </span>
              <input
                id="confirm-pw"
                type={showConfirm ? "text" : "password"}
                className="form-input"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  if (validationError) setValidationError(null);
                }}
                disabled={isSubmitting}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowConfirm(!showConfirm)}
                aria-label={showConfirm ? "Hide password confirmation" : "Show password confirmation"}
                title={showConfirm ? "Hide password confirmation" : "Show password confirmation"}
              >
                <Icon name="eye" size={16} />
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary auth-submit-btn"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <span className="loading-spinner-sm" aria-hidden="true" />
                <span>Updating Password...</span>
              </>
            ) : (
              <span>Update Password &amp; Continue</span>
            )}
          </button>
        </form>

        <div className="auth-footer-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={logout}
            disabled={isSubmitting}
          >
            <Icon name="arrow-left" size={14} />
            <span>Sign Out</span>
          </button>
        </div>
      </div>
    </div>
  );
}
