# AI-Hiring Platform: Frontend Design System, UI Components & End-to-End User Journeys
**Document Version:** 1.0.0  
**Framework:** React 19 | TypeScript 5.5+ | Vite | Modern Vanilla CSS Design System  
**Design Philosophy:** Dark Glassmorphism, Zero CSS Library Bloat, High-DPI Micro-interactions, Zero-Leakage Candidate Privacy

---

## 1. UI/UX Architecture & Design System

The frontend is crafted using a bespoke, production-grade **Vanilla CSS Design System** (`index.css`) engineered for performance, accessible contrast ratios, sleek dark-mode glassmorphism, and responsive layouts.

### 1.1 Design System Tokens & Foundations
- **Color Palettes**:
  - **Backgrounds**: Obsidian deep background (`#0B0F19`), card obsidian glass (`rgba(17, 24, 39, 0.75)` with `backdrop-filter: blur(16px)`).
  - **Accents & Brand**: Electric Indigo (`#6366F1`), Cyan Teal (`#06B6D4`), Emerald Green (`#10B981`), Amber Warning (`#F59E0B`), Crimson Danger (`#EF4444`).
  - **Text Gradients**: Multi-stop metallic titanium gradients (`linear-gradient(135deg, #FFFFFF 0%, #94A3B8 100%)`).
- **Typography**:
  - Inter & Outfit clean geometric type scales with strict vertical rhythm.
- **Glassmorphic Surface Hierarchy**:
  - `card-glass-subtle`: 1px translucent border (`rgba(255, 255, 255, 0.08)`), subtle shadow.
  - `card-glass-elevated`: Hover elevation with glow shadow (`box-shadow: 0 12px 32px -4px rgba(99, 102, 241, 0.15)`).
  - `modal-backdrop-blur`: Multi-layer blur preventing visual background bleed.

---

## 2. Master Component Architecture

```mermaid
graph TD
    subgraph AppRoot ["App.tsx (Routing & Global State)"]
        AuthCtx["AuthContext (User, Tenant Org, Role, CSRF Token)"]
        NotifCtx["Notification & Toast Context"]
    end

    subgraph RecruiterModules ["Recruiter & Admin UI Views"]
        JobModule["Job Requisition & Requirement Studio (JobEditor.tsx)"]
        CandModule["Candidate Roster & Resume Parser (CandidateDetailModal.tsx)"]
        MatchModule["Match Run & Gap Analysis Studio (MatchResultsView.tsx)"]
        AIStudioModule["AI Question Studio & Rubric Inspector (AIQuestionStudio.tsx)"]
        ReleaseModal["Practice Release Diagnostic Modal (CandidatePracticeReleaseModal.tsx)"]
        AdminModule["Model Provider Settings & Compatibility Test (AdminProviderSettings.tsx)"]
    end

    subgraph CandidateModules ["Candidate Practice UI Views"]
        CandAuthView["Portal Activation & Login (CandidateAuthView.tsx)"]
        CandCatalog["Practice Requisition Catalog (CandidatePracticeCatalog.tsx)"]
        CandSandbox["Interactive Practice Session Sandbox (CandidatePracticeSessionView.tsx)"]
        CandReport["Personalized Practice Coaching Report (CandidatePracticeReportView.tsx)"]
    end

    AppRoot --> RecruiterModules
    AppRoot --> CandidateModules
```

### 2.1 Key Recruiter Components
1. **`JobEditor.tsx`**:
   - Split-pane interface for authoring job requisitions.
   - Grounded requirement tagger with category filters (`TECHNICAL_SKILL`, `EXPERIENCE`, etc.) and taxonomy auto-complete.
   - Real-time readiness validator displaying blocking issues before marking `READY_FOR_MATCHING`.
2. **`MatchResultsView.tsx`**:
   - Multi-candidate ranking table with deterministic score breakdown (Technical %, Experience %, Education %).
   - Side-by-side candidate comparison with visual evidence span highlighters on original parsed resumes.
   - Interactive skill gap matrix displaying met vs. missing requirements.
3. **`AIQuestionStudio.tsx`**:
   - Question list with conversational and MCQ cards.
   - 20-Point validation pill badge (`PASSED`, `FAILED`, `BLOCKED`) with error explanation drawer.
   - Interactive AI Wording Assistant modal allowing real-time rewording requests with tone selectors.
   - Single-click Authoritative Approval with safety diagnostic summaries.
4. **`CandidatePracticeReleaseModal.tsx`**:
   - Recruiter modal showing candidate-specific eligible and ineligible job lists.
   - Ineligibility diagnostics with direct "Fix in AI Studio" deep links.
   - Instant practice release and release revocation actions.

### 2.2 Key Candidate Components
1. **`CandidatePracticeCatalog.tsx`**:
   - Card deck showing all released practice interviews and requestable job roles.
   - Direct status trackers: `READY_TO_START`, `IN_PROGRESS`, `COMPLETED`.
   - Remaining attempt badges and expiration indicators.
2. **`CandidatePracticeSessionView.tsx`**:
   - Distraction-free, immersive interview simulation environment.
   - Real-time turn-taking interface supporting:
     - Voice/Text answers with countdown timer.
     - Adaptive AI Follow-up animation and instant feedback cards.
     - Interactive MCQ radio button selector with instant score validation and educational rationale.
   - Live session progress bar and attempt counter.
