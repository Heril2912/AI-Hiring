# Phase 3A.3 — Secure Provider Configuration, Destination Validation and Secret Boundaries Record

- **Date**: 2026-09-15
- **Branch**: `main`
- **Phase Name**: Phase 3A.3 (Secure Provider Configuration, Destination Policy, Secret Resolution, and Eligibility Assessment)

---

## 1. Executive Summary

Phase 3A.3 implements the secure configuration foundation, SSRF-resistant destination validation policy, Pydantic `SecretStr`-backed environment secret resolution, and pure configuration eligibility services for Milestone 3.

In strict compliance with locked project requirements:
- **AI is disabled by default** across application settings and provider profiles.
- **Zero real model requests, downloads, or ATS network calls** were made.
- **Zero vendor SDKs** were introduced; all implementations use standard Python libraries (`urllib.parse`, `ipaddress`, `socket`, `hashlib`, `os`) and existing project dependencies.
- **No plaintext credentials** are ever stored, serialized, or emitted in logs, representation methods (`__repr__`), or API responses.
- **No automatic local-to-cloud failover**.
- Phase 1 & Phase 2 deterministic parsing, matching, scoring, and gap report mechanics remain untouched and verified with 100% test pass rate.

---

## 2. Supported Provider Types & Egress Classifications

### 2.1 Provider Types
1. **`DISABLED`** (Default): All model interactions are inactive.
2. **`LOCAL_OPENAI_COMPATIBLE`**: Local model runner (future local Qwen3-4B GGUF via llama.cpp or Ollama on loopback `127.0.0.1:8080`).
3. **`REMOTE_OPENAI_COMPATIBLE`**: Remote cloud endpoint; requires explicit opt-in (`LLM_ALLOW_REMOTE=true`), allowlisted hostnames, and approved privacy review.
4. **`CUSTOM_ADAPTER`**: Reserved for specialized internal connectors.

### 2.2 Egress Classifications
- **`LOCAL_ONLY`**: Restricts traffic strictly to loopback interfaces (`127.0.0.1`, `::1`, `localhost` resolving to loopback).
- **`APPROVED_REMOTE`**: Requires HTTPS, server-owned hostname allowlisting, and verified non-private/non-metadata IP resolution.

---

## 3. Configuration & Settings Architecture

Defined in `backend/app/config.py` and documented in `.env.example`:

| Environment Variable | Default Value | Description |
|---|---|---|
| `LLM_ENABLED` | `false` | Master toggle for LLM capability operations. |
| `LLM_PROVIDER` | `disabled` | Active provider type identifier (`disabled`, `local_openai_compatible`, `remote_openai_compatible`). |
| `LLM_PROFILE_NAME` | `Local Qwen3-4B` | Human-readable profile display name. |
| `LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | Base API URL for OpenAI-compatible endpoint. |
| `LLM_MODEL` | `qwen3-4b-instruct` | Target model identifier. |
| `LLM_API_MODE` | `chat_completions` | API mode (`chat_completions`, `responses`, `custom`). |
| `LLM_API_KEY_SECRET_REF`| `env:LLM_API_KEY` | Controlled secret reference format. Never holds plaintext key. |
| `LLM_ALLOW_REMOTE` | `false` | Hard security gate required to enable remote egress. |
| `LLM_REMOTE_ALLOWED_HOSTS`| `""` | Comma-delimited list of authorized remote hostnames. |
| `LLM_CONNECT_TIMEOUT_SECONDS` | `5.0` | Connection timeout ceiling (0.1 to 300.0s). |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `30.0` | Read/request timeout ceiling (0.1 to 300.0s). |
| `LLM_MAX_INPUT_TOKENS` | `4096` | Upper token ceiling for model prompts. |
| `LLM_MAX_OUTPUT_TOKENS` | `600` | Upper token ceiling for model responses. |
| `LLM_MAX_RESPONSE_BYTES` | `262144` (256 KB) | Hard payload size limit to prevent memory exhaustion. |
| `LLM_MAX_CONCURRENCY` | `1` | Concurrency limiter (defaults to 1). |
| `LLM_RETRY_LIMIT` | `0` | Bounded retries for transient errors (0 to 3). |

---

## 4. Destination Policy & SSRF Protection

Implemented in `backend/app/services/destination_policy.py` (`StrictDestinationPolicy`):

1. **Standard URL Parser**: Built on standard `urllib.parse.urlsplit` to prevent substring and regex bypasses.
2. **Scheme Rules**:
   - `LOCAL_ONLY`: Allows `http` or `https`.
   - `APPROVED_REMOTE`: Strictly requires `https`.
3. **Prohibited URL Components**:
   - URL credentials (`username:password@host`) are rejected with `EMBEDDED_CREDENTIALS_FORBIDDEN`.
   - URL fragments (`#fragment`) and query strings (`?query`) are rejected.
4. **Local Destination Validation**:
   - Host must be in approved list (`127.0.0.1`, `::1`, `localhost`).
   - Port must match approved ports (`8080`, `8000`, `11434`).
   - DNS resolution verifies that all returned IPs are strictly loopback (`ip.is_loopback`).
