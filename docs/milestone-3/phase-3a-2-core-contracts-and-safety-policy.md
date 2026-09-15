# Phase 3A.2 — Core Contracts and Versioned Safety Policy Record

- **Date**: 2026-09-15
- **Branch**: `main`
- **Audit Basis**: [docs/milestone-3/phase-3a-1-entry-audit.md](file:///Users/herilvyas/Desktop/AI-Hiring/docs/milestone-3/phase-3a-1-entry-audit.md)
- **Phase Name**: Phase 3A.2 (Core Contracts, Lifecycle Rules, Failure Vocabulary, Audit Classifications, and Versioned Safety Policy)

---

## 1. Executive Summary

Phase 3A.2 establishes the strict, provider-neutral and vendor-neutral domain contracts, lifecycle state transition rules, machine-readable failure vocabularies, safe audit event structures, and an immutable versioned safety policy for Milestone 3. 

In strict adherence to project constraints:
- **Zero real model or ATS requests** were made.
- **Zero vendor SDKs** (OpenAI, Anthropic, Google, AWS, llama.cpp, Greenhouse, Lever, Workday) were installed or imported.
- All domain code and contracts are 100% provider-independent.
- Phase 1 & Phase 2 deterministic parsing, matching, scoring, and gap report mechanics remain untouched and verified with 100% test pass rate.

---

## 2. Phase 3A.2 Contract Catalogue

All contracts are defined in `backend/app/schemas/` following the existing strict and frozen Pydantic conventions (`FrozenSchema`, `extra="forbid"`, `verify_no_prohibited_keys`).

### 2.1 Shared Enums (`backend/app/schemas/phase3_enums.py`)
- **`InterviewLayer`**:
  - `COMMON_CORE`: Uniform questions evaluated for all candidates on a requisition; included in the common score.
  - `SUPPLEMENTAL_EVIDENCE`: Targeted follow-up questions for unverified/missing skills; strictly excluded from common score.
- **`QuestionType`**: `BEHAVIORAL`, `SITUATIONAL`, `TECHNICAL`, `EVIDENCE_CLARIFICATION`.
- **`AuthoringOrigin`**: `DETERMINISTIC`, `AI_ASSISTED`, `RECRUITER_EDITED`.
- **`ValidationState`**: `PENDING`, `PASSED`, `BLOCKED`.
- **`PlanLifecycle`**: `DRAFT`, `VALIDATED`, `APPROVED`, `IN_USE`, `SUPERSEDED`.
- **`SimulationLifecycle`**: `NOT_STARTED`, `IN_PROGRESS`, `SUBMITTED`, `PROVISIONALLY_ASSESSED`, `HUMAN_REVIEWED`, `FINALIZED`.
- **`ATSExportLifecycle`**: `DRAFT`, `PREVIEWED`, `CONFIRMED`, `SENDING`, `SENT`, `RETRYABLE_FAILURE`, `PERMANENT_FAILURE`, `RECONCILIATION_REQUIRED`.
- **`ProviderType`**: `DISABLED`, `LOCAL_OPENAI_COMPATIBLE`, `REMOTE_OPENAI_COMPATIBLE`, `CUSTOM_ADAPTER`.
- **`ProviderOperation`**: Strictly four allowlisted operations:
  - `REWORD_QUESTION`
  - `CREATE_BOUNDED_VARIANTS`
  - `STRUCTURE_PROVISIONAL_ASSESSMENT`
  - `SUMMARIZE_SELECTED_EVIDENCE`
  *(Generic `CHAT`, `RUN_PROMPT`, or `COMPLETE_TEXT` operations are prohibited).*
- **`AuditRetentionClass`**: `IMMUTABLE_HIRING_EVIDENCE`, `DRAFT_CONTENT`, `MODEL_PROVENANCE`, `SIMULATION_CONTENT`, `INTEGRATION_AUDIT`, `OPERATIONAL_TRACE`.

### 2.2 Failure Vocabulary
- **`ValidationErrorCode`**: `INVALID_SCHEMA`, `UNKNOWN_FIELD`, `RESPONSE_TOO_LARGE`, `UNSUPPORTED_REFERENCE`, `UNSUPPORTED_CLAIM`, `PROHIBITED_TOPIC`, `PROTECTED_ATTRIBUTE`, `INTENT_CHANGED`, `DUPLICATE_OUTPUT`, `UNSAFE_CONTENT`, `STALE_SOURCE_VERSION`.
- **`ProviderErrorCode`**: `PROVIDER_DISABLED`, `PROVIDER_NOT_CONFIGURED`, `PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `PROVIDER_RATE_LIMITED`, `PROVIDER_INVALID_RESPONSE`, `PROVIDER_POLICY_REJECTED`, `PROVIDER_CONTEXT_TOO_LARGE`.

### 2.3 Strict Pydantic Data Contracts
1. **Policy Reference**: `PolicyVersionReference` (`policy_id`, `policy_version`, `policy_hash`, `schema_version`).
2. **Snapshot**: `BlueprintInputSnapshot` (captures job revision, candidate profile version, match result fingerprint, allowlisted requirement/evidence IDs).
3. **Interview Question & Rubric**:
   - `InterviewQuestion`: Enforces `included_in_common_score=True` for `COMMON_CORE` and `included_in_common_score=False` for `SUPPLEMENTAL_EVIDENCE` (requires source match/gap reference).
   - `InterviewRubric`: Enforces rating anchors for at least scale points `{1, 3, 5}` and checks prohibited topic phrases.
   - `InterviewBlueprint`: Aggregates layered questions, input snapshot, authoring origin, and approval state.
4. **Provider Capability Envelopes** (`backend/app/schemas/provider_capability.py`):
   - `ProviderCapabilityRequest`: Bounded, typed payloads (`RewordQuestionPayload`, `CreateBoundedVariantsPayload`, `StructureProvisionalAssessmentPayload`, `SummarizeSelectedEvidencePayload`).
   - `ProviderCapabilityResponse`: Bounded, typed results with validation state, error codes, and fallback flags.
5. **Simulation & Assessment** (`backend/app/schemas/simulation_assessment.py`):
   - `QuestionResponseRecord`, `ProvisionalRubricEvaluation`, `FinalRubricEvaluation`, `CandidateSimulationSession`.
6. **Canonical ATS DTOs** (`backend/app/schemas/ats_dto.py`):
   - `ATSJobReferenceDTO`, `ATSCandidateReferenceDTO`, `ATSApplicationReferenceDTO`, `ATSAttachmentMetadataDTO`, `ATSAssessmentNotePreviewDTO`, `ATSPaginatedResultDTO`, `ATSSyncCheckpointDTO`, `ATSWriteResultDTO`, `ATSHealthResultDTO`.
7. **Safe Audit Event Contract** (`backend/app/schemas/phase3_audit.py`):
   - `Phase3AuditEvent`: Enforces no API keys, bearer tokens, passwords, raw candidate answers, or full prompts in metadata.

---

## 3. Versioned Safety Policy Specification

Defined in `backend/app/schemas/safety_policy.py`:
- **Policy ID**: `safety_policy_v1`
- **Policy Version**: `1.0.0`
- **Schema Version**: `1.0.0`
- **Effective Date**: `2026-09-15T00:00:00Z`
- **Canonical Content Hash**: `fdf85a22bb0f0cff5c65a045508c9096773295c52bb33f7aa679cff541c41144`

### 3.1 Allowed vs Prohibited Model Purposes
- **Allowed**: Rewording deterministic questions, creating bounded question variants, structuring provisional observations against rubric indicators, summarizing explicitly selected evidence spans.
- **Prohibited**: Hiring decisions or recommendations, candidate ranking or score modification, requirement selection, ungrounded fact generation, protected attribute inference, health/disability inference, family status inference, personality/emotion/culture-fit/accent judgment, future performance prediction, tool/system execution, self-approval, external contact.

### 3.2 Prohibited Interview Topic Categories
- `AGE_AND_DOB`
- `RELIGION_AND_BELIEF`
- `ETHNICITY_AND_RACE`
- `IRRELEVANT_NATIONALITY`
- `DISABILITY_AND_MEDICAL`
- `PREGNANCY_AND_FAMILY_PLANS`
- `MARITAL_AND_FAMILY_STATUS`
- `SEXUALITY_AND_GENDER`
- `POLITICAL_BELIEF`
- `SOCIOECONOMIC_STATUS`
- `UNRELATED_PERSONAL_LIFE`

### 3.3 Failure Posture Matrix
| Failure Mode | Prescribed System Behavior |
|---|---|
| `PROVIDER_UNAVAILABLE` | Fallback to deterministic template wording |
| `INVALID_SCHEMA` | Reject response, allow at most one bounded repair |
| `UNSUPPORTED_REFERENCE` | Reject output |
| `SAFETY_POLICY_MATCH` | Block output immediately |
| `AUTHORIZATION_UNCERTAINTY` | Deny access |
| `STALE_SOURCE_VERSION` | Reject and require updated revision |
| `UNCERTAIN_ATS_WRITE` | Transition to `RECONCILIATION_REQUIRED` |

---

## 4. Lifecycle State Transitions

Defined in `backend/app/schemas/lifecycle.py`:

```
Plan Lifecycle:
[ DRAFT ] ──> [ VALIDATED ] ──> [ APPROVED ] ──> [ IN_USE ] ──> [ SUPERSEDED ]
                    │
                    └──> [ DRAFT ] (on rejection/edit)

Simulation Lifecycle:
[ NOT_STARTED ] ──> [ IN_PROGRESS ] ──> [ SUBMITTED ] ──> [ PROVISIONALLY_ASSESSED ] ──> [ HUMAN_REVIEWED ] ──> [ FINALIZED ]

ATS Export Lifecycle:
[ DRAFT ] ──> [ PREVIEWED ] ──> [ CONFIRMED ] ──> [ SENDING ] ──> [ SENT ]
      │                                                │
      └───<────────────────────────────────────────────┴─> [ RETRYABLE_FAILURE ] ──> [ SENDING ]
                                                       ├─> [ PERMANENT_FAILURE ]
                                                       └─> [ RECONCILIATION_REQUIRED ] ──> [ SENT / PERMANENT_FAILURE ]
```

---

## 5. Domain Abstract Interfaces (`backend/app/schemas/phase3_protocols.py`)

Narrow abstract protocol interfaces defined for implementation in subsequent phases:
- `InterviewBlueprintBuilder`
- `InterviewPolicyValidator`
- `QuestionWordingProvider`
- `DeterministicWordingProvider`
- `ModelGateway`
- `ModelOutputValidator`
- `AssessmentAssistant`
- `ATSAdapter`
- `SecretResolver`
- `DestinationPolicy`

---

## 6. Verification & Test Execution

### 6.1 Focused Phase 3A.2 Test Suite
Executed via `pytest tests/test_phase3a2_contracts.py`:
- `test_safety_policy_version_and_hash_stability`: Passed.
- `test_safety_policy_prohibited_topic_detection`: Passed.
- `test_interview_question_layer_scoring_invariants`: Passed.
- `test_rubric_scale_points_and_adversarial_topic_blocking`: Passed.
- `test_provider_capability_request_invariants`: Passed.
- `test_lifecycle_transition_enforcement`: Passed.
- `test_audit_event_security_redaction`: Passed.
- `test_no_vendor_sdk_imports_in_phase3_modules`: Passed.
- **Result**: **8 passed in 0.50s** (100% pass rate).

### 6.2 Full Regression Test Execution
- **Backend Full Suite**: **628 passed, 2 skipped, 23 warnings** in 11.33s.
- **Frontend Full Suite**: **78 passed** across 14 test files in 2.51s.
- **Frontend Build**: **Success** (Exit code 0, 55 modules transformed in 388ms).

---

## 7. Files Created & Modified

### Files Created:
1. `backend/app/schemas/phase3_enums.py`
2. `backend/app/schemas/safety_policy.py`
3. `backend/app/schemas/lifecycle.py`
4. `backend/app/schemas/interview_blueprint.py`
5. `backend/app/schemas/provider_capability.py`
6. `backend/app/schemas/simulation_assessment.py`
7. `backend/app/schemas/ats_dto.py`
8. `backend/app/schemas/phase3_audit.py`
9. `backend/app/schemas/phase3_protocols.py`
10. `backend/tests/test_phase3a2_contracts.py`
11. `docs/milestone-3/phase-3a-2-core-contracts-and-safety-policy.md`

### Files Modified:
1. `backend/app/schemas/__init__.py` (re-export of Phase 3A.2 public contract symbols)

---

## 8. Deferred Scope for Phase 3A.3

Phase 3A.3 will proceed with:
1. Deterministic interview question and rubric template generation (`DeterministicWordingProvider` live service).
2. Deterministic blueprint assembly engine (`InterviewBlueprintBuilder` live service) connecting Phase 2D requirement gap reports to structured common-core and supplemental interview plans.
3. Unit tests verifying deterministic blueprint generation and rubric completeness.
