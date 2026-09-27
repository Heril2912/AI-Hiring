# AI-Hiring Platform: System Architecture & Technical Blueprint

**Document Version:** 2.0.0 (Phase 1 through Phase 4B.5)  
**System Classification:** Enterprise AI-Assisted Candidate Sourcing, Deterministic Matching, Audited Resumé Ingestion, AI Question Studio & Interactive Practice Simulation Platform  
**Target Runtime:** Python 3.14 (FastAPI + SQLAlchemy 2.0 Async/Sync + PostgreSQL 16) | React 19 + TypeScript 5.5+ (Vite + Vanilla CSS Glassmorphic Design System) | Local MLX/Ollama/OpenAI-compatible Inference

---

## 1. Executive Summary & Core Architectural Philosophy

The **AI-Hiring Platform** is a dual-portal enterprise recruiting and evaluation system engineered to bridge recruiter workflow efficiency with candidate transparency. Unlike legacy Applicant Tracking Systems (ATS) and opaque "black-box" generative AI screeners, this platform enforces a strict separation between **auditable deterministic business logic** and **governed AI assistance**:

```
+---------------------------------------------------------------------------------------------------+
|                                  AI-HIRING PLATFORM ARCHITECTURE                                 |
+--------------------------------------------------+------------------------------------------------+
|          1. DETERMINISTIC CORE ENGINE             |          2. GROUNDED AI ASSISTANCE            |
+--------------------------------------------------+------------------------------------------------+
| * Exact Bounding-Box Evidence Spans (PDF/DOCX)   | * Requisition-Grounded Question Generation     |
| * Multi-Version Taxonomy Graph Normalization     | * 20-Point Server-Side Validation Matrix       |
| * Transparent Mathematical Scoring Equations     | * Zero-Leakage Candidate Simulation Sandbox    |
| * Immutable Job & Profile Revision Histories     | * Real-Time Adaptive Turn-Taking (Follow-ups)  |
| * Cryptographic Tenant Isolation & RBAC (Admin,  | * Multi-Dimensional Radar Coaching Analytics   |
|   Recruiter, Candidate)                          | * Strict Provenance & Model Audit Logging      |
+--------------------------------------------------+------------------------------------------------+
```

### Architectural Tenets
1. **Evidence-Based Grounding**: Resumé parsing must persist character-level and bounding-box evidence spans (`start_offset`, `end_offset`, `section`, `bbox`). No candidate profile assertion is accepted without audit proof in the source document.
2. **Deterministic, Explainable Matching**: Job match scores are calculated strictly via transparent category-weighted mathematical formulas. The system produces exact missing-skill gap breakdowns, never vague LLM approximations.
3. **20-Point Server-Side AI Guardrails**: AI-generated interview items (conversational and MCQ) must pass 20 automated checks (character lengths, injection prevention, protected attribute filters, hallucination traps, MCQ structure) before becoming eligible for recruiter approval or candidate release.
4. **Zero-Leakage Candidate Privacy**: Candidate-facing endpoints strip all internal calibration rubrics, target answers, and recruiter evaluation thresholds. Candidates receive diagnostic practice feedback without exposing hiring criteria.
5. **Complete Auditability & Provenance**: Every AI action logs `model_identifier`, `provider_class`, `prompt_template_version`, `guardrail_policy_version`, and user timestamps.

---

## 2. Complete Project Directory Tree

Below is the exhaustive file and directory map for the entire repository:

