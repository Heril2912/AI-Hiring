"""Candidate Official Interview Schemas (Phase 4C.2).

Provides allowlisted DTOs for candidate interview session starting, fetching, answer persistence,
reviewing, and final submission.
Strictly excludes recruiter rubrics, correct MCQ keys, internal notes, LLM prompts, and scoring parameters.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    """Base schema rejecting extraneous fields."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CandidateInterviewMcqOptionDto(StrictSchema):
    """Candidate-safe MCQ option strictly omitting correctness."""
    id: str
    text: str


class CandidateInterviewQuestionDto(StrictSchema):
    """Candidate-safe frozen question item strictly omitting rubrics, explanations, and model settings."""
    slot_id: uuid.UUID
    question_order: int
    question_format: str  # "CONVERSATION" or "MCQ_SINGLE_ANSWER"
    question_text: str
    competency: Optional[str] = None
    is_supplemental: bool = False
    options: List[CandidateInterviewMcqOptionDto] = Field(default_factory=list)
    # Candidate saved answer progress for this question
    saved_text_answer: Optional[str] = None
    saved_selected_option_id: Optional[str] = None
    is_answered: bool = False
    saved_at: Optional[datetime] = None


class CandidateInterviewSessionResponse(StrictSchema):
    """Candidate-safe representation of an official interview session."""
    session_id: uuid.UUID
    release_id: uuid.UUID
    application_id: Optional[uuid.UUID] = None
    job_id: uuid.UUID
    job_title: str
    job_revision: int
    status: str  # "IN_PROGRESS" or "SUBMITTED"
    total_questions: int
    answered_questions: int
    started_at: datetime
    last_saved_at: datetime
    submitted_at: Optional[datetime] = None
    questions: List[CandidateInterviewQuestionDto] = Field(default_factory=list)


class CandidateSaveAnswerRequest(StrictSchema):
    """Payload to save or update an answer for a question in an in-progress session."""
    text_answer: Optional[str] = Field(default=None, max_length=10000)
    selected_option_id: Optional[str] = Field(default=None, max_length=20)


class CandidateSaveAnswerResponse(StrictSchema):
    """Result of saving an answer."""
    answer_id: uuid.UUID
    session_id: uuid.UUID
    slot_id: uuid.UUID
    is_answered: bool
    saved_at: datetime
    total_questions: int
    answered_questions: int
    message: str = "Answer saved successfully."


class CandidateSubmitInterviewRequest(StrictSchema):
    """Payload to submit the official interview."""
    confirmed_incomplete: bool = Field(
        default=False,
        description="Must be set to True if submitting with unanswered questions.",
    )


class CandidateSubmitInterviewResponse(StrictSchema):
    """Receipt returned upon successful final interview submission."""
    session_id: uuid.UUID
    release_id: uuid.UUID
    status: str  # "SUBMITTED"
    submitted_at: datetime
    total_questions: int
    answered_questions: int
    unanswered_questions: int
    message: str = "Official interview submitted successfully. Your responses have been recorded."
