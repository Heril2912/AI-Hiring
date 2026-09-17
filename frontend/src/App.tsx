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
import { JobsDirectory } from "./components/jobs/JobsDirectory";
import { JobEditor } from "./components/jobs/JobEditor";
import { CandidateComparisonView } from "./components/jobs/CandidateComparisonView";
import { RequirementGapReportView } from "./components/jobs/RequirementGapReportView";
import { InterviewWorkspace } from "./components/interviews/InterviewWorkspace";
import { apiFetch } from "./api/client";
import { fetchJobs, JobSummary } from "./api/jobs";
import { Icon } from "./components/Icon";
import { validateInternalReturnUrl, ComparisonNavigationState } from "./utils/navigation";

// Re-export validation utility for direct callers and test assertions
export { validateInternalReturnUrl };

type ConnectionState = "checking" | "connected" | "unavailable";

export interface ComparisonParamsState {
  jobId: string;
  jobTitle: string;
  jobVersionId: string;
  revision: number;
  requirementsCount: number;
  runId?: string;
  searchQuery?: string;
  resultsSearch?: string;
  page?: number;
  sortField?: "rank" | "score" | "name" | "evidence";
  sortDirection?: "asc" | "desc";
  selectedProfileIds?: string[];
}

export interface InterviewRouteState {
  jobId: string;
  resumeId: string;
}

