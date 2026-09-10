import React, { useState } from "react";
import { MatchResultRankingItem } from "../../api/jobs";
import { CandidateSummary } from "../CandidatesDirectory";
import { Icon } from "../Icon";

export interface RequirementEvidenceMatrixProps {
  results: MatchResultRankingItem[];
  candidates: CandidateSummary[];
  onSelectCandidate?: (resultId: string) => void;
  selectedResultId?: string | null;
}

export interface MatrixRequirementCol {
  id: string;
  name: string;
  category: string;
  necessity: "REQUIRED" | "PREFERRED";
  priority?: string;
  displayOrder: number;
}

export type MatrixCellState =
  | "EVIDENCE_FOUND"
  | "PARTIAL_EVIDENCE"
  | "NEEDS_VERIFICATION"
  | "NOT_FOUND"
  | "EXCLUDED";

export interface MatrixCellData {
  state: MatrixCellState;
  stateLabel: string;
  candidateName: string;
  candidateId: string;
  requirementName: string;
  necessity: "REQUIRED" | "PREFERRED";
  evidenceCount: number;
  observedValue?: string | null;
  reasonCodes?: string[];
  reviewRecommended?: boolean;
}

export function classifyMatrixCellState(contrib: any): MatrixCellState {
  if (!contrib) return "NOT_FOUND";

  const matchState = (
    contrib.match_state ||
    contrib.matchState ||
    contrib.gap_state ||
    contrib.gapState ||
    contrib.result_state ||
    contrib.resultState ||
    ""
  ).toUpperCase();

  if (matchState === "NOT_APPLICABLE") {
    return "EXCLUDED";
  }

  if (
    matchState === "UNVERIFIED" ||
    matchState === "CONFLICTING_EVIDENCE" ||
    matchState === "CONFLICTING_REVIEW_REQUIRED" ||
    contrib.review_recommended === true ||
    contrib.reviewRecommended === true
  ) {
    return "NEEDS_VERIFICATION";
  }

  if (matchState === "PARTIALLY_MATCHED" || matchState === "PARTIALLY_COVERED") {
    return "PARTIAL_EVIDENCE";
  }

  if (matchState === "MATCHED" || matchState === "COVERED") {
    return "EVIDENCE_FOUND";
  }

  return "NOT_FOUND";
}

export function getMatrixStateLabel(state: MatrixCellState): string {
  switch (state) {
    case "EVIDENCE_FOUND":
      return "Evidence found";
    case "PARTIAL_EVIDENCE":
      return "Partial evidence found";
    case "NEEDS_VERIFICATION":
      return "Needs verification";
    case "EXCLUDED":
      return "Excluded from score";
    case "NOT_FOUND":
    default:
      return "Not found in resume";
  }
}

export function getMatrixStateBadgeStyle(state: MatrixCellState): React.CSSProperties {
  switch (state) {
    case "EVIDENCE_FOUND":
      return {
        backgroundColor: "rgba(13, 148, 136, 0.12)",
        color: "#0f766e",
        borderColor: "rgba(13, 148, 136, 0.3)",
      };
    case "PARTIAL_EVIDENCE":
      return {
        backgroundColor: "rgba(79, 70, 229, 0.12)",
        color: "#4338ca",
        borderColor: "rgba(79, 70, 229, 0.3)",
      };
    case "NEEDS_VERIFICATION":
      return {
        backgroundColor: "rgba(217, 119, 6, 0.12)",
        color: "#b45309",
        borderColor: "rgba(217, 119, 6, 0.3)",
      };
    case "EXCLUDED":
      return {
        backgroundColor: "rgba(148, 163, 184, 0.12)",
        color: "#64748b",
        borderColor: "rgba(148, 163, 184, 0.3)",
      };
    case "NOT_FOUND":
    default:
      return {
        backgroundColor: "rgba(100, 116, 139, 0.08)",
        color: "#64748b",
        borderColor: "rgba(100, 116, 139, 0.2)",
      };
  }
}

