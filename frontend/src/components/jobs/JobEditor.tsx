import React, { useState, useEffect, useMemo, FormEvent } from "react";
import {
  fetchJobDetail,
  createJobRequisition,
  updateJobDraft,
  saveDraftRequirements,
  JobDetail,
  JobCreatePayload,
  JobDraftUpdatePayload,
  RequirementItem,
  RequirementCategory,
} from "../../api/jobs";
import { OccupationSearchItem } from "../../api/taxonomy";
import { Icon } from "../Icon";
import { OccupationSelector } from "./OccupationSelector";
import { RequirementCard } from "./RequirementCard";
import {
  JobDescriptionImportModal,
  AppliedSuggestionsPayload,
  CurrentFormValues,
} from "./JobDescriptionImportModal";

interface JobEditorProps {
  jobId?: string | null; // null if creating a new job
  onNavigateBack: () => void;
  onJobCreated?: (newJobId: string) => void;
}

export function JobEditor({ jobId, onNavigateBack, onJobCreated }: JobEditorProps) {
  // Main Draft Data
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(jobId));
  const [loadError, setLoadError] = useState<string | null>(null);

  // Form Fields
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [location, setLocation] = useState("");
  const [employmentType, setEmploymentType] = useState<string>("FULL_TIME");
  const [workplaceType, setWorkplaceType] = useState<string>("HYBRID");
  const [openingsCount, setOpeningsCount] = useState<string>("1");
  const [internalReference, setInternalReference] = useState("");
  const [summary, setSummary] = useState("");
  const [responsibilities, setResponsibilities] = useState("");
  const [jobDescriptionText, setJobDescriptionText] = useState("");
  const [occupationConceptId, setOccupationConceptId] = useState<string | null>(null);
  const [occupationTitle, setOccupationTitle] = useState<string | null>(null);

  // Disclosures & Progressive Visibility
  const [showJobDetailsMore, setShowJobDetailsMore] = useState(false);
  const [showOccupationSection, setShowOccupationSection] = useState(false);

  // Requirements State
  const [requirements, setRequirements] = useState<RequirementItem[]>([]);

  // Revision & Status Tracking
  const [currentRevision, setCurrentRevision] = useState<number>(1);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflictError, setConflictError] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);

  // Initial Load for Existing Job
  useEffect(() => {
    if (!jobId) {
      setIsLoading(false);
      return;
    }

    let isMounted = true;
    async function loadJob() {
      try {
        setIsLoading(true);
        setLoadError(null);
        const data = await fetchJobDetail(jobId!);
        if (!isMounted) return;

        setJobDetail(data);
        const v = data.currentVersion;
        setTitle(v.title || "");
        setDepartment(v.department || "");
        setLocation(v.location || "");
        setEmploymentType(v.employmentType || "FULL_TIME");
        setWorkplaceType(v.workplaceType || "HYBRID");
        setOpeningsCount(v.openingsCount ? String(v.openingsCount) : "1");
        setInternalReference(v.internalReference || "");
        if (v.internalReference) {
          setShowJobDetailsMore(true);
        }
        setSummary(v.summary || "");
        setResponsibilities(v.responsibilities || "");
        setJobDescriptionText(v.jobDescriptionText || "");
        setOccupationConceptId(v.occupationConceptId || null);
        setOccupationTitle(v.occupationTitle || null);
        if (v.occupationConceptId) {
          setShowOccupationSection(true);
        }
        setCurrentRevision(v.revision || 1);
        setRequirements(v.requirements || []);
        setIsDirty(false);
      } catch (err: any) {
        if (isMounted) {
          setLoadError(err?.message || "Failed to load job requisition.");
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadJob();
    return () => {
      isMounted = false;
    };
  }, [jobId]);

  // Unsaved changes browser prompt
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  // Handle Occupation Selection
  const handleSelectOccupation = (item: OccupationSearchItem | null) => {
    if (item) {
      setOccupationConceptId(item.conceptId);
      setOccupationTitle(item.canonicalTitle);
    } else {
      setOccupationConceptId(null);
      setOccupationTitle(null);
    }
    setIsDirty(true);
  };

  // Requirement Handlers
  const handleAddRequirement = (category: RequirementCategory = "SKILL") => {
    const newReq: RequirementItem = {
      displayOrder: requirements.length,
      category,
      label: "",
      necessity: "MUST_HAVE",
      priority: "MEDIUM",
      acceptedEvidenceTypes: ["EMPLOYMENT", "PROJECT"],
      acceptedEquivalents: [],
      origin: "RECRUITER_ENTERED",
    };
    setRequirements([...requirements, newReq]);
    setIsDirty(true);
  };

  const handleUpdateRequirement = (idx: number, updated: RequirementItem) => {
    const copy = [...requirements];
    copy[idx] = updated;
    setRequirements(copy);
    setIsDirty(true);
  };

  const handleRemoveRequirement = (idx: number) => {
    const filtered = requirements.filter((_, i) => i !== idx);
    const reordered = filtered.map((r, i) => ({ ...r, displayOrder: i }));
    setRequirements(reordered);
    setIsDirty(true);
  };

  const handleMoveRequirement = (idx: number, direction: "up" | "down") => {
    const targetIdx = direction === "up" ? idx - 1 : idx + 1;
    if (targetIdx < 0 || targetIdx >= requirements.length) return;

    const copy = [...requirements];
    const temp = copy[idx];
    copy[idx] = copy[targetIdx];
    copy[targetIdx] = temp;

    const reordered = copy.map((r, i) => ({ ...r, displayOrder: i }));
    setRequirements(reordered);
    setIsDirty(true);
  };

  // Compute Draft Review Summary Metrics
  const reviewSummary = useMemo(() => {
    let mustHaveCount = 0;
    let preferredCount = 0;
    let onetConfirmedCount = 0;
    let customCount = 0;
    let reviewRequiredCount = 0;
    let missingRationaleCount = 0;

    for (const r of requirements) {
      if (r.necessity === "MUST_HAVE") mustHaveCount++;
      else preferredCount++;

      if (r.origin === "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED") onetConfirmedCount++;
      else customCount++;

      if (r.reviewRequired || (r.warningMetadata && r.warningMetadata.length > 0)) {
        reviewRequiredCount++;
      }

      if ((r.necessity === "MUST_HAVE" || r.priority === "CRITICAL") && !r.rationale?.trim()) {
        missingRationaleCount++;
      }
    }

    return {
      total: requirements.length,
      mustHaveCount,
      preferredCount,
      onetConfirmedCount,
      customCount,
      reviewRequiredCount,
      missingRationaleCount,
    };
  }, [requirements]);

  // Save Flow
  const handleSave = async (e?: FormEvent) => {
    if (e) e.preventDefault();
    setSaveError(null);
    setConflictError(null);
    setSaveSuccessMsg(null);

    if (!title.trim()) {
      setSaveError("Job title is required.");
      return;
    }

    // Validate requirements labels
    for (let i = 0; i < requirements.length; i++) {
      if (!requirements[i].label.trim()) {
        setSaveError(`Requirement #${i + 1} has an empty name.`);
        return;
      }
    }

    try {
      setIsSaving(true);

      if (!jobId) {
        // 1. Create New Job Requisition + Draft
        const createPayload: JobCreatePayload = {
          title: title.trim(),
          department: department.trim() || null,
          location: location.trim() || null,
          employmentType: employmentType as any,
          workplaceType: workplaceType as any,
          openingsCount: openingsCount ? parseInt(openingsCount, 10) : null,
          internalReference: internalReference.trim() || null,
          summary: summary.trim() || null,
          responsibilities: responsibilities.trim() || null,
          jobDescriptionText: jobDescriptionText.trim() || null,
          occupationConceptId: occupationConceptId || null,
        };

        const createdJob = await createJobRequisition(createPayload);
        const newJobId = createdJob.jobId;

        // If requirements exist, save them atomically
        if (requirements.length > 0) {
          const reqPayload = {
            expectedRevision: createdJob.currentVersion.revision,
            requirements: requirements.map((r, idx) => ({
              displayOrder: idx,
              category: r.category,
              label: r.label.trim(),
              taxonomySkillConceptId: r.taxonomySkillConceptId || null,
              necessity: r.necessity,
              priority: r.priority,
              customWeightOverride: r.customWeightOverride ?? null,
              minExperienceMonths: r.minExperienceMonths ?? null,
              recencyYears: r.recencyYears ?? null,
              acceptedEvidenceTypes: r.acceptedEvidenceTypes,
              acceptedEquivalents: r.acceptedEquivalents,
              rationale: r.rationale ? r.rationale.trim() : null,
            })),
          };
          const updatedWithReqs = await saveDraftRequirements(newJobId, reqPayload);
          setJobDetail(updatedWithReqs);
          setCurrentRevision(updatedWithReqs.currentVersion.revision);
        }

        setIsDirty(false);
        setSaveSuccessMsg("Job draft saved successfully.");
        if (onJobCreated) {
          onJobCreated(newJobId);
        }
      } else {
        // 2. Update Existing Job Requisition
        let latestDetail: JobDetail;

        // Step A: Update basic draft details
        const draftPayload: JobDraftUpdatePayload = {
          expectedRevision: currentRevision,
          title: title.trim(),
          department: department.trim() || null,
          location: location.trim() || null,
          employmentType: employmentType as any,
          workplaceType: workplaceType as any,
          openingsCount: openingsCount ? parseInt(openingsCount, 10) : null,
          internalReference: internalReference.trim() || null,
          summary: summary.trim() || null,
          responsibilities: responsibilities.trim() || null,
          jobDescriptionText: jobDescriptionText.trim() || null,
          occupationConceptId: occupationConceptId || null,
        };

        latestDetail = await updateJobDraft(jobId, draftPayload);
        let nextRev = latestDetail.currentVersion.revision;

        // Step B: Atomically save requirements with new expected revision
        const reqPayload = {
          expectedRevision: nextRev,
          requirements: requirements.map((r, idx) => ({
            displayOrder: idx,
            category: r.category,
            label: r.label.trim(),
            taxonomySkillConceptId: r.taxonomySkillConceptId || null,
            necessity: r.necessity,
            priority: r.priority,
            customWeightOverride: r.customWeightOverride ?? null,
            minExperienceMonths: r.minExperienceMonths ?? null,
            recencyYears: r.recencyYears ?? null,
            acceptedEvidenceTypes: r.acceptedEvidenceTypes,
            acceptedEquivalents: r.acceptedEquivalents,
            rationale: r.rationale ? r.rationale.trim() : null,
          })),
        };

        const finalDetail = await saveDraftRequirements(jobId, reqPayload);
        setJobDetail(finalDetail);
        setCurrentRevision(finalDetail.currentVersion.revision);
        setRequirements(finalDetail.currentVersion.requirements || []);
        setIsDirty(false);
        setSaveSuccessMsg("Job draft saved successfully.");
      }
    } catch (err: any) {
      if (err?.code === "REVISION_CONFLICT") {
        setConflictError(
          "Draft revision conflict: Another recruiter or session updated this requisition. Your local edits are preserved below."
        );
      } else {
        setSaveError(err?.message || "Failed to save job draft.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleReloadLatest = async () => {
    if (!jobId) return;
    try {
      setIsLoading(true);
      setConflictError(null);
      setSaveError(null);
      const data = await fetchJobDetail(jobId);
      setJobDetail(data);
      const v = data.currentVersion;
      setTitle(v.title || "");
      setDepartment(v.department || "");
      setLocation(v.location || "");
      setEmploymentType(v.employmentType || "FULL_TIME");
      setWorkplaceType(v.workplaceType || "HYBRID");
      setOpeningsCount(v.openingsCount ? String(v.openingsCount) : "1");
      setInternalReference(v.internalReference || "");
      setSummary(v.summary || "");
      setResponsibilities(v.responsibilities || "");
      setJobDescriptionText(v.jobDescriptionText || "");
      setOccupationConceptId(v.occupationConceptId || null);
      setOccupationTitle(v.occupationTitle || null);
      setCurrentRevision(v.revision || 1);
      setRequirements(v.requirements || []);
      setIsDirty(false);
      setSaveSuccessMsg("Draft reloaded from server.");
    } catch (err: any) {
      setLoadError(err?.message || "Failed to reload draft.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleApplySuggestions = (applied: AppliedSuggestionsPayload) => {
    if (applied.title !== undefined) setTitle(applied.title);
    if (applied.department !== undefined) setDepartment(applied.department);
    if (applied.location !== undefined) setLocation(applied.location);
    if (applied.employmentType !== undefined) setEmploymentType(applied.employmentType);
    if (applied.workplaceType !== undefined) setWorkplaceType(applied.workplaceType);
    if (applied.openingsCount !== undefined) setOpeningsCount(applied.openingsCount);
    if (applied.summary !== undefined) setSummary(applied.summary);
    if (applied.responsibilities && applied.responsibilities.length > 0) {
      const formattedResp = applied.responsibilities.map((r) => `- ${r}`).join("\n");
      setResponsibilities((prev) => (prev ? `${prev}\n${formattedResp}` : formattedResp));
    }
    if (applied.newRequirements && applied.newRequirements.length > 0) {
      setRequirements((prev) => [
        ...prev,
        ...applied.newRequirements.map((r, i) => ({
          ...r,
          displayOrder: prev.length + i,
        })),
      ]);
    }
    setIsDirty(true);
    setSaveSuccessMsg("Imported suggestions applied to editable draft. Click 'Save Draft' to persist changes.");
  };

  const currentFormValues: CurrentFormValues = {
    title,
    department,
    location,
    employmentType,
    workplaceType,
    openingsCount,
    summary,
    responsibilities,
    requirements,
  };

  const handleSafeNavigateBack = () => {
    if (isDirty) {
      if (
        window.confirm("You have unsaved changes in this job draft. Leave without saving?")
      ) {
        onNavigateBack();
      }
    } else {
      onNavigateBack();
    }
  };

  if (isLoading) {
    return (
      <div className="job-editor-loading">
        <div className="loading-spinner" />
        <p className="loading-text">Loading job draft...</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="feedback-box error" style={{ maxWidth: "600px", margin: "40px auto" }}>
        <Icon name="alert-triangle" size={18} />
        <div className="error-content">
          <p className="feedback-text error">{loadError}</p>
          <button type="button" onClick={onNavigateBack} className="btn btn-secondary btn-sm" style={{ marginTop: "10px" }}>
            Back to Jobs
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="job-editor-container">
      {/* Top Action Header */}
      <div className="job-editor-top-bar">
        <div className="top-bar-left">
          <button type="button" onClick={handleSafeNavigateBack} className="btn btn-secondary btn-sm">
            <Icon name="arrow-left" size={14} />
            <span>Jobs Directory</span>
          </button>
          <div>
            <h2 className="editor-heading-title">
              {jobId ? (title || "Job Draft") : "Create New Job Requisition"}
            </h2>
            <div className="editor-status-pills">
              <span className="badge badge-version">v1 (Draft)</span>
              {jobId && <span className="badge badge-revision">Rev #{currentRevision}</span>}
              {isDirty && <span className="badge badge-unsaved">Unsaved Changes</span>}
            </div>
          </div>
        </div>

        <div className="top-bar-right">
          <button
            type="button"
            className="btn btn-secondary btn-md"
            onClick={() => setIsImportModalOpen(true)}
          >
            <Icon name="upload" size={15} />
            <span>Import from job description</span>
          </button>
          <button
            type="button"
            className="btn btn-primary btn-md"
            onClick={handleSave}
            disabled={isSaving}
          >
            <Icon name="check" size={15} />
            <span>{isSaving ? "Saving..." : "Save Draft"}</span>
          </button>
        </div>
      </div>

      {/* Notification Banners */}
      {saveSuccessMsg && (
        <div className="feedback-box success" role="status" aria-live="polite">
          <Icon name="check" size={16} />
          <p className="feedback-text">{saveSuccessMsg}</p>
        </div>
      )}

      {saveError && (
        <div className="feedback-box error" role="alert">
          <Icon name="alert-triangle" size={16} />
          <p className="feedback-text error">{saveError}</p>
        </div>
      )}

      {conflictError && (
        <div className="conflict-alert-card" role="alert">
          <div className="conflict-icon-wrap">
            <Icon name="alert-triangle" size={20} />
          </div>
          <div className="conflict-content">
            <h4 className="conflict-title">Revision Conflict</h4>
            <p className="conflict-desc">{conflictError}</p>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleReloadLatest}
              style={{ marginTop: "8px" }}
            >
              <Icon name="refresh" size={14} />
              <span>Reload Latest Draft from Server</span>
            </button>
          </div>
        </div>
      )}

      {/* Single-Column Progressive Disclosure Form */}
      <div className="job-editor-single-col">
        {/* Section 1: Job details */}
        <section className="job-section-card" aria-labelledby="section-job-details-title">
          <div className="section-card-header">
            <Icon name="building" size={18} className="section-icon" />
            <div>
              <h3 id="section-job-details-title" className="section-title">1. Job details</h3>
              <p className="section-subtitle">Core title, department, and workplace parameters.</p>
            </div>
          </div>

          <div className="form-fields-stack">
            <div className="form-group">
              <label htmlFor="job-title-input" className="form-label">
                Job Title <span className="text-danger">*</span>
              </label>
              <input
                id="job-title-input"
                type="text"
                className="form-input"
                placeholder="e.g. Senior Backend Developer"
                value={title}
                onChange={(e) => {
                  setTitle(e.target.value);
                  setIsDirty(true);
                }}
                required
              />
            </div>

            <div className="form-two-col-grid">
              <div className="form-group">
                <label htmlFor="job-dept-input" className="form-label">Department</label>
                <input
                  id="job-dept-input"
                  type="text"
                  className="form-input"
                  placeholder="e.g. Engineering"
                  value={department}
                  onChange={(e) => {
                    setDepartment(e.target.value);
                    setIsDirty(true);
                  }}
                />
              </div>

              <div className="form-group">
                <label htmlFor="job-loc-input" className="form-label">Location</label>
                <input
                  id="job-loc-input"
                  type="text"
                  className="form-input"
                  placeholder="e.g. San Francisco, CA / Remote"
                  value={location}
                  onChange={(e) => {
                    setLocation(e.target.value);
                    setIsDirty(true);
                  }}
                />
              </div>
            </div>

            <div className="form-three-col-grid">
              <div className="form-group">
                <label htmlFor="job-emp-type" className="form-label">Employment Type</label>
                <select
                  id="job-emp-type"
                  className="form-input"
                  value={employmentType}
                  onChange={(e) => {
                    setEmploymentType(e.target.value);
                    setIsDirty(true);
                  }}
                >
                  <option value="FULL_TIME">Full-Time</option>
                  <option value="PART_TIME">Part-Time</option>
                  <option value="CONTRACT">Contract</option>
                  <option value="INTERNSHIP">Internship</option>
                  <option value="TEMPORARY">Temporary</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="job-work-type" className="form-label">Workplace Type</label>
                <select
                  id="job-work-type"
                  className="form-input"
                  value={workplaceType}
                  onChange={(e) => {
                    setWorkplaceType(e.target.value);
                    setIsDirty(true);
                  }}
                >
                  <option value="HYBRID">Hybrid</option>
                  <option value="ON_SITE">On-Site</option>
                  <option value="REMOTE">Remote</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="job-openings" className="form-label">Openings</label>
                <input
                  id="job-openings"
                  type="number"
                  min={1}
                  max={999}
                  className="form-input"
                  value={openingsCount}
                  onChange={(e) => {
                    setOpeningsCount(e.target.value);
                    setIsDirty(true);
                  }}
                />
              </div>
            </div>

            {/* Collapsed Job Details: More options */}
            <div className="form-disclosure-row">
              <button
                type="button"
                className="btn-disclosure"
                onClick={() => setShowJobDetailsMore(!showJobDetailsMore)}
                aria-expanded={showJobDetailsMore}
              >
                <Icon name={showJobDetailsMore ? "chevron-down" : "chevron-right"} size={13} />
                <span>Additional requisition details (Reference code)</span>
              </button>
            </div>

            {showJobDetailsMore && (
              <div className="form-disclosure-panel">
                <div className="form-group">
                  <label htmlFor="job-ref-input" className="form-label">
                    Internal Reference / Requisition Code
                  </label>
                  <input
                    id="job-ref-input"
                    type="text"
                    className="form-input"
                    placeholder="e.g. REQ-2026-084"
                    value={internalReference}
                    onChange={(e) => {
                      setInternalReference(e.target.value);
                      setIsDirty(true);
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Section 2: About the role */}
        <section className="job-section-card" aria-labelledby="section-about-role-title">
          <div className="section-card-header">
            <Icon name="file-text" size={18} className="section-icon" />
            <div>
              <h3 id="section-about-role-title" className="section-title">2. About the role</h3>
              <p className="section-subtitle">Overview narrative and primary responsibilities.</p>
            </div>
          </div>

          <div className="form-fields-stack">
            <div className="form-group">
              <label htmlFor="job-summary-input" className="form-label">Role Summary</label>
              <textarea
                id="job-summary-input"
                className="form-input form-textarea"
                rows={3}
                placeholder="Brief summary of the role..."
                value={summary}
                onChange={(e) => {
                  setSummary(e.target.value);
                  setIsDirty(true);
                }}
              />
            </div>

            <div className="form-group">
              <label htmlFor="job-resp-input" className="form-label">Responsibilities</label>
              <textarea
                id="job-resp-input"
                className="form-input form-textarea"
                rows={4}
                placeholder="Key duties and day-to-day responsibilities..."
                value={responsibilities}
                onChange={(e) => {
                  setResponsibilities(e.target.value);
                  setIsDirty(true);
                }}
              />
            </div>
          </div>
        </section>

        {/* Optional Collapsed Section: Occupation reference (optional) */}
        <section className="job-section-card" aria-labelledby="section-occupation-title">
          <div
            className="section-card-header section-card-header-toggle"
            onClick={() => setShowOccupationSection(!showOccupationSection)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setShowOccupationSection(!showOccupationSection);
              }
            }}
            aria-expanded={showOccupationSection}
          >
            <div className="section-header-left">
              <Icon name="briefcase" size={18} className="section-icon" />
              <div>
                <h3 id="section-occupation-title" className="section-title">
                  Occupation reference <span className="text-muted font-normal">(optional)</span>
                </h3>
                <p className="section-subtitle">
                  {occupationTitle ? `Selected: ${occupationTitle}` : "Optional standard O*NET occupation reference for advisory skill suggestions."}
                </p>
              </div>
            </div>
            <button
              type="button"
              className="btn-icon-subtle"
              aria-label={showOccupationSection ? "Collapse occupation reference" : "Expand occupation reference"}
            >
              <Icon name={showOccupationSection ? "chevron-down" : "chevron-right"} size={16} />
            </button>
          </div>

          {showOccupationSection && (
            <div className="section-collapsible-content">
              <OccupationSelector
                selectedConceptId={occupationConceptId}
                selectedTitle={occupationTitle}
                onSelectOccupation={handleSelectOccupation}
              />
            </div>
          )}
        </section>

        {/* Section 3: Requirements */}
        <section className="job-section-card" aria-labelledby="section-requirements-title">
          <div className="section-card-header-row">
            <div className="section-header-left">
              <Icon name="badge-check" size={18} className="section-icon" />
              <div>
                <div className="requirements-header-line">
                  <h3 id="section-requirements-title" className="section-title">3. Requirements</h3>
                  <div className="requirements-count-chips">
                    <span className="chip-req-total">
                      {reviewSummary.total} {reviewSummary.total === 1 ? "requirement" : "requirements"}
                    </span>
                    {reviewSummary.mustHaveCount > 0 && (
                      <span className="chip-req-must-have">
                        {reviewSummary.mustHaveCount} required
                      </span>
                    )}
                    {reviewSummary.preferredCount > 0 && (
                      <span className="chip-req-preferred">
                        {reviewSummary.preferredCount} preferred
                      </span>
                    )}
                  </div>
                </div>
                <p className="section-subtitle">
                  Structured skills, experience, and criteria for this role.
                </p>
              </div>
            </div>

            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => handleAddRequirement("SKILL")}
            >
              <Icon name="plus" size={14} />
              <span>Add Requirement</span>
            </button>
          </div>

          {requirements.length === 0 ? (
            <div className="requirements-empty-card">
              <Icon name="badge-check" size={28} className="empty-icon" />
              <h4 className="empty-title">No requirements added yet</h4>
              <p className="empty-desc">
                Add skills, experience, or qualifications for this requisition.
              </p>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => handleAddRequirement("SKILL")}
              >
                <Icon name="plus" size={14} />
                <span>Add Skill Requirement</span>
              </button>
            </div>
          ) : (
            <div className="requirements-list-container">
              {requirements.map((req, idx) => (
                <RequirementCard
                  key={req.requirementId || `req-${idx}`}
                  requirement={req}
                  index={idx}
                  totalCount={requirements.length}
                  onChange={(updated) => handleUpdateRequirement(idx, updated)}
                  onRemove={() => handleRemoveRequirement(idx)}
                  onMoveUp={() => handleMoveRequirement(idx, "up")}
                  onMoveDown={() => handleMoveRequirement(idx, "down")}
                />
              ))}
            </div>
          )}
        </section>

        {/* Section 4: Draft checks & Save */}
        <section className="job-section-card draft-checks-section" aria-labelledby="section-checks-title">
          <div className="section-card-header">
            <Icon name="check" size={18} className="section-icon" />
            <div>
              <h3 id="section-checks-title" className="section-title">4. Draft checks</h3>
              <p className="section-subtitle">Review actionable notes before saving.</p>
            </div>
          </div>

          <div className="draft-checks-container">
            {/* Must-Have Rationale Check (Correctly avoids false-positive on zero must-haves) */}
            {reviewSummary.mustHaveCount === 0 ? (
              <div className="check-item-row neutral">
                <Icon name="info" size={15} className="check-icon neutral" />
                <span className="check-item-text">No required criteria added yet.</span>
              </div>
            ) : reviewSummary.missingRationaleCount > 0 ? (
              <div className="check-item-row warn">
                <Icon name="alert-triangle" size={15} className="check-icon warn" />
                <span className="check-item-text">
                  {reviewSummary.missingRationaleCount} required criterion is missing a reason. (Click &quot;Reason suggested&quot; on the requirement card to add one).
                </span>
              </div>
            ) : (
              <div className="check-item-row pass">
                <Icon name="check" size={15} className="check-icon pass" />
                <span className="check-item-text">All required criteria have a reason.</span>
              </div>
            )}

            {reviewSummary.reviewRequiredCount > 0 && (
              <div className="check-item-row warn">
                <Icon name="info" size={15} className="check-icon warn" />
                <span className="check-item-text">
                  {reviewSummary.reviewRequiredCount} requirement(s) have human review suggestions.
                </span>
              </div>
            )}
          </div>

          {/* Prominent Save Draft Action */}
          <div className="draft-save-action-row">
            <button
              type="button"
              className="btn btn-primary btn-lg save-draft-primary-btn"
              onClick={handleSave}
              disabled={isSaving}
            >
              <Icon name="check" size={18} />
              <span>{isSaving ? "Saving draft..." : "Save Draft Requisition"}</span>
            </button>
          </div>
        </section>
      </div>

      {/* Optional Job Description Import & Review Modal */}
      {isImportModalOpen && (
        <JobDescriptionImportModal
          isOpen={isImportModalOpen}
          onClose={() => setIsImportModalOpen(false)}
          jobId={jobId}
          currentRevision={currentRevision}
          currentFormValues={currentFormValues}
          onApplySuggestions={handleApplySuggestions}
        />
      )}
    </div>
  );
}
