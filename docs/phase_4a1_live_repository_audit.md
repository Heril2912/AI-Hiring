# Phase 4A.1 — Live Repository Audit and Defect Trace

## 1. Phase and Audit Scope

This document records the diagnostic audit of the live AI-Driven Smart Hiring Platform repository for **Phase 4A.1**. The audit inspects code, database schemas, migration lineage, service implementations, and user workflows to identify the evidence-supported root causes of three primary defects:

1. **Defect 1**: Different jobs receive the same or overly generic AI-generated interview questions.
2. **Defect 2**: Candidate interview analysis is noisy, weakly connected to exact questions and answers, and difficult to understand.
3. **Defect 3**: Recruiter and Candidate navigation exposes disconnected modules instead of a coherent workflow.

This phase is **diagnostic only**. No refactoring, schema migration, dependency update, or application code fixes were performed.

---

## 2. Safety Boundaries Followed

The critical safety boundaries established for Phase 4A.1 were strictly upheld:
- **No Alembic migrations created or executed.**
- **No database schemas, tables, columns, or models modified.**
- **No dependencies installed, updated, or removed.**
- **No environment variables, secrets, or `.env` files exposed or modified.**
- **No Dockerfiles, compose specifications, or service topologies altered.**
- **No existing resumes, candidate accounts, answers, or evaluation records modified or deleted.**
- **All existing features (PDF/DOCX intake, deterministic matching, gap analysis, ATS sync, auth cookies) remained untouched.**
- **Only one new documentation file created**: `docs/phase_4a1_live_repository_audit.md`.

---

## 3. Repository and Runtime Baseline

- **Git Branch**: `main`
- **Git Commit**: `96f0da1` (HEAD -> main, origin/main) - *"Ver 3.7.1 Phase-3G.1 adding AI report"*
- **Git Working Tree Status**: Clean prior to creating this audit document.
- **Runtime Environment**:
  - **Operating System**: macOS (`Darwin 25.3.0`, arm64 / Apple Silicon).
  - **Database Service**: PostgreSQL 16 Alpine running in Docker container `ai-hiring-postgres-1` (port 5432).
  - **Backend API**: FastAPI running natively via Uvicorn on `http://localhost:8000` with Python 3.12 virtualenv (`backend/.venv`).
  - **Frontend Client**: Vite + React 19 + TypeScript running on `http://localhost:5173`.
  - **Local LLM Endpoint**: LM Studio local server configured on `http://127.0.0.1:1234/v1` targeting model `qwen/qwen3-4b-2507` (MLX).
- **Core Dependencies**:
  - Backend: `fastapi`, `uvicorn`, `sqlalchemy` (v2), `alembic`, `pydantic` (v2), `psycopg2-binary`, `spacy` (en_core_web_sm), `python-docx`, `pypdf`, `httpx`, `passlib/argon2-cffi`.
  - Frontend: `react` (v19), `react-dom`, `vite`, `typescript`, vanilla CSS tokens (`index.css`).

---

## 4. Current Architecture Summary

```
   +-------------------------------------------------------------------------------+
   |                             Vite + React 19 UI                                |
   |  [Admin Workspace]     [Recruiter Workspace]      [Candidate Practice Portal] |
   |  - User Management     - Jobs & Requirements       - Direct Token Login        |
   |  - Audit Log Viewer    - Resume Upload & Parsing   - Live AI Practice Room     |
   |  - AI Provider Config  - Deterministic Matches     - Instant Answer Feedback   |
   |  - ATS Integrations    - AI Question Workspace     - Overall Practice Report   |
   +---------------------------------------+---------------------------------------+
                                           | HTTP / REST (Separate Auth Cookies)
                                           v
   +-------------------------------------------------------------------------------+
   |                             FastAPI Backend API                               |
   |  /api/v1/auth                /api/v1/jobs              /api/v1/candidate-auth |
   |  /api/v1/admin               /api/v1/matches           /api/v1/candidate-prac |
   |  /api/v1/resumes             /api/v1/gap-reports       /api/v1/ats            |
   |  /api/v1/ai-interviews       /api/v1/interviews        /api/v1/taxonomy       |
   +---------------------------------------+---------------------------------------+
                                           |
                +--------------------------+--------------------------+
                |                                                     |
                v                                                     v
   +----------------------------+                      +----------------------------+
   |   PostgreSQL Persistence   |                      |  Local LLM Studio Adapter  |
   |   - Users & Sessions       |                      |  - Bounded JSON Prompts    |
   |   - Jobs & Requirements    |                      |  - Strict Timeout / Retry  |
   |   - Resumes & Extractions  |                      |  - Non-streaming HTTP      |
   |   - AI Question Sets       |                      |  - Qwen3-4B MLX Target     |
   |   - Practice Sessions & Rpt|                      +----------------------------+
   +----------------------------+
```