```
AI-Hiring/
├── compose.yaml                                 # Docker Compose configuration for PostgreSQL 16 database service
├── postgres.md                                  # PostgreSQL setup, connection strings, credentials & operational notes
├── AI_INTERVIEWS_UI_REFERENCE.md                # Phase 3G / Phase 4 AI Interview Studio UI specifications
├── HUMAN_LABELLING_PROTOCOL.md                  # Ground-truth evaluation protocol for parser benchmarking
├── THIRD_PARTY_DATA_NOTICES.md                  # Licensing and third-party notices for taxonomy datasets
├── Local_data/                                  # Seed datasets for occupational taxonomy & skill graph
│   ├── job_titles.csv                           # O*NET standardized job titles and concept identifiers
│   ├── occupation_data.csv                      # Occupation hierarchy, codes, and family categories
│   └── software_skills.csv                      # Software skills, tools, frameworks, and aliases
├── local_ats_demo/                              # Standalone demo ATS folder for local file-based ATS integration
│   ├── README.txt                               # Instructions for local folder ATS inbox/outbox syncing
│   └── inbox/                                   # Sample test resumes in PDF and DOCX formats
│       ├── Candidate_A_Alex_Morgan.docx
│       ├── Candidate_B_Priya_Shah.pdf
│       ├── Candidate_C_Daniel_Lee.docx
│       ├── Phase_1E2_Integrity_Table_Reordered_Resume.docx
│       ├── Phase_1E2_Integrity_Two_Column_Resume.pdf
│       ├── resume_test_A_table_reordered.docx
│       └── resume_test_B_two_column.pdf
├── docs/                                        # Master Platform Documentation Suite
│   ├── SYSTEM_ARCHITECTURE_BLUEPRINT.md         # [This File] Master architectural blueprint & file catalog
│   ├── BACKEND_SERVICES_AND_API_REFERENCE.md    # Detailed backend routers, models, schemas, services & tests
│   └── FRONTEND_UI_AND_USER_JOURNEYS.md         # Detailed frontend components, state, user journeys & tests
├── backend/                                     # Backend Application (Python 3.14, FastAPI, SQLAlchemy, Alembic)
│   ├── alembic.ini                              # Alembic database migration configuration
│   ├── pytest.ini                               # Pytest execution configuration, markers, and async settings
│   ├── requirements.txt                         # Python dependencies (FastAPI, SQLAlchemy, psycopg2, pdfplumber, etc.)
│   ├── app/                                     # Backend Application Package
│   │   ├── __init__.py                          # Package initialization
│   │   ├── config.py                            # Pydantic Settings (DB URL, Auth secrets, AI provider configs)
│   │   ├── database.py                          # SQLAlchemy engine, session maker, base model, and DB lifecycle
│   │   ├── main.py                              # FastAPI app assembly, CORS, CSRF middleware, router registration
│   │   ├── api/                                 # REST API Routers & Endpoint Controllers
│   │   │   ├── __init__.py
│   │   │   ├── admin.py                         # System health, taxonomy import, audit log queries
│   │   │   ├── admin_providers.py               # AI Model provider registration, health tests, provider switching
│   │   │   ├── ai_interviews.py                 # AI Interview generation, question selection, slot management
│   │   │   ├── ai_question_sets.py              # AI Question Studio, 20-point validation, recruiter approval
│   │   │   ├── ats.py                           # ATS integration (Greenhouse, Lever, Local Folder import/export)
│   │   │   ├── auth.py                          # Recruiter/Admin authentication, login, logout, password change
│   │   │   ├── candidate_access.py              # Candidate invitations, token generation, magic activation
│   │   │   ├── candidate_auth.py                # Candidate portal authentication, session verification, me endpoint
│   │   │   ├── candidate_jobs.py                # Candidate public/published job requisition catalog & detail
│   │   │   ├── candidate_practice.py            # Recruiter release management & candidate practice session endpoints
│   │   │   ├── candidates.py                    # Resumé upload, parsing, profile review, evidence span queries
│   │   │   ├── dependencies.py                  # FastAPI auth guards (`require_recruiter`, `require_candidate`, etc.)
│   │   │   ├── gap_reports.py                   # Requirement gap analysis and missing skill report endpoints
│   │   │   ├── health.py                        # Liveness, readiness, and DB connection health checks
│   │   │   ├── interviews.py                    # Legacy deterministic interview templates and scoring
│   │   │   ├── jobs.py                          # Job requisition CRUD, immutable versioning, readiness checks
│   │   │   ├── match_runs.py                    # Deterministic candidate-job matching execution & results
│   │   │   ├── recruiter_applications.py        # Recruiter applicant review workflow & state transitions
│   │   │   └── taxonomy.py                      # Skill taxonomy search, occupation concept resolution
│   │   ├── cli/                                 # Command-Line Utilities & Data Seeders
│   │   │   ├── __init__.py
│   │   │   └── seed_defaults.py                 # CLI seed script for default organization, admin user, and taxonomy
│   │   ├── models/                              # SQLAlchemy 2.0 Declarative Relational Models
│   │   │   ├── __init__.py
│   │   │   ├── ai_interview.py                  # AI Question Sets, AI Generated Items, Interview Rubrics
│   │   │   ├── ats.py                           # ATS Connection settings, sync jobs, external entity mappings
│   │   │   ├── audit.py                         # Security Audit Events and operational transaction logs
│   │   │   ├── candidate.py                     # Candidate Identities, Candidate Profiles, Evidence Spans
│   │   │   ├── candidate_access.py              # Candidate Account Bindings, Magic Invitations, Reset Tokens
│   │   │   ├── candidate_application.py         # Candidate Job Applications & Resume Artifact links
│   │   │   ├── candidate_practice.py            # Practice Releases, Practice Sessions, Answers, Coaching Reports
│   │   │   ├── gap_report.py                    # Gap Reports, Gap Items, and Category Summary records
│   │   │   ├── interview.py                     # Deterministic Interview Templates, Simulation & Review tables
│   │   │   ├── job.py                           # Job Requisitions, Job Versions, Grounded Requirements
│   │   │   ├── match_run.py                     # Match Runs, Candidate Match Results, Component Scores
│   │   │   ├── model_provider.py                # AI Model Providers, Adapter Configurations, Health States
│   │   │   ├── taxonomy.py                      # Skill Concepts, Skill Aliases, Occupations, Taxonomies
│   │   │   └── user.py                          # Organizations, Users, User Sessions, Password Reset Tokens
│   │   ├── schemas/                             # Pydantic v2 Request/Response Data Transfer Objects (DTOs)
│   │   │   ├── __init__.py
│   │   │   ├── admin_provider.py                # Model provider creation, configuration, test schemas
│   │   │   ├── ai_interview.py                  # AI Interview workspace DTOs, items, and response payloads
│   │   │   ├── ai_question_set.py               # AI Question set authoring, 20-point validation, approval DTOs
│   │   │   ├── ats.py                           # ATS connection payloads, sync status, import/export DTOs
│   │   │   ├── auth.py                          # Login, session, token, and user profile schemas
│   │   │   ├── candidate.py                     # Candidate profile, evidence span, and extraction DTOs
│   │   │   ├── candidate_access.py              # Invitation creation, account activation, credential setup
│   │   │   ├── candidate_application.py         # Application draft creation, resume submission, status DTOs
│   │   │   ├── candidate_job.py                 # Public job listing and requirement summaries for candidates
│   │   │   ├── candidate_practice.py            # Practice release, session turn-taking, answer, report schemas
│   │   │   ├── gap_report.py                    # Requirement gap request, filter, and report breakdown DTOs
│   │   │   ├── interview.py                     # Deterministic interview template, simulation, rubric schemas
│   │   │   ├── job.py                           # Job requisition, version, requirement, and readiness DTOs
│   │   │   ├── match_run.py                     # Match run creation, ranked score breakdowns, comparison DTOs
│   │   │   ├── recruiter_application.py         # Recruiter applicant list, review stage transition schemas
│   │   │   ├── taxonomy.py                      # Skill concept autocomplete and search result DTOs
│   │   │   └── user.py                          # User account creation, organization profile schemas
│   │   └── services/                            # Domain Services, Business Rules & Extraction Engines (63 Services)
│   │       ├── __init__.py
│   │       ├── admin_provider_service.py        # Local AI provider registry management & connectivity tests
│   │       ├── ai_interview_generation_service.py # LLM prompt building for question generation
│   │       ├── ai_interview_orchestrator.py     # Orchestrates question set creation from job requirements
│   │       ├── ai_interview_persistence_service.py # Database persistence for AI interview question sets
│   │       ├── ai_interview_question_selector.py # Selects and ranks generated questions for requisition slots
│   │       ├── ai_provenance_service.py         # 20-point server-side validation matrix & release eligibility
│   │       ├── ai_question_set_service.py       # Manages lifecycle (draft/approved) of AI question sets
│   │       ├── ai_wording_service.py            # AI-assisted question rewording and refinement
│   │       ├── ats_integration_service.py       # Greenhouse, Lever, and Local Folder ATS adapters
│   │       ├── audit_service.py                 # Structured security audit event emission and recording
│   │       ├── auth_service.py                  # Password hashing, session token creation, cookie management
│   │       ├── candidate_access_service.py      # Magic invitation token generation and candidate activation
│   │       ├── candidate_application_service.py # Manages candidate job applications & resume attachments
│   │       ├── candidate_job_service.py         # Retrieves published requisitions for candidate discovery
│   │       ├── candidate_practice_service.py    # Recruiter practice release authorization & catalog queries
│   │       ├── corpus_integrity.py              # Validates parsed document integrity against raw text
│   │       ├── deterministic_generator.py       # Rule-based interview template generation from taxonomy
│   │       ├── deterministic_matching.py        # Core category-weighted candidate-job matching algorithm
│   │       ├── docx_text_extraction.py          # Microsoft Word DOCX parser with paragraph/table span detection
│   │       ├── docx_validation.py               # Validates DOCX structure, MIME types, and file safety
│   │       ├── education_project_certification_extraction.py # Extracts degrees, institutions, projects, certs
│   │       ├── employment_extraction.py         # Extracts work history, employer names, job titles, date spans
│   │       ├── evaluation.py                    # Benchmarks parser precision/recall against ground-truth labels
│   │       ├── explanation.py                   # Generates human-readable explanations for match scores
│   │       ├── extraction_orchestration.py      # Master pipeline running text extraction, spans, & profile assembly
│   │       ├── extraction_persistence.py        # Persists parsed candidate profiles and evidence spans
│   │       ├── gap_derivation.py                # Compares job requirements against candidate skills to find gaps
│   │       ├── gap_report_service.py            # Compiles structured gap reports with categorical grouping
│   │       ├── gap_validation.py                # Validates consistency of requirement gap breakdowns
│   │       ├── human_review_service.py          # Handles recruiter overrides and human-in-the-loop review
│   │       ├── identity_extraction.py           # Extracts candidate name, email, phone, location from resume
│   │       ├── interview_catalogue.py           # Catalog of pre-approved deterministic interview questions
│   │       ├── interview_generator_service.py   # Generates structured interview question banks
│   │       ├── interview_lifecycle_service.py   # Manages interview template statuses (draft, published, archived)
│   │       ├── interview_segmentation_service.py # Segregates interview questions into technical/behavioral blocks
│   │       ├── interview_simulation_service.py  # Simulates interview responses for pre-release calibration
│   │       ├── interview_snapshot_service.py    # Creates immutable point-in-time snapshots of question sets
│   │       ├── job_description_parser.py        # Parses raw job descriptions into structured requirements
│   │       ├── job_document_extraction.py       # Extracts text from uploaded job description PDF/Word files
│   │       ├── job_lifecycle.py                 # Manages job requisition states (draft, ready, published, archived)
│   │       ├── job_readiness.py                 # Validates job requisition completeness before matching
│   │       ├── live_interview_service.py        # Orchestrates real-time live interview sessions
│   │       ├── match_orchestration.py           # Manages bulk match execution across multiple candidates
│   │       ├── matching_preflight.py            # Preflight validation ensuring jobs and candidates are matchable
│   │       ├── mcq_validation_service.py        # Validates Multiple-Choice Question options, keys, & explanations
│   │       ├── pdf_layout_extraction.py         # Multi-column and table layout detector for PDF resumes
│   │       ├── pdf_text_extraction.py           # PDFPlumber/PyPDF text and character bounding box extractor
│   │       ├── pdf_validation.py                # Validates PDF headers, encryption, and page boundaries
│   │       ├── practice_follow_up_service.py    # Evaluates answers and generates 1-turn adaptive follow-up probes
│   │       ├── practice_report_service.py       # Compiles multi-dimensional practice coaching reports
│   │       ├── practice_review_service.py       # Real-time per-answer AI review (clarity, depth, STAR structure)
│   │       ├── practice_session_service.py      # Candidate practice sandbox turn-taking state machine
│   │       ├── profile_assembly.py              # Assembles extracted entities into cohesive CandidateProfile
│   │       ├── profile_correction.py            # Recruiter granular manual correction engine (patch operations)
│   │       ├── provider_compatibility_service.py # Validates local LLM API endpoints and model response formats
│   │       ├── provider_eligibility.py          # Assesses AI provider suitability for question authoring
│   │       ├── provider_registry.py             # In-memory and DB registry of active AI inference adapters
│   │       ├── provisional_assessment_service.py # Computes provisional scores during interview simulations
│   │       ├── recruiter_applicant_service.py   # Recruiter workflow for reviewing applications and stages
│   │       ├── requirement_validation.py        # Validates grounded requirement syntax, weights, and categories
│   │       ├── scoring.py                       # Mathematical scoring functions for skills and experience
│   │       ├── secret_resolver.py               # Resolves encrypted secrets, API keys, and environment tokens
│   │       ├── section_detection.py             # Identifies resume section headers (Experience, Education, Skills)
│   │       ├── security.py                      # Cryptographic helpers, PBKDF2 hashing, HMAC signature checks
│   │       ├── skill_catalog.py                 # Hierarchical catalog of technical and soft skills
│   │       ├── skill_summary_extraction.py      # Summarizes candidate skill profiles and calculates years of exp
│   │       ├── taxonomy_normalization.py        # Normalizes raw skill text against standardized taxonomy graph
│   │       ├── text_normalization.py            # Text cleaning, unicode normalization, whitespace stripping
│   │       ├── wording_assistance_service.py    # Generates recruiter question wording variants via LLM
│   │       ├── wording_prompt_package.py        # Manages prompt templates for question wording assistance
│   │       ├── wording_provider.py              # LLM client adapter for question wording generation
│   │       └── wording_validation_service.py    # Validates rewritten questions against safety & length rules
│   ├── migrations/                              # Alembic Database Migration System
│   │   ├── env.py                               # Alembic environment runner loading SQLAlchemy MetaData
│   │   ├── script.py.mako                       # Template for auto-generated migration scripts
│   │   └── versions/                            # 33 Sequential Migration Scripts (Phase 1 to Phase 4B.5)
│   ├── runtime/                                 # Ephemeral storage for file uploads and quarantine
│   │   ├── quarantine/                          # Quarantined malformed or suspicious file uploads
│   │   └── resume_intake/                       # Temporary staging directory for active resume parsing
│   ├── tests/                                   # Pytest Test Suite (70+ Test Files, 900+ Tests)
│   │   ├── evaluation_support/                  # Evaluation harness for parser benchmarking
│   │   ├── fixtures/                            # Test resumes (PDF/DOCX) and ground truth JSON files
│   │   └── test_*.py                            # Test suites covering all domains, routers, models, and services
│   └── tools/                                   # Administrative & Evaluation Scripts
│       ├── bootstrap_admin.py                   # Script to create initial organization and admin user
│       └── run_evaluation.py                    # Parser precision/recall benchmark runner
├── frontend/                                    # Frontend Application (React 19, TypeScript 5.5+, Vite)
│   ├── index.html                               # HTML entry point with viewport and typography links
│   ├── package.json                             # Frontend dependencies (React, Lucide icons, Vitest, etc.)
│   ├── tsconfig.json                            # TypeScript compiler configuration (strict mode)
│   ├── vite.config.ts                           # Vite bundler configuration and proxy settings
│   └── src/                                     # Frontend Source Directory
│       ├── App.tsx                              # Main application router and shell container
│       ├── main.tsx                             # React DOM entry point mounting root App
│       ├── index.css                            # Master Vanilla CSS Design System (Glassmorphic dark-mode)
│       ├── setupTests.ts                        # Vitest testing setup and DOM matchers
│       ├── api/                                 # Typed API Client Modules
│       │   ├── ats.ts                           # ATS connection, sync, and import/export API client
│       │   ├── candidateApplications.ts         # Candidate application creation, resume upload, submission
│       │   ├── candidateAuth.ts                 # Candidate activation, login, session API client
│       │   ├── candidateJobs.ts                 # Candidate job catalog and published job detail API client
│       │   ├── candidatePractice.ts             # Recruiter practice release and candidate catalog API client
│       │   ├── candidatePracticeSession.ts      # Candidate practice sandbox turn-taking & report API client
│       │   ├── client.ts                        # Core HTTP fetch wrapper (CSRF injection, HttpOnly cookies)
│       │   ├── jobs.ts                          # Recruiter job requisition, versioning, requirement API client
│       │   ├── recruiterApplications.ts         # Recruiter applicant review and stage transition API client
│       │   └── taxonomy.ts                      # Skill autocomplete and taxonomy resolution API client
│       ├── components/                          # UI Component Tree
│       │   ├── AuthenticatedShell.tsx           # Recruiter/Admin top navigation bar and session header
│       │   ├── CandidateProfileReview.tsx       # Detailed candidate profile inspector with evidence viewer
│       │   ├── CandidatesDirectory.tsx          # Candidate roster table with search, filter, and upload
│       │   ├── EvidenceDrawer.tsx               # Slide-out drawer highlighting parsed resume text spans
│       │   ├── ExtractionReview.tsx             # Resumé parsing audit drawer for raw text vs. extracted entities
│       │   ├── Icon.tsx                         # Lightweight SVG icon system (50+ vector icons)
│       │   ├── ResumeUpload.tsx                 # Drag-and-drop resume uploader supporting PDF/DOCX
│       │   ├── ReviewDrawer.tsx                 # Recruiter manual profile correction drawer
│       │   ├── VersionHistoryDrawer.tsx         # Audit drawer showing revision history of candidate profiles
│       │   ├── admin/                           # Administrator Workspace Components
│       │   │   ├── AdminWorkspace.tsx           # Admin console (Users, Events, AI Providers, ATS tabs)
│       │   │   └── AtsConnectionsAdmin.tsx      # ATS connection management (Greenhouse, Lever, Local)
│       │   ├── ai_interviews/                   # AI Interview Studio Components
│       │   │   ├── AiInterviewsDirectory.tsx    # List of job requisitions with AI interview readiness status
│       │   │   ├── AiQuestionSetWorkspace.tsx   # AI Question Studio (Conversational & MCQ cards, approvals)
│       │   │   ├── CandidateSafePreviewModal.tsx # Zero-leakage preview modal showing candidate view
│       │   │   ├── McqAuthoringModal.tsx        # Modal for authoring and validating MCQ items
│       │   │   ├── SafeRubricModal.tsx          # Recruiter-only modal for inspecting evaluation rubrics
│       │   │   └── ai-interviews.css            # Studio-specific styles and animations
│       │   ├── ats/                             # ATS Modal Dialogs
│       │   │   ├── AtsExportModal.tsx           # Modal for exporting candidates/jobs to external ATS
│       │   │   └── AtsImportModal.tsx           # Modal for importing requisitions/resumes from ATS
│       │   ├── auth/                            # Authentication Views
│       │   │   ├── ChangePasswordPage.tsx       # Force-change password view for newly invited users
│       │   │   └── LoginPage.tsx                # Recruiter and Admin login portal
│       │   ├── candidate/                       # Candidate Portal Views & Components
│       │   │   ├── CandidateActivationPage.tsx  # Magic token account activation and password setup
│       │   │   ├── CandidateApplicationDetail.tsx # Candidate application detail & withdrawal view
│       │   │   ├── CandidateApplicationForm.tsx # Resume-first job application modal
│       │   │   ├── CandidateInvitationModal.tsx # Recruiter modal to send portal invitations to candidates
│       │   │   ├── CandidateJobDetail.tsx       # Candidate view of published requisition details
│       │   │   ├── CandidateLoginPage.tsx       # Candidate portal login page
│       │   │   ├── CandidateMyApplications.tsx  # Candidate dashboard of submitted applications
│       │   │   ├── CandidateOpenJobs.tsx        # Candidate job discovery board
│       │   │   ├── CandidatePracticeDirectory.tsx # Candidate practice catalog view
│       │   │   ├── CandidatePracticeReleaseModal.tsx # Recruiter modal to release practice sets to candidate
│       │   │   ├── CandidatePracticeReport.tsx  # Multi-dimensional radar coaching scorecard view
│       │   │   ├── CandidatePracticeRoom.tsx    # Interactive practice simulation sandbox (turn-taking)
│       │   │   ├── CandidateRegisterPage.tsx    # Candidate self-registration page
│       │   │   └── CandidateShell.tsx           # Candidate portal layout and navigation header
│       │   ├── common/                          # Reusable UI Primitives
│       │   │   ├── Button.tsx                   # Accessible button component with variant and size states
│       │   │   ├── Dialog.tsx                   # Accessible modal dialog with backdrop blur
│       │   │   ├── EmptyState.tsx               # Standardized empty state card with icon and action button
│       │   │   ├── FormField.tsx                # Labeled form field container with error text
│       │   │   ├── InlineNotice.tsx             # Alert banner (success, warning, info, error)
│       │   │   ├── PageHeader.tsx               # Standardized view header with title, subtitle, and actions
│       │   │   └── StatusBadge.tsx              # Colored status pill badge
│       │   ├── interviews/                      # Legacy Interview Components
│       │   │   ├── AnchoredRubricModal.tsx      # Modal displaying anchored 1/3/5 rating criteria
│       │   │   ├── InterviewReviewWorkspace.tsx # Workspace for human evaluation of completed interviews
│       │   │   ├── InterviewWorkspace.tsx       # Requisition interview template builder
│       │   │   ├── SimulationWorkspace.tsx      # Pre-release interview simulation tool
│       │   │   └── WordingComparisonModal.tsx   # Side-by-side comparison modal for wording variants
│       │   ├── jobs/                            # Job Requisition & Applicant Workflow Components
│       │   │   ├── CandidateComparisonView.tsx  # Multi-candidate match comparison and ranking matrix
│       │   │   ├── JobApplicantsView.tsx        # Recruiter applicant roster for a specific job requisition
│       │   │   ├── JobApplicationDetailView.tsx # Recruiter detailed view of candidate application
│       │   │   ├── JobEditor.tsx                # Master requisition editor with versioning and requirements
│       │   │   ├── JobsDirectory.tsx            # Table of all job requisitions with status filters
│       │   │   ├── OccupationSelector.tsx       # O*NET occupation taxonomy search and selector
│       │   │   ├── RequirementCard.tsx          # Card representing a single grounded job requirement
│       │   │   ├── RequirementGapReportView.tsx # Categorical requirement gap report inspector
│       │   │   ├── TaxonomySkillAutocomplete.tsx # Typeahead skill search component with taxonomy pills
│       │   │   └── VisualAnalyticsCharts.tsx    # Visual skill gap charts and score distribution bars
│       │   └── reviewer/                        # Evaluation Reviewer Workspace
│       │       └── ReviewerWorkspace.tsx        # Internal reviewer workspace for evaluation benchmarking
│       ├── context/                             # React Context State Providers
│       │   ├── AuthContext.tsx                  # Recruiter/Admin authentication, tenant context, CSRF token
│       │   └── CandidateAuthContext.tsx         # Candidate authentication and session state provider
│       ├── types/                               # Frontend TypeScript Type Definitions
│       │   ├── ai_question_set.ts               # AI Question set, item, slot, and validation interfaces
│       │   ├── ats.ts                           # ATS integration and connection interfaces
│       │   └── interview.ts                     # Interview template, question, and rubric interfaces
│       ├── utils/                               # Client Utility Functions
│       │   ├── navigation.ts                    # URL query parameter and tab routing helpers
│       │   └── portal.ts                        # DOM portal helpers for modal rendering
│       └── __tests__/                           # Vitest & React Testing Library Test Suites (34 Test Files)
│           └── *.test.tsx                       # Component, workflow, and integration test files
```

