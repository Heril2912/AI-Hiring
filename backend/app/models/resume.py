import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.extraction import ResumeExtraction


class ArtifactFormat(str, enum.Enum):
    pdf = "pdf"
    docx = "docx"


class ArtifactValidationStatus(str, enum.Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


class ProcessingJobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ResumeArtifact(Base):
    __tablename__ = "resume_artifacts"
    __table_args__ = (
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_resume_artifacts_size_bytes_non_negative",
        ),
        CheckConstraint(
            "sha256_hash IS NULL OR length(sha256_hash) = 64",
            name="ck_resume_artifacts_sha256_hash_length",
        ),
        Index("ix_resume_artifacts_sha256_hash", "sha256_hash"),
    )

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    declared_mime_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    detected_format: Mapped[Optional[ArtifactFormat]] = mapped_column(
        Enum(
            ArtifactFormat,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_resume_artifacts_detected_format",
        ),
        nullable=True,
    )
    size_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )
    sha256_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    validation_status: Mapped[ArtifactValidationStatus] = mapped_column(
        Enum(
            ArtifactValidationStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_resume_artifacts_validation_status",
        ),
        nullable=False,
        default=ArtifactValidationStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    quarantine_key: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        unique=True,
    )
    retention_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    extraction: Mapped[Optional["ResumeExtraction"]] = relationship(
        "ResumeExtraction",
        back_populates="artifact",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_processing_jobs_attempt_count_non_negative",
        ),
        Index("ix_processing_jobs_artifact_id", "artifact_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "resume_artifacts.artifact_id",
            ondelete="CASCADE",
            name="fk_processing_jobs_artifact_id_resume_artifacts",
        ),
        nullable=False,
    )
    status: Mapped[ProcessingJobStatus] = mapped_column(
        Enum(
            ProcessingJobStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_processing_jobs_status",
        ),
        nullable=False,
        default=ProcessingJobStatus.QUEUED,
        server_default=text("'QUEUED'"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    safe_error_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