---

## 5. Database and Entity Reconciliation

The Alembic migration chain is at revision **`k1a2b3c4d5e6` (head)** across 35 migration versions. All entity relationships were audited:

| Concept / Domain | Database Table Name | Primary Identity | Key Foreign Keys & Ownership | Lifecycle / Status Field | Versioning Relationship | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Users & Roles** | `users` | `user_id` (UUID) | None | `failed_login_count`, `locked_until` | N/A | **REUSE** |
| **User Sessions** | `user_sessions` | `session_id` (UUID) | `user_id` -> `users` | `revoked_at`, `revoke_reason` | N/A | **REUSE** |
| **Candidate Identity** | `candidate_identities` | `candidate_id` (UUID) | None | N/A | Linked to profiles | **REUSE** |
| **Candidate Profile** | `candidate_profiles` | `profile_id` (UUID) | `candidate_id` -> `candidate_identities` | `extraction_status` | `profile_version` | **REUSE** |
| **Profile Corrections** | `profile_corrections` | `correction_id` (UUID)| `profile_id` -> `candidate_profiles` | N/A | Audited edits | **REUSE** |
| **Resume Artifacts** | `resume_artifacts` | `resume_id` (UUID) | None | `validation_status` | SHA-256 hash | **REUSE** |
| **Job Requisitions** | `job_requisitions` | `job_id` (UUID) | `organization_id`, `created_by_user_id` | `lifecycle_status`, `is_deleted` | Has `versions` | **REUSE** |
| **Job Versions** | `job_versions` | `job_version_id` (UUID)| `job_id` -> `job_requisitions` | `status` (DRAFT/APPROVED) | `version_number` | **REUSE** |
| **Job Requirements** | `job_requirements` | `requirement_id` (UUID)| `job_version_id` -> `job_versions` | `category`, `necessity` | Linked to version | **REUSE** |
| **Deterministic Matches** | `match_runs`, `match_results`| `run_id`, `result_id`| `job_version_id`, `profile_id` | `lifecycle_status` | Exact score snapshot| **REUSE** |
| **Skill Gap Reports** | `gap_reports`, `gap_report_items`| `report_id`, `item_id` | `job_version_id`, `profile_id` | `lifecycle_status` | Deterministic | **REUSE** |
| **Deterministic Templates**| `job_interview_templates` | `template_id` (UUID) | `job_id`, `job_version_id` | `lifecycle_status` | `template_version` | **LEGACY BUT REQUIRED** |
| **Deterministic Questions**| `interview_questions` | `question_id` (UUID) | `template_id` -> `job_interview_templates`| `validation_state`| `question_version` | **LEGACY BUT REQUIRED** |
| **AI Question Sets** | `ai_interview_question_sets` | `ai_set_id` (UUID) | `job_id`, `job_version_id`, `template_id` (opt) | `lifecycle_status` | `set_version`, content_hash | **REUSE / EXTEND** |
| **Candidate Invitations** | `candidate_invitations` | `invitation_id` (UUID)| `job_id`, `created_by_user_id` | `status` (PENDING/ACCEPTED) | Token-based | **REUSE** |
| **Candidate Bindings** | `candidate_account_bindings`| `binding_id` (UUID) | `user_id`, `candidate_id`, `profile_id` | `status` (ACTIVE/SUSPENDED)| Multi-account safe | **REUSE** |
| **Practice Releases** | `candidate_practice_releases`| `release_id` (UUID) | `job_id`, `job_version_id`, `ai_set_id` | `status` (RELEASED/ARCHIVED)| Links approved AI set| **REUSE** |
| **Practice Sessions** | `candidate_practice_sessions`| `session_id` (UUID) | `candidate_user_id`, `job_id`, `release_id`| `lifecycle_status` | `snapshot_hash` | **REUSE** |
| **Practice Answers/Reviews**| `candidate_practice_answer_reviews`| `review_id` (UUID) | `session_id`, `answer_id`, `question_id` | `lifecycle_status` | Single answer review | **REUSE / EXTEND** |
| **Practice Reports** | `candidate_practice_reports` | `report_id` (UUID) | `session_id`, `job_id` | `lifecycle_status` | `source_review_hash`| **REUSE / EXTEND** |
| **Provider Profiles** | `provider_profiles` | `provider_profile_id`| `organization_id` | `is_active`, `is_archived`| Compatibility tested | **REUSE** |
| **Security / Audit Events**| `security_audit_events` | `event_id` (UUID) | `actor_user_id` | `event_type`, `result` | Immutable log | **REUSE** |

