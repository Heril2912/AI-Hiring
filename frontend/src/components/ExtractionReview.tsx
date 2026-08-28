export type ExtractionBlock = {
  blockId: string;
  sequenceIndex: number;
  pageNumber: number | null;
  structuralLocation: string | null;
  blockType: string;
  extractionMethod: string;
  rawText: string;
  normalizedText: string;
  confidence: number | null;
  reviewRequired: boolean;
};

export type ExtractionResultData = {
  artifactId: string;
  extractionId: string;
  extractorVersion: string;
  reviewRequired: boolean;
  blockCount: number;
  blocks: ExtractionBlock[];
};

interface ExtractionReviewProps {
  extraction: ExtractionResultData;
  onReset: () => void;
}

export function ExtractionReview({ extraction, onReset }: ExtractionReviewProps) {
  return (
    <section className="extraction-review-container" aria-labelledby="extraction-review-title">
      <div className="extraction-review-header">
        <div>
          <h2 id="extraction-review-title" className="extraction-review-title">
            Extraction &amp; Normalization Review
          </h2>
          <p className="extraction-meta-subtitle">
            Pipeline Version: <span className="mono">{extraction.extractorVersion}</span> &bull; Blocks:{" "}
            <strong>{extraction.blockCount}</strong>
          </p>
        </div>
        <button type="button" onClick={onReset} className="btn btn-secondary btn-sm">
          Upload Another Document
        </button>
      </div>

      {extraction.reviewRequired && (
        <div className="review-required-banner" role="alert">
          <span className="warning-icon" aria-hidden="true">⚠️</span>
          <div>
            <strong>Manual Review Advised</strong>
            <p>
              Quality signals detected potential formatting anomalies, unreadable pages, or low printable text ratios.
              Please inspect the evidence blocks below.
            </p>
          </div>
        </div>
      )}

      <div className="blocks-list" role="feed" aria-label="Extraction Blocks">
        {extraction.blocks.map((block) => {
          const isIdentical = block.rawText === block.normalizedText;

          return (
            <article
              key={block.blockId || block.sequenceIndex}
              className={`block-card ${block.reviewRequired ? "block-flagged" : ""}`}
              aria-labelledby={`block-header-${block.sequenceIndex}`}
            >
              <div className="block-header" id={`block-header-${block.sequenceIndex}`}>
                <div className="block-tag-group">
                  <span className="badge badge-index">#{block.sequenceIndex}</span>
                  <span className="badge badge-type">{block.blockType}</span>
                  <span className="badge badge-method">{block.extractionMethod}</span>
                  {block.pageNumber !== null && (
                    <span className="badge badge-location">Page {block.pageNumber}</span>
                  )}
                  {block.structuralLocation && (
                    <span className="badge badge-location mono">{block.structuralLocation}</span>
                  )}
                  {block.confidence !== null && (
                    <span className="badge badge-confidence">
                      {(block.confidence * 100).toFixed(0)}% conf
                    </span>
                  )}
                </div>

                {block.reviewRequired && (
                  <span className="badge badge-review-warn">Review Required</span>
                )}
              </div>

              <div className="block-content-grid">
                <div className="text-pane raw-pane">
                  <span className="pane-label">Immutable Raw Text</span>
                  <pre className="text-content">{block.rawText}</pre>
                </div>

                <div className="text-pane norm-pane">
                  <div className="pane-label-row">
                    <span className="pane-label">Normalized Text</span>
                    {isIdentical ? (
                      <span className="norm-badge-unchanged">No changes needed</span>
                    ) : (
                      <span className="norm-badge-changed">Normalized</span>
                    )}
                  </div>
                  <pre className="text-content">{block.normalizedText}</pre>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
