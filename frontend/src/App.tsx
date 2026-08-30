import React, { useEffect, useState } from "react";
import { Icon } from "./components/Icon";
import { CandidatesDirectory, CandidateSummary } from "./components/CandidatesDirectory";
import { ResumeUpload } from "./components/ResumeUpload";
import { CandidateProfileReview, CandidateProfileData } from "./components/CandidateProfileReview";
import { ExtractionReview, ExtractionResultData } from "./components/ExtractionReview";

type ActiveView = "candidates" | "upload" | "profile" | "extraction";
type ConnectionState = "checking" | "connected" | "unavailable";

export function App() {
  const [activeView, setActiveView] = useState<ActiveView>("candidates");
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState<boolean>(false);

  // Selected candidate state
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<CandidateProfileData | null>(null);
  const [selectedExtraction, setSelectedExtraction] = useState<ExtractionResultData | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState<boolean>(false);
  const [profileLoadError, setProfileLoadError] = useState<string | null>(null);

  // Health check
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

  // Fetch candidates list
  const fetchCandidates = async () => {
    try {
      setIsLoadingCandidates(true);
      const res = await fetch("/api/v1/resumes");
      if (res.ok) {
        const data: CandidateSummary[] = await res.json();
        setCandidates(data);
      }
    } catch (e) {
      console.error("Failed to fetch candidates", e);
    } finally {
      setIsLoadingCandidates(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, []);

  // Load specific candidate profile
  const handleSelectCandidate = async (artifactId: string) => {
    setSelectedArtifactId(artifactId);
    setIsLoadingProfile(true);
    setProfileLoadError(null);

    try {
      // 1. Fetch Profile
      const profRes = await fetch(`/api/v1/resumes/${artifactId}/profile`);
      if (!profRes.ok) {
        const err = await profRes.json();
        setProfileLoadError(err?.detail?.message || "Failed to load candidate profile.");
        setIsLoadingProfile(false);
        return;
      }
      const profData: CandidateProfileData = await profRes.json();
      setSelectedProfile(profData);

      // 2. Fetch Extraction Blocks
      try {
        const extRes = await fetch(`/api/v1/resumes/${artifactId}/extraction`);
        if (extRes.ok) {
          const extData: ExtractionResultData = await extRes.json();
          setSelectedExtraction(extData);
        }
      } catch {
        setSelectedExtraction(null);
      }

      setActiveView("profile");
      fetchCandidates();
    } catch (err) {
      console.error("Failed to load candidate", err);
      setProfileLoadError("A network error occurred while loading profile.");
    } finally {
      setIsLoadingProfile(false);
    }
  };

  const handleCandidateProcessed = (artifactId: string) => {
    fetchCandidates();
    handleSelectCandidate(artifactId);
  };

  return (
    <div className="dashboard-app-container">
      {/* Top Application Navigation Bar */}
      <header className="dashboard-top-nav">
        <div className="nav-brand-section">
          <div className="brand-logo-icon">
            <Icon name="sparkles" size={18} />
          </div>
          <div className="brand-title-group">
            <h1 className="brand-title">Smart Hiring Platform</h1>
            <span className="brand-subtitle">Evidence-Based Parsing &amp; Audited Profiles</span>
          </div>
        </div>

        {/* Global Navigation Tabs */}
        <nav className="nav-links-group" aria-label="Main Navigation">
          <button
            type="button"
            className={`nav-tab-btn ${activeView === "candidates" || activeView === "profile" || activeView === "extraction" ? "tab-active" : ""}`}
            onClick={() => {
              setActiveView("candidates");
              fetchCandidates();
            }}
          >
            <Icon name="user" size={15} />
            <span>Candidates</span>
            {candidates.length > 0 && (
              <span className="nav-count-pill">{candidates.length}</span>
            )}
          </button>

          <button
            type="button"
            className={`nav-tab-btn ${activeView === "upload" ? "tab-active" : ""}`}
            onClick={() => setActiveView("upload")}
          >
            <Icon name="upload" size={15} />
            <span>Upload Resume</span>
          </button>
        </nav>

        {/* System Health Indicator */}
        <div className="nav-system-status">
          <span className={`status-indicator-dot ${connectionState}`} />
          <span className="status-indicator-text">
            {connectionState === "checking" && "Connecting..."}
            {connectionState === "connected" && "System Connected"}
            {connectionState === "unavailable" && "Service Unavailable"}
          </span>
        </div>
      </header>

      {/* Main Content Viewport */}
      <main className="dashboard-main-viewport">
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
                onNavigateUpload={() => setActiveView("upload")}
              />
            )}

            {activeView === "upload" && (
              <ResumeUpload
                onCandidateProcessed={handleCandidateProcessed}
                onNavigateCandidates={() => {
                  setActiveView("candidates");
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
      </main>
    </div>
  );
}

export default App;
