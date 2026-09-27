import React, { useState, useEffect } from "react";
import {
  fetchJobApplicantDetail,
  updateApplicantReviewState,
  releaseApplicantInterview,
  RecruiterApplicationDetail,
  RecruiterReviewState,
} from "../../api/recruiterApplications";
import { Icon } from "../Icon";

interface JobApplicationDetailViewProps {
  jobId: string;
  applicationId: string;
  onNavigateBack: () => void;
  onOpenAiInterviews?: (jobId: string) => void;
  onOpenMatchingComparison?: () => void;
}

export const JobApplicationDetailView: React.FC<JobApplicationDetailViewProps> = ({
  jobId,
  applicationId,
  onNavigateBack,
  onOpenAiInterviews,
  onOpenMatchingComparison,
}) => {
  const [detail, setDetail] = useState<RecruiterApplicationDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isUpdatingState, setIsUpdatingState] = useState<boolean>(false);
  const [isReleasing, setIsReleasing] = useState<boolean>(false);
  const [showReleaseConfirm, setShowReleaseConfirm] = useState<boolean>(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const loadDetail = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await fetchJobApplicantDetail(jobId, applicationId);
      setDetail(res);
    } catch (err: any) {
      setError(err?.message || "Failed to load application details.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDetail();
  }, [jobId, applicationId]);

  const handleReviewStateTransition = async (targetState: RecruiterReviewState) => {
    if (!detail) return;
    try {
      setIsUpdatingState(true);
      setActionSuccess(null);
      setError(null);
      const updated = await updateApplicantReviewState(
        jobId,
        applicationId,
        targetState,
        detail.recruiterReviewState
      );
      setDetail(updated);
      setActionSuccess(`Review state updated to ${targetState}.`);
    } catch (err: any) {
      setError(err?.message || "Failed to update review state.");
    } finally {
      setIsUpdatingState(false);
    }
  };

  const handleReleaseInterview = async () => {
    if (!detail) return;
    try {
      setIsReleasing(true);
      setShowReleaseConfirm(false);
      setActionSuccess(null);
      setError(null);
      const res = await releaseApplicantInterview(
        jobId,
        applicationId,
        detail.interviewEligibility.questionSetId || undefined
      );
      setActionSuccess(res.message || "Interview released successfully.");
      await loadDetail();
    } catch (err: any) {
      setError(err?.message || "Failed to release interview.");
    } finally {
      setIsReleasing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 space-y-4">
        <Icon name="spinner" size={28} className="animate-spin text-indigo-600" />
        <p className="text-gray-500 font-medium">Loading applicant details...</p>
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="p-6 space-y-4 max-w-3xl mx-auto">
        <button
          type="button"
          onClick={onNavigateBack}
          className="btn btn-secondary btn-sm flex items-center gap-1"
        >
          <Icon name="arrow-left" size={14} /> Back to Applicants
        </button>
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-800">
          <p className="font-semibold">{error}</p>
        </div>
      </div>
    );
  }

  if (!detail) return null;

  const isWithdrawn = detail.status === "WITHDRAWN";
  const { interviewEligibility, matchEvidence } = detail;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Navigation & Header */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={onNavigateBack}
          className="btn btn-secondary btn-sm flex items-center gap-1.5"
        >
          <Icon name="arrow-left" size={14} /> Back to Applicants
        </button>
        <div className="flex items-center gap-2">
          <span
            className={`px-3 py-1 text-xs font-semibold rounded-full ${
              detail.status === "SUBMITTED"
                ? "bg-emerald-100 text-emerald-800"
                : "bg-gray-200 text-gray-700"
            }`}
          >
            {detail.status}
          </span>
          <span className="px-3 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
            Review: {detail.recruiterReviewState}
          </span>
        </div>
      </div>

      {actionSuccess && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-sm flex items-center gap-2">
          <Icon name="check" size={16} />
          <span>{actionSuccess}</span>
        </div>
      )}

      {error && (
        <div className="p-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg text-sm flex items-center gap-2">
          <Icon name="alert-triangle" size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Main Applicant Identity Card */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">{detail.candidateName}</h2>
            <p className="text-sm text-gray-500 mt-1">
              Applied to <span className="font-medium text-gray-700">{detail.jobTitle}</span> (Submitted Revision: Rev #{detail.jobRevision})
            </p>
          </div>
          <div className="text-right text-xs text-gray-400">
            <div>Submitted: {new Date(detail.submittedAt).toLocaleString()}</div>
            {detail.withdrawnAt && (
              <div className="text-amber-600 mt-0.5">Withdrawn: {new Date(detail.withdrawnAt).toLocaleString()}</div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-gray-100 text-sm">
          <div>
            <span className="text-gray-400 block text-xs uppercase tracking-wider">Email</span>
            <span className="text-gray-800 font-medium">{detail.candidateEmail || "Not provided"}</span>
          </div>
          <div>
            <span className="text-gray-400 block text-xs uppercase tracking-wider">Phone</span>
            <span className="text-gray-800 font-medium">{detail.candidatePhone || "Not provided"}</span>
          </div>
          <div>
            <span className="text-gray-400 block text-xs uppercase tracking-wider">Profile Version</span>
            <span className="text-gray-800 font-medium">v{detail.profileVersion}</span>
          </div>
        </div>
      </div>

      {/* Internal Recruiter Review Controls */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm space-y-4">
        <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
          <Icon name="user-check" size={18} className="text-indigo-600" />
          Internal Review Stage
        </h3>
        <p className="text-xs text-gray-500">
          Move the application through the review stages. Progressing to <span className="font-medium">INTERVIEW_READY</span> enables interview release.
        </p>

        <div className="flex flex-wrap items-center gap-3 pt-2">
          {detail.recruiterReviewState === "RECEIVED" && (
            <button
              type="button"
              className="btn btn-primary btn-sm flex items-center gap-1.5"
              onClick={() => handleReviewStateTransition("IN_REVIEW")}
              disabled={isUpdatingState || isWithdrawn}
            >
              <Icon name="play" size={14} /> Start Review (Move to IN_REVIEW)
            </button>
          )}

          {detail.recruiterReviewState === "IN_REVIEW" && (
            <>
              <button
                type="button"
                className="btn btn-primary btn-sm flex items-center gap-1.5"
                onClick={() => handleReviewStateTransition("INTERVIEW_READY")}
                disabled={isUpdatingState || isWithdrawn}
              >
                <Icon name="badge-check" size={14} /> Mark as INTERVIEW_READY
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm flex items-center gap-1.5"
                onClick={() => handleReviewStateTransition("RECEIVED")}
                disabled={isUpdatingState || isWithdrawn}
              >
                <Icon name="arrow-left" size={14} /> Reset to RECEIVED
              </button>
            </>
          )}

          {detail.recruiterReviewState === "INTERVIEW_READY" && (
            <button
              type="button"
              className="btn btn-secondary btn-sm flex items-center gap-1.5"
              onClick={() => handleReviewStateTransition("IN_REVIEW")}
              disabled={isUpdatingState || isWithdrawn}
            >
              <Icon name="arrow-left" size={14} /> Move back to IN_REVIEW
            </button>
          )}

          {isWithdrawn && (
            <span className="text-xs text-amber-700 italic">
              Application is withdrawn; review state transitions are restricted.
            </span>
          )}
        </div>
      </div>

      {/* Deterministic Match & Skill Gap Section */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
            <Icon name="sparkles" size={18} className="text-purple-600" />
            Deterministic Match & Skill Gap Evidence
          </h3>
          {onOpenMatchingComparison && (
            <button
              type="button"
              onClick={onOpenMatchingComparison}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1"
            >
              Open Match Workspace <Icon name="external-link" size={12} />
            </button>
          )}
        </div>

        {matchEvidence ? (
          <div className="p-4 bg-purple-50/50 border border-purple-100 rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-2xl font-bold text-purple-900">
                  {matchEvidence.displayScore.toFixed(1)}%
                </span>
                <span className="ml-2 px-2.5 py-0.5 text-xs font-semibold rounded-full bg-purple-200 text-purple-800">
                  {matchEvidence.confidenceTier} Tier
                </span>
              </div>
              <span className="text-xs text-gray-400">
                Rank #{matchEvidence.rank} • Evaluated: {new Date(matchEvidence.computedAt).toLocaleDateString()}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 pt-2 border-t border-purple-100">
              <div>Warnings: <span className="font-semibold text-gray-800">{matchEvidence.warningCount}</span></div>
              <div>Must-Have Warnings: <span className="font-semibold text-gray-800">{matchEvidence.mustHaveWarningCount}</span></div>
            </div>
          </div>
        ) : (
          <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-600 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Icon name="info" size={16} className="text-gray-400" />
              <span>Not evaluated. Matching has not been computed for this job version / candidate pair yet.</span>
            </div>
            {onOpenMatchingComparison && (
              <button
                type="button"
                onClick={onOpenMatchingComparison}
                className="btn btn-secondary btn-xs"
              >
                Run Match
              </button>
            )}
          </div>
        )}
      </div>

      {/* AI Interview Access & Release Section */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
            <Icon name="sparkles" size={18} className="text-blue-600" />
            Interview Access
          </h3>
          {onOpenAiInterviews && (
            <button
              type="button"
              onClick={() => onOpenAiInterviews(jobId)}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1"
            >
              Open AI Interviews for Rev #{detail.jobRevision} <Icon name="external-link" size={12} />
            </button>
          )}
        </div>

        <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg space-y-4 text-sm">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="bg-white p-3 rounded border border-gray-200">
              <span className="text-gray-500 block">Job Revision</span>
              <strong className="text-gray-900 text-sm">Rev #{detail.jobRevision}</strong>
            </div>
            <div className="bg-white p-3 rounded border border-gray-200">
              <span className="text-gray-500 block">Review Stage</span>
              <strong className="text-gray-900 text-sm">{detail.recruiterReviewState}</strong>
            </div>
            <div className="bg-white p-3 rounded border border-gray-200">
              <span className="text-gray-500 block">Approved Questions</span>
              <strong className="text-gray-900 text-sm">{interviewEligibility.questionCount} Questions</strong>
            </div>
            <div className="bg-white p-3 rounded border border-gray-200">
              <span className="text-gray-500 block">Official Status</span>
              <strong className={interviewEligibility.existingReleaseId ? "text-emerald-700 text-sm font-semibold" : "text-gray-700 text-sm"}>
                {interviewEligibility.existingReleaseId ? "RELEASED" : "NOT RELEASED"}
              </strong>
            </div>
          </div>

          <div className="flex items-start justify-between pt-2 border-t border-gray-200">
            <div>
              <p className="text-xs text-gray-600">{interviewEligibility.message}</p>
            </div>
            {interviewEligibility.isEligible && (
              <button
                type="button"
                onClick={() => setShowReleaseConfirm(true)}
                disabled={isReleasing || isWithdrawn}
                className="btn btn-primary btn-sm flex items-center gap-1.5"
              >
                <Icon name="sparkles" size={14} />
                <span>Release Interview</span>
              </button>
            )}
          </div>

          {!interviewEligibility.isEligible && !interviewEligibility.existingReleaseId && (
            <div className="text-xs text-amber-800 bg-amber-50 p-2.5 rounded border border-amber-200 flex items-center gap-2">
              <Icon name="alert-triangle" size={14} />
              <span>{interviewEligibility.message}</span>
            </div>
          )}

          {interviewEligibility.existingReleaseId && (
            <div className="text-xs text-emerald-800 bg-emerald-50 p-3 rounded border border-emerald-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Icon name="check" size={16} />
                <span>Interview released and active for candidate on Interviews portal.</span>
              </div>
              <span className="text-emerald-700 font-semibold uppercase text-[11px] tracking-wide">
                Interview Released
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Confirmation Dialog Modal */}
      {showReleaseConfirm && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="release-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
        >
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 border border-gray-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-600 shrink-0">
                <Icon name="sparkles" size={20} />
              </div>
              <div>
                <h3 id="release-modal-title" className="text-base font-bold text-gray-900">
                  Release Official Interview
                </h3>
                <p className="text-xs text-gray-500">
                  Application for {detail.candidateName}
                </p>
              </div>
            </div>

            <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-700 space-y-1.5 border border-gray-200">
              <div className="flex justify-between">
                <span className="text-gray-500">Job Title:</span>
                <span className="font-semibold text-gray-900">{detail.jobTitle}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Job Revision:</span>
                <span className="font-semibold text-gray-900">Rev #{detail.jobRevision}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Approved Questions:</span>
                <span className="font-semibold text-gray-900">{interviewEligibility.questionCount} Questions</span>
              </div>
            </div>

            <p className="text-xs text-gray-600 leading-relaxed">
              Releasing this official interview will freeze these exact approved questions to the candidate's application and make it available in their portal.
            </p>

            <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setShowReleaseConfirm(false)}
                disabled={isReleasing}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm flex items-center gap-1.5"
                onClick={handleReleaseInterview}
                disabled={isReleasing}
              >
                {isReleasing ? (
                  <>
                    <Icon name="spinner" size={14} className="animate-spin" />
                    <span>Releasing...</span>
                  </>
                ) : (
                  <>
                    <Icon name="check" size={14} />
                    <span>Confirm Release</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
