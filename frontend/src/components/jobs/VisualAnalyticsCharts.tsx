import React from "react";
import { MatchResultRankingItem, GapReportItem, EvidenceSummary } from "../../api/jobs";
import { CandidateSummary } from "../CandidatesDirectory";
import { Icon } from "../Icon";

// Helper to safely extract canonical evidence summary without defaulting missing data to 0
export function getCanonicalSummaryData(summary: EvidenceSummary | null | undefined) {
  if (!summary) return null;
  const s = summary as any;
  const reqTotal = s.requiredTotal ?? s.required_total;
  const reqFound = s.requiredEvidenceFound ?? s.required_evidence_found;
  const reqPartial = s.requiredPartialEvidence ?? s.required_partial_evidence ?? 0;
  const reqNotFound = s.requiredNotFound ?? s.required_not_found ?? 0;
  const reqVerification = s.requiredNeedsVerification ?? s.required_needs_verification ?? 0;

  const prefTotal = s.preferredTotal ?? s.preferred_total ?? 0;
  const prefFound = s.preferredEvidenceFound ?? s.preferred_evidence_found ?? 0;

  const overallFound = s.overallEvidenceFound ?? s.overall_evidence_found ?? (reqFound !== undefined ? (reqFound + prefFound) : 0);
  const overallPartial = s.overallPartialEvidence ?? s.overall_partial_evidence ?? reqPartial;
  const overallNotFound = s.overallNotFound ?? s.overall_not_found ?? reqNotFound;
  const totalCriteria = s.totalCriteria ?? s.total_criteria ?? (reqTotal !== undefined ? (reqTotal + prefTotal) : undefined);

  if (reqTotal === undefined || reqTotal === null || reqFound === undefined || reqFound === null) {
    return null;
  }

  return {
    totalCriteria: totalCriteria ?? reqTotal,
    requiredTotal: reqTotal,
    requiredEvidenceFound: reqFound,
    requiredPartialEvidence: reqPartial,
    requiredNotFound: reqNotFound,
    requiredNeedsVerification: reqVerification,
    preferredTotal: prefTotal,
    preferredEvidenceFound: prefFound,
    overallEvidenceFound: overallFound,
    overallPartialEvidence: overallPartial,
    overallNotFound: overallNotFound,
    extractionConfidence: s.extractionConfidence ?? s.extraction_confidence ?? "MEDIUM",
  };
}

/* =========================================================================
   1. Candidate Resume-Match Ranking Chart
   ========================================================================= */

interface CandidateRankingChartProps {
  results: MatchResultRankingItem[];
  candidates: CandidateSummary[];
  onSelectCandidate?: (resultId: string) => void;
  selectedResultId?: string | null;
}

