import { useState, useRef, ChangeEvent, FormEvent } from "react";
import { ExtractionReview, ExtractionResultData } from "./ExtractionReview";
import { CandidateProfileReview, CandidateProfileData } from "./CandidateProfileReview";

type UploadState =
  | "idle"
  | "selected"
  | "uploading"
  | "queued"
  | "processing"
  | "extracted"
  | "rejected"
  | "failed"
  | "processing_failed";

type ActiveTab = "profile" | "raw_blocks";

type UploadResponseData = {
  artifactId: string;
  jobId: string;
  status: string;
};

type ProcessResponseData = {
  artifactId: string;
  jobId: string;
  extractionId: string;
  processingStatus: string;
  reviewRequired: boolean;
  blockCount: number;
};

type StatusResponseData = {
  artifactId: string;
  jobId: string;
  detectedFormat: string | null;
  validationStatus: string;
  processingStatus: string;
  attemptCount: number;
  safeErrorCode: string | null;
};

const ERROR_MESSAGES: Record<string, string> = {
  FILE_TOO_LARGE: "The selected file exceeds the 10 MB limit.",
  INVALID_FILENAME: "The selected file has an invalid filename.",
  EMPTY_FILE: "The selected file is empty.",
  UNSUPPORTED_FILE_TYPE: "Only PDF (.pdf) and DOCX (.docx) files are supported.",
  FILE_TYPE_MISMATCH: "Declared file type does not match the file extension.",
  INVALID_PDF_SIGNATURE: "The selected file is not a valid PDF.",
  MALFORMED_PDF: "The PDF could not be validated.",
  ENCRYPTED_PDF: "Password-protected PDFs are not supported.",
  PDF_PAGE_LIMIT_EXCEEDED: "The PDF exceeds the five-page limit.",
  UNSAFE_PDF_CONTENT: "The PDF contains unsupported active or embedded content.",
  INVALID_DOCX_SIGNATURE: "The selected file is not a valid DOCX signature.",
  MALFORMED_DOCX: "The DOCX archive is corrupted or malformed.",
  INVALID_DOCX_STRUCTURE: "The selected file is not a valid DOCX document.",
  ENCRYPTED_DOCX: "Password-protected DOCX documents are not supported.",
  DOCX_ARCHIVE_LIMIT_EXCEEDED: "The DOCX package exceeds the safe processing limits.",
  UNSAFE_DOCX_CONTENT: "The DOCX contains unsupported active or embedded content.",
  INTAKE_UNAVAILABLE: "The service is temporarily unavailable. Please try again.",
  PDF_VALIDATION_UNAVAILABLE: "The service is temporarily unavailable. Please try again.",
  DOCX_VALIDATION_UNAVAILABLE: "The service is temporarily unavailable. Please try again.",
  RESUME_NOT_FOUND: "Resume artifact or processing job not found.",
  DIRECT_TEXT_UNAVAILABLE: "No readable digital text was found. Please upload a text-based PDF or DOCX document.",
  ARTIFACT_INTEGRITY_FAILED: "The stored document could not be verified.",
  RESOURCE_LIMIT_EXCEEDED: "The document exceeded the safe extraction limits.",
  UNSUPPORTED_DOCUMENT_CONTENT: "The document contains unsupported or unreadable content.",
  EXTRACTION_UNAVAILABLE: "The extraction service is currently unavailable.",
  JOB_ALREADY_RUNNING: "A processing job is already running for this document.",
  EXTRACTION_ALREADY_EXISTS: "An extraction already exists for this document.",
};

const SAFE_PROCESSING_ERROR_MESSAGES: Record<string, string> = {
  DIRECT_TEXT_UNAVAILABLE: "No readable digital text was found. Please upload a text-based PDF or DOCX document.",
  DOCUMENT_READ_FAILED: "The document could not be read during processing.",
  RESOURCE_LIMIT_EXCEEDED: "The document exceeded processing resource limits.",
  ARTIFACT_INTEGRITY_FAILED: "The stored document could not be verified.",
  PROCESSING_TIMEOUT: "The document processing timed out.",
  INTERNAL_PROCESSING_ERROR: "An internal error occurred during processing.",
};

