import React, { useState, useEffect, useMemo } from "react";
import {
  MatchRunSummary,
  MatchResultRankingItem,
  createMatchRun,
  fetchMatchResults,
  fetchMatchRun,
  fetchGapReportsForResult,
  createGapReport,
} from "../../api/jobs";
import { apiFetch } from "../../api/client";
import { CandidateSummary } from "../CandidatesDirectory";
import { Icon } from "../Icon";
import {
  CandidateRankingChart,
  RequirementEvidenceDistributionChart,
  getCanonicalSummaryData,
} from "./VisualAnalyticsCharts";
import { RequirementEvidenceMatrix } from "./RequirementEvidenceMatrix";

export type RowReportStatus = "idle" | "checking" | "preparing" | "retry" | "unavailable";

export interface RowReportState {
  status: RowReportStatus;
  errorMessage?: string | null;
  reportId?: string | null;
}

export interface CandidateComparisonViewProps {
  jobId: string;
  jobTitle: string;
  jobVersionId: string;
  revision: number;
  requirementsCount: number;
  onNavigateBack: () => void;
  onOpenGapReport?: (reportId: string, returnContext?: any) => void;
  initialRunId?: string;
  initialResults?: MatchResultRankingItem[];
  initialMatchRun?: MatchRunSummary | null;
  initialCandidates?: CandidateSummary[];
  initialSearchQuery?: string;
  initialResultsSearch?: string;
  initialSelectedProfileIds?: string[];
  initialPage?: number;
  initialSortField?: "rank" | "score" | "name" | "evidence";
  initialSortDirection?: "asc" | "desc";
}

