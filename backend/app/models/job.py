import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.auth import UserRecord


class JobLifecycleStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class JobVersionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERNSHIP = "INTERNSHIP"
    TEMPORARY = "TEMPORARY"


class WorkplaceType(str, enum.Enum):
    ON_SITE = "ON_SITE"
    HYBRID = "HYBRID"
    REMOTE = "REMOTE"


class JobRequisition(Base):
    __tablename__ = "job_requisitions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="ck_job_requisitions_status",
        ),
        Index("ix_job_requisitions_created_by_user_id", "created_by_user_id"),
        Index("ix_job_requisitions_status", "status"),
        Index("ix_job_requisitions_created_by_updated_at", "created_by_user_id", "updated_at"),
        Index("ix_job_requisitions_idempotency_key", "idempotency_key"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_job_requisitions_created_by_user_id_users",
        ),
        nullable=False,
    )
    status: Mapped[JobLifecycleStatus] = mapped_column(
        Enum(
            JobLifecycleStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_requisitions_status_enum",
        ),
        nullable=False,
        default=JobLifecycleStatus.ACTIVE,
        server_default=text("'ACTIVE'"),
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    idempotency_payload_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
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
    creator: Mapped["UserRecord"] = relationship(
        "UserRecord",
        foreign_keys=[created_by_user_id],
    )
    versions: Mapped[List["JobVersion"]] = relationship(
        "JobVersion",
        back_populates="requisition",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="JobVersion.version_number.asc()",
    )


class JobVersion(Base):
    __tablename__ = "job_versions"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "version_number",
            name="uq_job_versions_job_id_version_number",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_job_versions_version_number_positive",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_job_versions_revision_positive",
        ),
        CheckConstraint(
            "openings_count IS NULL OR openings_count > 0",
            name="ck_job_versions_openings_count_positive",
        ),
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_job_versions_title_not_empty",
        ),
        CheckConstraint(
            "version_status IN ('DRAFT', 'APPROVED')",
            name="ck_job_versions_version_status",
        ),
        CheckConstraint(
            "employment_type IS NULL OR employment_type IN ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'INTERNSHIP', 'TEMPORARY')",
            name="ck_job_versions_employment_type",
        ),
        CheckConstraint(
            "workplace_type IS NULL OR workplace_type IN ('ON_SITE', 'HYBRID', 'REMOTE')",
            name="ck_job_versions_workplace_type",
        ),
        CheckConstraint(
            "summary IS NULL OR length(summary) <= 10000",
            name="ck_job_versions_summary_length",
        ),
        CheckConstraint(
            "responsibilities IS NULL OR length(responsibilities) <= 50000",
            name="ck_job_versions_responsibilities_length",
        ),
        CheckConstraint(
            "job_description_text IS NULL OR length(job_description_text) <= 100000",
            name="ck_job_versions_job_description_text_length",
        ),
        Index("ix_job_versions_job_id", "job_id"),
        Index("ix_job_versions_created_by_user_id", "created_by_user_id"),
        Index("ix_job_versions_version_status", "version_status"),
    )

    job_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="CASCADE",
            name="fk_job_versions_job_id_job_requisitions",
        ),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    version_status: Mapped[JobVersionStatus] = mapped_column(
        Enum(
            JobVersionStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_versions_version_status_enum",
        ),
        nullable=False,
        default=JobVersionStatus.DRAFT,
        server_default=text("'DRAFT'"),
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    department: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    employment_type: Mapped[Optional[EmploymentType]] = mapped_column(
        Enum(
            EmploymentType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_versions_employment_type_enum",
        ),
        nullable=True,
    )
    workplace_type: Mapped[Optional[WorkplaceType]] = mapped_column(
        Enum(
            WorkplaceType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_versions_workplace_type_enum",
        ),
        nullable=True,
    )
    openings_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    internal_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    responsibilities: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    job_description_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    taxonomy_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    parser_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_job_versions_created_by_user_id_users",
        ),
        nullable=False,
    )
    approved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_job_versions_approved_by_user_id_users",
        ),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
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
    requisition: Mapped["JobRequisition"] = relationship(
        "JobRequisition",
        back_populates="versions",
    )
    creator: Mapped["UserRecord"] = relationship(
        "UserRecord",
        foreign_keys=[created_by_user_id],
    )
    approver: Mapped[Optional["UserRecord"]] = relationship(
        "UserRecord",
        foreign_keys=[approved_by_user_id],
    )
