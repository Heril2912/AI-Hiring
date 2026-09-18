"""Pydantic schemas for Phase 3D.5 Dedicated AI Interview Questions Workspace.

Zero-leakage guarantees:
- Never includes deterministic question wording or alternative text.
- Never includes reasoning_content, chain-of-thought, or raw prompts.
- Never includes provider secrets or raw provider JSON.
- Never exposes Phase 2 match scores or ranks.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class FrozenSchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EligibleJobItemResponse(FrozenSchema):
    """Job selector option exposing minimum required fields only.
    
    Zero-leakage: does not expose full description or individual requirement text.
    """
    job_id: UUID
    job_title: str
    requirement_count: int
    current_ai_set_id: Optional[UUID] = None
    current_ai_set_status: Optional[str] = None


class EligibleJobsResponse(FrozenSchema):
    """List of jobs eligible for AI question generation."""
    items: List[EligibleJobItemResponse]


class AiQuestionSetGenerateRequest(BaseModel):
    """Server-authoritative generation command payload."""
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    force_regenerate: bool = False


class SafeRubricResponse(FrozenSchema):
    """Safe rubric details without leaking sensitive internal calibration logic."""
    rubric_id: UUID
    rubric_version: int
    competency_definition: str
    question_intent: str
    observable_indicators: List[str] = Field(default_factory=list)
    rating_anchors: Dict[str, str] = Field(default_factory=dict)
    sufficient_evidence_guidance: Optional[str] = None
    insufficient_evidence_guidance: Optional[str] = None
    permitted_probes: List[str] = Field(default_factory=list)


class AiQuestionSlotItemResponse(FrozenSchema):
    """Safe question slot inside an AI question set.
    
    Zero-leakage: deterministic_source_text and deterministic alternative texts
    are strictly omitted from this model.
    """
    slot_id: UUID
    display_order: int
    competency_name: str
    question_type: str
    estimated_time_minutes: int
    permitted_probes: List[str] = Field(default_factory=list)
    rubric: Optional[SafeRubricResponse] = None
    source_requirement_ids: List[UUID] = Field(default_factory=list)
    
    # AI question generation & review state
    ai_wording: Optional[str] = None
    review_state: str = "UNREVIEWED"  # UNREVIEWED, KEPT, EDITED, REVISED, RECRUITER_AUTHORED
    authoring_origin: str = "AI_GENERATED"  # AI_GENERATED, RECRUITER_EDITED, RECRUITER_AUTHORED
    validation_status: str = "PASSED"  # PASSED, PENDING, FAILED
    safe_failure_code: Optional[str] = None  # None if valid, else e.g. "SEMANTIC_VALIDATION_FAILED", "PROHIBITED_CONTENT"
    rationale_code: Optional[str] = None
    updated_at: Optional[datetime] = None


class AiQuestionSetDetailResponse(FrozenSchema):
    """Full detail view for the master-detail workspace /ai-interviews/:templateId or /ai-interviews/:aiSetId."""
    ai_set_id: UUID
    set_version: int
    template_id: Optional[UUID] = None
    source_template_version: Optional[int] = None
    source_mode: str = "BLUEPRINT_GROUNDED"  # BLUEPRINT_GROUNDED or REQUIREMENT_GROUNDED
    source_content_hash: str
    source_requirement_ids: List[UUID] = Field(default_factory=list)
    job_id: UUID
    job_title: str
    job_revision: int
    lifecycle_status: str  # DRAFT, STALE, VALIDATED, APPROVED
    is_immutable: bool
    content_hash: Optional[str] = None
    action: Optional[str] = None  # GENERATED or OPENED_EXISTING
    
    # Slots
    slots: List[AiQuestionSlotItemResponse] = Field(default_factory=list)
    total_slots_count: int
    generated_slots_count: int
    reviewed_slots_count: int
    
    # Staleness check
    is_source_stale: bool = False
    stale_reason: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime] = None


class AiQuestionSetSummaryResponse(FrozenSchema):
    """Card/row item for the /ai-interviews directory listing."""
    ai_set_id: UUID
    set_version: int
    template_id: Optional[UUID] = None
    source_mode: str = "BLUEPRINT_GROUNDED"
    job_id: UUID
    job_title: str
    lifecycle_status: str
    is_immutable: bool
    is_source_stale: bool = False
    generated_question_count: int
    total_blueprint_slots: int
    created_at: datetime
    updated_at: datetime


class AiQuestionSetDirectoryResponse(FrozenSchema):
    """Directory listing response with status counts."""
    sets: List[AiQuestionSetSummaryResponse]
    total_count: int
    awaiting_review_count: int
    ready_for_approval_count: int
    approved_count: int


class AiQuestionSlotUpdateRequest(BaseModel):
    """Request to update/review a single question slot."""
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(..., description="KEPT, EDITED, REVISED, MANUAL_AUTHOR")
    wording: Optional[str] = Field(default=None, max_length=1500)
    reason: Optional[str] = Field(default=None, max_length=500)


class AiQuestionSetValidateResponse(FrozenSchema):
    """Result of validating an AI question set."""
    is_valid: bool
    lifecycle_status: str
    blocking_errors: List[str] = Field(default_factory=list)
    safe_message: str


class AiQuestionSetApproveResponse(FrozenSchema):
    """Result of approving and sealing an AI question set."""
    ai_set_id: UUID
    set_version: int
    lifecycle_status: str = "APPROVED"
    is_immutable: bool = True
    content_hash: str
    approved_at: datetime
    safe_message: str
