import React, { useState, useEffect } from "react";
import {
  MatchRunSummary,
  MatchResultRankingItem,
  createMatchRun,
  fetchMatchResults,
  fetchGapReportsForResult,
  createGapReport,
} from "../../api/jobs";
import { apiFetch } from "../../api/client";
import { CandidateSummary } from "../CandidatesDirectory";
import { Icon } from "../Icon";

export type RowReportStatus = "idle" | "checking" | "preparing" | "retry" | "unavailable";

export interface RowReportState {
  status: RowReportStatus;
  errorMessage?: string | null;
  reportId?: string | null;
}

interface CandidateComparisonViewProps {
  jobId: string;
  jobTitle: string;
  jobVersionId: string;
  revision: number;
  requirementsCount: number;
  onNavigateBack: () => void;
  onOpenGapReport?: (reportId: string) => void;
  initialResults?: MatchResultRankingItem[];
  initialMatchRun?: MatchRunSummary | null;
  initialCandidates?: CandidateSummary[];
}

export function CandidateComparisonView({
  jobId,
  jobTitle,
  jobVersionId,
  revision,
  requirementsCount,
  onNavigateBack,
  onOpenGapReport,
  initialResults,
  initialMatchRun,
  initialCandidates,
}: CandidateComparisonViewProps) {
  // Candidate pool state
  const [candidates, setCandidates] = useState<CandidateSummary[]>(initialCandidates || []);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState<boolean>(!initialCandidates && !initialResults);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedProfileIds, setSelectedProfileIds] = useState<Set<string>>(new Set());

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
        // Auto-select candidate profiles that have extraction/profile ready
        const validIds = new Set<string>();
        (data || []).forEach((c) => {
          if (c.latestProfileVersion && c.latestProfileVersion > 0) {
            validIds.add(c.artifactId);
          }
        });
        setSelectedProfileIds(validIds);
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

  // Filter candidates by search query
  const filteredCandidates = candidates.filter((c) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const nameMatch = c.fullName?.toLowerCase().includes(q);
    const headlineMatch = c.headline?.toLowerCase().includes(q);
    const filenameMatch = c.originalFilename.toLowerCase().includes(q);
    return Boolean(nameMatch || headlineMatch || filenameMatch);
  });

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
    } catch (err: any) {
      setRunError(err?.message || "Failed to execute candidate comparison match run.");
    } finally {
      setIsComparing(false);
    }
  };

  // 3. View Gaps Action: Ensure-Then-Open Implementation
  const ensureGapReport = async (matchResultId: string) => {
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
          onOpenGapReport(reportId);
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
        onOpenGapReport(reportId);
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

  return (
    <div className="comparison-view-container">
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
                    onChange={() => {}} // handled by parent onClick
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

      {/* Comparison Results Card */}
      {matchRun && (
        <div className="comparison-results-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <h3 style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
                Candidate Comparison
              </h3>
              <p style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                {results.length} candidate{results.length === 1 ? "" : "s"} evaluated against configured criteria
              </p>
            </div>
            <span className="badge badge-onet-confirmed">
              {results.length} Candidates Evaluated
            </span>
          </div>

          {results.length === 0 ? (
            <p style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
              No candidates were ranked in this run.
            </p>
          ) : (
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
                {results.map((item) => {
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

                  // Canonical summary calculation or fallback to item counts
                  const summary = item.evidence_summary;
                  const reqTotal = summary ? summary.required_total : item.mustHaveTotalCount;
                  const reqFound = summary ? summary.required_evidence_found : item.mustHaveEvidencedCount;
                  const reqPartial = summary ? summary.required_partial_evidence : 0;
                  const reqVerification = summary ? summary.required_needs_verification : (item.needsConfirmationCount ?? 0);
                  const extractionConfidence = summary?.extraction_confidence || item.confidenceTier || "MEDIUM";

                  const isSummaryUnavailable = reqTotal === undefined || reqTotal === null;
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
                            {Math.round(item.displayCompatibilityScore)}%
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
                              {/* Secondary line: only when relevant (> 0), never show '0 need confirmation' */}
                              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
                                {reqVerification > 0 && (
                                  <span style={{ fontSize: "11px", color: "var(--gap-conflicting)", display: "inline-flex", alignItems: "center", gap: "3px" }}>
                                    <Icon name="alert-circle" size={11} />
                                    <span>{reqVerification} require verification</span>
                                  </span>
                                )}
                                {reqPartial > 0 && (
                                  <span style={{ fontSize: "11px", color: "var(--gap-partial)", display: "inline-flex", alignItems: "center", gap: "3px" }}>
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
                                Rerun comparison to view updated results.
                              </span>
                            )}
                            {rowStates[item.resultId]?.errorMessage && (
                              <span
                                style={{
                                  fontSize: "11px",
                                  color: "var(--gap-conflicting)",
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
                                  <code>{item.runId.substring(0, 8)}</code>
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
                              {summary && (
                                <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginTop: "4px" }}>
                                  <span>Total criteria: <strong>{summary.total_criteria}</strong></span>
                                  <span>Required criteria: <strong>{summary.required_total}</strong></span>
                                  <span>Evidence found: <strong>{summary.overall_evidence_found}</strong></span>
                                  <span>Partial evidence: <strong>{summary.overall_partial_evidence}</strong></span>
                                  <span>Not found in resume: <strong>{summary.overall_not_found}</strong></span>
                                  {summary.preferred_total > 0 && (
                                    <span>Preferred evidenced: <strong>{summary.preferred_evidence_found} of {summary.preferred_total}</strong></span>
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
          )}
        </div>
      )}
    </div>
  );
}
