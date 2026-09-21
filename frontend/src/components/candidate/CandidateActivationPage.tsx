import React, { useState, useEffect } from "react";
import { useCandidateAuth } from "../../context/CandidateAuthContext";
import { Icon } from "../Icon";

interface CandidateActivationPageProps {
  onSuccess?: () => void;
  onNavigateLogin?: () => void;
}

export function CandidateActivationPage({
  onSuccess,
  onNavigateLogin,
}: CandidateActivationPageProps) {
  const { activate } = useCandidateAuth();

  const [token, setToken] = useState<string>("");
  const [hasToken, setHasToken] = useState<boolean>(true);
  const [password, setPassword] = useState<string>("");
  const [confirmation, setConfirmation] = useState<string>("");
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [showConfirmation, setShowConfirmation] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Read fragment token once on mount and immediately strip it from displayed URL
  useEffect(() => {
    if (typeof window === "undefined") return;

    let extractedToken = "";
    const hash = window.location.hash;
    if (hash && hash.includes("token=")) {
      const match = hash.match(/token=([^&]+)/);
      if (match && match[1]) {
        extractedToken = decodeURIComponent(match[1]);
      }
    }

    if (extractedToken) {
      setToken(extractedToken);
      setHasToken(true);
      // Remove hash from URL without reloading page or polluting browser history
      try {
        window.history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search
        );
      } catch {
        // Fallback for non-standard environments
      }
    } else {
      setHasToken(false);
      setErrorMessage(
        "No activation token detected. Please ensure you clicked the full activation link provided by your recruiter."
      );
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!token) {
      setErrorMessage("Activation token is missing. Please check your link.");
      return;
    }

    if (password.length < 8) {
      setErrorMessage("Password must be at least 8 characters long.");
      return;
    }

    if (password !== confirmation) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await activate(token, password, confirmation);
      if (onSuccess) {
        onSuccess();
      }
    } catch (err: any) {
      setErrorMessage(
        err.message ||
          "Unable to activate account. The invitation may be invalid, expired, or already used."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="candidate-auth-layout">
      <div className="candidate-auth-card" role="main">
        <header className="candidate-auth-header">
          <div className="candidate-badge-container">
            <span className="candidate-portal-badge">Candidate Practice Portal</span>
          </div>
          <h1 className="candidate-auth-title">Activate Practice Account</h1>
          <p className="candidate-auth-subtitle">
            Set a secure password to access your candidate practice interview portal.
          </p>
        </header>

        {errorMessage && (
          <div
            className="candidate-auth-error-banner"
            role="alert"
            aria-live="assertive"
          >
            <Icon name="alert-triangle" className="error-icon" aria-hidden="true" />
            <span>{errorMessage}</span>
          </div>
        )}

        {!hasToken ? (
          <div className="candidate-auth-empty-state">
            <p className="empty-description">
              If your link expired or is invalid, please ask your recruiter to generate a fresh invitation.
            </p>
            {onNavigateLogin && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onNavigateLogin}
              >
                Go to Candidate Sign In
              </button>
            )}
          </div>
        ) : (
          <form className="candidate-auth-form" onSubmit={handleSubmit} noValidate>
            <div className="form-group">
              <label htmlFor="candidate-password">New Password</label>
              <div className="password-input-wrapper">
                <input
                  id="candidate-password"
                  name="candidate-password"
                  type={showPassword ? "text" : "password"}
                  className="form-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  required
                  autoComplete="new-password"
                  disabled={isSubmitting}
                />
                <button
                  type="button"
                  className="password-toggle-btn"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  tabIndex={0}
                >
                  <Icon
                    name={showPassword ? "eye-off" : "eye"}
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="candidate-password-confirm">Confirm Password</label>
              <div className="password-input-wrapper">
                <input
                  id="candidate-password-confirm"
                  name="candidate-password-confirm"
                  type={showConfirmation ? "text" : "password"}
                  className="form-input"
                  value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)}
                  placeholder="Re-enter password"
                  required
                  autoComplete="new-password"
                  disabled={isSubmitting}
                />
                <button
                  type="button"
                  className="password-toggle-btn"
                  onClick={() => setShowConfirmation(!showConfirmation)}
                  aria-label={showConfirmation ? "Hide confirmation password" : "Show confirmation password"}
                  tabIndex={0}
                >
                  <Icon
                    name={showConfirmation ? "eye-off" : "eye"}
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>

            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary btn-block"
                disabled={isSubmitting || !password || !confirmation}
              >
                {isSubmitting ? (
                  <>
                    <span className="spinner-inline" aria-hidden="true" />
                    <span>Activating Account...</span>
                  </>
                ) : (
                  "Activate Account & Continue"
                )}
              </button>
            </div>
          </form>
        )}

        <footer className="candidate-auth-footer">
          <p className="footer-text">
            Already activated?{" "}
            <button
              type="button"
              className="link-button"
              onClick={onNavigateLogin}
            >
              Sign In to Practice Portal
            </button>
          </p>
        </footer>
      </div>
    </div>
  );
}
