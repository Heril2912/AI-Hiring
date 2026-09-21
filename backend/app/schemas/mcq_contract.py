"""Pydantic schemas and contracts for Multiple Choice Questions (MCQ) in Phase 3F.2."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.phase3_enums import (
    AuthoringOrigin,
    QuestionDifficulty,
    QuestionFormat,
    ValidationState,
)


class StrictSchema(BaseModel):
    """Base schema rejecting extraneous fields."""
    model_config = ConfigDict(extra="forbid")


class FrozenSchema(BaseModel):
    """Immutable base schema rejecting extraneous fields."""
    model_config = ConfigDict(frozen=True, extra="forbid")


class McqOptionDto(StrictSchema):
    """A single option inside an MCQ."""
    option_id: str = Field(..., min_length=1, max_length=100)
    text: str = Field(..., min_length=1, max_length=500)


class McqItemDto(StrictSchema):
    """Recruiter-facing MCQ item with full answer key and explanation."""
    slot_id: UUID
    display_order: int
    question_format: QuestionFormat = QuestionFormat.MCQ_SINGLE_ANSWER
    question_text: str = Field(..., min_length=10, max_length=1200)
    options: List[McqOptionDto] = Field(..., min_length=2, max_length=5)
    correct_option_id: str = Field(..., min_length=1, max_length=100)
    answer_explanation: str = Field(..., min_length=1, max_length=1000)
    requirement_id: Optional[UUID] = None
    competency_name: str = Field(..., min_length=1, max_length=200)
    difficulty: QuestionDifficulty = QuestionDifficulty.FOUNDATIONAL
    authoring_origin: AuthoringOrigin = AuthoringOrigin.AI_GENERATED
    validation_status: ValidationState = ValidationState.PENDING
    safe_failure_code: Optional[str] = None
    updated_at: Optional[datetime] = None


class McqCreateRequest(StrictSchema):
    """Manual MCQ creation payload by recruiter."""
    question_text: str = Field(..., min_length=10, max_length=1200)
    options: List[McqOptionDto] = Field(..., min_length=2, max_length=5)
    correct_option_id: str = Field(..., min_length=1, max_length=100)
    answer_explanation: str = Field(..., min_length=1, max_length=1000)
    requirement_id: Optional[UUID] = None
    competency_name: Optional[str] = Field(default="General Competency", max_length=200)
    difficulty: QuestionDifficulty = QuestionDifficulty.FOUNDATIONAL


class McqUpdateRequest(StrictSchema):
    """Manual MCQ update payload by recruiter."""
    question_text: Optional[str] = Field(default=None, min_length=10, max_length=1200)
    options: Optional[List[McqOptionDto]] = Field(default=None, min_length=2, max_length=5)
    correct_option_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    answer_explanation: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    requirement_id: Optional[UUID] = None
    competency_name: Optional[str] = Field(default=None, max_length=200)
    difficulty: Optional[QuestionDifficulty] = None


class McqGenerateRequest(StrictSchema):
    """Server-authoritative generation request for MCQs."""
    count: int = Field(default=5, ge=1, le=10)
    difficulty: QuestionDifficulty = QuestionDifficulty.FOUNDATIONAL
    requirement_ids: Optional[List[UUID]] = None


class McqReorderRequest(StrictSchema):
    """Reorder payload for MCQs in a question set."""
    slot_ids: List[UUID] = Field(..., min_length=1)


# Structured AI Provider Output Contract
class StructuredAiMcqOption(StrictSchema):
    option_id: str
    text: str


class StructuredAiMcqQuestion(StrictSchema):
    question_text: str
    options: List[StructuredAiMcqOption]
    correct_option_id: str
    answer_explanation: str
    requirement_id: Optional[str] = None
    competency_id: Optional[str] = None
    difficulty: str = "FOUNDATIONAL"


class StructuredAiMcqBatchResponse(StrictSchema):
    questions: List[StructuredAiMcqQuestion]


# Candidate-Safe Practice Discovery Contracts
class CandidateSafeMcqOption(FrozenSchema):
    """Safe option for candidates omitting correctness."""
    option_id: str
    text: str


class CandidateSafeMcqItem(FrozenSchema):
    """Safe MCQ item for candidates strictly omitting correct option and explanation."""
    slot_id: UUID
    display_order: int
    question_format: QuestionFormat = QuestionFormat.MCQ_SINGLE_ANSWER
    question_text: str
    options: List[CandidateSafeMcqOption]
    competency_name: str
    difficulty: QuestionDifficulty


class CandidatePracticeJobSummary(FrozenSchema):
    """Safe job discovery card for candidates."""
    release_id: UUID
    job_id: UUID
    job_title: str
    department: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    conversation_question_count: int
    mcq_count: int
    released_at: datetime
    status_label: str = "Practice content ready"


class CandidatePracticeDiscoveryResponse(FrozenSchema):
    """List of active released practice jobs for authenticated candidate."""
    items: List[CandidatePracticeJobSummary]
