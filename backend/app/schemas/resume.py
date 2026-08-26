from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models.resume import ProcessingJobStatus


class ResumeUploadResponse(BaseModel):
    artifact_id: UUID
    job_id: UUID
    status: ProcessingJobStatus = Field(default=ProcessingJobStatus.QUEUED)

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