### Entity Reconciliation & Collision Analysis
1. **`job_interview_templates` vs. `ai_interview_question_sets`**:
   - `job_interview_templates` stores curated catalogue questions (`InterviewQuestionRecord`) based on fixed competency tags.
   - `ai_interview_question_sets` stores generated JSON slots grounded in job requirements or deterministic blueprints. Both coexist safely; AI question generation supports `REQUIREMENT_GROUNDED` mode which does not require a deterministic template.
2. **`candidate_practice_sessions` vs. `interview_simulations`**:
   - `interview_simulations` (Phase 3D.1) was an internal recruiter/admin test harness.
   - `candidate_practice_sessions` (Phase 3F/3G) is the authoritative candidate practice entity.
3. **Candidate User Account vs. Extracted Profile**:
   - Resolved cleanly through `candidate_account_bindings`, linking `users.user_id` (`role=CANDIDATE`) to `candidate_identities` and `candidate_profiles`.

---

## 6. Authentication and Authorization Map

- **Roles**:
  - `ADMIN`: Full access to user management, provider configuration, ATS integrations, security event logs, and system audits.
  - `RECRUITER`: Access to job creation/editing, candidate resume upload, profile review, deterministic matching, AI question generation, and candidate invitations. Scoped by `organization_id` and ownership.
  - `REVIEWER`: Read-only access to assigned candidates and review queues.
  - `CANDIDATE`: Restricted access strictly to their invited practice jobs, live practice interview room, and their own practice feedback reports.
- **Session & Cookie Mechanism**:
  - **Simultaneous Role Isolation**:
    - Recruiter/Admin/Reviewer session cookie: `ai_hiring_session` (HttpOnly, SameSite=Lax).
    - Candidate session cookie: `ai_hiring_candidate_session` (HttpOnly, SameSite=Lax).
    - Allows a recruiter and a candidate to test or operate simultaneously in the same browser without session overwrite.
  - **Session Lifetimes**: Idle lifetime = 30 minutes (`1800s`), Absolute lifetime = 12 hours (`43200s`).
  - **CSRF Protection**: Double-submit cookie / header verification for state-changing endpoints.
  - **Route Guards**:
    - Frontend: `AuthenticatedShell` checks `AuthContext`; `CandidateShell` checks `CandidateAuthContext`.
    - Backend: Fast-failing FastAPI dependencies (`require_admin`, `require_recruiter`, `require_candidate`, `require_authenticated_user`).

---

## 7. Defect 1: Question-Generation Trace

### Defect Statement
*Different jobs are receiving the same or overly generic AI-generated interview questions.*

### Trace Findings & Root Causes

