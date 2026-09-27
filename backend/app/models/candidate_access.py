import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

json_type = JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

if TYPE_CHECKING:
    from app.models.auth import UserRecord
    from app.models.candidate import CandidateIdentityRecord, CandidateProfileRecord
    from app.models.interview import AiInterviewQuestionSetRecord, JobInterviewTemplateRecord
    from app.models.job import JobRequisition, JobVersion
    from app.models.matching import MatchResultRecord
    from app.models.resume import ResumeArtifact


class CandidateBindingStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class CandidateInvitationRecord(Base):
    __tablename__ = "candidate_invitations"
    __table_args__ = (
        CheckConstraint(
            "length(token_hash) = 64",
            name="ck_candidate_invitations_token_hash_length",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_candidate_invitations_token_hash",
        ),
        Index("ix_candidate_invitations_token_hash", "token_hash"),
        Index("ix_candidate_invitations_candidate_id", "candidate_id"),
        Index("ix_candidate_invitations_org_id", "organization_id"),
        Index("ix_candidate_invitations_created_by", "created_by_user_id"),
        Index("ix_candidate_invitations_resulting_user", "resulting_user_id"),
    )

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_candidate_invitations_candidate_id_identities",
        ),
        nullable=False,
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="CANDIDATE_ACCESS",
        server_default=text("'CANDIDATE_ACCESS'"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_candidate_invitations_created_by_users",
        ),
        nullable=False,
    )
    resulting_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_candidate_invitations_resulting_user_id_users",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    candidate: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
    )
    created_by_user: Mapped["UserRecord"] = relationship(
        "UserRecord",
        foreign_keys=[created_by_user_id],
    )
    resulting_user: Mapped[Optional["UserRecord"]] = relationship(
        "UserRecord",
        foreign_keys=[resulting_user_id],
    )


class CandidateAccountBindingRecord(Base):
    __tablename__ = "candidate_account_bindings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED')",
            name="ck_candidate_account_bindings_status",
        ),
        UniqueConstraint(
            "user_id",
            name="uq_candidate_account_bindings_user_id",
        ),
        Index("ix_candidate_account_bindings_user_id", "user_id"),
        Index("ix_candidate_account_bindings_candidate_id", "candidate_id"),
        Index("ix_candidate_account_bindings_org_id", "organization_id"),
        Index("ix_candidate_account_bindings_invitation_id", "invitation_id"),
    )

    binding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "users.user_id",
            ondelete="CASCADE",
            name="fk_candidate_account_bindings_user_id_users",
        ),
        nullable=False,
        unique=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_candidate_account_bindings_candidate_id_identities",
        ),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    invitation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_invitations.invitation_id",
            ondelete="RESTRICT",
            name="fk_candidate_account_bindings_invitation_id",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CandidateBindingStatus.ACTIVE.value,
        server_default=text("'ACTIVE'"),
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
    user: Mapped["UserRecord"] = relationship(
        "UserRecord",
    )
    candidate: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
    )
    invitation: Mapped["CandidateInvitationRecord"] = relationship(
        "CandidateInvitationRecord",
    )