3. **`CandidatePracticeReportView.tsx`**:
   - Comprehensive performance dashboard:
     - Multi-dimensional radar chart of competencies.
     - Strengths and Priority Improvement Area accordion cards.
     - Per-question breakdown with STAR structure guidance and recommended response refinements.

---

## 3. End-to-End User Journeys & Workflows

### 3.1 Journey A: Recruiter Sourcing, Matching & AI Practice Release
```mermaid
sequenceDiagram
    autonumber
    actor R as Recruiter
    participant UI as Recruiter UI
    participant API as FastAPI Backend
    participant LLM as Local AI / MLX
    actor C as Candidate

    R->>UI: Create Job Requisition & Define Requirements
    UI->>API: POST /api/v1/jobs/ (Mark Ready)
    R->>UI: Ingest Candidate Resume (PDF/DOCX)
    UI->>API: POST /api/v1/candidates/resumes (Extract Spans)
    R->>UI: Run Deterministic Match
    UI->>API: POST /api/v1/match-runs/
    API-->>UI: Return Ranked Match Breakdown & Gap Analysis
    R->>UI: Open AI Question Studio & Generate Practice Set
    UI->>API: POST /api/v1/ai-question-sets/generate
    API->>LLM: Generate Grounded Conversational & MCQ Items
    LLM-->>API: Stream Items + Provenance + Rubrics
    API->>API: Execute 20-Point Server-Side Validation
    API-->>UI: Display Validated Question Set
    R->>UI: Approve Question Set
    UI->>API: POST /api/v1/ai-question-sets/{id}/approve
    R->>UI: Open Release Modal & Select Candidate
    UI->>API: POST /api/v1/recruiter/candidate-practice/candidates/{id}/release
    API->>API: Verify Authoritative Release Eligibility
    API-->>UI: Release Confirmed
    API-->>C: Practice Interview Available in Candidate Portal
```

### 3.2 Journey B: Candidate Activation, Simulation & Coaching
```mermaid
sequenceDiagram
    autonumber
    actor C as Candidate
    participant UI as Candidate Portal UI
    participant API as FastAPI Backend
    participant LLM as Local AI / MLX

    C->>UI: Click Magic Invitation Link & Set Password
    UI->>API: POST /api/v1/candidates/auth/activate
    API-->>UI: Set HttpOnly Session & Return Profile
    C->>UI: View Practice Catalog & Launch Session
    UI->>API: POST /api/v1/candidate/practice/sessions/start
    API-->>UI: Return First Question Item (Zero-Leakage)
    loop For Each Conversational Slot
        C->>UI: Submit Audio/Text Answer
        UI->>API: POST /api/v1/candidate/practice/sessions/{id}/answer
        API->>LLM: Evaluate Answer & Determine Follow-up (1 Turn Max)
        LLM-->>API: Follow-up Question + Instant Feedback
        API-->>UI: Render Adaptive Follow-up Question
        C->>UI: Submit Follow-up Answer
        UI->>API: POST /api/v1/candidate/practice/sessions/{id}/answer
        API-->>UI: Complete Slot -> Advance
    end
    loop For Each MCQ Slot
        C->>UI: Select MCQ Option
        UI->>API: POST /api/v1/candidate/practice/sessions/{id}/answer
        API->>API: Validate Correct Key & Record Score
        API-->>UI: Reveal Explanation & Advance
    end
    C->>UI: Finalize Practice Session
    UI->>API: POST /api/v1/candidate/practice/sessions/{id}/submit
    API->>API: Compile Multi-Dimensional Coaching Report
    API-->>UI: Return Full Coaching Report & Radar Chart
    C->>UI: Review Improvement Areas & Takeaways
```

---

## 4. Setup, Deployment & Local Execution Runbook

### 4.1 Prerequisites
- **Docker & Docker Compose** (PostgreSQL 16)
- **Python 3.14** with Virtualenv
- **Node.js 20+** with npm
- **Local AI Provider** (MLX Server on Apple Silicon, Ollama, or OpenAI-compatible endpoint)

### 4.2 Step-by-Step Initialization Runbook

```bash
# 1. Start PostgreSQL 16 Container
docker compose up -d postgres

# 2. Setup and Activate Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Apply Database Migrations & Seed Default Data
alembic upgrade head
python -m app.cli.seed_defaults   # Optional default seed

# 4. Start Backend API Server (Port 8000)
uvicorn app.main:app --reload --port 8000

# 5. Start Frontend Development Server (Port 5173) in a new terminal
cd ../frontend
npm install
npm run dev

# 6. Run Automated Test Verification
cd ../backend
pytest tests/
```

### 4.3 Environment Configuration (`.env`)
```ini
# PostgreSQL Connection
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_hiring_db

# Security & Session Secrets
SECRET_KEY=enterprise-super-secret-key-change-in-production-min-32-chars
SESSION_EXPIRE_HOURS=24
CSRF_SECRET_KEY=csrf-hmac-salt-enterprise-key

# Local Inference Provider (Default MLX on localhost:8080)
DEFAULT_AI_PROVIDER_TYPE=LOCAL_OPENAI_COMPATIBLE
DEFAULT_AI_PROVIDER_URL=http://localhost:8080/v1
DEFAULT_AI_MODEL_IDENTIFIER=qwen/qwen3-4b-2507
```
