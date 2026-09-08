import enum
import uuid
from datetime import datetime
from decimal import Decimal
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.job import (
    RequirementCategory,
    RequirementNecessity,
    RequirementPriority,
)
from app.schemas.requirement_gap import (
    GapReviewActionCode,
    RequirementGapState,
)
from app.schemas.requirement_match import MatchResultState

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

if TYPE_CHECKING:
    from app.models.auth import UserRecord
    from app.models.candidate import CandidateProfileRecord
    from app.models.job import JobRequisition, JobVersion
    from app.models.matching import MatchResultRecord, MatchRunRecord


class GapAuditEventType(str, enum.Enum):
    GAP_REPORT_CREATED = "GAP_REPORT_CREATED"
    GAP_REPORT_REUSED = "GAP_REPORT_REUSED"
    GAP_REPORT_CREATION_FAILED = "GAP_REPORT_CREATION_FAILED"
    GAP_REPORT_VIEWED = "GAP_REPORT_VIEWED"
    GAP_REPORT_JSON_ACCESSED = "GAP_REPORT_JSON_ACCESSED"


class GapReportRecord(Base):
    """Immutable gap-report header bound to organization/recruiter ownership,
    source match result, exact versions, and canonical fingerprints.
    """

    __tablename__ = "gap_reports"
    __table_args__ = (
        UniqueConstraint(
            "recruiter_id",
            "idempotency_key",
            name="uq_gap_reports_recruiter_id_idempotency_key",
        ),
        UniqueConstraint(
            "report_fingerprint",
            name="uq_gap_reports_report_fingerprint",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_gap_reports_revision_positive",
        ),
        CheckConstraint(
            "profile_version >= 1",
            name="ck_gap_reports_profile_version_positive",
        ),
        CheckConstraint(
            "total_requirements >= 0",
            name="ck_gap_reports_total_requirements_non_negative",
        ),
        Index("ix_gap_reports_recruiter_id", "recruiter_id"),
        Index("ix_gap_reports_match_result_id", "match_result_id"),
        Index("ix_gap_reports_match_run_id", "match_run_id"),
        Index("ix_gap_reports_job_id", "job_id"),
        Index("ix_gap_reports_job_version_id", "job_version_id"),
        Index("ix_gap_reports_profile_id", "profile_id"),
        Index("ix_gap_reports_created_at", "created_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    recruiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_gap_reports_recruiter_id_users",
        ),
        nullable=False,
    )
    match_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "match_runs.run_id",
            ondelete="RESTRICT",
            name="fk_gap_reports_match_run_id_match_runs",
        ),
        nullable=False,
    )
    match_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "match_results.result_id",
            ondelete="RESTRICT",
            name="fk_gap_reports_match_result_id_match_results",
        ),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="RESTRICT",
            name="fk_gap_reports_job_id_job_requisitions",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="RESTRICT",
            name="fk_gap_reports_job_version_id_job_versions",
        ),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "candidate_profiles.profile_id",
            ondelete="RESTRICT",
            name="fk_gap_reports_profile_id_candidate_profiles",
        ),
        nullable=False,
    )
    profile_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    evaluation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Version Provenance
    matcher_algorithm_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    matching_rule_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    scoring_policy_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    match_input_schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    taxonomy_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    gap_schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    gap_policy_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    wording_template_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Fingerprints & Idempotency
    source_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    report_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Summary Statistics
    total_requirements: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    covered_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    partially_covered_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    not_evidenced_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    unverified_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    conflicting_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    not_applicable_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    must_have_warning_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    recruiter: Mapped["UserRecord"] = relationship("UserRecord")
    requisition: Mapped["JobRequisition"] = relationship("JobRequisition")
    job_version: Mapped["JobVersion"] = relationship("JobVersion")
    match_run: Mapped["MatchRunRecord"] = relationship("MatchRunRecord")
    match_result: Mapped["MatchResultRecord"] = relationship("MatchResultRecord")
    profile: Mapped["CandidateProfileRecord"] = relationship("CandidateProfileRecord")
    items: Mapped[List["GapReportItemRecord"]] = relationship(
        "GapReportItemRecord",
        back_populates="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GapReportItemRecord.display_order",
    )