function AuthenticatedApp() {
  const { user } = useAuth();
  const role = user?.role || "REVIEWER";

  // Navigation tab state
  const [activeNavTab, setActiveNavTab] = useState<string>(
    role === "ADMIN" ? "users" : role === "RECRUITER" ? "candidates" : "reviews"
  );
  const [activeView, setActiveView] = useState<
    "jobs" | "new_job" | "edit_job" | "compare_candidates" | "gap_report" | "candidates" | "upload" | "profile" | "extraction" | "interview_workspace"
  >("candidates");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [interviewRoute, setInterviewRoute] = useState<InterviewRouteState | null>(null);

  // Health check
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");

  // Jobs state
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [isLoadingJobs, setIsLoadingJobs] = useState<boolean>(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [comparisonParams, setComparisonParams] = useState<ComparisonParamsState | null>(null);

  // Candidates state
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState<boolean>(false);
  const [selectedProfile, setSelectedProfile] = useState<CandidateProfileData | null>(null);
  const [selectedExtraction, setSelectedExtraction] = useState<ExtractionResultData | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState<boolean>(false);
  const [profileLoadError, setProfileLoadError] = useState<string | null>(null);

  // Initialize from URL query parameters if present
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const searchParams = new URLSearchParams(window.location.search);
      const viewParam = searchParams.get("view");
      const reportIdParam = searchParams.get("reportId");
      const jobIdParam = searchParams.get("jobId");
      const runIdParam = searchParams.get("runId");

      if (viewParam === "gap_report" && reportIdParam) {
        setSelectedReportId(reportIdParam);
        setActiveView("gap_report");
        setActiveNavTab("jobs");
      } else if (viewParam === "compare_candidates" && jobIdParam) {
        setComparisonParams({
          jobId: jobIdParam,
          jobTitle: searchParams.get("jobTitle") || "Job Requisition",
          jobVersionId: searchParams.get("jobVersionId") || "",
          revision: Number(searchParams.get("revision")) || 1,
          requirementsCount: Number(searchParams.get("requirementsCount")) || 0,
          runId: runIdParam || undefined,
        });
        setActiveView("compare_candidates");
        setActiveNavTab("jobs");
      }
    } catch {
      // Ignore URL parsing errors in test environments
    }
  }, []);

  useEffect(() => {
    const defaultTab = role === "ADMIN" ? "users" : role === "RECRUITER" ? "candidates" : "reviews";
    setActiveNavTab(defaultTab);
    if (role === "RECRUITER" && activeView === "candidates") {
      setActiveView("candidates");
    }
  }, [role]);

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

  // Fetch Jobs if role is RECRUITER or ADMIN
  const loadJobsList = async () => {
    if (role !== "RECRUITER" && role !== "ADMIN") return;
    try {
      setIsLoadingJobs(true);
      setJobsError(null);
      const data = await fetchJobs();
      setJobs(data || []);
    } catch (e: any) {
      setJobsError(e?.message || "Failed to load jobs.");
    } finally {
      setIsLoadingJobs(false);
    }
  };

  // Fetch Candidates if role is RECRUITER
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
      loadJobsList();
      fetchCandidates();
    } else if (role === "ADMIN") {
      loadJobsList();
    }
  }, [role]);

  const handleSelectJob = (jobId: string) => {
    setSelectedJobId(jobId);
    setActiveView("edit_job");
  };

  const handleCreateJob = () => {
    setSelectedJobId(null);
    setActiveView("new_job");
  };

  const handleJobCreated = (newJobId: string) => {
    loadJobsList();
    setSelectedJobId(newJobId);
    setActiveView("edit_job");
  };

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
    if (tab === "jobs") {
      setActiveView("jobs");
      loadJobsList();
    } else if (tab === "candidates") {
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
      jobsCount={jobs.length}
      connectionState={connectionState}
    >
      {role === "ADMIN" && (
        <>
          {activeNavTab === "jobs" ? (
            activeView === "jobs" ? (
              <JobsDirectory
                jobs={jobs}
                isLoading={isLoadingJobs}
                error={jobsError}
                onSelectJob={handleSelectJob}
                onCreateJob={handleCreateJob}
                onRefresh={loadJobsList}
                onOpenInterviewTemplate={(jobId) => {
                  setSelectedJobId(jobId);
                  setInterviewRoute({ jobId, resumeId: "" });
                  setActiveView("interview_workspace");
                }}
              />
            ) : activeView === "interview_workspace" && interviewRoute ? (
              <InterviewWorkspace
                jobId={interviewRoute.jobId}
                resumeId={interviewRoute.resumeId}
                onNavigateBack={() => {
                  if (selectedJobId) {
                    setActiveView("edit_job");
                  } else {
                    setActiveView("jobs");
                  }
                  loadJobsList();
                }}
              />
            ) : (
              <JobEditor
                jobId={selectedJobId}
                onNavigateBack={() => {
                  setActiveView("jobs");
                  loadJobsList();
                }}
                onJobCreated={handleJobCreated}
                onOpenInterviewTemplate={(jobId) => {
                  setInterviewRoute({ jobId, resumeId: "" });
                  setActiveView("interview_workspace");
                }}
              />
            )
          ) : (
            <AdminWorkspace activeTab={activeNavTab} />
          )}
        </>
      )}

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
              {activeView === "jobs" && (
                <JobsDirectory
                  jobs={jobs}
                  isLoading={isLoadingJobs}
                  error={jobsError}
                  onSelectJob={handleSelectJob}
                  onCreateJob={handleCreateJob}
                  onRefresh={loadJobsList}
                  onOpenInterviewTemplate={(jobId) => {
                    setSelectedJobId(jobId);
                    setInterviewRoute({ jobId, resumeId: "" });
                    setActiveView("interview_workspace");
                  }}
                />
              )}

              {activeView === "new_job" && (
                <JobEditor
                  jobId={null}
                  onNavigateBack={() => {
                    setActiveView("jobs");
                    loadJobsList();
                  }}
                  onJobCreated={handleJobCreated}
                />
              )}

              {activeView === "edit_job" && selectedJobId && (
                <JobEditor
                  jobId={selectedJobId}
                  onNavigateBack={() => {
                    setActiveView("jobs");
                    loadJobsList();
                  }}
                  onCompareCandidates={(params) => {
                    setComparisonParams(params);
                    setActiveView("compare_candidates");
                  }}
                  onOpenInterviewTemplate={(jobId) => {
                    setInterviewRoute({ jobId, resumeId: "" });
                    setActiveView("interview_workspace");
                  }}
                />
              )}

              {activeView === "compare_candidates" && comparisonParams && (
                <CandidateComparisonView
                  jobId={comparisonParams.jobId}
                  jobTitle={comparisonParams.jobTitle}
                  jobVersionId={comparisonParams.jobVersionId}
                  revision={comparisonParams.revision}
                  requirementsCount={comparisonParams.requirementsCount}
                  initialRunId={comparisonParams.runId}
                  initialSearchQuery={comparisonParams.searchQuery}
                  initialResultsSearch={comparisonParams.resultsSearch}
                  initialSelectedProfileIds={comparisonParams.selectedProfileIds}
                  initialPage={comparisonParams.page}
                  initialSortField={comparisonParams.sortField}
                  initialSortDirection={comparisonParams.sortDirection}
                  onNavigateBack={() => setActiveView("edit_job")}
                  onOpenGapReport={(reportId, returnContext) => {
                    if (returnContext) {
                      setComparisonParams((prev) => ({
                        ...prev,
                        ...returnContext,
                      }));
                    }
                    setSelectedReportId(reportId);
                    setActiveView("gap_report");
                  }}
                  onOpenInterviewWorkspace={(jobId, resumeId) => {
                    setInterviewRoute({ jobId, resumeId });
                    setActiveView("interview_workspace");
                  }}
                />
              )}

              {activeView === "gap_report" && selectedReportId && (
                <RequirementGapReportView
                  reportId={selectedReportId}
                  jobTitle={comparisonParams?.jobTitle}
                  returnUrl={`/?view=compare_candidates&jobId=${comparisonParams?.jobId || ""}&runId=${comparisonParams?.runId || ""}`}
                  onNavigateBack={() => setActiveView("compare_candidates")}
                  onNavigateBackWithFallback={(fallback) => {
                    setComparisonParams((prev) => ({
                      jobId: fallback.jobId,
                      jobTitle: prev?.jobTitle || `Job #${fallback.jobId.substring(0, 8)}`,
                      jobVersionId: fallback.jobVersionId,
                      revision: fallback.revision,
                      requirementsCount: prev?.requirementsCount || 0,
                      runId: fallback.runId,
                    }));
                    setActiveView("compare_candidates");
                  }}
                />
              )}

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

              {activeView === "interview_workspace" && interviewRoute && (
                <InterviewWorkspace
                  jobId={interviewRoute.jobId}
                  resumeId={interviewRoute.resumeId}
                  onNavigateBack={() => {
                    if (interviewRoute.resumeId && comparisonParams) {
                      setActiveView("compare_candidates");
                      setActiveNavTab("jobs");
                    } else if (selectedJobId) {
                      setActiveView("edit_job");
                      setActiveNavTab("jobs");
                    } else {
                      setActiveView("jobs");
                      setActiveNavTab("jobs");
                    }
                  }}
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
  const { status } = useAuth();

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
