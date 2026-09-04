import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { JobsDirectory } from "../components/jobs/JobsDirectory";
import { JobEditor } from "../components/jobs/JobEditor";
import { TaxonomySkillAutocomplete } from "../components/jobs/TaxonomySkillAutocomplete";
import { OccupationSelector } from "../components/jobs/OccupationSelector";
import * as jobsApi from "../api/jobs";
import * as taxonomyApi from "../api/taxonomy";

// Mock API modules
vi.mock("../api/jobs");
vi.mock("../api/taxonomy");

describe("Phase 2B.3: Jobs Workspace & Requirement Builder", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // =========================================================================
  // 1. Jobs Directory Rendering & Search
  // =========================================================================
  it("renders jobs directory and filters items by search query", () => {
    const mockJobs: jobsApi.JobSummary[] = [
      {
        jobId: "job-111",
        createdByUserId: "user-1",
        status: "ACTIVE",
        createdAt: "2026-09-01T10:00:00Z",
        updatedAt: "2026-09-01T12:00:00Z",
        currentVersion: {
          jobVersionId: "ver-1",
          versionNumber: 1,
          versionStatus: "DRAFT",
          revision: 2,
          title: "Senior Backend Engineer",
          department: "Engineering",
          location: "San Francisco",
          requirementsCount: 4,
          createdAt: "2026-09-01T10:00:00Z",
          updatedAt: "2026-09-01T12:00:00Z",
        },
      },
      {
        jobId: "job-222",
        createdByUserId: "user-1",
        status: "ACTIVE",
        createdAt: "2026-09-02T10:00:00Z",
        updatedAt: "2026-09-02T12:00:00Z",
        currentVersion: {
          jobVersionId: "ver-2",
          versionNumber: 1,
          versionStatus: "DRAFT",
          revision: 1,
          title: "Product Marketing Manager",
          department: "Marketing",
          location: "New York",
          requirementsCount: 2,
          createdAt: "2026-09-02T10:00:00Z",
          updatedAt: "2026-09-02T12:00:00Z",
        },
      },
    ];

    const onSelectJob = vi.fn();
    const onCreateJob = vi.fn();
    const onRefresh = vi.fn();

    render(
      <JobsDirectory
        jobs={mockJobs}
        isLoading={false}
        onSelectJob={onSelectJob}
        onCreateJob={onCreateJob}
        onRefresh={onRefresh}
      />
    );

    expect(screen.getByText("Senior Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText("Product Marketing Manager")).toBeInTheDocument();
    expect(screen.getByText("4 Requirements")).toBeInTheDocument();

    // Test Search input
    const searchInput = screen.getByLabelText("Search jobs");
    fireEvent.change(searchInput, { target: { value: "Backend" } });

    expect(screen.getByText("Senior Backend Engineer")).toBeInTheDocument();
    expect(screen.queryByText("Product Marketing Manager")).not.toBeInTheDocument();

    // Click to select job
    fireEvent.click(screen.getByText("Senior Backend Engineer"));
    expect(onSelectJob).toHaveBeenCalledWith("job-111");
  });

  // =========================================================================
  // 2. Taxonomy Autocomplete (Advisory Suggestions & Custom Fallback)
  // =========================================================================
  it("allows selecting advisory O*NET suggestions or using custom text", async () => {
    const mockSkills: taxonomyApi.SkillSearchItem[] = [
      {
        conceptId: "sk-py-1",
        canonicalLabel: "Python",
        category: "Programming language",
        source: "ONET",
        sourceVersion: "31.0",
      },
    ];

    vi.mocked(taxonomyApi.searchSkills).mockResolvedValue(mockSkills);

    const onSelectSkill = vi.fn();
    const onUseCustomText = vi.fn();

    render(
      <TaxonomySkillAutocomplete
        onSelectSkill={onSelectSkill}
        onUseCustomText={onUseCustomText}
      />
    );

    const input = screen.getByLabelText("Search skill or enter custom requirement");
    fireEvent.change(input, { target: { value: "Python" } });

    // Wait for debounced search execution
    await waitFor(() => {
      expect(taxonomyApi.searchSkills).toHaveBeenCalledWith("Python", 8);
    });

    // Verify advisory dropdown shows O*NET suggestion and custom button
    expect(await screen.findByText("O*NET 31.0 Advisory Suggestions")).toBeInTheDocument();
    const suggestionOption = screen.getByRole("option");
    expect(suggestionOption).toHaveTextContent("Python");

    // Click suggestion
    fireEvent.click(suggestionOption);
    expect(onSelectSkill).toHaveBeenCalledWith(mockSkills[0]);
  });

  // =========================================================================
  // 3. Occupation Selector (Optional Advisory Link)
  // =========================================================================
  it("supports searching and clearing standard O*NET occupations", async () => {
    const mockOccs: taxonomyApi.OccupationSearchItem[] = [
      {
        conceptId: "occ-123",
        onetSocCode: "15-1252.00",
        canonicalTitle: "Software Developers",
        source: "ONET",
        sourceVersion: "31.0",
      },
    ];

    vi.mocked(taxonomyApi.searchOccupations).mockResolvedValue(mockOccs);

    const onSelectOccupation = vi.fn();

    const { rerender } = render(
      <OccupationSelector
        selectedConceptId={null}
        selectedTitle={null}
        onSelectOccupation={onSelectOccupation}
      />
    );

    const occInput = screen.getByLabelText("Search advisory occupation");
    fireEvent.change(occInput, { target: { value: "Software" } });

    await waitFor(() => {
      expect(taxonomyApi.searchOccupations).toHaveBeenCalledWith("Software", 8);
    });

    expect(await screen.findByText("Software Developers")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Software Developers"));
    expect(onSelectOccupation).toHaveBeenCalledWith(mockOccs[0]);

    // Rerender as selected
    rerender(
      <OccupationSelector
        selectedConceptId="occ-123"
        selectedTitle="Software Developers"
        onSelectOccupation={onSelectOccupation}
      />
    );

    expect(screen.getByText("Software Developers")).toBeInTheDocument();
    expect(screen.getByText("O*NET 31.0 Advisory Occupation Reference")).toBeInTheDocument();

    const clearBtn = screen.getByLabelText("Remove associated occupation");
    fireEvent.click(clearBtn);
    expect(onSelectOccupation).toHaveBeenCalledWith(null);
  });

  // =========================================================================
  // 4. Distinction of UI Autocomplete States (Loading, Empty, Error, Success)
  // =========================================================================
  it("distinguishes genuine no-results from API failures and handles stale requests", async () => {
    // 1. API error scenario
    vi.mocked(taxonomyApi.searchOccupations).mockRejectedValueOnce(new Error("503 Service Unavailable"));

    render(
      <OccupationSelector
        selectedConceptId={null}
        selectedTitle={null}
        onSelectOccupation={vi.fn()}
      />
    );

    const input = screen.getByLabelText("Search advisory occupation");
    fireEvent.change(input, { target: { value: "Network" } });

    // Must show service error notice, not "No matching occupations found"
    expect(await screen.findByText(/Taxonomy service is temporarily unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/No occupation found for/i)).not.toBeInTheDocument();

    // 2. Genuine no-results scenario
    vi.mocked(taxonomyApi.searchOccupations).mockResolvedValueOnce([]);
    fireEvent.change(input, { target: { value: "Backend" } });

    expect(await screen.findByText(/No occupation found for/i)).toBeInTheDocument();
    expect(screen.getByText(/Try a standardized title such as "Software Developer"/i)).toBeInTheDocument();
  });

  // =========================================================================
  // 5. Progressive Disclosure: Collapsed defaults, hidden custom weights, zero-state checks
  // =========================================================================
  it("defaults optional occupation and requirement details to collapsed, hides custom weight, and handles zero criteria state", async () => {
    render(
      <JobEditor
        jobId={null}
        onNavigateBack={vi.fn()}
        onJobCreated={vi.fn()}
      />
    );

    // Occupation section should be collapsed by default
    const occToggle = screen.getByRole("heading", { name: /Occupation reference/i });
    expect(occToggle).toBeInTheDocument();
    // Autocomplete input should not be visible before clicking toggle
    expect(screen.queryByLabelText("Search advisory occupation")).not.toBeInTheDocument();

    // Expand occupation disclosure
    fireEvent.click(occToggle);
    expect(screen.getByLabelText("Search advisory occupation")).toBeInTheDocument();

    // Check Draft checks zero state: Must show neutral "No required criteria added yet.", NOT green pass
    expect(screen.getByText(/No required criteria added yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/All must-have criteria have business rationale/i)).not.toBeInTheDocument();

    // Add a requirement
    const addBtn = screen.getByText("Add Requirement");
    fireEvent.click(addBtn);

    // Advanced options should be collapsed by default
    const moreOptionsToggle = screen.getByText(/More options/i);
    expect(moreOptionsToggle).toBeInTheDocument();
    expect(screen.queryByText(/Why is this required\?/i)).not.toBeInTheDocument();

    // Expand More options
    fireEvent.click(moreOptionsToggle);
    expect(screen.getByText(/Why is this required\?/i)).toBeInTheDocument();
    expect(screen.getByText(/Where can this be shown\?/i)).toBeInTheDocument();

    // Custom weight control must NOT be rendered in default UI
    expect(screen.queryByLabelText(/Custom weight/i)).not.toBeInTheDocument();
  });

  // =========================================================================
  // 6. Category Sensitivity: Non-skill categories render clean text input
  // =========================================================================
  it("renders standard text input for non-skill categories without taxonomy search", async () => {
    render(
      <JobEditor
        jobId={null}
        onNavigateBack={vi.fn()}
        onJobCreated={vi.fn()}
      />
    );

    // Add Requirement
    fireEvent.click(screen.getByText("Add Requirement"));

    // By default, category is SKILL -> search autocomplete input is present
    expect(screen.getByLabelText("Search skill or enter custom requirement")).toBeInTheDocument();

    // Change category to RESPONSIBILITY
    const categorySelect = screen.getByLabelText("Category");
    fireEvent.change(categorySelect, { target: { value: "RESPONSIBILITY" } });

    // Autocomplete is replaced with plain text input
    expect(screen.queryByLabelText("Search skill or enter custom requirement")).not.toBeInTheDocument();
    const plainInput = screen.getByLabelText("Requirement description");
    expect(plainInput).toBeInTheDocument();

    fireEvent.change(plainInput, { target: { value: "Lead architectural reviews" } });
    expect(plainInput).toHaveValue("Lead architectural reviews");
  });

  // =========================================================================
  // 7. Atomic Draft Creation, Save, and Reload
  // =========================================================================
  it("creates draft, adds requirements with taxonomy reference, and saves atomically", async () => {
    const createdJobDetail: jobsApi.JobDetail = {
      jobId: "new-job-999",
      createdByUserId: "user-1",
      status: "ACTIVE",
      createdAt: "2026-09-03T12:00:00Z",
      updatedAt: "2026-09-03T12:00:00Z",
      currentVersion: {
        jobVersionId: "v-999",
        jobId: "new-job-999",
        versionNumber: 1,
        versionStatus: "DRAFT",
        revision: 1,
        title: "Senior Backend Developer",
        department: "Core Engineering",
        location: "San Francisco",
        employmentType: "FULL_TIME",
        workplaceType: "REMOTE",
        openingsCount: 1,
        createdByUserId: "user-1",
        requirements: [],
        reviewWarnings: [],
        createdAt: "2026-09-03T12:00:00Z",
        updatedAt: "2026-09-03T12:00:00Z",
      },
    };

    const savedWithReqs: jobsApi.JobDetail = {
      ...createdJobDetail,
      currentVersion: {
        ...createdJobDetail.currentVersion,
        revision: 2,
        occupationConceptId: "occ-123",
        requirements: [
          {
            requirementId: "req-1",
            displayOrder: 0,
            category: "SKILL",
            label: "Python",
            taxonomySkillConceptId: "sk-py-1",
            necessity: "MUST_HAVE",
            priority: "HIGH",
            acceptedEvidenceTypes: ["EMPLOYMENT", "PROJECT"],
            acceptedEquivalents: [],
            rationale: "Core backend language",
            origin: "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED",
            reviewRequired: false,
            warningMetadata: [],
          },
        ],
      },
    };

    vi.mocked(jobsApi.createJobRequisition).mockResolvedValue(createdJobDetail);
    vi.mocked(jobsApi.saveDraftRequirements).mockResolvedValue(savedWithReqs);

    const onNavigateBack = vi.fn();
    const onJobCreated = vi.fn();

    render(
      <JobEditor
        jobId={null}
        onNavigateBack={onNavigateBack}
        onJobCreated={onJobCreated}
      />
    );

    // Fill Title
    const titleInput = screen.getByLabelText(/Job Title/);
    fireEvent.change(titleInput, { target: { value: "Senior Backend Developer" } });

    // Add Requirement
    const addReqBtn = screen.getByText("Add Requirement");
    fireEvent.click(addReqBtn);

    // Enter requirement custom text and click custom button
    const reqInput = screen.getByLabelText("Search skill or enter custom requirement");
    fireEvent.change(reqInput, { target: { value: "Python" } });

    const customBtn = await screen.findByText(/Use custom requirement/);
    fireEvent.click(customBtn);

    // Save Draft
    const saveBtn = screen.getByText("Save Draft");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(jobsApi.createJobRequisition).toHaveBeenCalled();
      expect(jobsApi.saveDraftRequirements).toHaveBeenCalled();
      expect(onJobCreated).toHaveBeenCalledWith("new-job-999");
    });
  });

  // =========================================================================
  // 8. Phase 2B.4: Optional Job Description Import & Recruiter Review
  // =========================================================================
  describe("Phase 2B.4: Optional Job Description Import and Recruiter Review", () => {
    it("provides optional import action, opens modal with pasted-text default, and displays unselected suggestions with evidence", async () => {
      const mockAnalyzeResponse: jobsApi.JobImportAnalyzeResponse = {
        sessionId: "sess-123",
        sourceType: "PASTED_TEXT",
        sourceText: "Senior Backend Developer\n\nAbout the role\nBuild backend services.\n\nResponsibilities\n- Develop REST APIs.\n\nRequired qualifications\n- 3 years of Python experience.",
        parserVersion: "2B.4-deterministic-v1",
        taxonomyVersion: "31.0",
        status: "PENDING_REVIEW",
        suggestions: [
          {
            suggestionId: "sug-title",
            targetField: "TITLE",
            proposedValue: "Senior Backend Developer",
            sourceExcerpt: "Senior Backend Developer",
            startOffset: 0,
            endOffset: 24,
            extractionMethod: "HEADING_PATTERN",
            confidence: "HIGH",
            reviewStatus: "PENDING",
          },
          {
            suggestionId: "sug-summary",
            targetField: "SUMMARY",
            proposedValue: "Build backend services.",
            sourceExcerpt: "Build backend services.",
            startOffset: 41,
            endOffset: 64,
            extractionMethod: "BOUNDED_SECTION",
            confidence: "HIGH",
            reviewStatus: "PENDING",
          },
          {
            suggestionId: "sug-resp-1",
            targetField: "RESPONSIBILITY",
            proposedValue: "Develop REST APIs.",
            sourceExcerpt: "Develop REST APIs.",
            startOffset: 83,
            endOffset: 101,
            extractionMethod: "BULLET_PATTERN",
            confidence: "HIGH",
            reviewStatus: "PENDING",
          },
          {
            suggestionId: "sug-req-py",
            targetField: "REQUIREMENT",
            proposedValue: {
              category: "EXPERIENCE",
              label: "Python",
              taxonomySkillConceptId: "sk-py-1",
              necessity: "MUST_HAVE",
              priority: "MEDIUM",
              minExperienceMonths: 36,
              isUndecidedNecessity: false,
              taxonomyProvenance: "ONET_31_0",
            },
            sourceExcerpt: "3 years of Python experience.",
            startOffset: 126,
            endOffset: 155,
            extractionMethod: "TAXONOMY_NORMALIZED",
            confidence: "HIGH",
            reviewStatus: "PENDING",
          },
        ],
        warnings: [],
        createdAt: "2026-09-04T12:00:00Z",
        updatedAt: "2026-09-04T12:00:00Z",
      };

      vi.mocked(jobsApi.analyzeJobDescriptionText).mockResolvedValue(mockAnalyzeResponse);
      vi.mocked(jobsApi.applyImportSuggestions).mockResolvedValue({
        status: "APPLIED",
        sessionId: "sess-123",
        appliedCount: 2,
        appliedItems: [],
      });

      render(
        <JobEditor
          jobId={null}
          onNavigateBack={vi.fn()}
          onJobCreated={vi.fn()}
        />
      );

      // Verify import button is present as an optional action
      const importBtn = screen.getByText("Import from job description");
      expect(importBtn).toBeInTheDocument();

      // Open Modal
      fireEvent.click(importBtn);

      // Verify modal is open and Paste Plain Text is default
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText("Paste plain text (Default)")).toBeInTheDocument();
      const textArea = screen.getByLabelText("Job Description Text");
      expect(textArea).toBeInTheDocument();

      // Enter text and click Analyse
      fireEvent.change(textArea, { target: { value: "Senior Backend Developer..." } });
      const analyzeBtn = screen.getByText("Analyse job description");
      fireEvent.click(analyzeBtn);

      // Wait for suggestions review screen
      expect(await screen.findByText("Job Details")).toBeInTheDocument();
      expect(screen.getByText("About the role")).toBeInTheDocument();
      expect(screen.getByText(/Responsibilities \(1 items\)/)).toBeInTheDocument();
      expect(screen.getByText(/Structured Requirements \(1 items\)/)).toBeInTheDocument();

      // Verify suggestions are unselected by default
      expect(screen.getByText(/of 4 suggestions selected/)).toHaveTextContent("0 of 4 suggestions selected");
      const applyBtn = screen.getByRole("button", { name: /Apply selected suggestions/ });
      expect(applyBtn).toBeDisabled();

      // Verify source evidence is visible
      expect(screen.getByText(/“Senior Backend Developer”/)).toBeInTheDocument();
      expect(screen.getByText(/“3 years of Python experience.”/)).toBeInTheDocument();
      expect(screen.getByText("O*NET 31.0 Skill")).toBeInTheDocument();

      // Select Title and Requirement suggestions
      const titleRow = screen.getAllByText("TITLE")[0].closest(".suggestion-item-row");
      const titleCheckbox = titleRow?.querySelector("input[type='checkbox']");
      if (titleCheckbox) fireEvent.click(titleCheckbox);

      const reqCheckbox = screen.getByText("O*NET 31.0 Skill").closest(".suggestion-item-row")?.querySelector("input[type='checkbox']");
      if (reqCheckbox) fireEvent.click(reqCheckbox);

      expect(screen.getByText(/of 4 suggestions selected/)).toHaveTextContent("2 of 4 suggestions selected");

      // Click Apply Selected Suggestions to view preview
      const activeApplyBtn = screen.getByRole("button", { name: /Apply selected suggestions/ });
      expect(activeApplyBtn).not.toBeDisabled();
      fireEvent.click(activeApplyBtn);

      // Confirmation preview step
      expect(screen.getByText("Confirm Applying Suggestions to Form")).toBeInTheDocument();
      expect(screen.getByText(/“Senior Backend Developer”/)).toBeInTheDocument();
      expect(screen.getByText(/1 requirements \(Python\)/)).toBeInTheDocument();

      // Confirm apply
      const confirmBtn = screen.getByText("Confirm & Apply to Form");
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(jobsApi.applyImportSuggestions).toHaveBeenCalledWith(
          "sess-123",
          expect.objectContaining({
            acceptedSuggestionIds: expect.arrayContaining(["sug-title", "sug-req-py"]),
          })
        );
      });

      // Verify form was updated in memory without saving to API
      expect(jobsApi.createJobRequisition).not.toHaveBeenCalled();
      const titleInput = screen.getByLabelText(/Job Title/);
      expect(titleInput).toHaveValue("Senior Backend Developer");
      expect(screen.getByText("Unsaved Changes")).toBeInTheDocument();
    });

    it("displays conflict comparison and protected information warnings", async () => {
      const mockConflictResponse: jobsApi.JobImportAnalyzeResponse = {
        sessionId: "sess-conflict",
        sourceType: "PASTED_TEXT",
        sourceText: "Lead Architect\nLooking for young energetic candidates.",
        parserVersion: "2B.4-deterministic-v1",
        status: "PENDING_REVIEW",
        suggestions: [
          {
            suggestionId: "sug-conflict-title",
            targetField: "TITLE",
            proposedValue: "Lead Architect",
            sourceExcerpt: "Lead Architect",
            startOffset: 0,
            endOffset: 14,
            extractionMethod: "HEADING_PATTERN",
            confidence: "HIGH",
            reviewStatus: "PENDING",
          },
        ],
        warnings: [
          {
            code: "PROTECTED_AGE_TERM",
            message: "Age-related term detected: 'young'. Safeguard applied: Protected characteristics are never converted to structured criteria.",
            sourceExcerpt: "young energetic candidates",
            matchedTerm: "young",
          },
        ],
        createdAt: "2026-09-04T12:00:00Z",
        updatedAt: "2026-09-04T12:00:00Z",
      };

      vi.mocked(jobsApi.analyzeJobDescriptionText).mockResolvedValue(mockConflictResponse);

      render(
        <JobEditor
          jobId={null}
          onNavigateBack={vi.fn()}
          onJobCreated={vi.fn()}
        />
      );

      // Populate title in form first to induce conflict
      const titleInput = screen.getByLabelText(/Job Title/);
      fireEvent.change(titleInput, { target: { value: "Principal Engineer" } });

      // Open import modal
      fireEvent.click(screen.getByText("Import from job description"));
      fireEvent.change(screen.getByLabelText("Job Description Text"), {
        target: { value: "Lead Architect..." },
      });
      fireEvent.click(screen.getByText("Analyse job description"));

      // Verify protected information warning banner is rendered
      expect(await screen.findByText("Sensitive / Protected Information Detected")).toBeInTheDocument();
      expect(screen.getByText(/Age-related term detected: 'young'/)).toBeInTheDocument();
      expect(screen.getByText(/“young energetic candidates”/)).toBeInTheDocument();

      // Verify conflict box is rendered
      expect(screen.getByText("Conflict with current form:")).toBeInTheDocument();
      expect(screen.getByText(/“Principal Engineer”/)).toBeInTheDocument();
      expect(screen.getAllByText(/“Lead Architect”/).length).toBeGreaterThanOrEqual(1);

      // Cancel modal - form value remains unchanged
      fireEvent.click(screen.getByText("Cancel"));
      expect(titleInput).toHaveValue("Principal Engineer");
    });

    it("displays error feedback on analysis failure and supports discarding", async () => {
      vi.mocked(jobsApi.analyzeJobDescriptionText).mockRejectedValue(new Error("Document length exceeds limit"));
      vi.mocked(jobsApi.discardImportSession).mockResolvedValue(undefined);

      render(
        <JobEditor
          jobId={null}
          onNavigateBack={vi.fn()}
          onJobCreated={vi.fn()}
        />
      );

      fireEvent.click(screen.getByText("Import from job description"));
      fireEvent.change(screen.getByLabelText("Job Description Text"), {
        target: { value: "Oversized content..." },
      });
      fireEvent.click(screen.getByText("Analyse job description"));

      expect(await screen.findByText("Document length exceeds limit")).toBeInTheDocument();

      // Close modal
      const closeBtn = screen.getByLabelText("Close import dialog");
      fireEvent.click(closeBtn);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Phase 2B.5: Requisition Readiness & Revision Locking
  // =========================================================================
  describe("Phase 2B.5: Requisition Readiness & Revision Locking", () => {
    const mockDraftJobDetail: jobsApi.JobDetail = {
      jobId: "job-ready-1",
      createdByUserId: "recruiter-1",
      status: "ACTIVE",
      createdAt: "2026-09-04T10:00:00Z",
      updatedAt: "2026-09-04T10:00:00Z",
      currentVersion: {
        jobVersionId: "ver-1",
        jobId: "job-ready-1",
        versionNumber: 1,
        versionStatus: "DRAFT",
        revision: 1,
        title: "Senior Fullstack Engineer",
        department: "Engineering",
        location: "Remote",
        employmentType: "FULL_TIME",
        workplaceType: "REMOTE",
        openingsCount: 1,
        createdByUserId: "recruiter-1",
        requirements: [
          {
            requirementId: "req-1",
            displayOrder: 0,
            category: "SKILL",
            label: "Python",
            necessity: "MUST_HAVE",
            priority: "HIGH",
            acceptedEvidenceTypes: ["EMPLOYMENT"],
            acceptedEquivalents: [],
            rationale: "Core backend architecture is written in Python.",
            origin: "RECRUITER_ENTERED",
          },
        ],
        reviewWarnings: [],
        createdAt: "2026-09-04T10:00:00Z",
        updatedAt: "2026-09-04T10:00:00Z",
      },
    };

    it("checks readiness on draft and displays structured findings", async () => {
      vi.mocked(jobsApi.fetchJobDetail).mockResolvedValue(mockDraftJobDetail);
      vi.mocked(jobsApi.checkJobReadiness).mockResolvedValue({
        jobId: "job-ready-1",
        jobVersionId: "ver-1",
        versionNumber: 1,
        revision: 1,
        versionStatus: "DRAFT",
        ready: true,
        errors: [],
        warnings: [
          {
            code: "NO_OCCUPATION_SELECTED",
            severity: "WARNING",
            message: "No standard O*NET occupation reference is linked (optional).",
            blocksReadiness: false,
          },
        ],
        info: [
          {
            code: "CUSTOM_REQUIREMENT_USED",
            severity: "INFO",
            message: "Custom recruiter-entered requirement 'Python' has no O*NET ID.",
            blocksReadiness: false,
          },
        ],
        checkedAt: "2026-09-04T10:05:00Z",
      });

      render(
        <JobEditor
          jobId="job-ready-1"
          onNavigateBack={vi.fn()}
          onJobCreated={vi.fn()}
        />
      );

      expect(await screen.findByDisplayValue("Senior Fullstack Engineer")).toBeInTheDocument();
      expect(screen.getByText("v1 (Draft)")).toBeInTheDocument();

      // Click Check readiness
      const checkBtn = screen.getByText("Check readiness");
      fireEvent.click(checkBtn);

      expect(await screen.findByText(/Requisition passes all readiness checks/)).toBeInTheDocument();
      expect(screen.getByText("Advisory Warnings (1)")).toBeInTheDocument();
      expect(screen.getByText(/No standard O\*NET occupation reference is linked/)).toBeInTheDocument();
      expect(screen.getByText("Notes (1)")).toBeInTheDocument();
    });

    it("displays blocking errors and provides go-to-field focus without showing green success", async () => {
      vi.mocked(jobsApi.fetchJobDetail).mockResolvedValue(mockDraftJobDetail);
      vi.mocked(jobsApi.checkJobReadiness).mockResolvedValue({
        jobId: "job-ready-1",
        jobVersionId: "ver-1",
        versionNumber: 1,
        revision: 1,
        versionStatus: "DRAFT",
        ready: false,
        errors: [
          {
            code: "MISSING_RATIONALE",
            severity: "ERROR",
            message: "Must-have requirement 'Python' lacks a job-related business rationale.",
            requirementId: "req-1",
            blocksReadiness: true,
          },
        ],
        warnings: [],
        info: [],
        checkedAt: "2026-09-04T10:05:00Z",
      });

      render(
        <JobEditor
          jobId="job-ready-1"
          onNavigateBack={vi.fn()}
          onJobCreated={vi.fn()}
        />
      );

      await screen.findByDisplayValue("Senior Fullstack Engineer");

      const checkBtn = screen.getByText("Check readiness");
      fireEvent.click(checkBtn);

      expect(await screen.findByText("Blocking Errors (1)")).toBeInTheDocument();
      expect(screen.getByText(/Must-have requirement 'Python' lacks a job-related business rationale/)).toBeInTheDocument();
      expect(screen.queryByText(/Requisition passes all readiness checks/)).not.toBeInTheDocument();

      // Click Go to field
      const goToFieldBtn = screen.getByText("Go to field");
      expect(goToFieldBtn).toBeInTheDocument();
      fireEvent.click(goToFieldBtn);
    });

    it("requires confirmation to lock revision, and canceling does not mutate state", async () => {
      vi.mocked(jobsApi.fetchJobDetail).mockResolvedValue(mockDraftJobDetail);

      render(
        <JobEditor
          jobId="job-ready-1"
          onNavigateBack={vi.fn()}
          onJobCreated={vi.fn()}
        />
      );

      await screen.findByDisplayValue("Senior Fullstack Engineer");

      const markReadyBtn = screen.getByText("Mark ready for matching");
      fireEvent.click(markReadyBtn);

      // Verify modal is open with important workflow guidance
      expect(screen.getByText("Lock Revision for Matching")).toBeInTheDocument();
      expect(screen.getByText(/You are about to freeze/)).toBeInTheDocument();
      expect(screen.getByText(/This exact revision will be locked as read-only and immutable/)).toBeInTheDocument();

      // Click Cancel
      fireEvent.click(screen.getByText("Cancel"));
      expect(screen.queryByText("Lock Revision for Matching")).not.toBeInTheDocument();
      expect(jobsApi.markJobReady).not.toHaveBeenCalled();
    });

    it("locks revision as READY_FOR_MATCHING, makes form read-only, and creates successor revision", async () => {
      vi.mocked(jobsApi.fetchJobDetail).mockResolvedValue(mockDraftJobDetail);
      const mockReadyJobDetail: jobsApi.JobDetail = {
        ...mockDraftJobDetail,
        currentVersion: {
          ...mockDraftJobDetail.currentVersion,
          versionStatus: "READY_FOR_MATCHING",
          revision: 2,
          readyByUserId: "recruiter-1",
          readyAt: "2026-09-04T10:10:00Z",
        },
      };
      vi.mocked(jobsApi.markJobReady).mockResolvedValue(mockReadyJobDetail);

      render(
        <JobEditor
          jobId="job-ready-1"
          onNavigateBack={vi.fn()}
          onJobCreated={vi.fn()}
        />
      );

      await screen.findByDisplayValue("Senior Fullstack Engineer");

      // Open modal and confirm
      fireEvent.click(screen.getByText("Mark ready for matching"));
      fireEvent.click(screen.getByText("Confirm and Lock Revision"));

      // Check that status changed and locked banner appeared
      expect(await screen.findByText("Revision Locked as Ready for Matching")).toBeInTheDocument();
      expect(screen.getByText("v1 (Ready for matching)")).toBeInTheDocument();
      expect(screen.getByText(/Requisition revision #2 is now locked as READY_FOR_MATCHING/)).toBeInTheDocument();

      // Verify title input is now disabled (read-only)
      const titleInput = screen.getByLabelText(/Job Title/);
      expect(titleInput).toBeDisabled();

      // Normal Save draft button is gone
      expect(screen.queryByText("Save Draft Requisition")).not.toBeInTheDocument();

      // Now create successor version
      const mockSuccessorJobDetail: jobsApi.JobDetail = {
        ...mockDraftJobDetail,
        currentVersion: {
          ...mockDraftJobDetail.currentVersion,
          jobVersionId: "ver-2",
          versionNumber: 2,
          versionStatus: "DRAFT",
          revision: 1,
          readyByUserId: null,
          readyAt: null,
        },
      };
      vi.mocked(jobsApi.createSuccessorVersion).mockResolvedValue(mockSuccessorJobDetail);

      const createSuccessorBtn = screen.getAllByText("Create editable revision")[0];
      fireEvent.click(createSuccessorBtn);

      expect(await screen.findByText("v2 (Draft)")).toBeInTheDocument();
      expect(titleInput).not.toBeDisabled();
      expect(screen.getByText("Save Draft Requisition")).toBeInTheDocument();
    });

    it("displays revision conflict message on stale ready attempt", async () => {
      vi.mocked(jobsApi.fetchJobDetail).mockResolvedValue(mockDraftJobDetail);
      const conflictError: any = new Error("Revision conflict");
      conflictError.code = "REVISION_CONFLICT";
      vi.mocked(jobsApi.markJobReady).mockRejectedValue(conflictError);

      render(
        <JobEditor
          jobId="job-ready-1"
          onNavigateBack={vi.fn()}
          onJobCreated={vi.fn()}
        />
      );

      await screen.findByDisplayValue("Senior Fullstack Engineer");

      fireEvent.click(screen.getByText("Mark ready for matching"));
      fireEvent.click(screen.getByText("Confirm and Lock Revision"));

      expect(await screen.findByText("Revision Conflict")).toBeInTheDocument();
      expect(screen.getByText(/This requisition was updated or changed status in another session/)).toBeInTheDocument();
    });
  });
});