5. **Remote Destination Validation**:
   - Hostname must match normalized server-owned allowlist (`LLM_REMOTE_ALLOWED_HOSTS`).
   - Dual-stack DNS resolution across IPv4 and IPv6 (`socket.AF_UNSPEC`).
   - Rejects private (`ip.is_private`), loopback (`ip.is_loopback`), multicast (`ip.is_multicast`), link-local (`ip.is_link_local`), unspecified (`0.0.0.0`), and cloud metadata (`169.254.169.254`) endpoints.
6. **DNS Rebinding Prevention Notice**:
   - While prevalidation blocks DNS resolution to private targets, the future HTTP client near connection time must disable redirects and re-validate resolved addresses to ensure complete rebinding protection.

---

## 5. Secret Resolution & Masking

Implemented in `backend/app/services/secret_resolver.py` (`EnvironmentSecretResolver`):

1. **Controlled Reference Format**: References must follow `env:<VAR_NAME>` where `<VAR_NAME>` is a valid Python identifier.
2. **Pydantic SecretStr Integration**:
   - Secrets are wrapped in `SecretStr`.
   - `str(secret)` returns `'**********'`.
   - `repr(secret)` returns `'SecretStr(\'**********\')'`.
   - `model_dump()` and `model_dump_json()` on `ProviderProfile` serialize only the reference string (`'env:LLM_API_KEY'`), never the underlying secret.
3. **Log & Error Redaction**: Plaintext secrets are never injected into exception messages or tracebacks. Unit tests verify that sample fake keys are absent from caplog output.

---

## 6. Provider Eligibility vs Health Separation

Implemented in `backend/app/services/provider_eligibility.py` (`evaluate_provider_eligibility`):

- **Eligibility Criteria**:
  - `enabled == true`
  - `provider_type != DISABLED`
  - `model_identifier` is non-empty
  - `compatibility_status != INCOMPATIBLE`
  - `privacy_review_status == APPROVED` (for remote providers)
  - Base URL satisfies `StrictDestinationPolicy`
  - Secret reference is resolvable and present
- **Health State Separation**:
  - Valid configuration produces `is_eligible = true` but leaves `compatibility_status = NOT_TESTED`.
  - A profile is never marked `HEALTHY` until an actual runtime capability probe is executed (deferred to Phase 3B).

---

## 7. Persistence Architecture Decision

- **Decision**: In alignment with the Phase 3A.1 entry audit and the server-owned configuration paradigm, the active provider configuration is managed via immutable `Settings` and the server-owned `ProviderProfile` schema.
- **Database Migrations**: Speculative PostgreSQL tables for provider profiles were intentionally avoided in Phase 3A.3. All database integrity is preserved cleanly at migration head `f35cae6d57b1`.

---

## 8. Verification & Test Results

### 8.1 Focused Phase 3A.3 Suite (`pytest tests/test_phase3a3_provider_config.py`)
- `test_default_disabled_configuration`: Passed.
- `test_local_provider_configuration_and_destination_policy`: Passed (loopback validation, port gating, credential rejection).
- `test_remote_destination_policy_and_ssrf_blocking`: Passed (remote opt-in, allowlist check, private IP & metadata SSRF blocking).
- `test_secret_resolver_masking_and_non_serialization`: Passed (masking, non-serialization, caplog log assertion).
- `test_provider_eligibility_vs_health_separation`: Passed.
- **Result**: **5 passed in 0.41s** (100% pass rate).

### 8.2 Full Baseline Test Execution
- **Backend Full Suite**: **633 passed, 2 skipped, 23 warnings** in 10.11s.
- **Frontend Full Suite**: **78 passed** (14 test files) in 2.39s.
- **Frontend Production Build**: **Success** (55 modules transformed in 388ms).

---

## 9. Files Created & Modified

### Files Created:
1. `backend/app/schemas/provider_profile.py`
2. `backend/app/services/destination_policy.py`
3. `backend/app/services/secret_resolver.py`
4. `backend/app/services/provider_eligibility.py`
5. `backend/tests/test_phase3a3_provider_config.py`
6. `docs/milestone-3/phase-3a-3-provider-config-and-secret-boundaries.md`

### Files Modified:
1. `backend/app/config.py` (LLM configuration fields and validators)
2. `backend/app/schemas/phase3_enums.py` (extended with `ProviderApiMode`, `ProviderEgressClass`, `ProviderCompatibilityStatus`, `PrivacyReviewStatus`)
3. `backend/app/schemas/__init__.py` (exported Phase 3A.3 provider configuration symbols)
4. `.env.example` (documented LLM provider settings template)

---

## 10. Deferred Scope for Phase 3A.4

Phase 3A.4 will proceed with:
1. Deterministic interview question and rubric template generation (`DeterministicWordingProvider` live service).
2. Deterministic blueprint assembly engine (`InterviewBlueprintBuilder` live service) connecting Phase 2D requirement gap reports to structured common-core and supplemental interview plans.
3. Unit tests verifying deterministic blueprint generation and rubric completeness.
