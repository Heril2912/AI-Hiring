import React, { useState } from "react";
import { useCandidateAuth } from "../../context/CandidateAuthContext";
import { Icon } from "../Icon";

interface CandidateLoginPageProps {
  onSuccess?: () => void;
  onNavigateRegister?: () => void;
}

export function CandidateLoginPage({
  onSuccess,
  onNavigateRegister,
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
            <span className="candidate-portal-badge">Candidate portal</span>
          </div>
          <h1 className="candidate-auth-title">Sign in</h1>
          <p className="candidate-auth-subtitle">
            Apply for roles and complete your released interviews securely.
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
            <label htmlFor="candidate-email">Email address</label>
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
              aria-label="Sign In to Candidate Portal"
            >
              {isSubmitting ? (
                <>
                  <span className="spinner-inline" aria-hidden="true" />
                  <span>Signing in…</span>
                </>
              ) : (
                "Sign in"
              )}
            </button>
          </div>
        </form>

        <footer className="candidate-auth-footer" style={{ display: "flex", flexDirection: "column", gap: "8px", textAlign: "center" }}>
          <p className="footer-text" style={{ margin: 0 }}>
            Don't have an account?{" "}
            <button
              type="button"
              className="link-button"
              onClick={onNavigateRegister}
            >
              Create candidate account
            </button>
          </p>
          <p className="footer-text" style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
            Are you a recruiter or hiring manager?{" "}
            <a
              href="/"
              className="link-button"
              style={{ fontSize: "var(--text-xs)", color: "var(--accent-primary)" }}
              onClick={(e) => {
                if (typeof window !== "undefined" && window.history?.pushState) {
                  e.preventDefault();
                  window.history.pushState(null, "", "/");
                  window.dispatchEvent(new PopStateEvent("popstate"));
                }
              }}
            >
              Staff sign in
            </a>
          </p>
        </footer>
      </div>
    </div>
  );
}
