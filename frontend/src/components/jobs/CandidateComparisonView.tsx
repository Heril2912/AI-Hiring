import React, { useState, useEffect } from "react";
import {
  MatchRunSummary,
  MatchResultRankingItem,
  createMatchRun,
  fetchMatchResults,
} from "../../api/jobs";
import { apiFetch } from "../../api/client";
import { CandidateSummary } from "../CandidatesDirectory";
import { Icon } from "../Icon";

interface CandidateComparisonViewProps {
  jobId: string;
  jobTitle: string;
  jobVersionId: string;
  revision: number;
  requirementsCount: number;
  onNavigateBack: () => void;
  onOpenGapReport?: (matchResultId: string) => void;
}

export function CandidateComparisonView({
  jobId,
  jobTitle,
  jobVersionId,
  revision,
  requirementsCount,
  onNavigateBack,
  onOpenGapReport,
}: CandidateComparisonViewProps) {
  // Candidate pool state
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedProfileIds, setSelectedProfileIds] = useState<Set<string>>(new Set());

  // Match run & results state
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [matchRun, setMatchRun] = useState<MatchRunSummary | null>(null);
  const [results, setResults] = useState<MatchResultRankingItem[]>([]);
  const [runError, setRunError] = useState<string | null>(null);
  const [openingGapForId, setOpeningGapForId] = useState<string | null>(null);
  const [gapError, setGapError] = useState<string | null>(null);

  // 1. Fetch available candidate pool
  useEffect(() => {
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

      const idempotencyKey = `comp-${jobId}-rev${revision}-${Array.from(selectedProfileIds).sort().join("-")}`.substring(0, 100);

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

  // 3. View Gaps Action (Ensures Phase 2D report exists or calls onOpenGapReport)
  const handleOpenGapReport = async (matchResultId: string) => {
    setGapError(null);
    setOpeningGapForId(matchResultId);
    try {
      if (onOpenGapReport) {
        onOpenGapReport(matchResultId);
      } else {
        // Idempotent creation / retrieval of gap report
        const gapSummary = await apiFetch<any>("/api/v1/gap-reports", {
          method: "POST",
          headers: {
            "Idempotency-Key": `gap-view-${matchResultId}`,
          },
          body: JSON.stringify({
            match_result_id: matchResultId,
            idempotency_key: `gap-view-${matchResultId}`,
          }),
        });
        alert(`Opened gap report ${gapSummary.report_id} for match result ${matchResultId}`);
      }
    } catch (err: any) {
      setGapError(err?.message || "Failed to load requirement gap report.");
    } finally {
      setOpeningGapForId(null);
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
                Comparison Results
              </h3>
              <p style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                Run ID: <code>{matchRun.runId.substring(0, 8)}...</code> &bull; Algorithm: {matchRun.matcherAlgorithmVersion} &bull; Rule Version: {matchRun.matchingRuleVersion}
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
                  <th style={{ width: "60px" }}>Rank</th>
                  <th>Candidate</th>
                  <th>Compatibility</th>
                  <th>Confidence</th>
                  <th>Must-Have Status</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {results.map((item) => {
                  const candidateDetail = candidates.find((c) => c.artifactId === item.profileId);
                  const candidateName = candidateDetail?.fullName || `Candidate #${item.profileId.substring(0, 6)}`;
                  const candidateHeadline = candidateDetail?.headline || candidateDetail?.originalFilename;
                  const isTop = item.rank === 1;

                  return (
                    <tr key={item.resultId}>
                      <td>
                        <span className={`rank-badge ${isTop ? "top-rank" : ""}`}>
                          {item.rank}
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
                        <span className="badge badge-meta">
                          {item.confidenceTier}
                        </span>
                      </td>
                      <td>
                        {item.mustHaveWarningCount > 0 ? (
                          <span className="must-have-warn-pill">
                            <Icon name="alert-triangle" size={12} />
                            <span>{item.mustHaveWarningCount} shortfall{item.mustHaveWarningCount === 1 ? "" : "s"}</span>
                          </span>
                        ) : (
                          <span className="must-have-clean-pill">
                            <Icon name="check" size={12} />
                            <span>All satisfied</span>
                          </span>
                        )}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleOpenGapReport(item.resultId)}
                          disabled={openingGapForId === item.resultId}
                          aria-label={`View requirement gaps for ${candidateName}`}
                        >
                          <Icon name="badge-check" size={13} />
                          <span>{openingGapForId === item.resultId ? "Loading..." : "View Gaps"}</span>
                        </button>
                      </td>
                    </tr>
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
