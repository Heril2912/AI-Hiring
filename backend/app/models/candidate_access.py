import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.auth import UserRecord
    from app.models.candidate import CandidateIdentityRecord


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