```
+--------------------------------------------------------------------------------------------------+
| FRONTEND TRIGGER: AiQuestionSetWorkspace / generate_ai_questions_by_job_id                       |
|   POST /api/v1/ai-interviews/generate  { job_id: "..." }                                         |
+-------------------------------------------------+------------------------------------------------+
                                                  |
                                                  v
+--------------------------------------------------------------------------------------------------+
| BACKEND EXECUTION: ai_question_set_service.py                                                    |
|                                                                                                  |
| [Root Cause 1A: Blueprint Mode Hardcoded Fallback]                                               |
|   - Default source mode uses deterministic curated catalogue (interview_catalogue.py).           |
|   - Catalogue contains only 9 generic competency entries (e.g., Q-PYTHON-CORE-TECH-01,           |
|     Q-DISTRIBUTED-SYSTEMS-01, Q-API-DESIGN-01).                                                  |
|   - Any backend job with 'python' in requirements gets the EXACT same question template seed:     |
|     "How does the Python asyncio event loop operate under the hood...".                          |
|                                                                                                  |
| [Root Cause 1B: Requirement Grounded Mode Seed Under-Specification]                              |
|   - In REQUIREMENT_GROUNDED mode, _build_requirement_grounded_plan selects top 4-6 requirements. |
|   - Seed text sent to LLM prompt is:                                                             |
|     seed_text = f"Assess hands-on proficiency in {slot['competency_name']}."                     |
|   - Entire job description context, company domain, job level, and detailed requirement          |
|     rationale are omitted from the prompt packet.                                                |
|   - LLM receives only a bare keyword (e.g., "Python") and generates a generic textbook question. |
|                                                                                                  |
| [Root Cause 1C: Prompt Constraint Over-Normalization]                                            |
|   - Prompt package instructions strictly forbid role-specific details or specific frameworks     |
|     unless matching exact keyword strings.                                                       |
+--------------------------------------------------------------------------------------------------+
```