const MAX_BYTES = 10 * 1024 * 1024; // 10 MB

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function ResumeUpload() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResponseData | null>(null);
  const [statusResult, setStatusResult] = useState<StatusResponseData | null>(null);
  const [extractionResult, setExtractionResult] = useState<ExtractionResultData | null>(null);
  const [profileResult, setProfileResult] = useState<CandidateProfileData | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("profile");
  const [isCheckingStatus, setIsCheckingStatus] = useState<boolean>(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) {
      setSelectedFile(null);
      setUploadState("idle");
      setErrorMessage(null);
      return;
    }

    const file = files[0];
    const lowerName = file.name.toLowerCase();

    // Client-side extension validation
    if (!lowerName.endsWith(".pdf") && !lowerName.endsWith(".docx")) {
      setSelectedFile(null);
      setUploadState("rejected");
      setErrorMessage("Only PDF (.pdf) and DOCX (.docx) files are supported.");
      return;
    }

    // Client-side size bounds
    if (file.size === 0) {
      setSelectedFile(null);
      setUploadState("rejected");
      setErrorMessage("The selected file is empty.");
      return;
    }

    if (file.size > MAX_BYTES) {
      setSelectedFile(null);
      setUploadState("rejected");
      setErrorMessage("The selected file exceeds the 10 MB limit.");
      return;
    }

    setSelectedFile(file);
    setUploadState("selected");
    setErrorMessage(null);
    setUploadResult(null);
    setStatusResult(null);
    setExtractionResult(null);
    setProfileResult(null);
    setStatusError(null);
  };

  const handleUpload = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedFile || uploadState === "uploading") {
      return;
    }

    setUploadState("uploading");
    setErrorMessage(null);
    setUploadResult(null);
    setStatusResult(null);
    setExtractionResult(null);
    setProfileResult(null);
    setStatusError(null);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await fetch("/api/v1/resumes", {
        method: "POST",
        body: formData,
      });

      if (response.status === 202) {
        const data: UploadResponseData = await response.json();
        setUploadResult(data);
        setUploadState("queued");
        return;
      }

      // Handle 4xx / 5xx error responses
      const errorJson = await response.json().catch(() => null);
      const detail = errorJson?.detail;
      const code = typeof detail === "object" ? detail?.code : null;

      if (response.status >= 400 && response.status < 500) {
        setUploadState("rejected");
        if (code && ERROR_MESSAGES[code]) {
          setErrorMessage(ERROR_MESSAGES[code]);
        } else {
          setErrorMessage("The document was rejected during validation.");
        }
      } else {
        setUploadState("failed");
        setErrorMessage("The service is temporarily unavailable. Please try again.");
      }
    } catch {
      setUploadState("failed");
      setErrorMessage("The service is temporarily unavailable. Please try again.");
    }
  };

  const handleExtractText = async () => {
    if (!uploadResult?.artifactId || uploadState === "processing") {
      return;
    }

    setUploadState("processing");
    setErrorMessage(null);
    setStatusError(null);

    try {
      // 1. Trigger extraction & profile assembly
      const processResponse = await fetch(`/api/v1/resumes/${uploadResult.artifactId}/process`, {
        method: "POST",
      });

      if (processResponse.ok) {
        // 2. Fetch full extraction blocks
        const extResponse = await fetch(`/api/v1/resumes/${uploadResult.artifactId}/extraction`);
        if (extResponse.ok) {
          const extData: ExtractionResultData = await extResponse.json();
          setExtractionResult(extData);
        }

        // 3. Fetch assembled CandidateProfile
        const profResponse = await fetch(`/api/v1/resumes/${uploadResult.artifactId}/profile`);
        if (profResponse.ok) {
          const profData: CandidateProfileData = await profResponse.json();
          setProfileResult(profData);
          setUploadState("extracted");
          setActiveTab("profile");
          return;
        } else if (extResponse.ok) {
          setUploadState("extracted");
          setActiveTab("raw_blocks");
          return;
        }
      }

      // Handle failure
      const errorJson = await processResponse.json().catch(() => null);
      const detail = errorJson?.detail;
      const code = typeof detail === "object" ? detail?.code : null;
      const message = typeof detail === "object" ? detail?.message : null;

      setUploadState("processing_failed");
      if (code && ERROR_MESSAGES[code]) {
        setErrorMessage(ERROR_MESSAGES[code]);
      } else if (message) {
        setErrorMessage(message);
      } else {
        setErrorMessage("Text extraction failed. Please check the document and try again.");
      }
    } catch {
      setUploadState("processing_failed");
      setErrorMessage("The extraction service is temporarily unavailable. Please try again.");
    }
  };

  const handleCheckStatus = async () => {
    if (!uploadResult?.artifactId || isCheckingStatus) {
      return;
    }

    setIsCheckingStatus(true);
    setStatusError(null);

    try {
      const response = await fetch(`/api/v1/resumes/${uploadResult.artifactId}/status`);
      if (response.ok) {
        const data: StatusResponseData = await response.json();
        setStatusResult(data);
      } else {
        const errorJson = await response.json().catch(() => null);
        const detail = errorJson?.detail;
        const code = typeof detail === "object" ? detail?.code : null;
        if (code && ERROR_MESSAGES[code]) {
          setStatusError(ERROR_MESSAGES[code]);
        } else {
          setStatusError("Failed to fetch resume status.");
        }
      }
    } catch {
      setStatusError("Failed to fetch resume status. Service unavailable.");
    } finally {
      setIsCheckingStatus(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setUploadState("idle");
    setErrorMessage(null);
    setUploadResult(null);
    setStatusResult(null);
    setExtractionResult(null);
    setProfileResult(null);
    setStatusError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  if (uploadState === "extracted" && (profileResult || extractionResult)) {
    return (
      <div className="review-tabs-container">
        <div className="review-tabs-header">
          {profileResult && (
            <button
              type="button"
              className={`tab-btn ${activeTab === "profile" ? "active" : ""}`}
              onClick={() => setActiveTab("profile")}
            >
              Candidate Profile Review
            </button>
          )}
          {extractionResult && (
            <button
              type="button"
              className={`tab-btn ${activeTab === "raw_blocks" ? "active" : ""}`}
              onClick={() => setActiveTab("raw_blocks")}
            >
              Raw Extraction Review ({extractionResult.blockCount} blocks)
            </button>
          )}
        </div>

        {activeTab === "profile" && profileResult && (
          <CandidateProfileReview
            profile={profileResult}
            extraction={extractionResult}
            onReset={handleReset}
          />
        )}

        {activeTab === "raw_blocks" && extractionResult && (
          <ExtractionReview extraction={extractionResult} onReset={handleReset} />
        )}
      </div>
    );
  }

  return (
    <section className="upload-card" aria-labelledby="resume-upload-title">
      <h2 id="resume-upload-title" className="upload-card-title">
        Resume Document Intake &amp; Extraction
      </h2>
      <p className="upload-card-notice">
        Upload only a resume you own or have permission to process. Supported formats: text-based PDF (.pdf) and native DOCX (.docx) up to 10 MB.
      </p>

      {uploadState !== "queued" && uploadState !== "processing" && uploadState !== "processing_failed" && (
        <form onSubmit={handleUpload} className="upload-form">
          <div className="form-group">
            <label htmlFor="resume-file-input" className="file-input-label">
              Select resume file (.pdf, .docx):
            </label>
            <input
              id="resume-file-input"
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx"
              onChange={handleFileChange}
              disabled={uploadState === "uploading"}
              className="file-input"
            />
          </div>

          {selectedFile && (
            <div className="file-meta">
              <span className="file-name">{selectedFile.name}</span>
              <span className="file-size">({formatFileSize(selectedFile.size)})</span>
            </div>
          )}

          <div className="action-row">
            <button
              type="submit"
              disabled={!selectedFile || uploadState === "uploading"}
              className="btn btn-primary"
              aria-busy={uploadState === "uploading"}
            >
              {uploadState === "uploading" ? "Uploading..." : "Upload Resume"}
            </button>

            {(selectedFile || errorMessage) && uploadState !== "uploading" && (
              <button type="button" onClick={handleReset} className="btn btn-secondary">
                Clear
              </button>
            )}
          </div>
        </form>
      )}

      {/* Accessible Live Status Messages */}
      <div className="status-feedback" aria-live="polite">
        {uploadState === "uploading" && (
          <p className="feedback-text info">Streaming document to secure intake storage...</p>
        )}

        {(uploadState === "rejected" || uploadState === "failed" || uploadState === "processing_failed") && errorMessage && (
          <div className="feedback-box error" role="alert">
            <p className="feedback-text error">{errorMessage}</p>
            <div className="action-row">
              {uploadState === "processing_failed" && (
                <button
                  type="button"
                  onClick={handleExtractText}
                  className="btn btn-primary btn-sm"
                >
                  Retry extraction
                </button>
              )}
              <button type="button" onClick={handleReset} className="btn btn-secondary btn-sm">
                Choose another file
              </button>
            </div>
          </div>
        )}

        {(uploadState === "queued" || uploadState === "processing") && uploadResult && (
          <div className="feedback-box success">
            <h3 className="success-header">Resume accepted for processing.</h3>
            <div className="success-details">
              <div className="detail-row">
                <span className="detail-label">Status:</span>
                <span className="detail-value badge-queued">
                  {uploadState === "processing" ? "RUNNING" : uploadResult.status}
                </span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Artifact ID:</span>
                <span className="detail-value mono">{uploadResult.artifactId}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Job ID:</span>
                <span className="detail-value mono">{uploadResult.jobId}</span>
              </div>
            </div>

            <div className="action-row">
              <button
                type="button"
                onClick={handleExtractText}
                disabled={uploadState === "processing"}
                className="btn btn-primary"
                aria-busy={uploadState === "processing"}
              >
                {uploadState === "processing" ? "Extracting resume text…" : "Extract text"}
              </button>
              <button
                type="button"
                onClick={handleCheckStatus}
                disabled={isCheckingStatus || uploadState === "processing"}
                className="btn btn-secondary btn-sm"
              >
                {isCheckingStatus ? "Checking..." : "Check current status"}
              </button>
              <button
                type="button"
                onClick={handleReset}
                disabled={uploadState === "processing"}
                className="btn btn-secondary btn-sm"
              >
                Choose another file
              </button>
            </div>

            {statusError && <p className="feedback-text error">{statusError}</p>}

            {statusResult && (
              <div className="status-inspect-card">
                <h4 className="inspect-title">Processing Status Details</h4>
                <div className="inspect-grid">
                  <div>
                    <strong>Format:</strong> {statusResult.detectedFormat || "Unknown"}
                  </div>
                  <div>
                    <strong>Validation:</strong> {statusResult.validationStatus}
                  </div>
                  <div>
                    <strong>Job Status:</strong> {statusResult.processingStatus}
                  </div>
                  <div>
                    <strong>Attempts:</strong> {statusResult.attemptCount}
                  </div>
                </div>
                {statusResult.safeErrorCode && (
                  <div className="inspect-error">
                    <strong>Error:</strong>{" "}
                    {SAFE_PROCESSING_ERROR_MESSAGES[statusResult.safeErrorCode] || statusResult.safeErrorCode}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
