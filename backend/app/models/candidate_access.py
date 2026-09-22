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
    from app.models.candidate import CandidateIdentityRecord
    from app.models.interview import AiInterviewQuestionSetRecord, JobInterviewTemplateRecord
    from app.models.job import JobRequisition, JobVersion


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
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "candidate_invitations.invitation_id",
            ondelete="RESTRICT",
            name="fk_candidate_account_bindings_invitation_id",
        ),
        nullable=False,
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
    sessions: Mapped[List["CandidatePracticeSessionRecord"]] = relationship(
        "CandidatePracticeSessionRecord",
        back_populates="release",
        cascade="all, delete-orphan",
    )


class CandidatePracticeSessionRecord(Base):
    __tablename__ = "candidate_practice_sessions"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('IN_PROGRESS', 'COMPLETED', 'ABANDONED', 'EXPIRED', 'REVOKED')",
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
        String(30),
        nullable=False,
        default="IN_PROGRESS",
        server_default=text("'IN_PROGRESS'"),
    )
    current_section: Mapped[str] = mapped_column(
        String(30),
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