class CandidatePracticeReleaseRecord(Base):
    __tablename__ = "candidate_practice_releases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RELEASED', 'REVOKED')",
            name="ck_candidate_practice_releases_status",
        ),
        CheckConstraint(
            "job_revision >= 1",
            name="ck_candidate_practice_releases_job_revision_positive",
        ),
        CheckConstraint(
            "set_version >= 1",
            name="ck_candidate_practice_releases_set_version_positive",
        ),
        Index("ix_candidate_practice_releases_candidate_id", "candidate_id"),
        Index("ix_candidate_practice_releases_org_id", "organization_id"),
        Index("ix_candidate_practice_releases_job_id", "job_id"),
        Index("ix_candidate_practice_releases_status", "status"),
        Index("ix_candidate_practice_releases_ai_set_id", "ai_set_id"),
        Index("ix_candidate_practice_releases_template_id", "template_id"),
    )

    release_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_releases_candidate_id",
        ),
        nullable=False,
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_releases_job_id",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_releases_job_version_id",
        ),
        nullable=False,
    )
    job_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "job_interview_templates.template_id",
            ondelete="SET NULL",
            name="fk_candidate_practice_releases_template_id",
        ),
        nullable=True,
    )
    ai_set_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "ai_interview_question_sets.ai_set_id",
            ondelete="SET NULL",
            name="fk_candidate_practice_releases_ai_set_id",
        ),
        nullable=True,
    )
    match_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "match_results.result_id",
            ondelete="SET NULL",
            name="fk_candidate_practice_releases_match_result_id",
        ),
        nullable=True,
    )
    set_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="RELEASED",
        server_default=text("'RELEASED'"),
    )
    released_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_candidate_practice_releases_released_by",
        ),
        nullable=False,
    )
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_candidate_practice_releases_revoked_by",
        ),
        nullable=True,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
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
    candidate: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
    )
    released_by_user: Mapped["UserRecord"] = relationship(
        "UserRecord",
        foreign_keys=[released_by_user_id],
    )
    revoked_by_user: Mapped[Optional["UserRecord"]] = relationship(
        "UserRecord",
        foreign_keys=[revoked_by_user_id],
    )
    job: Mapped["JobRequisition"] = relationship(
        "JobRequisition",
    )
    job_version: Mapped["JobVersion"] = relationship(
        "JobVersion",
    )
    template: Mapped[Optional["JobInterviewTemplateRecord"]] = relationship(
        "JobInterviewTemplateRecord",
    )
    ai_set: Mapped[Optional["AiInterviewQuestionSetRecord"]] = relationship(
        "AiInterviewQuestionSetRecord",
    )
    match_result: Mapped[Optional["MatchResultRecord"]] = relationship(
        "MatchResultRecord",
    )
    sessions: Mapped[List["CandidatePracticeSessionRecord"]] = relationship(
        "CandidatePracticeSessionRecord",
        back_populates="release",
        cascade="all, delete-orphan",
    )


class CandidatePracticeSessionRecord(Base):
    __tablename__ = "candidate_practice_sessions"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('IN_PROGRESS', 'QUESTION_GENERATING', 'AWAITING_ANSWER', 'ANSWER_SAVING', 'QUESTION_GENERATION_FAILED_RETRYABLE', 'FINAL_ANSWER_SAVING', 'FINAL_REVIEW_GENERATING', 'FINAL_REVIEW_FAILED_RETRYABLE', 'COMPLETED', 'ABANDONED', 'EXPIRED', 'REVOKED')",
            name="ck_candidate_practice_sessions_lifecycle",
        ),
        CheckConstraint(
            "current_section IN ('CONVERSATION', 'MCQ', 'COMPLETE')",
            name="ck_candidate_practice_sessions_section",
        ),
        CheckConstraint(
            "length(snapshot_hash) = 64",
            name="ck_candidate_practice_sessions_snapshot_hash_length",
        ),
        Index("ix_candidate_practice_sessions_candidate_id", "candidate_id"),
        Index("ix_candidate_practice_sessions_org_id", "organization_id"),
        Index("ix_candidate_practice_sessions_release_id", "release_id"),
        Index("ix_candidate_practice_sessions_job_id", "job_id"),
        Index("ix_candidate_practice_sessions_status", "lifecycle_status"),
        Index("ix_candidate_practice_sessions_started_at", "started_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    binding_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_account_bindings.binding_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_sessions_binding_id",
        ),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_sessions_candidate_id",
        ),
        nullable=False,
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_releases.release_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_sessions_release_id",
        ),
        nullable=False,
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_sessions_job_id",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_sessions_job_version_id",
        ),
        nullable=False,
    )
    job_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    ai_set_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "ai_interview_question_sets.ai_set_id",
            ondelete="SET NULL",
            name="fk_candidate_practice_sessions_ai_set_id",
        ),
        nullable=True,
    )
    set_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    snapshot_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    questions_snapshot: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="IN_PROGRESS",
        server_default=text("'IN_PROGRESS'"),
    )
    current_section: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="CONVERSATION",
        server_default=text("'CONVERSATION'"),
    )
    current_conv_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    current_conv_turn_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    current_mcq_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_conv_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_mcq_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_response_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    model_call_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    concurrency_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    abandoned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    retention_class: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="SIMULATION_CONTENT",
        server_default=text("'SIMULATION_CONTENT'"),
    )
    fallback_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    fallback_reason: Mapped[Optional[str]] = mapped_column(
        String(50),
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
    binding: Mapped["CandidateAccountBindingRecord"] = relationship(
        "CandidateAccountBindingRecord",
    )
    candidate: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
    )
    release: Mapped["CandidatePracticeReleaseRecord"] = relationship(
        "CandidatePracticeReleaseRecord",
        back_populates="sessions",
    )
    job: Mapped["JobRequisition"] = relationship(
        "JobRequisition",
    )
    job_version: Mapped["JobVersion"] = relationship(
        "JobVersion",
    )
    ai_set: Mapped[Optional["AiInterviewQuestionSetRecord"]] = relationship(
        "AiInterviewQuestionSetRecord",
    )
    messages: Mapped[List["CandidatePracticeMessageRecord"]] = relationship(
        "CandidatePracticeMessageRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CandidatePracticeMessageRecord.sequence_number",
    )
    mcq_answers: Mapped[List["CandidatePracticeMcqAnswerRecord"]] = relationship(
        "CandidatePracticeMcqAnswerRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CandidatePracticeMcqAnswerRecord.submitted_at",
    )
    answer_reviews: Mapped[List["CandidatePracticeAnswerReviewRecord"]] = relationship(
        "CandidatePracticeAnswerReviewRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CandidatePracticeAnswerReviewRecord.created_at",
    )
    reports: Mapped[List["CandidatePracticeReportRecord"]] = relationship(
        "CandidatePracticeReportRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CandidatePracticeReportRecord.report_version",
    )


