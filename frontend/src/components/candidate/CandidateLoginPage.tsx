import React, { useState } from "react";
import { useCandidateAuth } from "../../context/CandidateAuthContext";
import { Icon } from "../Icon";

interface CandidateLoginPageProps {
  onSuccess?: () => void;
  onNavigateActivate?: () => void;
}

export function CandidateLoginPage({
  onSuccess,
  onNavigateActivate,
}: CandidateLoginPageProps) {
  const { login } = useCandidateAuth();

  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const cleanEmail = email.trim();
    if (!cleanEmail || !password) {
      setErrorMessage("Please enter both your email address and password.");
      return;
    }

    setIsSubmitting(true);
    try {
      await login(cleanEmail, password);
      if (onSuccess) {
        onSuccess();
      }
    } catch (err: any) {
      setErrorMessage(
        err.message || "Unable to sign in with the provided credentials."
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
          <h1 className="candidate-auth-title">Candidate Sign In</h1>
          <p className="candidate-auth-subtitle">
            Sign in to access your practice interviews and review your sessions.
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

        <form className="candidate-auth-form" onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="candidate-email">Email Address</label>
            <input
              id="candidate-email"
              name="candidate-email"
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@example.com"
              required
              autoComplete="username"
              disabled={isSubmitting}
            />
          </div>

          <div className="form-group">
            <label htmlFor="candidate-login-password">Password</label>
            <div className="password-input-wrapper">
              <input
                id="candidate-login-password"
                name="candidate-login-password"
                type={showPassword ? "text" : "password"}
                className="form-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                required
                autoComplete="current-password"
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

          <div className="form-actions">
            <button
              type="submit"
              className="btn btn-primary btn-block"
              disabled={isSubmitting || !email.trim() || !password}
            >
              {isSubmitting ? (
                <>
                  <span className="spinner-inline" aria-hidden="true" />
                  <span>Signing in...</span>
                </>
              ) : (
                "Sign In to Practice Portal"
              )}
            </button>
          </div>
        </form>

        <footer className="candidate-auth-footer">
          <p className="footer-text">
            Received an invitation link?{" "}
            <button
              type="button"
              className="link-button"
              onClick={onNavigateActivate}
            >
              Activate your account
            </button>
          </p>
        </footer>
      </div>
    </div>
  );
}