---

## 3. Global Tenancy, RBAC & Security Model

The system enforces strict multi-tenant data isolation and role-based access control across all database queries and API endpoints:

```mermaid
flowchart TD
    subgraph OrganizationTenant ["Organization Tenancy Boundary (UUID)"]
        Users["Users (Admin, Recruiter)"]
        Jobs["Job Requisitions & Versions"]
        Candidates["Candidate Identities & Profiles"]
        Matches["Match Runs & Gap Reports"]
        AISets["AI Question Sets & Rubrics"]
        Apps["Job Applications & Practice Releases"]
    end

    subgraph SecurityShield ["Cryptographic Security & Auth Guard"]
        CSRF["Double-Submit HMAC CSRF Token Verification"]
        Cookie["HttpOnly, SameSite=Lax Session Cookies"]
        RBAC["FastAPI Dependency Guards (`require_recruiter`, etc.)"]
        Isolation["Cross-Tenant Shield (Reject Cross-Org UUIDs with 403)"]
    end

    SecurityShield --> OrganizationTenant
```

### 3.1 Tenancy Enforcement Rules
1. **Organization Isolation**: Every database entity (`JobRequisition`, `CandidateIdentity`, `MatchRun`, `AIQuestionSet`, `CandidateApplication`) possesses an `organization_id` foreign key.
2. **Cross-Tenant Shielding**: Any attempt to associate an entity from Organization A with an entity from Organization B (e.g., releasing a practice set owned by Org A to a candidate bound to Org B) raises a `403 Forbidden` (`FORBIDDEN_ORGANIZATION`).
3. **Session Management**: Session tokens are stored in the database (`user_sessions` or `candidate_account_bindings`), authenticated via signed HttpOnly cookies, and expired after a configurable window (`SESSION_EXPIRE_HOURS=24`).
4. **CSRF Protection**: All mutating HTTP requests (`POST`, `PUT`, `PATCH`, `DELETE`) require a valid `X-CSRF-Token` header that matches the cryptographically signed CSRF cookie.

