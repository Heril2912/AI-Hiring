from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models.resume import ArtifactFormat, ArtifactValidationStatus, ProcessingJobStatus


class ResumeUploadResponse(BaseModel):
    artifact_id: UUID
    job_id: UUID
    status: ProcessingJobStatus = Field(default=ProcessingJobStatus.QUEUED)

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ResumeStatusResponse(BaseModel):
    artifact_id: UUID
    job_id: UUID
    detected_format: Optional[ArtifactFormat] = None
    validation_status: ArtifactValidationStatus
    processing_status: ProcessingJobStatus
    attempt_count: int
    safe_error_code: Optional[str] = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ResumeUploadErrorDetail(BaseModel):
    code: str
    message: str

    model_config = ConfigDict(
        extra="forbid",
    )
