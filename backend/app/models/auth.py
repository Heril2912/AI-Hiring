import enum
import uuid
from datetime import datetime, timezone
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


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    RECRUITER = "RECRUITER"
    REVIEWER = "REVIEWER"
    CANDIDATE = "CANDIDATE"


class SessionRevokeReason(str, enum.Enum):
    LOGOUT = "LOGOUT"
    EXPIRED_IDLE = "EXPIRED_IDLE"
    EXPIRED_ABSOLUTE = "EXPIRED_ABSOLUTE"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    ADMIN_REVOKED = "ADMIN_REVOKED"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"


class AuditEventType(str, enum.Enum):
    LOGIN_ATTEMPT = "LOGIN_ATTEMPT"
    LOGOUT = "LOGOUT"
    SESSION_REVOKED = "SESSION_REVOKED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    USER_BOOTSTRAPPED = "USER_BOOTSTRAPPED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED"
    PROVIDER_PROFILE_CREATED = "PROVIDER_PROFILE_CREATED"
    PROVIDER_PROFILE_UPDATED = "PROVIDER_PROFILE_UPDATED"
    PROVIDER_PROFILE_ACTIVATED = "PROVIDER_PROFILE_ACTIVATED"
    PROVIDER_PROFILE_DISABLED = "PROVIDER_PROFILE_DISABLED"
    PROVIDER_CONFIG_REJECTED = "PROVIDER_CONFIG_REJECTED"
    PROVIDER_COMPATIBILITY_TESTED = "PROVIDER_COMPATIBILITY_TESTED"
    ACCESS_DENIED = "ACCESS_DENIED"
    CANDIDATE_INVITATION_CREATED = "CANDIDATE_INVITATION_CREATED"
    CANDIDATE_INVITATION_REVOKED = "CANDIDATE_INVITATION_REVOKED"
    CANDIDATE_ACTIVATED = "CANDIDATE_ACTIVATED"
    CANDIDATE_BINDING_UPDATED = "CANDIDATE_BINDING_UPDATED"


class AuditResult(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"


class AuditReasonCode(str, enum.Enum):
    CREDENTIALS_INVALID = "CREDENTIALS_INVALID"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    UNAUTHORIZED = "UNAUTHORIZED"
    SYSTEM_BOOTSTRAP = "SYSTEM_BOOTSTRAP"
    SUCCESSFUL_AUTHENTICATION = "SUCCESSFUL_AUTHENTICATION"
    PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"
    PROVIDER_CONFIGURED = "PROVIDER_CONFIGURED"
    PROVIDER_UPDATED = "PROVIDER_UPDATED"
    PROVIDER_ACTIVATED = "PROVIDER_ACTIVATED"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    PROVIDER_INVALID_CONFIG = "PROVIDER_INVALID_CONFIG"
    PROVIDER_INCOMPATIBLE = "PROVIDER_INCOMPATIBLE"
    PROVIDER_COMPATIBILITY_SUCCESS = "PROVIDER_COMPATIBILITY_SUCCESS"
    PROVIDER_COMPATIBILITY_FAILED = "PROVIDER_COMPATIBILITY_FAILED"
    ACCESS_DENIED = "ACCESS_DENIED"
    STALE_VERSION = "STALE_VERSION"
    MASS_ASSIGNMENT_ATTEMPT = "MASS_ASSIGNMENT_ATTEMPT"
    INVITATION_EXPIRED = "INVITATION_EXPIRED"
    INVITATION_REVOKED = "INVITATION_REVOKED"
    INVITATION_CONSUMED = "INVITATION_CONSUMED"
    INVITATION_INVALID = "INVITATION_INVALID"
    BINDING_SUSPENDED = "BINDING_SUSPENDED"
    INVITATION_CREATED = "INVITATION_CREATED"
    INVITATION_REVOKED_BY_RECRUITER = "INVITATION_REVOKED_BY_RECRUITER"
    CANDIDATE_ACCOUNT_ACTIVATED = "CANDIDATE_ACCOUNT_ACTIVATED"



class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "failed_login_count >= 0",
            name="ck_users_failed_login_count_non_negative",
        ),
        CheckConstraint(
            "length(trim(email)) > 0",
            name="ck_users_email_not_empty",
        ),
        CheckConstraint(
            "length(trim(display_name)) > 0",
            name="ck_users_display_name_not_empty",
        ),
        Index("ix_users_email", "email", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_users_role",
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
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
    sessions: Mapped[List["UserSessionRecord"]] = relationship(
        "UserSessionRecord",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_events: Mapped[List["SecurityAuditEventRecord"]] = relationship(
        "SecurityAuditEventRecord",
        back_populates="actor_user",
    )


class UserSessionRecord(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint(
            "idle_expires_at <= absolute_expires_at",
            name="ck_user_sessions_idle_lte_absolute_expiry",
        ),
        CheckConstraint(
            "length(token_hash) = 64",
            name="ck_user_sessions_token_hash_length",
        ),
        CheckConstraint(
            "length(csrf_token_hash) = 64",
            name="ck_user_sessions_csrf_token_hash_length",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_user_sessions_token_hash",
        ),
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_token_hash", "token_hash"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="CASCADE",
            name="fk_user_sessions_user_id_users",
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    csrf_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    idle_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoke_reason: Mapped[Optional[SessionRevokeReason]] = mapped_column(
        Enum(
            SessionRevokeReason,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_user_sessions_revoke_reason",
        ),
        nullable=True,
    )

    # Relationships
    user: Mapped["UserRecord"] = relationship(
        "UserRecord",
        back_populates="sessions",
    )


class SecurityAuditEventRecord(Base):
    __tablename__ = "security_audit_events"
    __table_args__ = (
        Index("ix_security_audit_events_occurred_at", "occurred_at"),
        Index("ix_security_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_security_audit_events_event_type", "event_type"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="SET NULL",
            name="fk_security_audit_events_actor_user_id_users",
        ),
        nullable=True,
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(
            AuditEventType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_security_audit_events_event_type",
        ),
        nullable=False,
    )
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    result: Mapped[AuditResult] = mapped_column(
        Enum(
            AuditResult,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_security_audit_events_result",
        ),
        nullable=False,
    )
    reason_code: Mapped[AuditReasonCode] = mapped_column(
        Enum(
            AuditReasonCode,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_security_audit_events_reason_code",
        ),
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
    actor_user: Mapped[Optional["UserRecord"]] = relationship(
        "UserRecord",
        back_populates="audit_events",
    )
