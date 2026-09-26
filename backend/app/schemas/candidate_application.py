"""Candidate-Safe Application Response and Request Schemas (Phase 4B.4).

Provides allowlisted DTOs for candidate application submission, application detail,
My Applications listing, and application withdrawal.
Strictly excludes recruiter notes, scoring parameters, AI prompts, candidate rankings, and ATS identifiers.
"""
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import Field

from app.models.candidate_access import CandidateApplicationStatus
from app.schemas.candidate import StrictSchema
from app.schemas.candidate_job import CandidateJobSummaryResponse


class CandidateApplicationSubmitRequest(StrictSchema):
    """Input payload for applying to an open job."""
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional idempotency key to prevent double submissions.",
    )
    expected_revision: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional expected revision number for optimistic stale view detection.",
    )


class CandidateApplicationResponse(StrictSchema):
    """Safe, allowlisted details of a submitted or withdrawn candidate application."""
    application_id: uuid.UUID
    job_id: uuid.UUID
    job_version_id: uuid.UUID
    job_revision: int
    profile_version: int
    status: CandidateApplicationStatus
    submitted_at: datetime
    withdrawn_at: Optional[datetime] = None
    can_withdraw: bool = Field(
        description="True if application is in SUBMITTED status and permitted for candidate withdrawal."
    )
    job: CandidateJobSummaryResponse


class CandidateApplicationListResponse(StrictSchema):
    """Paginated list of candidate's own submitted and withdrawn applications."""
    items: List[CandidateApplicationResponse] = Field(default_factory=list)
    total: int
    page: int
    limit: int
