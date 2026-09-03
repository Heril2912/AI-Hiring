import uuid
from datetime import datetime
from typing import Optional
from pydantic import Field, field_validator

from app.models.job import (
    EmploymentType,
    JobLifecycleStatus,
    JobVersionStatus,
    WorkplaceType,
)
from app.schemas.candidate import StrictSchema


class JobCreateRequest(StrictSchema):
    title: str = Field(min_length=1, max_length=255)
    department: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=255)
    employment_type: Optional[EmploymentType] = None
    workplace_type: Optional[WorkplaceType] = None
    openings_count: Optional[int] = Field(default=None, ge=1)
    internal_reference: Optional[str] = Field(default=None, max_length=100)
    summary: Optional[str] = Field(default=None, max_length=10000)
    responsibilities: Optional[str] = Field(default=None, max_length=50000)
    job_description_text: Optional[str] = Field(default=None, max_length=100000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be empty or whitespace.")
        return cleaned

    @field_validator("department", "location", "internal_reference")
    @classmethod
    def trim_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None

    @field_validator("summary", "responsibilities", "job_description_text")
    @classmethod
    def trim_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None


class JobDraftUpdateRequest(StrictSchema):
    expected_revision: int = Field(ge=1)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    department: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=255)
    employment_type: Optional[EmploymentType] = None
    workplace_type: Optional[WorkplaceType] = None
    openings_count: Optional[int] = Field(default=None, ge=1)
    internal_reference: Optional[str] = Field(default=None, max_length=100)
    summary: Optional[str] = Field(default=None, max_length=10000)
    responsibilities: Optional[str] = Field(default=None, max_length=50000)
    job_description_text: Optional[str] = Field(default=None, max_length=100000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Title cannot be empty or whitespace.")
            return cleaned
        return None

    @field_validator("department", "location", "internal_reference")
    @classmethod
    def trim_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None

    @field_validator("summary", "responsibilities", "job_description_text")
    @classmethod
    def trim_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None


class JobVersionSummaryResponse(StrictSchema):
    job_version_id: uuid.UUID
    version_number: int
    version_status: JobVersionStatus
    revision: int
    title: str
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    workplace_type: Optional[WorkplaceType] = None
    openings_count: Optional[int] = None
    internal_reference: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobVersionDetailResponse(StrictSchema):
    job_version_id: uuid.UUID
    job_id: uuid.UUID
    version_number: int
    version_status: JobVersionStatus
    revision: int
    title: str
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    workplace_type: Optional[WorkplaceType] = None
    openings_count: Optional[int] = None
    internal_reference: Optional[str] = None
    summary: Optional[str] = None
    responsibilities: Optional[str] = None
    job_description_text: Optional[str] = None
    taxonomy_version: Optional[str] = None
    parser_version: Optional[str] = None
    created_by_user_id: uuid.UUID
    approved_by_user_id: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class JobSummaryResponse(StrictSchema):
    job_id: uuid.UUID
    created_by_user_id: uuid.UUID
    status: JobLifecycleStatus
    created_at: datetime
    updated_at: datetime
    current_version: JobVersionSummaryResponse


class JobDetailResponse(StrictSchema):
    job_id: uuid.UUID
    created_by_user_id: uuid.UUID
    status: JobLifecycleStatus
    created_at: datetime
    updated_at: datetime
    current_version: JobVersionDetailResponse