export function RequirementEvidenceMatrix({
  results,
  candidates,
  onSelectCandidate,
  selectedResultId,
}: RequirementEvidenceMatrixProps) {
  const [selectedCell, setSelectedCell] = useState<MatrixCellData | null>(null);

  if (!results || results.length === 0) {
    return null;
  }

  // Check if requirement-level results are available in the result payload
  const hasRequirementData = results.some((r) => {
    const contribs = r.requirement_contributions || (r as any).requirementContributions;
    return Array.isArray(contribs) && contribs.length > 0;
  });

  if (!hasRequirementData) {
    return (
      <div
        className="visual-analytics-card requirement-matrix-card"
        role="region"
        aria-label="Requirement Evidence Matrix"
      >
        <div className="chart-header">
          <div>
            <h4 className="chart-title">Requirement Evidence Matrix</h4>
            <p className="chart-subtitle">
              Evaluation breakdown across all candidate-requirement intersections
            </p>
          </div>
        </div>
        <div className="empty-state-card" style={{ padding: "28px 20px", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)", fontSize: "13px", margin: 0 }}>
            Evidence matrix unavailable until requirement-level results are available for this completed run.
          </p>
        </div>
      </div>
    );
  }

  // Extract columns in stored job-revision order
  const columnsMap = new Map<string, MatrixRequirementCol>();

  results.forEach((r) => {
    const contribs = r.requirement_contributions || (r as any).requirementContributions || [];
    contribs.forEach((c: any, idx: number) => {
      const id = String(c.requirement_id || c.requirementId || `req-${idx}`);
      if (!columnsMap.has(id)) {
        const rawNec = String(c.necessity || "REQUIRED").toUpperCase();
        const necessity = rawNec === "PREFERRED" || rawNec === "NICE_TO_HAVE" ? "PREFERRED" : "REQUIRED";
        columnsMap.set(id, {
          id,
          name: c.requirement_name || c.requirementName || c.label || `Requirement ${idx + 1}`,
          category: c.category || "SKILL",
          necessity,
          priority: c.priority,
          displayOrder: typeof c.display_order === "number" ? c.display_order : (typeof c.displayOrder === "number" ? c.displayOrder : idx),
        });
      }
    });
  });

  const columns = Array.from(columnsMap.values()).sort((a, b) => a.displayOrder - b.displayOrder);

  return (
    <div
      className="visual-analytics-card requirement-matrix-card"
      role="region"
      aria-label="Requirement Evidence Matrix"
    >
      <div className="chart-header">
        <div>
          <h4 className="chart-title">Requirement Evidence Matrix</h4>
          <p className="chart-subtitle">
            Compact matrix of {results.length} candidate{results.length === 1 ? "" : "s"} evaluated across {columns.length} requirement{columns.length === 1 ? "" : "s"} in job-revision order
          </p>
        </div>

        {/* Legend without red colors */}
        <div className="chart-legend" aria-label="Matrix evidence status legend">
          <span className="legend-item">
            <span className="legend-swatch" style={{ backgroundColor: "#0d9488" }} />
            <span>Evidence found</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ backgroundColor: "#4f46e5" }} />
            <span>Partial evidence</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ backgroundColor: "#d97706" }} />
            <span>Needs verification</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ backgroundColor: "#64748b" }} />
            <span>Not found</span>
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ backgroundColor: "#94a3b8" }} />
            <span>Excluded</span>
          </span>
        </div>
      </div>

      <div className="matrix-table-wrapper" style={{ overflowX: "auto", marginTop: "12px" }}>
        <table
          className="requirement-evidence-table"
          role="table"
          aria-label="Candidate Requirement Evidence Matrix"
          style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-color, #e2e8f0)" }}>
              <th
                scope="col"
                style={{
                  textAlign: "left",
                  padding: "10px 12px",
                  fontWeight: 600,
                  color: "var(--text-secondary)",
                  minWidth: "160px",
                }}
              >
                Candidate (Rank)
              </th>
              {columns.map((col) => (
                <th
                  key={col.id}
                  scope="col"
                  style={{
                    textAlign: "center",
                    padding: "10px 8px",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    minWidth: "120px",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "2px" }}>
                    <span style={{ fontWeight: 600 }}>{col.name}</span>
                    <span
                      className={`badge ${col.necessity === "REQUIRED" ? "badge-must-have" : "badge-neutral"}`}
                      style={{ fontSize: "10px", padding: "1px 6px" }}
                    >
                      {col.necessity === "REQUIRED" ? "Required" : "Preferred"}
                    </span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.map((item) => {
              const candidate = candidates.find((c) => c.artifactId === item.profileId);
              const candidateName = candidate?.fullName || `Candidate #${item.profileId.substring(0, 6)}`;
              const rankText = item.isTied ? `Tied #${item.rank}` : `#${item.rank}`;
              const isSelected = selectedResultId === item.resultId;
              const contribs = item.requirement_contributions || (item as any).requirementContributions || [];

              return (
                <tr
                  key={item.resultId || item.profileId}
                  className={`matrix-candidate-row ${isSelected ? "selected-row" : ""}`}
                  style={{
                    borderBottom: "1px solid var(--border-color, #e2e8f0)",
                    backgroundColor: isSelected ? "var(--bg-highlight, rgba(79, 70, 229, 0.04))" : "transparent",
                  }}
                >
                  <th
                    scope="row"
                    style={{
                      padding: "10px 12px",
                      fontWeight: 500,
                      textAlign: "left",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span className={`rank-badge ${item.rank === 1 && !item.isTied ? "top-rank" : ""}`} style={{ fontSize: "11px" }}>
                        {rankText}
                      </span>
                      <button
                        type="button"
                        className="candidate-row-btn"
                        onClick={() => onSelectCandidate && onSelectCandidate(item.resultId)}
                        style={{
                          background: "none",
                          border: "none",
                          padding: 0,
                          textAlign: "left",
                          cursor: onSelectCandidate ? "pointer" : "default",
                          color: "inherit",
                          fontWeight: 500,
                          textDecoration: onSelectCandidate ? "underline" : "none",
                          textDecorationColor: "var(--border-color)",
                        }}
                        aria-label={`Select ${candidateName}, rank ${item.rank}`}
                      >
                        {candidateName}
                      </button>
                    </div>
                  </th>

                  {columns.map((col) => {
                    const contrib = contribs.find(
                      (c: any) =>
                        String(c.requirement_id || c.requirementId) === col.id ||
                        (c.requirement_name || c.requirementName || c.label) === col.name
                    );

                    const state = classifyMatrixCellState(contrib);
                    const stateLabel = getMatrixStateLabel(state);
                    const evRefs = contrib?.evidence_references || contrib?.evidenceReferences || contrib?.evidence_ids || [];
                    const evidenceCount = Array.isArray(evRefs) ? evRefs.length : 0;
                    const cellBadgeStyle = getMatrixStateBadgeStyle(state);

                    const cellData: MatrixCellData = {
                      state,
                      stateLabel,
                      candidateName,
                      candidateId: item.profileId,
                      requirementName: col.name,
                      necessity: col.necessity,
                      evidenceCount,
                      observedValue: contrib?.observed_value || contrib?.observedValue,
                      reasonCodes: contrib?.reason_codes || contrib?.reasonCodes,
                      reviewRecommended: contrib?.review_recommended || contrib?.reviewRecommended,
                    };

                    const accessibleAriaLabel = `${candidateName}, ${col.name} (${col.necessity === "REQUIRED" ? "Required" : "Preferred"}): ${stateLabel}${evidenceCount > 0 ? ` with ${evidenceCount} evidence citation${evidenceCount === 1 ? "" : "s"}` : ""}`;

                    return (
                      <td
                        key={col.id}
                        style={{
                          textAlign: "center",
                          padding: "8px 6px",
                        }}
                      >
                        <button
                          type="button"
                          className="matrix-cell-chip"
                          onClick={() => setSelectedCell(cellData)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setSelectedCell(cellData);
                            }
                          }}
                          aria-label={accessibleAriaLabel}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: "4px",
                            padding: "4px 8px",
                            borderRadius: "6px",
                            border: "1px solid",
                            fontSize: "11px",
                            fontWeight: 500,
                            cursor: "pointer",
                            width: "100%",
                            maxWidth: "130px",
                            boxSizing: "border-box",
                            transition: "all 0.15s ease",
                            ...cellBadgeStyle,
                          }}
                        >
                          <span className="matrix-cell-text">{stateLabel}</span>
                          {evidenceCount > 0 && (
                            <span
                              className="matrix-evidence-pill"
                              style={{
                                fontSize: "10px",
                                opacity: 0.85,
                                fontWeight: 600,
                              }}
                            >
                              ({evidenceCount})
                            </span>
                          )}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Selected Cell Assessment Detail Modal/Popover */}
      {selectedCell && (
        <div
          className="matrix-cell-detail-card"
          role="dialog"
          aria-label={`Assessment details for ${selectedCell.candidateName} on ${selectedCell.requirementName}`}
          style={{
            marginTop: "16px",
            padding: "16px",
            borderRadius: "8px",
            border: "1px solid var(--border-color, #e2e8f0)",
            backgroundColor: "var(--bg-secondary, #f8fafc)",
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <h5 style={{ margin: 0, fontSize: "13px", fontWeight: 600 }}>
                {selectedCell.requirementName}{" "}
                <span style={{ fontSize: "11px", color: "var(--text-secondary)", fontWeight: 400 }}>
                  ({selectedCell.necessity === "REQUIRED" ? "Required criterion" : "Preferred criterion"})
                </span>
              </h5>
              <p style={{ margin: "2px 0 0 0", fontSize: "12px", color: "var(--text-secondary)" }}>
                Candidate: <strong>{selectedCell.candidateName}</strong>
              </p>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-xs"
              onClick={() => setSelectedCell(null)}
              aria-label="Close matrix cell details"
            >
              <Icon name="x" size={12} />
              <span>Close</span>
            </button>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px" }}>
            <span>Assessment:</span>
            <span
              style={{
                display: "inline-flex",
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "11px",
                fontWeight: 600,
                border: "1px solid",
                ...getMatrixStateBadgeStyle(selectedCell.state),
              }}
            >
              {selectedCell.stateLabel}
            </span>
            {selectedCell.evidenceCount > 0 && (
              <span style={{ color: "var(--text-secondary)" }}>
                {selectedCell.evidenceCount} citation{selectedCell.evidenceCount === 1 ? "" : "s"} in resume
              </span>
            )}
          </div>

          {selectedCell.observedValue && (
            <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
              <span>Observed evidence: </span>
              <code style={{ fontSize: "11px", backgroundColor: "rgba(0,0,0,0.04)", padding: "1px 4px", borderRadius: "3px" }}>
                {selectedCell.observedValue}
              </code>
            </div>
          )}

          {selectedCell.reasonCodes && selectedCell.reasonCodes.length > 0 && (
            <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              Reasons: {selectedCell.reasonCodes.join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
