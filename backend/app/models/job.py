import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

if TYPE_CHECKING:
    from app.models.auth import UserRecord
    from app.models.taxonomy import OccupationConcept, SkillConcept


class JobLifecycleStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class JobVersionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    READY_FOR_MATCHING = "READY_FOR_MATCHING"
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


class JobImportSourceType(str, enum.Enum):
    PASTED_TEXT = "PASTED_TEXT"
    PDF = "PDF"
    DOCX = "DOCX"


class JobImportStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPLIED = "APPLIED"
    DISCARDED = "DISCARDED"


class RequirementCategory(str, enum.Enum):
    SKILL = "SKILL"
    EXPERIENCE = "EXPERIENCE"
    RESPONSIBILITY = "RESPONSIBILITY"
    EDUCATION = "EDUCATION"
    CERTIFICATION = "CERTIFICATION"
    LANGUAGE = "LANGUAGE"
    OTHER = "OTHER"


class RequirementNecessity(str, enum.Enum):
    MUST_HAVE = "MUST_HAVE"
    PREFERRED = "PREFERRED"


class RequirementPriority(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RequirementOrigin(str, enum.Enum):
    RECRUITER_ENTERED = "RECRUITER_ENTERED"
    TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED = "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED"


class RequirementEvidenceType(str, enum.Enum):
    EMPLOYMENT = "EMPLOYMENT"
    PROJECT = "PROJECT"
    EDUCATION = "EDUCATION"
    CERTIFICATION = "CERTIFICATION"
    SKILL_LIST = "SKILL_LIST"
    PUBLICATION = "PUBLICATION"
    PATENT = "PATENT"
    OTHER = "OTHER"


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
        Index("ix_job_requisitions_deleted_at", "deleted_at"),
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
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_job_requisitions_deleted_by_user_id_users",
        ),
        nullable=True,
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
            "version_status IN ('DRAFT', 'READY_FOR_MATCHING', 'APPROVED')",
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
        Index("ix_job_versions_occupation_concept_id", "occupation_concept_id"),
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
    occupation_concept_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "occupation_concepts.concept_id",
            ondelete="SET NULL",
            name="fk_job_versions_occupation_concept_id_occupation_concepts",
        ),
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
    ready_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_job_versions_ready_by_user_id_users",
        ),
        nullable=True,
    )
    ready_at: Mapped[Optional[datetime]] = mapped_column(
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
    ready_by_user: Mapped[Optional["UserRecord"]] = relationship(
        "UserRecord",
        foreign_keys=[ready_by_user_id],
    )
    occupation: Mapped[Optional["OccupationConcept"]] = relationship(
        "OccupationConcept",
        foreign_keys=[occupation_concept_id],
    )
    requirements: Mapped[List["JobRequirement"]] = relationship(
        "JobRequirement",
        back_populates="job_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="JobRequirement.display_order.asc()",
    )


class JobRequirement(Base):
    __tablename__ = "job_requirements"
    __table_args__ = (
        UniqueConstraint(
            "job_version_id",
            "category",
            "normalized_label",
            name="uq_job_requirements_version_category_normalized_label",
        ),
        CheckConstraint(
            "display_order >= 0",
            name="ck_job_requirements_display_order_non_negative",
        ),
        CheckConstraint(
            "length(trim(label)) > 0",
            name="ck_job_requirements_label_not_empty",
        ),
        CheckConstraint(
            "length(trim(normalized_label)) > 0",
            name="ck_job_requirements_normalized_label_not_empty",
        ),
        CheckConstraint(
            "category IN ('SKILL', 'EXPERIENCE', 'RESPONSIBILITY', 'EDUCATION', 'CERTIFICATION', 'LANGUAGE', 'OTHER')",
            name="ck_job_requirements_category",
        ),
        CheckConstraint(
            "necessity IN ('MUST_HAVE', 'PREFERRED')",
            name="ck_job_requirements_necessity",
        ),
        CheckConstraint(
            "priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')",
            name="ck_job_requirements_priority",
        ),
        CheckConstraint(
            "min_experience_months IS NULL OR min_experience_months > 0",
            name="ck_job_requirements_min_experience_positive",
        ),
        CheckConstraint(
            "recency_years IS NULL OR (recency_years >= 1 AND recency_years <= 50)",
            name="ck_job_requirements_recency_years_bounded",
        ),
        CheckConstraint(
            "custom_weight_override IS NULL OR (custom_weight_override >= 0.0 AND custom_weight_override <= 10.0)",
            name="ck_job_requirements_custom_weight_bounded",
        ),
        CheckConstraint(
            "rationale IS NULL OR length(rationale) <= 2000",
            name="ck_job_requirements_rationale_length",
        ),
        Index("ix_job_requirements_job_version_id", "job_version_id"),
        Index("ix_job_requirements_display_order", "job_version_id", "display_order"),
        Index("ix_job_requirements_taxonomy_skill_concept_id", "taxonomy_skill_concept_id"),
    )

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="CASCADE",
            name="fk_job_requirements_job_version_id_job_versions",
        ),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    category: Mapped[RequirementCategory] = mapped_column(
        Enum(
            RequirementCategory,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_requirements_category_enum",
        ),
        nullable=False,
        default=RequirementCategory.SKILL,
    )
    label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    normalized_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    taxonomy_skill_concept_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "skill_concepts.concept_id",
            ondelete="SET NULL",
            name="fk_job_requirements_taxonomy_skill_concept_id_skill_concepts",
        ),
        nullable=True,
    )
    necessity: Mapped[RequirementNecessity] = mapped_column(
        Enum(
            RequirementNecessity,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_requirements_necessity_enum",
        ),
        nullable=False,
        default=RequirementNecessity.MUST_HAVE,
    )
    priority: Mapped[RequirementPriority] = mapped_column(
        Enum(
            RequirementPriority,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_requirements_priority_enum",
        ),
        nullable=False,
        default=RequirementPriority.MEDIUM,
    )
    custom_weight_override: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    min_experience_months: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    recency_years: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    accepted_evidence_types: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    accepted_equivalents: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    rationale: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    origin: Mapped[RequirementOrigin] = mapped_column(
        Enum(
            RequirementOrigin,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_requirements_origin_enum",
        ),
        nullable=False,
        default=RequirementOrigin.RECRUITER_ENTERED,
        server_default=text("'RECRUITER_ENTERED'"),
    )
    review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    warning_metadata: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
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
    job_version: Mapped["JobVersion"] = relationship(
        "JobVersion",
        back_populates="requirements",
    )
    taxonomy_skill: Mapped[Optional["SkillConcept"]] = relationship(
        "SkillConcept",
        foreign_keys=[taxonomy_skill_concept_id],
    )


