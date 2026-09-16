import enum


class InterviewLayer(str, enum.Enum):
    """Structural layer of an interview question."""
    COMMON_CORE = "COMMON_CORE"
    SUPPLEMENTAL_EVIDENCE = "SUPPLEMENTAL_EVIDENCE"


class QuestionType(str, enum.Enum):
    """Categorical question taxonomy."""
    BEHAVIORAL = "BEHAVIORAL"
    SITUATIONAL = "SITUATIONAL"
    TECHNICAL = "TECHNICAL"
    EVIDENCE_CLARIFICATION = "EVIDENCE_CLARIFICATION"


class AuthoringOrigin(str, enum.Enum):
    """Provenance of the question text or rubric."""
    DETERMINISTIC = "DETERMINISTIC"
    AI_ASSISTED = "AI_ASSISTED"
    RECRUITER_EDITED = "RECRUITER_EDITED"


class ValidationState(str, enum.Enum):
    """Quality and safety validation state for interview items."""
    PENDING = "PENDING"
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"


class PlanLifecycle(str, enum.Enum):
    """Lifecycle states for interview plans/blueprints."""
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    IN_USE = "IN_USE"
    SUPERSEDED = "SUPERSEDED"


class SimulationLifecycle(str, enum.Enum):
    """Lifecycle states for candidate simulation sessions."""
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    PROVISIONALLY_ASSESSED = "PROVISIONALLY_ASSESSED"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    FINALIZED = "FINALIZED"


class ATSExportLifecycle(str, enum.Enum):
    """Lifecycle states for ATS export jobs."""
    DRAFT = "DRAFT"
    PREVIEWED = "PREVIEWED"
    CONFIRMED = "CONFIRMED"
    SENDING = "SENDING"
    SENT = "SENT"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ProviderType(str, enum.Enum):
    """Supported model provider adapter types."""
    DISABLED = "DISABLED"
    LOCAL_OPENAI_COMPATIBLE = "LOCAL_OPENAI_COMPATIBLE"
    REMOTE_OPENAI_COMPATIBLE = "REMOTE_OPENAI_COMPATIBLE"
    CUSTOM_ADAPTER = "CUSTOM_ADAPTER"


class ProviderApiMode(str, enum.Enum):
    """API mode supported by the provider endpoint."""
    CHAT_COMPLETIONS = "CHAT_COMPLETIONS"
    RESPONSES = "RESPONSES"
    CUSTOM = "CUSTOM"


class ProviderEgressClass(str, enum.Enum):
    """Network egress scope and isolation classification."""
    LOCAL_ONLY = "LOCAL_ONLY"
    APPROVED_REMOTE = "APPROVED_REMOTE"


class ProviderCompatibilityStatus(str, enum.Enum):
    """Health and compatibility test status of a provider profile."""
    NOT_TESTED = "NOT_TESTED"
    HEALTHY = "HEALTHY"
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    DISABLED = "DISABLED"


class PrivacyReviewStatus(str, enum.Enum):
    """Data protection and privacy review clearance state."""
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProviderOperation(str, enum.Enum):
    """Strictly allowlisted model capability operations.
    
    Prohibits generic operations (e.g., CHAT, RUN_PROMPT, COMPLETE_TEXT).
    """
    REWORD_QUESTION = "REWORD_QUESTION"
    CREATE_BOUNDED_VARIANTS = "CREATE_BOUNDED_VARIANTS"
    STRUCTURE_PROVISIONAL_ASSESSMENT = "STRUCTURE_PROVISIONAL_ASSESSMENT"
    SUMMARIZE_SELECTED_EVIDENCE = "SUMMARIZE_SELECTED_EVIDENCE"


class AuditRetentionClass(str, enum.Enum):
    """Data retention and governance classifications for Milestone 3 audit records."""
    IMMUTABLE_HIRING_EVIDENCE = "IMMUTABLE_HIRING_EVIDENCE"
    DRAFT_CONTENT = "DRAFT_CONTENT"
    MODEL_PROVENANCE = "MODEL_PROVENANCE"
    SIMULATION_CONTENT = "SIMULATION_CONTENT"
    INTEGRATION_AUDIT = "INTEGRATION_AUDIT"
    OPERATIONAL_TRACE = "OPERATIONAL_TRACE"


class ValidationErrorCode(str, enum.Enum):
    """Machine-readable validation and policy failure codes."""
    INVALID_SCHEMA = "INVALID_SCHEMA"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    UNSUPPORTED_REFERENCE = "UNSUPPORTED_REFERENCE"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    PROHIBITED_TOPIC = "PROHIBITED_TOPIC"
    PROTECTED_ATTRIBUTE = "PROTECTED_ATTRIBUTE"
    INTENT_CHANGED = "INTENT_CHANGED"
    DUPLICATE_OUTPUT = "DUPLICATE_OUTPUT"
    UNSAFE_CONTENT = "UNSAFE_CONTENT"
    STALE_SOURCE_VERSION = "STALE_SOURCE_VERSION"


class ProviderErrorCode(str, enum.Enum):
    """Machine-readable provider failure codes."""
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"
    PROVIDER_RESPONSE_INVALID = "PROVIDER_RESPONSE_INVALID"
    PROVIDER_POLICY_REJECTED = "PROVIDER_POLICY_REJECTED"
    PROVIDER_CONTEXT_TOO_LARGE = "PROVIDER_CONTEXT_TOO_LARGE"
    PROVIDER_RESPONSE_TOO_LARGE = "PROVIDER_RESPONSE_TOO_LARGE"
    PROFILE_INCOMPATIBLE = "PROFILE_INCOMPATIBLE"
    DESTINATION_DENIED = "DESTINATION_DENIED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"