export function CandidateComparisonView({
  jobId,
  jobTitle,
  jobVersionId,
  revision,
  requirementsCount,
  onNavigateBack,
  onOpenGapReport,
  initialRunId,
  initialResults,
  initialMatchRun,
  initialCandidates,
  initialSearchQuery = "",
  initialResultsSearch = "",
  initialSelectedProfileIds,
  initialPage = 1,
  initialSortField = "rank",
  initialSortDirection = "asc",
}: CandidateComparisonViewProps) {
  // Candidate pool state
  const [candidates, setCandidates] = useState<CandidateSummary[]>(initialCandidates || []);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState<boolean>(!initialCandidates && !initialResults && !initialRunId);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>(initialSearchQuery);
  const [selectedProfileIds, setSelectedProfileIds] = useState<Set<string>>(
    new Set(initialSelectedProfileIds || [])
  );

  // Match run & results state
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [matchRun, setMatchRun] = useState<MatchRunSummary | null>(
    initialMatchRun || (initialResults && initialResults.length > 0 ? ({
      runId: initialResults[0].runId,
      lifecycleStatus: "COMPLETED",
      jobId,
      jobVersionId,
      revision,
      candidateCount: initialResults.length,
      matcherAlgorithmVersion: "2.4.0",
      matchingRuleVersion: "2.4.0",
      scoringPolicyVersion: "2.4.0",
      matchInputSchemaVersion: "2.4.0",
      inputFingerprint: "fp",
      candidateInputFingerprint: "cfp",
      reused: false,
      createdAt: new Date().toISOString(),
      resultsUrl: "",
    }) : null)
  );
  const [results, setResults] = useState<MatchResultRankingItem[]>(initialResults || []);
  const [runError, setRunError] = useState<string | null>(null);
  const [rowStates, setRowStates] = useState<Record<string, RowReportState>>({});
  const [gapError, setGapError] = useState<string | null>(null);
  const [expandedDetails, setExpandedDetails] = useState<Set<string>>(new Set());

  // Visual Analytics toggle & results filtering/sorting/pagination
  const [showVisualAnalytics, setShowVisualAnalytics] = useState<boolean>(true);
  const [resultsSearch, setResultsSearch] = useState<string>(initialResultsSearch);
  const [sortField, setSortField] = useState<"rank" | "score" | "name" | "evidence">(initialSortField);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">(initialSortDirection);
  const [currentPage, setCurrentPage] = useState<number>(initialPage);
  const pageSize = 25;

  // 0. Automatically load existing match run and ranking results if initialRunId is provided
  useEffect(() => {
    const targetRunId = initialRunId || initialMatchRun?.runId;
    if (targetRunId && results.length === 0) {
      const activeRunId = targetRunId;
      let isMounted = true;
      async function loadExistingRunResults() {
        try {
          setIsComparing(true);
          setRunError(null);
          if (!initialMatchRun) {
            const runData = await fetchMatchRun(activeRunId);
            if (isMounted) {
              setMatchRun(runData);
            }
          }
          const resData = await fetchMatchResults(activeRunId, 50, 0);
          if (isMounted) {
            setResults(resData.items || []);
          }
        } catch (err: any) {
          if (isMounted) {
            setRunError(err?.message || "Failed to load match run results.");
          }
        } finally {
          if (isMounted) {
            setIsComparing(false);
          }
        }
      }
      loadExistingRunResults();
      return () => {
        isMounted = false;
      };
    }
  }, [initialRunId, initialMatchRun]);

  // 1. Fetch available candidate pool
  useEffect(() => {
    if (initialCandidates && initialCandidates.length > 0) {
      setCandidates(initialCandidates);
      setIsLoadingCandidates(false);
      return;
    }
    let isMounted = true;
    async function loadCandidates() {
      try {
        setIsLoadingCandidates(true);
        setLoadError(null);
        const data = await apiFetch<CandidateSummary[]>("/api/v1/resumes");
        if (!isMounted) return;
        setCandidates(data || []);
        // Auto-select candidate profiles that have extraction/profile ready if no initial selection provided
        if (!initialSelectedProfileIds || initialSelectedProfileIds.length === 0) {
          const validIds = new Set<string>();
          (data || []).forEach((c) => {
            if (c.latestProfileVersion && c.latestProfileVersion > 0) {
              validIds.add(c.artifactId);
            }
          });
          setSelectedProfileIds(validIds);
        }
      } catch (err: any) {
        if (isMounted) {
          setLoadError(err?.message || "Failed to load candidate directory.");
        }
      } finally {
        if (isMounted) setIsLoadingCandidates(false);
      }
    }
    loadCandidates();
    return () => {
      isMounted = false;
    };
  }, []);

  // Filter candidate pool by search query
  const filteredCandidates = useMemo(() => {
    return candidates.filter((c) => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      const nameMatch = c.fullName?.toLowerCase().includes(q);
      const headlineMatch = c.headline?.toLowerCase().includes(q);
      const filenameMatch = c.originalFilename?.toLowerCase().includes(q);
      return Boolean(nameMatch || headlineMatch || filenameMatch);
    });
  }, [candidates, searchQuery]);

  const toggleCandidateSelection = (profileId: string) => {
    const updated = new Set(selectedProfileIds);
    if (updated.has(profileId)) {
      updated.delete(profileId);
    } else {
      updated.add(profileId);
    }
    setSelectedProfileIds(updated);
  };

  const handleSelectAllVisible = () => {
    const updated = new Set(selectedProfileIds);
    filteredCandidates.forEach((c) => {
      if (c.latestProfileVersion && c.latestProfileVersion > 0) {
        updated.add(c.artifactId);
      }
    });
    setSelectedProfileIds(updated);
  };

  const handleClearSelection = () => {
    setSelectedProfileIds(new Set());
  };

  // 2. Run Match Comparison Orchestration
  const handleRunComparison = async () => {
    if (selectedProfileIds.size === 0) return;
    setRunError(null);
    setIsComparing(true);

    try {
      const candidatesPayload = candidates
        .filter((c) => selectedProfileIds.has(c.artifactId) && c.latestProfileVersion)
        .map((c) => ({
          profile_id: c.latestProfileId || c.artifactId,
          profile_version: c.latestProfileVersion || 1,
        }));

      if (candidatesPayload.length === 0) {
        setRunError("None of the selected candidates have an active processed profile version.");
        return;
      }

      const idempotencyKey = `comp-${jobId}-rev${revision}-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;

      const runSummary = await createMatchRun({
        jobId,
        expectedRevision: revision,
        candidates: candidatesPayload,
        idempotencyKey,
      });

      setMatchRun(runSummary);

      // Fetch ranking results
      const res = await fetchMatchResults(runSummary.runId, 50, 0);
      setResults(res.items || []);
      setCurrentPage(1);
    } catch (err: any) {
      setRunError(err?.message || "Failed to execute candidate comparison match run.");
    } finally {
      setIsComparing(false);
    }
  };

  // 3. Review Evidence Action: Ensure-Then-Open Implementation
  const ensureGapReport = async (matchResultId: string) => {
    if (!matchResultId) return;

    // Prevent duplicate requests if this row is already checking or preparing
    const currentState = rowStates[matchResultId]?.status;
    if (currentState === "checking" || currentState === "preparing") {
      return;
    }

    setGapError(null);
    setRowStates((prev) => ({
      ...prev,
      [matchResultId]: { status: "checking", errorMessage: null },
    }));

    const returnContext = {
      jobId,
      jobTitle,
      jobVersionId,
      revision,
      requirementsCount,
      runId: matchRun?.runId,
      searchQuery,
      resultsSearch,
      page: currentPage,
      sortField,
      sortDirection,
      selectedProfileIds: Array.from(selectedProfileIds),
    };

    try {
      // Step A: Check for an existing authorized immutable gap report for this result
      const existingReports = await fetchGapReportsForResult(matchResultId);
      if (existingReports && existingReports.length > 0 && existingReports[0].reportId) {
        const reportId = existingReports[0].reportId;
        setRowStates((prev) => ({
          ...prev,
          [matchResultId]: { status: "idle", reportId },
        }));
        if (onOpenGapReport) {
          onOpenGapReport(reportId, returnContext);
        }
        return;
      }

      // Step B: If no report exists, prepare it through Phase 2D creation endpoint
      setRowStates((prev) => ({
        ...prev,
        [matchResultId]: { status: "preparing", errorMessage: null },
      }));

      const idempotencyKey = `gap-${matchResultId}`;
      const newReport = await createGapReport(matchResultId, idempotencyKey);
      const reportId = newReport?.reportId;

      if (!reportId) {
        throw new Error("Gap report was created but did not return a valid report ID.");
      }

      setRowStates((prev) => ({
        ...prev,
        [matchResultId]: { status: "idle", reportId },
      }));

      if (onOpenGapReport) {
        onOpenGapReport(reportId, returnContext);
      }
    } catch (err: any) {
      const errCode = err?.code || "";
      const errMsg = err?.message || "";
      const isMissingProvenance =
        errCode === "GAP_SOURCE_VERSION_MISSING" ||
        errCode === "GAP_SOURCE_INCOMPLETE" ||
        errMsg.toLowerCase().includes("version information") ||
        errMsg.toLowerCase().includes("not contain the version");

      const userMessage = isMissingProvenance
        ? "This comparison result does not contain the version information required for a reproducible gap report. Run a new candidate comparison."
        : errMsg || "Failed to load requirement gap report.";

      const status: RowReportStatus = isMissingProvenance ? "unavailable" : "retry";

      setRowStates((prev) => ({
        ...prev,
        [matchResultId]: { status, errorMessage: userMessage },
      }));
      setGapError(userMessage);
    }
  };

  // Filtered & Sorted comparison results
  const processedResults = useMemo(() => {
    let list = [...results];

    if (resultsSearch.trim()) {
      const q = resultsSearch.toLowerCase();
      list = list.filter((item) => {
        const candidate = candidates.find((c) => c.artifactId === item.profileId);
        const name = candidate?.fullName?.toLowerCase() || "";
        const headline = candidate?.headline?.toLowerCase() || "";
        const profId = item.profileId.toLowerCase();
        return name.includes(q) || headline.includes(q) || profId.includes(q);
      });
    }

    list.sort((a, b) => {
      let comparison = 0;
      if (sortField === "rank") {
        comparison = a.rank - b.rank;
      } else if (sortField === "score") {
        comparison = Number(b.displayCompatibilityScore) - Number(a.displayCompatibilityScore);
      } else if (sortField === "name") {
        const nameA = candidates.find((c) => c.artifactId === a.profileId)?.fullName || "";
        const nameB = candidates.find((c) => c.artifactId === b.profileId)?.fullName || "";
        comparison = nameA.localeCompare(nameB);
      } else if (sortField === "evidence") {
        const evA = a.evidence_summary?.required_evidence_found ?? a.mustHaveEvidencedCount ?? 0;
        const evB = b.evidence_summary?.required_evidence_found ?? b.mustHaveEvidencedCount ?? 0;
        comparison = evB - evA;
      }
      return sortDirection === "asc" ? comparison : -comparison;
    });

    return list;
  }, [results, resultsSearch, sortField, sortDirection, candidates]);

  const totalPages = Math.max(1, Math.ceil(processedResults.length / pageSize));
  const paginatedResults = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return processedResults.slice(start, start + pageSize);
  }, [processedResults, currentPage, pageSize]);

  return (
    <div className="comparison-view-container" aria-label="Candidate Comparison and Visual Analytics Workspace">
      {/* Top Header */}
      <div className="comparison-header">
        <div className="comparison-title-wrap">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onNavigateBack}
            aria-label="Back to Job Requisition"
          >
            <Icon name="arrow-left" size={14} />
            <span>Back to Job</span>
          </button>
          <div>
            <h2 className="editor-heading-title">Candidate Comparison &amp; Match Analysis</h2>
            <p className="section-subtitle">
              Comparing against <strong>{jobTitle}</strong> (Revision #{revision} &bull; {requirementsCount} requirements)
            </p>
          </div>
        </div>

        <button
          type="button"
          className="btn btn-primary btn-md"
          onClick={handleRunComparison}
          disabled={isComparing || selectedProfileIds.size === 0}
          aria-label="Run candidate comparison"
        >
          <Icon name="refresh" size={15} />
          <span>
            {isComparing
              ? "Running Comparison..."
              : `Compare ${selectedProfileIds.size} Candidate${selectedProfileIds.size === 1 ? "" : "s"}`}
          </span>
        </button>
      </div>

      {/* Errors */}
      {loadError && (
        <div className="feedback-box error" role="alert">
          <Icon name="alert-triangle" size={16} />
          <p className="feedback-text error">{loadError}</p>
        </div>
      )}

      {runError && (
        <div className="feedback-box error" role="alert">
          <Icon name="alert-triangle" size={16} />
          <p className="feedback-text error">{runError}</p>
        </div>
      )}

      {gapError && (
        <div className="feedback-box error" role="alert">
          <Icon name="alert-triangle" size={16} />
          <p className="feedback-text error">{gapError}</p>
        </div>
      )}

      {/* Candidate Pool Selection Card */}
      <div className="comparison-selector-card">
        <div className="comparison-selector-toolbar">
          <div className="search-input-wrapper" style={{ maxWidth: "360px" }}>
            <Icon name="search" size={14} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Search candidate pool..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Filter candidates for comparison"
            />
            {searchQuery && (
              <button
                type="button"
                className="search-clear-btn"
                onClick={() => setSearchQuery("")}
                aria-label="Clear candidate search"
              >
                <Icon name="x" size={13} />
              </button>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
              {selectedProfileIds.size} selected of {candidates.length}
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleSelectAllVisible}
            >
              Select All
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleClearSelection}
            >
              Clear
            </button>
          </div>
        </div>

        {isLoadingCandidates ? (
          <p style={{ fontSize: "13px", color: "var(--text-secondary)", padding: "12px" }}>
            Loading candidate profiles...
          </p>
        ) : filteredCandidates.length === 0 ? (
          <p style={{ fontSize: "13px", color: "var(--text-secondary)", padding: "12px" }}>
            No matching candidates found in directory.
          </p>
        ) : (
          <div className="candidate-select-grid">
            {filteredCandidates.map((c) => {
              const isSelected = selectedProfileIds.has(c.artifactId);
              const hasProfile = Boolean(c.latestProfileVersion && c.latestProfileVersion > 0);
              return (
                <div
                  key={c.artifactId}
                  className={`candidate-select-item ${isSelected ? "selected" : ""}`}
                  onClick={() => hasProfile && toggleCandidateSelection(c.artifactId)}
                  style={{ opacity: hasProfile ? 1 : 0.5, cursor: hasProfile ? "pointer" : "not-allowed" }}
                  role="checkbox"
                  aria-checked={isSelected}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      if (hasProfile) toggleCandidateSelection(c.artifactId);
                    }
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    disabled={!hasProfile}
                    onChange={() => {}}
                    aria-label={`Select candidate ${c.fullName || c.originalFilename}`}
                  />
                  <div className="candidate-select-info">
                    <span className="candidate-select-name">
                      {c.fullName || c.originalFilename}
                    </span>
                    <span className="candidate-select-headline">
                      {c.headline || (hasProfile ? `Version ${c.latestProfileVersion}` : "No profile extracted")}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Comparison Results Section */}
      {matchRun && (
        <div className="comparison-results-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
                Candidate Comparison
              </h3>
              <p style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                {results.length} candidate{results.length === 1 ? "" : "s"} evaluated against configured criteria
              </p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setShowVisualAnalytics((prev) => !prev)}
                aria-expanded={showVisualAnalytics}
                aria-label="Toggle visual analytics charts"
              >
                <Icon name="bar-chart" size={14} />
                <span>{showVisualAnalytics ? "Hide Visual Analytics" : "Show Visual Analytics"}</span>
              </button>
              <span className="badge badge-onet-confirmed">
                {results.length} Candidates Evaluated
              </span>
            </div>
          </div>

          {/* Visual Analytics Charts Panel */}
          {showVisualAnalytics && results.length > 0 && (
            <div className="visual-analytics-panel-container" style={{ marginBottom: "24px" }}>
              <div className="visual-analytics-grid">
                <CandidateRankingChart
                  results={results}
                  candidates={candidates}
                  onSelectCandidate={ensureGapReport}
                />
                <RequirementEvidenceDistributionChart
                  results={results}
                  candidates={candidates}
                  onSelectCandidate={ensureGapReport}
                />
              </div>
              <div style={{ marginTop: "16px" }}>
                <RequirementEvidenceMatrix
                  results={results}
                  candidates={candidates}
                  onSelectCandidate={ensureGapReport}
                />
              </div>
            </div>
          )}

          {/* Filter, Search, and Sort Toolbar for Results */}
          {results.length > 0 && (
            <div className="results-toolbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", marginBottom: "14px", flexWrap: "wrap" }}>
              <div className="search-input-wrapper" style={{ maxWidth: "280px" }}>
                <Icon name="search" size={13} className="search-icon" />
                <input
                  type="text"
                  className="search-input"
                  placeholder="Filter evaluated results..."
                  value={resultsSearch}
                  onChange={(e) => {
                    setResultsSearch(e.target.value);
                    setCurrentPage(1);
                  }}
                  aria-label="Filter evaluated candidate results"
                />
                {resultsSearch && (
                  <button
                    type="button"
                    className="search-clear-btn"
                    onClick={() => setResultsSearch("")}
                    aria-label="Clear results filter"
                  >
                    <Icon name="x" size={12} />
                  </button>
                )}
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <label htmlFor="results-sort-select" style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                    Sort by:
                  </label>
                  <select
                    id="results-sort-select"
                    className="form-select-sm"
                    value={sortField}
                    onChange={(e) => setSortField(e.target.value as any)}
                  >
                    <option value="rank">Rank</option>
                    <option value="score">Match Score</option>
                    <option value="evidence">Evidence Count</option>
                    <option value="name">Candidate Name</option>
                  </select>
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => setSortDirection((d) => (d === "asc" ? "desc" : "asc"))}
                    aria-label={`Sort direction: ${sortDirection}`}
                    title={`Toggle sort direction (current: ${sortDirection})`}
                  >
                    {sortDirection === "asc" ? "▲" : "▼"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {results.length === 0 ? (
            <p style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
              No candidates were ranked in this run.
            </p>
          ) : paginatedResults.length === 0 ? (
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", padding: "16px 0" }}>
              No candidate results match the search filter "{resultsSearch}".
            </p>
          ) : (
            <>
              <table className="comparison-table" aria-label="Candidate Comparison Rankings">
                <thead>
                  <tr>
                    <th style={{ width: "90px" }}>Rank</th>
                    <th>Candidate</th>
                    <th style={{ width: "140px" }}>Resume match</th>
                    <th>Required evidence</th>
                    <th style={{ width: "160px", textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedResults.map((item) => {
                    const candidateDetail = candidates.find((c) => c.artifactId === item.profileId);
                    const candidateName = candidateDetail?.fullName || `Candidate #${item.profileId.substring(0, 6)}`;
                    const candidateHeadline = candidateDetail?.headline || candidateDetail?.originalFilename;
                    const isTop = item.rank === 1 && !item.isTied;

                    const isLegacy = !item.resultId;
                    const rowState = isLegacy ? "unavailable" : (rowStates[item.resultId]?.status || "idle");
                    const isRowBusy = rowState === "checking" || rowState === "preparing";

                    let buttonLabel = "Review evidence";
                    if (isLegacy || rowState === "unavailable") {
                      buttonLabel = "Summary unavailable";
                    } else if (rowState === "checking") {
                      buttonLabel = "Checking evidence…";
                    } else if (rowState === "preparing") {
                      buttonLabel = "Preparing evidence…";
                    } else if (rowState === "retry") {
                      buttonLabel = "Try again";
                    }

                    // Canonical summary calculation
                    const summary = item.evidence_summary || (item as any).evidenceSummary;
                    const canon = getCanonicalSummaryData(summary);

                    const isSummaryUnavailable = !canon && (item.mustHaveTotalCount === undefined || item.mustHaveTotalCount === null);
                    const reqTotal = canon ? canon.requiredTotal : item.mustHaveTotalCount;
                    const reqFound = canon ? canon.requiredEvidenceFound : item.mustHaveEvidencedCount;
                    const reqPartial = canon ? canon.requiredPartialEvidence : 0;
                    const reqVerification = canon ? canon.requiredNeedsVerification : (item.needsConfirmationCount ?? 0);
                    const extractionConfidence = canon?.extractionConfidence || item.confidenceTier || "MEDIUM";

                    const isExpanded = expandedDetails.has(item.resultId);
                    const rankText = item.isTied ? `Tied #${item.rank}` : `#${item.rank}`;

                    return (
                      <React.Fragment key={item.resultId || item.profileId}>
                        <tr>
                          <td>
                            <span className={`rank-badge ${isTop ? "top-rank" : ""}`} style={{ width: "auto", padding: "0 8px" }}>
                              {rankText}
                            </span>
                          </td>
                          <td>
                            <div style={{ display: "flex", flexDirection: "column" }}>
                              <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                                {candidateName}
                              </span>
                              {candidateHeadline && (
                                <span style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
                                  {candidateHeadline}
                                </span>
                              )}
                            </div>
                          </td>
                          <td>
                            <span className="score-cell-value">
                              {Math.round(Number(item.displayCompatibilityScore))}%
                            </span>
                          </td>
                          <td>
                            {isSummaryUnavailable ? (
                              <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                                Summary unavailable
                              </span>
                            ) : (
                              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                                <span style={{ fontSize: "12px", color: "var(--text-primary)", fontWeight: 500 }}>
                                  {reqFound} of {reqTotal} required criteria have supporting resume evidence
                                </span>
                                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
                                  {reqVerification > 0 && (
                                    <span style={{ fontSize: "11px", color: "var(--gap-partial)", display: "inline-flex", alignItems: "center", gap: "3px" }}>
                                      <Icon name="alert-circle" size={11} />
                                      <span>{reqVerification} require verification</span>
                                    </span>
                                  )}
                                  {reqPartial > 0 && (
                                    <span style={{ fontSize: "11px", color: "var(--gap-unverified)", display: "inline-flex", alignItems: "center", gap: "3px" }}>
                                      <Icon name="clock" size={11} />
                                      <span>{reqPartial} ha{reqPartial === 1 ? "s" : "ve"} partial evidence</span>
                                    </span>
                                  )}
                                </div>
                              </div>
                            )}
                          </td>
                          <td style={{ textAlign: "right" }}>
                            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "6px" }}>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => ensureGapReport(item.resultId)}
                                disabled={isRowBusy || rowState === "unavailable" || isLegacy}
                                aria-label={`${buttonLabel} for ${candidateName}`}
                              >
                                <Icon name="badge-check" size={13} />
                                <span>{buttonLabel}</span>
                              </button>
                              <button
                                type="button"
                                className="btn-link-action"
                                onClick={() => {
                                  setExpandedDetails((prev) => {
                                    const next = new Set(prev);
                                    if (next.has(item.resultId)) {
                                      next.delete(item.resultId);
                                    } else {
                                      next.add(item.resultId);
                                    }
                                    return next;
                                  });
                                }}
                                style={{ fontSize: "11px", textDecoration: "none" }}
                                aria-expanded={isExpanded}
                              >
                                {isExpanded ? "Hide details ▲" : "Analysis details ▼"}
                              </button>
                              {isLegacy && (
                                <span
                                  style={{
                                    fontSize: "11px",
                                    color: "var(--text-secondary)",
                                    maxWidth: "260px",
                                    textAlign: "right",
                                    lineHeight: "1.3",
                                  }}
                                >
                                  Rerun comparison to view gap report.
                                </span>
                              )}
                              {rowStates[item.resultId]?.errorMessage && (
                                <span
                                  style={{
                                    fontSize: "11px",
                                    color: "var(--status-danger)",
                                    maxWidth: "260px",
                                    textAlign: "right",
                                    lineHeight: "1.3",
                                  }}
                                  role="alert"
                                >
                                  {rowStates[item.resultId]!.errorMessage}
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                        {/* Expandable Analysis details row */}
                        {isExpanded && (
                          <tr style={{ backgroundColor: "var(--bg-surface-subtle)" }}>
                            <td colSpan={5} style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-medium)" }}>
                              <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "12px", color: "var(--text-secondary)" }}>
                                <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", alignItems: "center" }}>
                                  <div>
                                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Extraction confidence: </span>
                                    <span
                                      className="badge badge-meta"
                                      title="How confidently the system extracted and connected evidence from the uploaded resume. This is not a candidate rating."
                                      style={{ cursor: "help" }}
                                    >
                                      {extractionConfidence}
                                    </span>
                                  </div>
                                  <div>
                                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Run ID: </span>
                                    <code>{item.runId ? item.runId.substring(0, 8) : "N/A"}</code>
                                  </div>
                                  <div>
                                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Algorithm: </span>
                                    <span>{matchRun.matcherAlgorithmVersion}</span>
                                  </div>
                                  <div>
                                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Rule version: </span>
                                    <span>{matchRun.matchingRuleVersion}</span>
                                  </div>
                                  <div>
                                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Policy version: </span>
                                    <span>{matchRun.scoringPolicyVersion}</span>
                                  </div>
                                </div>
                                {canon && (
                                  <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginTop: "4px" }}>
                                    <span>Total criteria: <strong>{canon.totalCriteria}</strong></span>
                                    <span>Required criteria: <strong>{canon.requiredTotal}</strong></span>
                                    <span>Evidence found: <strong>{canon.overallEvidenceFound}</strong></span>
                                    <span>Partial evidence: <strong>{canon.overallPartialEvidence}</strong></span>
                                    <span>Not found in resume: <strong>{canon.overallNotFound}</strong></span>
                                    {canon.preferredTotal > 0 && (
                                      <span>Preferred evidenced: <strong>{canon.preferredEvidenceFound} of {canon.preferredTotal}</strong></span>
                                    )}
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>

              {/* Pagination Controls */}
              {totalPages > 1 && (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "16px", fontSize: "12px", color: "var(--text-secondary)" }}>
                  <span>
                    Showing {(currentPage - 1) * pageSize + 1} to {Math.min(currentPage * pageSize, processedResults.length)} of {processedResults.length} candidates
                  </span>
                  <div style={{ display: "flex", gap: "6px" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    >
                      Previous
                    </button>
                    <span style={{ padding: "4px 8px" }}>
                      Page {currentPage} of {totalPages}
                    </span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      disabled={currentPage === totalPages}
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