---

## 4. Subsystem Topology & Data Flow

```mermaid
flowchart LR
    subgraph Ingestion ["1. Ingestion & Grounding"]
        PDF_DOCX["Resume File (PDF/DOCX)"] --> DocParser["pdf/docx_text_extraction.py"]
        DocParser --> Spans["Evidence Spans (start, end, bbox)"]
        Spans --> Profile["CandidateProfile Assembly"]
    end

    subgraph Requisition ["2. Job Authoring"]
        JobRaw["Job Description"] --> JParser["job_description_parser.py"]
        JParser --> Reqs["Grounded Requirements + Taxonomy"]
        Reqs --> JVersion["JobVersion (Immutable)"]
    end

    subgraph Matching ["3. Deterministic Matching"]
        Profile --> Matcher["deterministic_matching.py"]
        JVersion --> Matcher
        Matcher --> MatchResult["MatchRun (Score Math + Gaps)"]
    end

    subgraph Studio ["4. AI Question Studio"]
        JVersion --> AIOrch["ai_interview_orchestrator.py"]
        AIOrch --> LocalLLM["Local LLM Inference (MLX/Ollama)"]
        LocalLLM --> Checks["ai_provenance_service.py (20 Checks)"]
        Checks --> ApprovedSet["Approved AI Question Set"]
    end

    subgraph Simulation ["5. Candidate Practice"]
        ApprovedSet --> Release["candidate_practice_service.py"]
        Release --> Sandbox["Candidate Practice Room"]
        Sandbox --> TurnEng["practice_session_service.py (1-Turn Probe)"]
        TurnEng --> Report["practice_report_service.py (Radar Chart)"]
    end
```