class CandidatePracticeMessageRecord(Base):
    __tablename__ = "candidate_practice_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('INTERVIEWER', 'CANDIDATE')",
            name="ck_candidate_practice_messages_role",
        ),
        CheckConstraint(
            "message_kind IN ('GREETING', 'PRIMARY_QUESTION', 'ANSWER', 'ACKNOWLEDGEMENT', 'FOLLOW_UP')",
            name="ck_candidate_practice_messages_kind",
        ),
        UniqueConstraint(
            "session_id",
            "sequence_number",
            name="uq_candidate_practice_messages_session_seq",
        ),
        Index("ix_candidate_practice_messages_session_id", "session_id"),
        Index("ix_candidate_practice_messages_seq", "session_id", "sequence_number"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_sessions.session_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_messages_session_id",
        ),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    message_kind: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    source_question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    model_invocation_ref: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    session: Mapped["CandidatePracticeSessionRecord"] = relationship(
        "CandidatePracticeSessionRecord",
        back_populates="messages",
    )


class CandidatePracticeAnswerSegmentRecord(Base):
    __tablename__ = "candidate_practice_answer_segments"
    __table_args__ = (
        UniqueConstraint(
            "answer_id",
            "sequence_order",
            name="uq_candidate_practice_segments_answer_seq",
        ),
        Index("ix_cand_practice_segments_answer_id", "answer_id"),
        Index("ix_cand_practice_segments_session_id", "session_id"),
        Index("ix_cand_practice_segments_question_id", "question_id"),
    )

    segment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_sessions.session_id",
            ondelete="CASCADE",
            name="fk_cand_practice_segments_session_id",
        ),
        nullable=False,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_messages.message_id",
            ondelete="CASCADE",
            name="fk_cand_practice_segments_answer_id",
        ),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    sequence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    start_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    end_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    segment_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    segmentation_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="1.0.0",
        server_default=text("'1.0.0'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CandidatePracticeAnswerReviewRecord(Base):
    __tablename__ = "candidate_practice_answer_reviews"
    __table_args__ = (
        UniqueConstraint(
            "answer_id",
            name="uq_candidate_practice_answer_reviews_answer_id",
        ),
        UniqueConstraint(
            "session_id",
            "idempotency_key",
            name="uq_candidate_practice_answer_reviews_idempotency",
        ),
        Index("ix_cand_practice_reviews_session_id", "session_id"),
        Index("ix_cand_practice_reviews_question_id", "question_id"),
        Index("ix_cand_practice_reviews_answer_id", "answer_id"),
        Index("ix_cand_practice_reviews_status", "lifecycle_status"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_sessions.session_id",
            ondelete="CASCADE",
            name="fk_cand_practice_reviews_session_id",
        ),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_messages.message_id",
            ondelete="CASCADE",
            name="fk_cand_practice_reviews_answer_id",
        ),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="practice-answer-review.v1",
        server_default=text("'practice-answer-review.v1'"),
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="REVIEW_READY",
        server_default=text("'REVIEW_READY'"),
    )
    answer_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ASSESSABLE",
        server_default=text("'ASSESSABLE'"),
    )
    acknowledgement: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    strengths: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    improvement_areas: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    next_steps: Mapped[List[str]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    stronger_structure: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    dimension_levels: Mapped[Dict[str, str]] = mapped_column(
        json_type,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    follow_up_needed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    follow_up_question: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    uncertainty_codes: Mapped[List[str]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    provider_class: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    model_identifier: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    prompt_template_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    guardrail_policy_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    validation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PASSED",
        server_default=text("'PASSED'"),
    )
    retry_count: Mapped[int] = mapped_column(
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
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    session: Mapped["CandidatePracticeSessionRecord"] = relationship(
        "CandidatePracticeSessionRecord",
        back_populates="answer_reviews",
    )


class CandidatePracticeMcqAnswerRecord(Base):
    __tablename__ = "candidate_practice_mcq_answers"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "question_id",
            name="uq_candidate_practice_mcq_answers_session_question",
        ),
        Index("ix_candidate_practice_mcq_answers_session_id", "session_id"),
        Index("ix_candidate_practice_mcq_answers_question_id", "question_id"),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_sessions.session_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_mcq_answers_session_id",
        ),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    selected_option_id: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    is_correct: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    session: Mapped["CandidatePracticeSessionRecord"] = relationship(
        "CandidatePracticeSessionRecord",
        back_populates="mcq_answers",
    )


class CandidatePracticeRequestStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    RELEASED = "RELEASED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"


class CandidatePracticeRequestRecord(Base):
    __tablename__ = "candidate_practice_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUESTED', 'RELEASED', 'DECLINED', 'WITHDRAWN')",
            name="ck_candidate_practice_requests_status",
        ),
        Index("ix_candidate_practice_requests_candidate_id", "candidate_id"),
        Index("ix_candidate_practice_requests_org_id", "organization_id"),
        Index("ix_candidate_practice_requests_job_id", "job_id"),
        Index("ix_candidate_practice_requests_job_version_id", "job_version_id"),
        Index("ix_candidate_practice_requests_status", "status"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_requests_candidate_id",
        ),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_requests_job_id",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="CASCADE",
            name="fk_candidate_practice_requests_job_version_id",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=CandidatePracticeRequestStatus.REQUESTED.value,
        server_default=text("'REQUESTED'"),
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processed_by_recruiter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_candidate_practice_requests_processed_by",
        ),
        nullable=True,
    )
    resulting_release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_releases.release_id",
            ondelete="SET NULL",
            name="fk_candidate_practice_requests_resulting_release_id",
        ),
        nullable=True,
    )
    decline_reason: Mapped[Optional[str]] = mapped_column(
        Text,
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
    candidate: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
    )
    job: Mapped["JobRequisition"] = relationship(
        "JobRequisition",
    )
    job_version: Mapped["JobVersion"] = relationship(
        "JobVersion",
    )
    processed_by_recruiter: Mapped[Optional["UserRecord"]] = relationship(
        "UserRecord",
        foreign_keys=[processed_by_recruiter_id],
    )
    resulting_release: Mapped[Optional["CandidatePracticeReleaseRecord"]] = relationship(
        "CandidatePracticeReleaseRecord",
        foreign_keys=[resulting_release_id],
    )