export function CandidateRankingChart({
  results,
  candidates,
  onSelectCandidate,
  selectedResultId,
}: CandidateRankingChartProps) {
  if (!results || results.length === 0) {
    return null;
  }

  return (
    <div
      className="visual-analytics-card ranking-chart-card"
      role="region"
      aria-label="Candidate Resume-Match Ranking Chart"
    >
      <div className="chart-header">
        <div>
          <h4 className="chart-title">Candidate Resume-Match Ranking</h4>
          <p className="chart-subtitle">
            Ranked deterministically by stored backend compatibility scores ({results.length} candidate{results.length === 1 ? "" : "s"})
          </p>
        </div>
      </div>

      <div className="ranking-bars-list" role="list" aria-label="Candidate match score rankings">
        {results.map((item) => {
          const candidate = candidates.find((c) => c.artifactId === item.profileId);
          const candidateName = candidate?.fullName || `Candidate #${item.profileId.substring(0, 6)}`;
          const score = Number(item.displayCompatibilityScore);
          const clampedPercent = Math.max(0, Math.min(100, isNaN(score) ? 0 : score));
          const rankText = item.isTied ? `Tied #${item.rank}` : `#${item.rank}`;
          const isSelected = selectedResultId === item.resultId;
          const isTop = item.rank === 1 && !item.isTied;

          return (
            <div
              key={item.resultId || item.profileId}
              role="listitem"
              className={`ranking-bar-row ${isSelected ? "selected" : ""} ${onSelectCandidate && item.resultId ? "interactive" : ""}`}
              onClick={() => {
                if (onSelectCandidate && item.resultId) {
                  onSelectCandidate(item.resultId);
                }
              }}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && onSelectCandidate && item.resultId) {
                  e.preventDefault();
                  onSelectCandidate(item.resultId);
                }
              }}
              tabIndex={onSelectCandidate && item.resultId ? 0 : undefined}
              aria-label={`${rankText}: ${candidateName} — ${Math.round(clampedPercent)}% resume match`}
            >
              <div className="ranking-row-meta">
                <span className={`rank-badge ${isTop ? "top-rank" : ""}`}>
                  {rankText}
                </span>
                <span className="candidate-name-label" title={candidateName}>
                  {candidateName}
                </span>
                <span className="exact-score-text">
                  {Math.round(clampedPercent)}%
                </span>
              </div>

              <div
                className="ranking-bar-track"
                role="progressbar"
                aria-valuenow={Math.round(clampedPercent)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Match score: ${Math.round(clampedPercent)}% for ${candidateName}`}
              >
                <div
                  className="ranking-bar-fill"
                  style={{
                    width: `${clampedPercent}%`,
                    backgroundColor: isTop ? "var(--gap-covered)" : "var(--accent-primary)",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* =========================================================================
   2. Requirement Evidence Distribution Chart (100% Stacked Bar)
   ========================================================================= */

interface RequirementEvidenceDistributionChartProps {
  results: MatchResultRankingItem[];
  candidates: CandidateSummary[];
  onSelectCandidate?: (resultId: string) => void;
}

export function RequirementEvidenceDistributionChart({
  results,
  candidates,
  onSelectCandidate,
}: RequirementEvidenceDistributionChartProps) {
  if (!results || results.length === 0) {
    return null;
  }

  // Determine which categories have at least one non-zero occurrence across all rendered candidates
  let hasCovered = false;
  let hasPartial = false;
  let hasVerification = false;
  let hasNotFound = false;
  let hasExcluded = false;

  const rowsData = results.map((item) => {
    const candidate = candidates.find((c) => c.artifactId === item.profileId);
    const candidateName = candidate?.fullName || `Candidate #${item.profileId.substring(0, 6)}`;
    const summary = item.evidence_summary || (item as any).evidenceSummary;
    const canon = getCanonicalSummaryData(summary);

    if (!canon) {
      return {
        item,
        candidateName,
        isUnavailable: true,
        covered: 0,
        partial: 0,
        verification: 0,
        notFound: 0,
        excluded: 0,
        total: 0,
      };
    }

    const covered = canon.requiredEvidenceFound;
    const partial = canon.requiredPartialEvidence;
    const verification = canon.requiredNeedsVerification;
    const notFound = canon.requiredNotFound;
    const excluded = (canon as any).not_applicable_count ?? 0;
    const total = canon.requiredTotal || (covered + partial + verification + notFound + excluded) || 1;

    if (covered > 0) hasCovered = true;
    if (partial > 0) hasPartial = true;
    if (verification > 0) hasVerification = true;
    if (notFound > 0) hasNotFound = true;
    if (excluded > 0) hasExcluded = true;

    return {
      item,
      candidateName,
      isUnavailable: false,
      covered,
      partial,
      verification,
      notFound,
      excluded,
      total,
      canon,
    };
  });

  return (
    <div
      className="visual-analytics-card evidence-distribution-card"
      role="region"
      aria-label="Requirement Evidence Distribution Chart"
    >
      <div className="chart-header">
        <div>
          <h4 className="chart-title">Requirement Evidence Distribution</h4>
          <p className="chart-subtitle">
            100% evidence breakdown for evaluated required criteria across candidates
          </p>
        </div>

        {/* Dynamic Legend: Omit zero-value categories */}
        <div className="chart-legend" aria-label="Evidence distribution categories">
          {hasCovered && (
            <span className="legend-item">
              <span className="legend-swatch" style={{ backgroundColor: "var(--gap-covered)" }} />
              <span>Evidence found</span>
            </span>
          )}
          {hasPartial && (
            <span className="legend-item">
              <span className="legend-swatch" style={{ backgroundColor: "var(--gap-unverified)" }} />
              <span>Partial evidence</span>
            </span>
          )}
          {hasVerification && (
            <span className="legend-item">
              <span className="legend-swatch" style={{ backgroundColor: "var(--gap-partial)" }} />
              <span>Needs verification</span>
            </span>
          )}
          {hasNotFound && (
            <span className="legend-item">
              <span className="legend-swatch" style={{ backgroundColor: "var(--gap-not-evidenced)" }} />
              <span>Not found in resume</span>
            </span>
          )}
          {hasExcluded && (
            <span className="legend-item">
              <span className="legend-swatch" style={{ backgroundColor: "var(--gap-not-applicable)" }} />
              <span>Excluded from score</span>
            </span>
          )}
        </div>
      </div>

      <div className="distribution-bars-list" role="list" aria-label="Candidate requirement distributions">
        {rowsData.map((row) => {
          const { item, candidateName, isUnavailable, covered, partial, verification, notFound, excluded, total } = row;

          if (isUnavailable) {
            return (
              <div
                key={item.resultId || item.profileId}
                className="distribution-bar-row"
                role="listitem"
                aria-label={`${candidateName}: Summary unavailable`}
              >
                <div className="distribution-row-meta">
                  <span className="candidate-name-label">{candidateName}</span>
                  <span className="summary-unavailable-badge">Summary unavailable</span>
                </div>
                <div className="distribution-bar-track unavailable-track">
                  <div className="unavailable-bar-fill" />
                </div>
              </div>
            );
          }

          const pctCovered = (covered / total) * 100;
          const pctPartial = (partial / total) * 100;
          const pctVerification = (verification / total) * 100;
          const pctNotFound = (notFound / total) * 100;
          const pctExcluded = (excluded / total) * 100;

          const desc = `${candidateName}: ${covered} of ${total} evidenced, ${partial} partial, ${verification} require verification, ${notFound} not found in resume${excluded > 0 ? `, ${excluded} excluded` : ""}`;

          return (
            <div
              key={item.resultId || item.profileId}
              className={`distribution-bar-row ${onSelectCandidate && item.resultId ? "interactive" : ""}`}
              role="listitem"
              onClick={() => {
                if (onSelectCandidate && item.resultId) {
                  onSelectCandidate(item.resultId);
                }
              }}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && onSelectCandidate && item.resultId) {
                  e.preventDefault();
                  onSelectCandidate(item.resultId);
                }
              }}
              tabIndex={onSelectCandidate && item.resultId ? 0 : undefined}
              aria-label={desc}
            >
              <div className="distribution-row-meta">
                <span className="candidate-name-label" title={candidateName}>
                  {candidateName}
                </span>
                <span className="exact-counts-text">
                  {covered} of {total} evidenced
                  {verification > 0 && ` • ${verification} verify`}
                  {partial > 0 && ` • ${partial} partial`}
                </span>
              </div>

              <div
                className="distribution-bar-track"
                role="img"
                aria-label={desc}
              >
                {pctCovered > 0 && (
                  <div
                    className="segment segment-covered"
                    style={{ width: `${pctCovered}%`, backgroundColor: "var(--gap-covered)" }}
                    title={`Evidence found: ${covered} (${Math.round(pctCovered)}%)`}
                  />
                )}
                {pctPartial > 0 && (
                  <div
                    className="segment segment-partial"
                    style={{ width: `${pctPartial}%`, backgroundColor: "var(--gap-unverified)" }}
                    title={`Partial evidence found: ${partial} (${Math.round(pctPartial)}%)`}
                  />
                )}
                {pctVerification > 0 && (
                  <div
                    className="segment segment-verification"
                    style={{ width: `${pctVerification}%`, backgroundColor: "var(--gap-partial)" }}
                    title={`Needs verification: ${verification} (${Math.round(pctVerification)}%)`}
                  />
                )}
                {pctNotFound > 0 && (
                  <div
                    className="segment segment-not-found"
                    style={{ width: `${pctNotFound}%`, backgroundColor: "var(--gap-not-evidenced)" }}
                    title={`Not found in resume: ${notFound} (${Math.round(pctNotFound)}%)`}
                  />
                )}
                {pctExcluded > 0 && (
                  <div
                    className="segment segment-excluded"
                    style={{ width: `${pctExcluded}%`, backgroundColor: "var(--gap-not-applicable)" }}
                    title={`Excluded from score: ${excluded} (${Math.round(pctExcluded)}%)`}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* =========================================================================
   3. Category Evidence Coverage Chart (Detailed Report)
   ========================================================================= */

interface CategoryEvidenceCoverageChartProps {
  items: GapReportItem[];
}

export function CategoryEvidenceCoverageChart({ items }: CategoryEvidenceCoverageChartProps) {
  if (!items || items.length === 0) {
    return null;
  }

  // Aggregate by requirement category
  const categoriesMap = new Map<
    string,
    {
      category: string;
      total: number;
      covered: number;
      partial: number;
      verification: number;
      notFound: number;
    }
  >();

  items.forEach((it) => {
    const rawCat = (it.category || "OTHER").toUpperCase();
    const existing = categoriesMap.get(rawCat) || {
      category: rawCat,
      total: 0,
      covered: 0,
      partial: 0,
      verification: 0,
      notFound: 0,
    };

    existing.total += 1;
    const state = it.gapState || (it as any).reconciled_state || (it as any).gap_state;

    if (state === "COVERED") {
      existing.covered += 1;
    } else if (state === "PARTIALLY_COVERED") {
      existing.partial += 1;
    } else if (state === "UNVERIFIED" || state === "CONFLICTING_REVIEW_REQUIRED") {
      existing.verification += 1;
    } else {
      existing.notFound += 1;
    }

    categoriesMap.set(rawCat, existing);
  });

  // Filter only categories that have active requirements (count > 0)
  const activeCategories = Array.from(categoriesMap.values()).filter((c) => c.total > 0);

  if (activeCategories.length === 0) {
    return null;
  }

  return (
    <div
      className="visual-analytics-card category-coverage-card"
      role="region"
      aria-label="Category Evidence Coverage Chart"
    >
      <div className="chart-header">
        <div>
          <h4 className="chart-title">Category Evidence Coverage</h4>
          <p className="chart-subtitle">
            Resume evidence coverage across active requirement categories (diagnostic only)
          </p>
        </div>
      </div>

      <div className="category-bars-list" role="list" aria-label="Category evidence breakdown">
        {activeCategories.map((cat) => {
          const catName = `${cat.category.charAt(0).toUpperCase()}${cat.category.slice(1).toLowerCase()}`;
          const pctCovered = Math.round((cat.covered / cat.total) * 100);
          const ratioText = `${cat.covered} of ${cat.total} evidenced`;
          const desc = `${catName}: ${cat.covered} of ${cat.total} evidenced (${pctCovered}%). ${cat.notFound} not evidenced in resume.`;

          return (
            <div
              key={cat.category}
              className="category-bar-row"
              role="listitem"
              aria-label={desc}
            >
              <div className="category-row-meta">
                <span className="category-name-label">{catName}</span>
                <span className="exact-coverage-text">{ratioText}</span>
              </div>

              <div
                className="category-bar-track"
                role="progressbar"
                aria-valuenow={cat.covered}
                aria-valuemin={0}
                aria-valuemax={cat.total}
                aria-label={`${catName}: ${ratioText}`}
              >
                <div
                  className="category-bar-fill"
                  style={{
                    width: `${(cat.covered / cat.total) * 100}%`,
                    backgroundColor: "var(--gap-covered)",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <p className="category-chart-disclaimer" style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "8px", fontStyle: "italic" }}>
        Missing resume evidence indicates an unevidenced criterion in the supplied profile—it does not establish lack of candidate ability or create a threshold.
      </p>
    </div>
  );
}
