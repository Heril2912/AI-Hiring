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
});
