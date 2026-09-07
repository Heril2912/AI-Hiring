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

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

if TYPE_CHECKING:
    from app.models.auth import UserRecord
    from app.models.candidate import CandidateProfileRecord
    from app.models.job import JobRequisition, JobVersion


class MatchRunLifecycleStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class MatchAuditEventType(str, enum.Enum):
    MATCH_RUN_CREATED = "MATCH_RUN_CREATED"
    MATCH_RUN_SUCCEEDED = "MATCH_RUN_SUCCEEDED"
    MATCH_RUN_FAILED = "MATCH_RUN_FAILED"
    MATCH_RUN_REUSED = "MATCH_RUN_REUSED"
    MATCH_RESULTS_VIEWED = "MATCH_RESULTS_VIEWED"


class MatchRunRecord(Base):
    __tablename__ = "match_runs"
    __table_args__ = (
        UniqueConstraint(
            "recruiter_id",
            "idempotency_key",
            name="uq_match_runs_recruiter_id_idempotency_key",
        ),
        CheckConstraint(
            "lifecycle_status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ck_match_runs_lifecycle_status",
        ),
        CheckConstraint(
            "candidate_count >= 0",
            name="ck_match_runs_candidate_count",
        ),
        Index("ix_match_runs_recruiter_id", "recruiter_id"),
        Index("ix_match_runs_job_id", "job_id"),
        Index("ix_match_runs_job_version_id", "job_version_id"),
        Index("ix_match_runs_lifecycle_status", "lifecycle_status"),
        Index("ix_match_runs_created_at", "created_at"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    recruiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_match_runs_recruiter_id_users",
        ),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="RESTRICT",
            name="fk_match_runs_job_id_job_requisitions",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="RESTRICT",
            name="fk_match_runs_job_version_id_job_versions",
        ),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    evaluation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    match_input_schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
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
    candidate_input_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    input_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    lifecycle_status: Mapped[MatchRunLifecycleStatus] = mapped_column(
        Enum(
            MatchRunLifecycleStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_match_runs_lifecycle_status_enum",
        ),
        nullable=False,
        default=MatchRunLifecycleStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    error_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
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

    # Relationships
    recruiter: Mapped["UserRecord"] = relationship("UserRecord")
    requisition: Mapped["JobRequisition"] = relationship("JobRequisition")
    job_version: Mapped["JobVersion"] = relationship("JobVersion")
    results: Mapped[List["MatchResultRecord"]] = relationship(
        "MatchResultRecord",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MatchResultRecord.rank",
    )


class MatchResultRecord(Base):
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "profile_id",
            "profile_version",
            name="uq_match_results_run_id_profile_id_version",
        ),
        CheckConstraint(
            "raw_compatibility_score >= 0.0 AND raw_compatibility_score <= 100.0",
            name="ck_match_results_raw_score",
        ),
        CheckConstraint(
            "display_compatibility_score >= 0.0 AND display_compatibility_score <= 100.0",
            name="ck_match_results_display_score",
        ),
        CheckConstraint(
            "rank >= 1",
            name="ck_match_results_rank",
        ),
        CheckConstraint(
            "warning_count >= 0",
            name="ck_match_results_warning_count",
        ),
        CheckConstraint(
            "must_have_warning_count >= 0",
            name="ck_match_results_must_have_warning_count",
        ),
        Index("ix_match_results_run_id", "run_id"),
        Index("ix_match_results_profile_id", "profile_id"),
        Index("ix_match_results_run_id_rank", "run_id", "rank"),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "match_runs.run_id",
            ondelete="CASCADE",
            name="fk_match_results_run_id_match_runs",
        ),
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "candidate_profiles.profile_id",
            ondelete="RESTRICT",
            name="fk_match_results_profile_id_candidate_profiles",
        ),
        nullable=False,
    )
    profile_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    raw_compatibility_score: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6),
        nullable=False,
    )
    display_compatibility_score: Mapped[Decimal] = mapped_column(
        Numeric(precision=6, scale=2),
        nullable=False,
    )
    confidence_tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    warning_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    must_have_warning_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    is_tied: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    tie_group_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    score_decomposition: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    run: Mapped["MatchRunRecord"] = relationship(
        "MatchRunRecord",
        back_populates="results",
    )
    profile: Mapped["CandidateProfileRecord"] = relationship(
        "CandidateProfileRecord",
    )


class MatchAuditEventRecord(Base):
    __tablename__ = "match_audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('MATCH_RUN_CREATED', 'MATCH_RUN_SUCCEEDED', 'MATCH_RUN_FAILED', 'MATCH_RUN_REUSED', 'MATCH_RESULTS_VIEWED')",
            name="ck_match_audit_events_event_type",
        ),
        Index("ix_match_audit_events_run_id", "run_id"),
        Index("ix_match_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_match_audit_events_occurred_at", "occurred_at"),
        Index("ix_match_audit_events_event_type", "event_type"),
    )

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "match_runs.run_id",
            ondelete="SET NULL",
            name="fk_match_audit_events_run_id_match_runs",
        ),
        nullable=True,
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_match_audit_events_actor_user_id_users",
        ),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    job_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    revision: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    candidate_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    matcher_algorithm_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    scoring_policy_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    input_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
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
    run: Mapped[Optional["MatchRunRecord"]] = relationship("MatchRunRecord")
