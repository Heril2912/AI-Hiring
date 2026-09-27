import React, { useState, useEffect } from "react";
import {
  fetchJobApplicants,
  RecruiterApplicationSummary,
} from "../../api/recruiterApplications";
import { Icon } from "../Icon";

interface JobApplicantsViewProps {
  jobId: string;
  jobTitle?: string;
  onSelectApplication: (applicationId: string) => void;
  onNavigateBack?: () => void;
}

export const JobApplicantsView: React.FC<JobApplicantsViewProps> = ({
  jobId,
  jobTitle,
  onSelectApplication,
  onNavigateBack,
}) => {
  const [applications, setApplications] = useState<RecruiterApplicationSummary[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [activeCount, setActiveCount] = useState<number>(0);
  const [withdrawnCount, setWithdrawnCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [reviewStateFilter, setReviewStateFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [page, setPage] = useState<number>(1);
  const limit = 20;

  const loadApplicants = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await fetchJobApplicants(jobId, {
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        reviewState: reviewStateFilter !== "ALL" ? reviewStateFilter : undefined,
        page,
        limit,
      });
      setApplications(res.items);
      setTotal(res.total);
      setActiveCount(res.activeCount);
      setWithdrawnCount(res.withdrawnCount);
    } catch (err: any) {
      setError(err?.message || "Failed to load applicants for this job.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadApplicants();
  }, [jobId, statusFilter, reviewStateFilter, page]);

  const filteredApplications = applications.filter((app) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      app.candidateName.toLowerCase().includes(q) ||
      (app.candidateEmail && app.candidateEmail.toLowerCase().includes(q))
    );
  });

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Top bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          {onNavigateBack && (
            <button
              type="button"
              onClick={onNavigateBack}
              className="btn btn-secondary btn-xs flex items-center gap-1 mb-2"
            >
              <Icon name="arrow-left" size={12} /> Back to Job Details
            </button>
          )}
          <h2 className="text-xl font-bold text-gray-900">
            Applicants {jobTitle ? `for ${jobTitle}` : ""}
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Job-contextual applicant review and approved interview handoff.
          </p>
        </div>

        {/* Counts summary */}
        <div className="flex items-center gap-2 text-xs">
          <span className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 font-medium">
            Active: {activeCount}
          </span>
          <span className="px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 border border-gray-200 font-medium">
            Withdrawn: {withdrawnCount}
          </span>
        </div>
      </div>

      {/* Restrained Filters Bar */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm flex flex-wrap items-center gap-3 text-xs">
        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            placeholder="Search applicant name or email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 text-xs"
          />
        </div>

        <div className="flex items-center gap-2">
          <label className="text-gray-500 font-medium">Status:</label>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="px-2.5 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 text-xs"
          >
            <option value="ALL">All Applications</option>
            <option value="SUBMITTED">Active (Submitted)</option>
            <option value="WITHDRAWN">Withdrawn</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-gray-500 font-medium">Review Stage:</label>
          <select
            value={reviewStateFilter}
            onChange={(e) => {
              setReviewStateFilter(e.target.value);
              setPage(1);
            }}
            className="px-2.5 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500 text-xs"
          >
            <option value="ALL">All Stages</option>
            <option value="RECEIVED">Received</option>
            <option value="IN_REVIEW">In Review</option>
            <option value="INTERVIEW_READY">Interview Ready</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-xs flex items-center gap-2">
          <Icon name="alert-triangle" size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Applicant List Table / Cards */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center p-12 space-y-3">
          <Icon name="spinner" size={24} className="animate-spin text-indigo-600" />
          <p className="text-gray-500 text-xs">Loading applicants...</p>
        </div>
      ) : filteredApplications.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-xl p-12 text-center shadow-sm space-y-2">
          <Icon name="users" size={32} className="mx-auto text-gray-300" />
          <h3 className="text-base font-semibold text-gray-800">No applicants found</h3>
          <p className="text-xs text-gray-500">
            {searchQuery || statusFilter !== "ALL" || reviewStateFilter !== "ALL"
              ? "No applications match the selected filter criteria."
              : "No candidates have applied to this job requisition yet."}
          </p>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200 text-gray-500 uppercase tracking-wider font-semibold">
                <th className="py-3 px-4">Applicant</th>
                <th className="py-3 px-4">Submitted</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Review Stage</th>
                <th className="py-3 px-4">Deterministic Match</th>
                <th className="py-3 px-4">Interview</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredApplications.map((app) => (
                <tr key={app.applicationId} className="hover:bg-gray-50/75 transition-colors">
                  <td className="py-3 px-4 font-medium text-gray-900">
                    <div>{app.candidateName}</div>
                    <div className="text-[11px] text-gray-400 font-normal">{app.candidateEmail || "No email"}</div>
                  </td>
                  <td className="py-3 px-4 text-gray-500">
                    {new Date(app.submittedAt).toLocaleDateString()}
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-0.5 text-[11px] font-semibold rounded-full ${
                        app.status === "SUBMITTED"
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-gray-100 text-gray-600 border border-gray-200"
                      }`}
                    >
                      {app.status}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                      {app.recruiterReviewState}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    {app.matchStatus === "Evaluated" && app.matchScore !== null && app.matchScore !== undefined ? (
                      <span className="font-semibold text-purple-900">
                        {app.matchScore.toFixed(1)}% <span className="text-[10px] text-purple-600">({app.confidenceTier})</span>
                      </span>
                    ) : (
                      <span className="text-gray-400 italic">Not evaluated</span>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-0.5 text-[11px] font-medium rounded-full ${
                        app.interviewStatus === "RELEASED"
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {app.interviewStatus}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <button
                      type="button"
                      onClick={() => onSelectApplication(app.applicationId)}
                      className="btn btn-secondary btn-xs"
                    >
                      View Application
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
