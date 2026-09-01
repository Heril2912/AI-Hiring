import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import Field, field_validator

from app.models.auth import (
    AuditEventType,
    AuditReasonCode,
    AuditResult,
    SessionRevokeReason,
    UserRole,
)
from app.schemas.candidate import StrictSchema
from app.services.security import canonicalize_email


class UserResponse(StrictSchema):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    locked_until: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class UserSessionResponse(StrictSchema):
    session_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    is_revoked: bool
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[SessionRevokeReason] = None


class SecurityAuditEventResponse(StrictSchema):
    event_id: uuid.UUID
    actor_user_id: Optional[uuid.UUID] = None
    event_type: AuditEventType
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    result: AuditResult
    reason_code: AuditReasonCode
    safe_metadata: Dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class BootstrapAdminInput(StrictSchema):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_and_canonicalize_email(cls, v: str) -> str:
        return canonicalize_email(v)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Display name cannot be empty or whitespace.")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not v.strip():
            raise ValueError("Password cannot be solely whitespace.")
        return v


class AuthErrorDetail(StrictSchema):
    code: str
    message: str


class LoginRequest(StrictSchema):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_and_canonicalize_email(cls, v: str) -> str:
        return canonicalize_email(v)


class LoginResponse(StrictSchema):
    user: UserResponse
    csrf_token: str


class AuthMeResponse(StrictSchema):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    idle_expires_at: datetime
    absolute_expires_at: datetime
    csrf_token: str


class ChangePasswordRequest(StrictSchema):
    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)
    new_password_confirmation: str = Field(min_length=8, max_length=255)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters.")
        if not v.strip():
            raise ValueError("New password cannot be solely whitespace.")
        return v