class JobPracticeCatalogRecord(Base):
    __tablename__ = "job_practice_catalogs"
    __table_args__ = (
        UniqueConstraint("job_version_id", name="uq_job_practice_catalogs_job_version_id"),
        Index("ix_job_practice_catalogs_org_id", "organization_id"),
        Index("ix_job_practice_catalogs_job_id", "job_id"),
        Index("ix_job_practice_catalogs_is_published", "is_published"),
    )

    catalog_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="CASCADE",
            name="fk_job_practice_catalogs_job_id",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="CASCADE",
            name="fk_job_practice_catalogs_job_version_id",
        ),
        nullable=False,
    )
    safe_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    safe_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    skill_labels: Mapped[List[str]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    published_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_job_practice_catalogs_published_by",
        ),
        nullable=False,
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
    job: Mapped["JobRequisition"] = relationship(
        "JobRequisition",
    )
    job_version: Mapped["JobVersion"] = relationship(
        "JobVersion",
    )
    published_by_user: Mapped["UserRecord"] = relationship(
        "UserRecord",
        foreign_keys=[published_by_user_id],
    )


class CandidatePracticeReportRecord(Base):
    __tablename__ = "candidate_practice_reports"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "report_version",
            name="uq_candidate_practice_reports_session_version",
        ),
        UniqueConstraint(
            "session_id",
            "source_review_hash",
            name="uq_candidate_practice_reports_session_hash",
        ),
        Index("ix_cand_practice_reports_session_id", "session_id"),
        Index("ix_cand_practice_reports_candidate_id", "candidate_id"),
        Index("ix_cand_practice_reports_org_id", "organization_id"),
        Index("ix_cand_practice_reports_status", "lifecycle_status"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_sessions.session_id",
            ondelete="CASCADE",
            name="fk_cand_practice_reports_session_id",
        ),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_cand_practice_reports_candidate_id",
        ),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    report_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    schema_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="practice-coaching-summary.v1",
        server_default=text("'practice-coaching-summary.v1'"),
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="SUMMARY_READY",
        server_default=text("'SUMMARY_READY'"),
    )
    source_review_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    aggregation_policy_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="1.0.0",
        server_default=text("'1.0.0'"),
    )
    summary_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    strongest_areas: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    priority_improvements: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    competency_commentary: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    response_patterns: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    next_practice_plan: Mapped[List[str]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    competency_aggregates: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    dimension_aggregates: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    question_trend: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    trend_classification: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="NOT_ENOUGH_ASSESSABLE_DATA",
        server_default=text("'NOT_ENOUGH_ASSESSABLE_DATA'"),
    )
    mcq_breakdown: Mapped[Dict[str, Any]] = mapped_column(
        json_type,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    completion_counts: Mapped[Dict[str, Any]] = mapped_column(
        json_type,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    disclaimer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="This is practice coaching and not a hiring decision.",
        server_default=text("'This is practice coaching and not a hiring decision.'"),
    )
    provider_class: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    model_identifier: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    prompt_template_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    guardrail_policy_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    validation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PASSED",
        server_default=text("'PASSED'"),
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    superseded_by_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    session: Mapped["CandidatePracticeSessionRecord"] = relationship(
        "CandidatePracticeSessionRecord",
        back_populates="reports",
    )
    candidate: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
    )


class CandidateApplicationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    RESUME_PROCESSING = "RESUME_PROCESSING"
    READY_TO_SUBMIT = "READY_TO_SUBMIT"
    SUBMITTED = "SUBMITTED"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    WITHDRAWN = "WITHDRAWN"


class RecruiterReviewState(str, enum.Enum):
    RECEIVED = "RECEIVED"
    IN_REVIEW = "IN_REVIEW"
    INTERVIEW_READY = "INTERVIEW_READY"


class CandidateApplicationRecord(Base):
    __tablename__ = "candidate_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'RESUME_PROCESSING', 'READY_TO_SUBMIT', 'SUBMITTED', 'PROCESSING_FAILED', 'WITHDRAWN')",
            name="ck_candidate_applications_status",
        ),
        CheckConstraint(
            "recruiter_review_state IN ('RECEIVED', 'IN_REVIEW', 'INTERVIEW_READY')",
            name="ck_candidate_applications_recruiter_review_state",
        ),
        CheckConstraint(
            "job_revision >= 1",
            name="ck_candidate_applications_job_revision_positive",
        ),
        CheckConstraint(
            "profile_version IS NULL OR profile_version >= 1",
            name="ck_candidate_applications_profile_version_positive",
        ),
        CheckConstraint(
            "(status = 'WITHDRAWN' AND withdrawn_at IS NOT NULL) OR (status != 'WITHDRAWN' AND withdrawn_at IS NULL)",
            name="ck_candidate_applications_withdrawn_timestamp_consistency",
        ),
        Index("ix_candidate_applications_binding_id", "binding_id"),
        Index("ix_candidate_applications_candidate_id", "candidate_id"),
        Index("ix_candidate_applications_org_id", "organization_id"),
        Index("ix_candidate_applications_job_id", "job_id"),
        Index("ix_candidate_applications_artifact_id", "artifact_id"),
        Index("ix_candidate_applications_status", "status"),
        Index("ix_candidate_applications_recruiter_review_state", "recruiter_review_state"),
        Index("ix_candidate_applications_idempotency_key", "binding_id", "idempotency_key", unique=True),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "users.user_id",
            ondelete="CASCADE",
            name="fk_candidate_applications_user_id_users",
        ),
        nullable=True,
    )
    binding_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_account_bindings.binding_id",
            ondelete="CASCADE",
            name="fk_candidate_applications_binding_id_bindings",
        ),
        nullable=True,
    )
    candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_candidate_applications_candidate_id_identities",
        ),
        nullable=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="CASCADE",
            name="fk_candidate_applications_job_id_requisitions",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="CASCADE",
            name="fk_candidate_applications_job_version_id_versions",
        ),
        nullable=False,
    )
    job_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "resume_artifacts.artifact_id",
            ondelete="SET NULL",
            name="fk_candidate_applications_artifact_id_artifacts",
        ),
        nullable=True,
    )
    profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_profiles.profile_id",
            ondelete="RESTRICT",
            name="fk_candidate_applications_profile_id_profiles",
        ),
        nullable=True,
    )
    profile_version: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=CandidateApplicationStatus.DRAFT.value,
        server_default=text("'DRAFT'"),
    )
    recruiter_review_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=RecruiterReviewState.RECEIVED.value,
        server_default=text("'RECEIVED'"),
    )
    submission_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="CANDIDATE_PORTAL",
        server_default=text("'CANDIDATE_PORTAL'"),
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(
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
    binding: Mapped["CandidateAccountBindingRecord"] = relationship(
        "CandidateAccountBindingRecord",
    )
    candidate: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
    )
    job: Mapped["JobRequisition"] = relationship(
        "JobRequisition",
    )
    job_version: Mapped["JobVersion"] = relationship(
        "JobVersion",
    )
    artifact: Mapped[Optional["ResumeArtifact"]] = relationship(
        "ResumeArtifact",
    )
    profile: Mapped[Optional["CandidateProfileRecord"]] = relationship(
        "CandidateProfileRecord",
    )


