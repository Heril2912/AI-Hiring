import React, { useState, FormEvent } from "react";
import { useAuth } from "../../context/AuthContext";
import { Icon } from "../Icon";

export function LoginPage() {
  const { login, sessionError, clearSessionError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setValidationError(null);
    setServerError(null);
    clearSessionError();

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setValidationError("Please enter your email address.");
      return;
    }
    if (!password) {
      setValidationError("Please enter your password.");
      return;
    }

    try {
      setIsSubmitting(true);
      await login(trimmedEmail, password);
    } catch (err: any) {
      setServerError(
        err?.message || "Unable to sign in with the provided credentials."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="auth-page-container">
      <div className="auth-card" role="region" aria-label="Sign In Card">
        <div className="auth-header">
          <div className="auth-logo-badge" aria-hidden="true">
            <Icon name="sparkles" size={24} />
          </div>
          <h1 className="auth-title">AI-Driven Smart Hiring</h1>
          <p className="auth-subtitle">
            Internal Recruitment Platform &amp; Audited Candidate Profiles
          </p>
        </div>

        {sessionError && (
          <div className="feedback-box info" role="status" aria-live="polite">
            <Icon name="info" size={16} />
            <p className="feedback-text">{sessionError}</p>
          </div>
        )}

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
            <label htmlFor="login-email" className="form-label">
              Work Email Address
            </label>
            <div className="input-with-icon">
              <span className="input-icon-prefix" aria-hidden="true">
                <Icon name="mail" size={16} />
              </span>
              <input
                id="login-email"
                type="email"
                className="form-input"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (validationError) setValidationError(null);
                }}
                disabled={isSubmitting}
                autoComplete="email"
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="login-password" className="form-label">
              Password
            </label>
            <div className="input-with-icon">
              <span className="input-icon-prefix" aria-hidden="true">
                <Icon name="shield" size={16} />
              </span>
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                className="form-input"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (validationError) setValidationError(null);
                }}
                disabled={isSubmitting}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                title={showPassword ? "Hide password" : "Show password"}
              >
                <Icon name={showPassword ? "eye" : "eye"} size={16} />
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
                <span>Signing In...</span>
              </>
            ) : (
              <span>Sign In to Platform</span>
            )}
          </button>
        </form>

        <div className="auth-footer">
          <p className="auth-footer-note">
            Protected internal system. Unauthorized access is prohibited and audited.
          </p>
        </div>
      </div>
    </div>
  );
}