class GapReportItemRecord(Base):
    """Immutable individual requirement gap record inside a gap report."""

    __tablename__ = "gap_report_items"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "requirement_id",
            name="uq_gap_report_items_report_id_requirement_id",
        ),
        UniqueConstraint(
            "report_id",
            "display_order",
            name="uq_gap_report_items_report_id_display_order",
        ),
        CheckConstraint(
            "display_order >= 0",
            name="ck_gap_report_items_display_order_non_negative",
        ),
        CheckConstraint(
            "source_match_value >= 0.0 AND source_match_value <= 1.0",
            name="ck_gap_report_items_source_match_value_bounds",
        ),
        CheckConstraint(
            "measurable_shortfall_value IS NULL OR measurable_shortfall_value >= 0.0",
            name="ck_gap_report_items_shortfall_value_non_negative",
        ),
        CheckConstraint(
            "(measurable_shortfall_value IS NULL AND shortfall_unit IS NULL) OR (measurable_shortfall_value IS NOT NULL AND shortfall_unit IS NOT NULL)",
            name="ck_gap_report_items_shortfall_unit_required_with_value",
        ),
        Index("ix_gap_report_items_report_id", "report_id"),
        Index("ix_gap_report_items_requirement_id", "requirement_id"),
        Index("ix_gap_report_items_gap_state", "gap_state"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "gap_reports.report_id",
            ondelete="CASCADE",
            name="fk_gap_report_items_report_id_gap_reports",
        ),
        nullable=False,
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    category: Mapped[RequirementCategory] = mapped_column(
        Enum(
            RequirementCategory,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_gap_report_items_category_enum",
        ),
        nullable=False,
    )
    necessity: Mapped[RequirementNecessity] = mapped_column(
        Enum(
            RequirementNecessity,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_gap_report_items_necessity_enum",
        ),
        nullable=False,
    )
    priority: Mapped[RequirementPriority] = mapped_column(
        Enum(
            RequirementPriority,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_gap_report_items_priority_enum",
        ),
        nullable=False,
    )
    source_match_state: Mapped[MatchResultState] = mapped_column(
        Enum(
            MatchResultState,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_gap_report_items_source_match_state_enum",
        ),
        nullable=False,
    )
    source_match_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    gap_state: Mapped[RequirementGapState] = mapped_column(
        Enum(
            RequirementGapState,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_gap_report_items_gap_state_enum",
        ),
        nullable=False,
    )
    required_value: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    documented_value: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    measurable_shortfall_value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    shortfall_unit: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    shortfall_reason_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    evidence_references: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    review_action_code: Mapped[GapReviewActionCode] = mapped_column(
        Enum(
            GapReviewActionCode,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_gap_report_items_review_action_code_enum",
        ),
        nullable=False,
        default=GapReviewActionCode.NO_ACTION_REQUIRED,
    )
    must_have_warning_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    recruiter_wording: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    report: Mapped["GapReportRecord"] = relationship(
        "GapReportRecord",
        back_populates="items",
    )


class GapAuditEventRecord(Base):
    """Audit event tracking for gap report operations."""

    __tablename__ = "gap_audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('GAP_REPORT_CREATED', 'GAP_REPORT_REUSED', 'GAP_REPORT_CREATION_FAILED', 'GAP_REPORT_VIEWED', 'GAP_REPORT_JSON_ACCESSED')",
            name="ck_gap_audit_events_event_type",
        ),
        Index("ix_gap_audit_events_report_id", "report_id"),
        Index("ix_gap_audit_events_match_result_id", "match_result_id"),
        Index("ix_gap_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_gap_audit_events_occurred_at", "occurred_at"),
        Index("ix_gap_audit_events_event_type", "event_type"),
    )

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "gap_reports.report_id",
            ondelete="SET NULL",
            name="fk_gap_audit_events_report_id_gap_reports",
        ),
        nullable=True,
    )
    match_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "match_results.result_id",
            ondelete="SET NULL",
            name="fk_gap_audit_events_match_result_id_match_results",
        ),
        nullable=True,
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_gap_audit_events_actor_user_id_users",
        ),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    safe_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    actor_user: Mapped[Optional["UserRecord"]] = relationship("UserRecord")
    report: Mapped[Optional["GapReportRecord"]] = relationship("GapReportRecord")


# Immutability enforcement at ORM event layer
from sqlalchemy import event


@event.listens_for(GapReportRecord, "before_update")
def _prevent_gap_report_update(mapper, connection, target):
    raise ValueError("Gap reports are immutable and cannot be updated once persisted.")


@event.listens_for(GapReportItemRecord, "before_update")
def _prevent_gap_report_item_update(mapper, connection, target):
    raise ValueError("Gap report items are immutable and cannot be updated once persisted.")