class JobDescriptionImport(Base):
    __tablename__ = "job_description_imports"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('PASTED_TEXT', 'PDF', 'DOCX')",
            name="ck_job_description_imports_source_type",
        ),
        CheckConstraint(
            "status IN ('PENDING_REVIEW', 'APPLIED', 'DISCARDED')",
            name="ck_job_description_imports_status",
        ),
        CheckConstraint(
            "length(trim(source_text)) > 0",
            name="ck_job_description_imports_source_text_not_empty",
        ),
        Index("ix_job_description_imports_created_by_user_id", "created_by_user_id"),
        Index("ix_job_description_imports_job_id", "job_id"),
        Index("ix_job_description_imports_job_version_id", "job_version_id"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="CASCADE",
            name="fk_job_description_imports_job_id_job_requisitions",
        ),
        nullable=True,
    )
    job_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="CASCADE",
            name="fk_job_description_imports_job_version_id_job_versions",
        ),
        nullable=True,
    )
    expected_revision: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_job_description_imports_created_by_user_id_users",
        ),
        nullable=False,
    )
    source_type: Mapped[JobImportSourceType] = mapped_column(
        Enum(
            JobImportSourceType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_description_imports_source_type_enum",
        ),
        nullable=False,
        default=JobImportSourceType.PASTED_TEXT,
    )
    source_filename: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    source_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    parser_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="1.0.0",
        server_default=text("'1.0.0'"),
    )
    taxonomy_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    status: Mapped[JobImportStatus] = mapped_column(
        Enum(
            JobImportStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_description_imports_status_enum",
        ),
        nullable=False,
        default=JobImportStatus.PENDING_REVIEW,
        server_default=text("'PENDING_REVIEW'"),
    )
    suggestions: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
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
    job: Mapped[Optional["JobRequisition"]] = relationship(
        "JobRequisition",
        foreign_keys=[job_id],
    )
    version: Mapped[Optional["JobVersion"]] = relationship(
        "JobVersion",
        foreign_keys=[job_version_id],
    )