- **Confidence**: **CONFIRMED**
- **Files / Code Locations**:
  - [`backend/app/services/interview_catalogue.py`](file:///Users/herilvyas/Desktop/AI-Hiring/backend/app/services/interview_catalogue.py#L487-L565): `COMPETENCY_KEY_MAPPINGS` collapses diverse job requirements into 9 static catalogue question templates.
  - [`backend/app/services/ai_question_set_service.py`](file:///Users/herilvyas/Desktop/AI-Hiring/backend/app/services/ai_question_set_service.py#L325-L342): `BoundedWordingRequest` constructs prompts using only `competency_name` and generic seed strings without rich job context.
  - [`backend/app/services/wording_prompt_package.py`](file:///Users/herilvyas/Desktop/AI-Hiring/backend/app/services/wording_prompt_package.py#L27-L51): `SYSTEM_INSTRUCTION_TEMPLATE` enforces wording-only restructuring rather than scenario-grounded question synthesis.

---

## 8. Defect 2: Assessment and Report Trace

### Defect Statement
*Candidate interview analysis is noisy, weakly connected to the exact questions and answers, and difficult to understand.*

### Trace Findings & Root Causes

```
+--------------------------------------------------------------------------------------------------+
| CANDIDATE SUBMISSION: Candidate answers question during live interview / practice session        |
|   POST /api/v1/candidate-practice/sessions/{id}/answer                                          |
+-------------------------------------------------+------------------------------------------------+
                                                  |
                                                  v
+--------------------------------------------------------------------------------------------------+
| BACKEND EVALUATION: practice_review_service.py / live_interview_service.py                       |
|                                                                                                  |
| [Root Cause 2A: Full Transcript Batch Processing Without Question Intent Anchor]                 |
|   - Final interview evaluation sends the entire concatenated transcript to the LLM at once.      |
|   - For short answers (1-2 sentences), the LLM hallucinates standard textbook answers and        |
|     evaluates what was NOT said rather than what was asked.                                      |
|                                                                                                  |
| [Root Cause 2B: Dimension Disconnection & Level Drift]                                           |
|   - Evaluator prompt asks for 5 abstract dimensions (relevance, clarity, technical_depth,        |
|     evidence, problem_solving_structure) without concrete behavioral rubrics per question.      |
|   - LLM generates generic feedback: "Answer lacked specific examples from production".           |
|                                                                                                  |
| [Root Cause 2C: Weak Evidence Citation Validation]                                               |
|   - When answer text is short or conversational, segmentation produces 1 segment.                |
|   - The model's evidence quote is often a restatement of the entire answer, making               |
|     feedback commentary feel repetitive and disconnected from specific claims.                   |
|                                                                                                  |
| [Root Cause 2D: Disconnected Dual Reporting Pipelines]                                           |
|   - Candidate practice reports (practice_report_service.py) and recruiter provisional assessment |
|     (provisional_assessment_service.py) use different schema structures and calculation rules.   |
+--------------------------------------------------------------------------------------------------+
```

- **Confidence**: **CONFIRMED**
- **Files / Code Locations**:
  - [`backend/app/services/live_interview_service.py`](file:///Users/herilvyas/Desktop/AI-Hiring/backend/app/services/live_interview_service.py#L103-L160): `LIVE_FINAL_REVIEW_SYSTEM_PROMPT` prompts LLM for all question reviews simultaneously without feeding back the original question's specific intent and rubric anchors.
  - [`backend/app/services/practice_review_service.py`](file:///Users/herilvyas/Desktop/AI-Hiring/backend/app/services/practice_review_service.py#L250-L330): Review generation prompt asks for generalized strengths/improvements without calibrating to expected junior/senior answer depth.
  - [`backend/app/services/practice_report_service.py`](file:///Users/herilvyas/Desktop/AI-Hiring/backend/app/services/practice_report_service.py#L116-L195): Aggregation maps string levels (`STRONG`=4.0, `DEVELOPING`=3.0) into arbitrary visual percentages that confuse candidates when no questions were failed.

---

## 9. Defect 3: Navigation and Route Trace

### Defect Statement
*Recruiter and Candidate navigation exposes disconnected modules instead of a coherent workflow.*

### Trace Findings & Root Causes

```
+--------------------------------------------------------------------------------------------------+
| RECRUITER PORTAL NAVIGATION MAP                                                                  |
|                                                                                                  |
|  [Tab: Jobs] ---------> List of Jobs ---> Job Details / Edit ---> Candidate Matches               |
|                                 |                                                                |
|                                 +---> [DISCONNECTED] No button to generate AI questions          |
|                                       or invite candidates directly from job card                |
|                                                                                                  |
|  [Tab: Candidates] ---> List of Candidates ---> View Profile ---> Extraction Data                |
|                                 |                                                                |
|                                 +---> [DISCONNECTED] No link to launch interview or assign job   |
|                                                                                                  |
|  [Tab: Upload Resume]-> Upload Form ---> Extraction Results ---> Redirects to /candidates        |
|                                                                                                  |
|  [Tab: AI Questions] -> AI Questions Directory ---> View/Edit Question Set Workspace             |
|                                 |                                                                |
|                                 +---> [DISCONNECTED] Standalone workspace isolated from Jobs tab |
|                                       Recruiter must re-select job from dropdown                 |
+--------------------------------------------------------------------------------------------------+
| CANDIDATE PORTAL NAVIGATION MAP                                                                  |
|                                                                                                  |
|  [Direct Token Link] -> Activation / Login ---> CandidatePracticeDirectory                      |
|                                                       |                                          |
|                                                       v                                          |
|                                         Active Practice Session / Room                           |
|                                                       |                                          |
|                                                       v                                          |
|                                         Practice Report / Feedback                               |
|                                                       |                                          |
|  [DISCONNECTED] No return path to Job Directory or home without manual browser back/refresh      |
+--------------------------------------------------------------------------------------------------+
```

### Detailed Route Map & Disconnection Analysis

| Route / View Identifier | Role | User Task | Entry Point | Expected Next Action | Actual Current Experience & Disconnection |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `jobs` | Recruiter | Browse & manage jobs | Top Nav "Jobs" | View matches, AI questions, candidates | Isolated table. Cannot generate questions or view applicants in one unified job pipeline view. |
| `ai_interviews` | Recruiter | Manage AI question sets | Top Nav "AI Questions" | Review/approve generated questions | Separate module. Recruiter has to manually cross-reference Job IDs to know which job needs questions. |
| `candidates` | Recruiter | View candidate resumes | Top Nav "Candidates" | Match to job, view gap report | Candidate directory has no job context attached. Match results are hidden in Job Comparison view. |
| `compare_candidates` | Recruiter | Compare applicants | Job row action | View gap report, invite candidate | Deeply nested URL parameter view; breadcrumb navigation frequently resets search filters. |
| `candidate_practice` | Candidate | Complete live practice | Email / Token link | Complete sequential interview | Linear modal. Once report is viewed, candidate has no clear dashboard to view other released jobs. |

- **Confidence**: **CONFIRMED**
- **Files / Code Locations**:
  - [`frontend/src/App.tsx`](file:///Users/herilvyas/Desktop/AI-Hiring/frontend/src/App.tsx#L61-L150): Navigation state uses disconnected `activeNavTab` and `activeView` state machines with complex query-parameter syncing.
  - [`frontend/src/components/AuthenticatedShell.tsx`](file:///Users/herilvyas/Desktop/AI-Hiring/frontend/src/components/AuthenticatedShell.tsx#L110-L186): Top navigation tabs (`Jobs`, `Candidates`, `Upload Resume`, `AI Questions`) present horizontal tool silos rather than a recruiter hiring funnel (Job -> Applicants -> Matches -> Interview -> Decision).

---

## 10. Logging and Privacy Review

An audit of application logging across backend services was conducted:
- **Sensitive Credentials & Tokens**:
  - Passwords and token inputs are properly redacted in `FastAPI` validation handlers (`backend/app/main.py:40-53`).
  - Passwords hashed using Argon2id/scrypt.
- **Model Payload & Prompt Logging**:
  - In [`backend/app/services/wording_provider.py`](file:///Users/herilvyas/Desktop/AI-Hiring/backend/app/services/wording_provider.py), debug logs occasionally log error responses. No candidate PII or raw secrets were observed in standard `INFO` level logs.
- **Candidate Data Boundary**:
  - `SecurityAuditEventRecord` uses safe metadata dictionaries and avoids storing raw resume texts or answer transcripts.

---

## 11. Confirmed Findings

```
+-----------+----------+--------------------------------------+-------------------------------------------------------------+------------+
| Finding   | Defect   | Module / Component                   | Root Cause Summary                                          | Confidence |
+-----------+----------+--------------------------------------+-------------------------------------------------------------+------------+
| F-4A1-01  | Defect 1 | interview_catalogue.py               | Static catalogue maps all jobs to 9 generic questions       | CONFIRMED  |
| F-4A1-02  | Defect 1 | ai_question_set_service.py           | Prompt lacks job title, seniority, domain, & full context   | CONFIRMED  |
| F-4A1-03  | Defect 2 | live_interview_service.py            | Evaluation evaluates batch transcript without question rubric| CONFIRMED  |
| F-4A1-04  | Defect 2 | practice_report_service.py           | Numerical scoring conversion creates confusing report metric| CONFIRMED  |
| F-4A1-05  | Defect 3 | App.tsx / AuthenticatedShell.tsx     | Recruiter UI organized as disconnected feature silos        | CONFIRMED  |
| F-4A1-06  | Defect 3 | CandidateShell.tsx                   | Candidate lacks cohesive multi-job practice home view       | CONFIRMED  |
+-----------+----------+--------------------------------------+-------------------------------------------------------------+------------+
```

---

## 12. Unresolved Questions

1. **Recruiter Question Approval Workflow**: Should approved AI question sets automatically link to candidate invitations upon job release, or should recruiters be required to seal an AI question set version explicitly? *(To be resolved in Phase 4A.2 / 4B)*.
2. **Evaluation Depth Calibration**: Should candidate practice feedback include an optional "Seniority Calibration" setting (e.g., Junior vs Senior target) to adjust LLM critique expectations? *(To be evaluated in Phase 4A.3)*.

---

## 13. Functionality Preservation Register

The following systems are verified healthy and MUST NOT be broken during future Phase 4 modules:
- PDF/DOCX multi-page intake and quarantine security filters.
- spaCy candidate identity and profile extraction pipelines.
- Deterministic candidate-job matching algorithm and gap analysis scoring.
- Isolated recruiter/candidate simultaneous cookie authentication.
- PostgreSQL transactional persistence and Alembic migration integrity.
- Local OpenAI-compatible provider adapter and LM Studio connection bounds.

---

## 14. Handoff to Phase 4A.2

Phase 4A.1 diagnostic objectives are fully satisfied. The findings provide the necessary evidence baseline for:
- **Phase 4A.2**: Question Generation Architecture & Prompt Grounding Redesign.
- **Phase 4A.3**: Candidate Answer Assessment & Rubric Connection Redesign.
- **Phase 4A.4**: Recruiter & Candidate Workflow Navigation Unification.

---

## 15. Phase 4A.1 Exit-Gate Result

**PASSED — READY FOR PHASE 4A.2**
- All 3 defects fully traced with code-level evidence.
- Zero codebase modifications made; repository integrity intact.
- Audit report documented in `docs/phase_4a1_live_repository_audit.md`.