---

## 5. Technology Stack & Runtime Infrastructure

| Subsystem | Technology | Version | Key Responsibilities & Capabilities |
|---|---|---|---|
| **Backend API** | FastAPI + Python | 3.14 / 0.115+ | High-performance ASGI async server, Pydantic v2 strict serialization, dependency injection security guards |
| **Database ORM** | PostgreSQL + SQLAlchemy | 16 / 2.0+ | Relational persistence, JSONB document snapshots, Alembic schema migrations, strict FK cascades |
| **Document Parsing** | pdfplumber + python-docx | 0.11+ / 1.1+ | Character-level coordinate extraction, font metadata, multi-column layout recognition, evidence offsets |
| **Frontend UI** | React + TypeScript + Vite | 19 / 5.5+ / 6.0+ | Strict type safety, Vanilla CSS Glassmorphic design tokens, zero external UI framework bloat |
| **Local AI Inference** | MLX / Ollama / OpenAI API | Native / 0.3+ | Apple Silicon MLX local inference, Ollama OpenAI-compatible endpoints, zero resume data egress |
| **Testing Engine** | Pytest + Vitest | 8.0+ / 4.1+ | 70+ Python backend test suites (900+ tests), 34 TypeScript frontend test suites (200+ tests) |

---

## 6. Environment Configuration & Local Execution

### 6.1 Environment Variables (`.env`)
```ini
# PostgreSQL 16 Connection
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_hiring_db

# Security Secrets (Must be min 32 characters in production)
SECRET_KEY=enterprise-super-secret-key-change-in-production-min-32-chars
CSRF_SECRET_KEY=csrf-hmac-salt-enterprise-key
SESSION_EXPIRE_HOURS=24

# Local AI Inference Provider (MLX / Ollama)
DEFAULT_AI_PROVIDER_TYPE=LOCAL_OPENAI_COMPATIBLE
DEFAULT_AI_PROVIDER_URL=http://localhost:8080/v1
DEFAULT_AI_MODEL_IDENTIFIER=qwen/qwen3-4b-2507
```

### 6.2 Quick-Start Execution Commands
```bash
# 1. Start PostgreSQL 16 Database
docker compose up -d postgres

# 2. Setup and Run Backend API
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.cli.seed_defaults
uvicorn app.main:app --reload --port 8000

# 3. Setup and Run Frontend UI (in a separate terminal)
cd frontend
npm install
npm run dev

# 4. Execute Full Verification Test Suites
# Backend Tests:
cd backend && pytest tests/ -v
# Frontend Tests:
cd frontend && npm test
```