class CandidateInterviewSessionRecord(Base):
    __tablename__ = "candidate_interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('IN_PROGRESS', 'SUBMITTED')",
            name="ck_candidate_interview_sessions_status",
        ),
        CheckConstraint(
            "job_revision >= 1",
            name="ck_candidate_interview_sessions_job_rev_positive",
        ),
        CheckConstraint(
            "set_version >= 1",
            name="ck_candidate_interview_sessions_set_ver_positive",
        ),
        CheckConstraint(
            "length(snapshot_hash) = 64",
            name="ck_candidate_interview_sessions_hash_length",
        ),
        Index("ix_candidate_interview_sessions_release_id", "release_id"),
        Index("ix_candidate_interview_sessions_candidate_id", "candidate_id"),
        Index("ix_candidate_interview_sessions_org_id", "organization_id"),
        Index("ix_candidate_interview_sessions_status", "status"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_practice_releases.release_id",
            ondelete="CASCADE",
            name="fk_candidate_interview_sessions_release_id",
        ),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_candidate_interview_sessions_candidate_id",
        ),
        nullable=False,
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        nullable=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="CASCADE",
            name="fk_candidate_interview_sessions_job_id",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="CASCADE",
            name="fk_candidate_interview_sessions_job_version_id",
        ),
        nullable=False,
    )
    job_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    ai_set_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey(
            "ai_interview_question_sets.ai_set_id",
            ondelete="SET NULL",
            name="fk_candidate_interview_sessions_ai_set_id",
        ),
        nullable=True,
    )
    set_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    snapshot_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    questions_snapshot: Mapped[List[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="IN_PROGRESS",
        server_default=text("'IN_PROGRESS'"),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
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
    candidate: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
    )
    release: Mapped["CandidatePracticeReleaseRecord"] = relationship(
        "CandidatePracticeReleaseRecord",
    )
    job: Mapped["JobRequisition"] = relationship(
        "JobRequisition",
    )
    job_version: Mapped["JobVersion"] = relationship(
        "JobVersion",
    )
    ai_set: Mapped[Optional["AiInterviewQuestionSetRecord"]] = relationship(
        "AiInterviewQuestionSetRecord",
    )
    answers: Mapped[List["CandidateInterviewAnswerRecord"]] = relationship(
        "CandidateInterviewAnswerRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CandidateInterviewAnswerRecord.answer_order",
    )


class CandidateInterviewAnswerRecord(Base):
    __tablename__ = "candidate_interview_answers"
    __table_args__ = (
        CheckConstraint(
            "question_format IN ('CONVERSATION', 'MCQ_SINGLE_ANSWER')",
            name="ck_candidate_interview_answers_format",
        ),
        UniqueConstraint(
            "session_id",
            "slot_id",
            name="uq_candidate_interview_answers_session_slot",
        ),
        Index("ix_candidate_interview_answers_session_id", "session_id"),
        Index("ix_candidate_interview_answers_slot_id", "slot_id"),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_interview_sessions.session_id",
            ondelete="CASCADE",
            name="fk_candidate_interview_answers_session_id",
        ),
        nullable=False,
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )
    question_format: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    text_answer: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    selected_option_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    answer_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    is_skipped: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
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

    session: Mapped["CandidateInterviewSessionRecord"] = relationship(
        "CandidateInterviewSessionRecord",
        back_populates="answers",
    )




