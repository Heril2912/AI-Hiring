import React, { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LoginPage } from "./components/auth/LoginPage";
import { ChangePasswordPage } from "./components/auth/ChangePasswordPage";
import { AuthenticatedShell } from "./components/AuthenticatedShell";
import { AdminWorkspace } from "./components/admin/AdminWorkspace";
import { ReviewerWorkspace } from "./components/reviewer/ReviewerWorkspace";
import { CandidatesDirectory, CandidateSummary } from "./components/CandidatesDirectory";
import { ResumeUpload } from "./components/ResumeUpload";
import { CandidateProfileReview, CandidateProfileData } from "./components/CandidateProfileReview";
import { ExtractionReview, ExtractionResultData } from "./components/ExtractionReview";
import { apiFetch } from "./api/client";
import { Icon } from "./components/Icon";

type ConnectionState = "checking" | "connected" | "unavailable";

function AuthenticatedApp() {
  const { user } = useAuth();
  const role = user?.role || "REVIEWER";

  // Navigation tab state
  const [activeNavTab, setActiveNavTab] = useState<string>(
    role === "ADMIN" ? "users" : role === "RECRUITER" ? "candidates" : "reviews"
  );
  const [activeView, setActiveView] = useState<"candidates" | "upload" | "profile" | "extraction">("candidates");

  useEffect(() => {
    setActiveNavTab(role === "ADMIN" ? "users" : role === "RECRUITER" ? "candidates" : "reviews");
  }, [role]);

  // Health check
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");

  // Recruiter candidate state
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState<boolean>(false);
  const [selectedProfile, setSelectedProfile] = useState<CandidateProfileData | null>(null);
  const [selectedExtraction, setSelectedExtraction] = useState<ExtractionResultData | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState<boolean>(false);
  const [profileLoadError, setProfileLoadError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth() {
      try {
        const response = await fetch("/api/v1/health", {
          signal: controller.signal,
        });

        if (!response.ok) {
          setConnectionState("unavailable");
          return;
        }

        const data = await response.json();
        if (data.status === "healthy" && data.database === "connected") {
          setConnectionState("connected");
        } else {
          setConnectionState("unavailable");
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setConnectionState("unavailable");
        }
      }
    }

    checkHealth();
    return () => controller.abort();
  }, []);

  // Fetch candidates if role is RECRUITER
  const fetchCandidates = async () => {
    if (role !== "RECRUITER") return;
    try {
      setIsLoadingCandidates(true);
      const data = await apiFetch<CandidateSummary[]>("/api/v1/resumes");
      setCandidates(data || []);
    } catch (e) {
      console.error("Failed to fetch candidates", e);
    } finally {
      setIsLoadingCandidates(false);
    }
  };

  useEffect(() => {
    if (role === "RECRUITER") {
      fetchCandidates();
    }
  }, [role]);

  const handleSelectCandidate = async (artifactId: string) => {
    setIsLoadingProfile(true);
    setProfileLoadError(null);

    try {
      const profData = await apiFetch<CandidateProfileData>(
        `/api/v1/resumes/${artifactId}/profile`
      );
      setSelectedProfile(profData);

      try {
        const extData = await apiFetch<ExtractionResultData>(
          `/api/v1/resumes/${artifactId}/extraction`
        );
        setSelectedExtraction(extData);
      } catch {
        setSelectedExtraction(null);
      }

      setActiveView("profile");
      fetchCandidates();
    } catch (err: any) {
      console.error("Failed to load candidate", err);
      setProfileLoadError(err?.message || "A network error occurred while loading profile.");
    } finally {
      setIsLoadingProfile(false);
    }
  };

  const handleCandidateProcessed = (artifactId: string) => {
    fetchCandidates();
    handleSelectCandidate(artifactId);
  };

  const handleNavigateTab = (tab: string) => {
    setActiveNavTab(tab);
    if (tab === "candidates") {
      setActiveView("candidates");
      fetchCandidates();
    } else if (tab === "upload") {
      setActiveView("upload");
    }
  };

  return (
    <AuthenticatedShell
      activeNavTab={activeNavTab}
      onNavigateTab={handleNavigateTab}
      candidateCount={candidates.length}
      connectionState={connectionState}
    >
      {role === "ADMIN" && <AdminWorkspace activeTab={activeNavTab} />}

      {role === "REVIEWER" && <ReviewerWorkspace />}

      {role === "RECRUITER" && (
        <>
          {isLoadingProfile && (
            <div className="profile-loading-overlay">
              <div className="loading-spinner" />
              <p className="loading-text">Loading candidate profile &amp; verified evidence...</p>
            </div>
          )}

          {profileLoadError && (
            <div className="feedback-box error" style={{ maxWidth: "600px", margin: "32px auto" }}>
              <Icon name="alert-triangle" size={18} />
              <div className="error-content">
                <p className="feedback-text error">{profileLoadError}</p>
                <button
                  type="button"
                  onClick={() => {
                    setActiveView("candidates");
                    setProfileLoadError(null);
                  }}
                  className="btn btn-secondary btn-sm"
                  style={{ marginTop: "10px" }}
                >
                  Back to Candidates
                </button>
              </div>
            </div>
          )}

          {!isLoadingProfile && !profileLoadError && (
            <>
              {activeView === "candidates" && (
                <CandidatesDirectory
                  candidates={candidates}
                  isLoading={isLoadingCandidates}
                  onSelectCandidate={handleSelectCandidate}
                  onNavigateUpload={() => {
                    setActiveView("upload");
                    setActiveNavTab("upload");
                  }}
                />
              )}

              {activeView === "upload" && (
                <ResumeUpload
                  onCandidateProcessed={handleCandidateProcessed}
                  onNavigateCandidates={() => {
                    setActiveView("candidates");
                    setActiveNavTab("candidates");
                    fetchCandidates();
                  }}
                />
              )}

              {activeView === "profile" && selectedProfile && (
                <CandidateProfileReview
                  profile={selectedProfile}
                  extraction={selectedExtraction}
                  onNavigateBack={() => {
                    setActiveView("candidates");
                    setActiveNavTab("candidates");
                    fetchCandidates();
                  }}
                  onNavigateExtraction={() => setActiveView("extraction")}
                />
              )}

              {activeView === "extraction" && selectedExtraction && (
                <ExtractionReview
                  extraction={selectedExtraction}
                  onNavigateBack={() => setActiveView("profile")}
                />
              )}
            </>
          )}
        </>
      )}
    </AuthenticatedShell>
  );
}

function MainContent() {
  const { status, refreshSession } = useAuth();

  if (status === "RESTORING_SESSION") {
    return (
      <div className="auth-loading-splash" role="status" aria-live="polite">
        <div className="loading-spinner" />
        <p className="loading-text">Authenticating hiring workspace session...</p>
      </div>
    );
  }

  if (status === "UNAUTHENTICATED") {
    return <LoginPage />;
  }

  if (status === "PASSWORD_CHANGE_REQUIRED") {
    return <ChangePasswordPage />;
  }

  return <AuthenticatedApp />;
}

export function App() {
  return (
    <AuthProvider>
      <MainContent />
    </AuthProvider>
  );
}

export default App;

