import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import (
    AuthenticatedContext,
    _record_audit_event,
    require_admin,
    verify_csrf_and_origin,
)
from app.config import Settings, get_settings
from app.database import get_db
from app.models.auth import (
    AuditEventType,
    AuditReasonCode,
    AuditResult,
    SecurityAuditEventRecord,
    SessionRevokeReason,
    UserRecord,
    UserRole,
    UserSessionRecord,
)
from app.schemas.auth import (
    AdminPasswordResetRequest,
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    PaginatedSecurityAuditEventsResponse,
    SecurityAuditEventResponse,
    UserResponse,
)
from app.services.security import hash_password

logger = logging.getLogger("ai_hiring.api.admin")

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
)


@router.get(
    "/users",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="List Internal Users",
    description="Returns all internal accounts for Administrator management, ordered by created_at descending.",
)
async def list_users(
    auth_ctx: AuthenticatedContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[UserResponse]:
    stmt = select(UserRecord).order_by(UserRecord.created_at.desc())
    users = db.execute(stmt).scalars().all()
    return [
        UserResponse(
            user_id=u.user_id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            is_active=u.is_active,
            must_change_password=u.must_change_password,
            locked_until=u.locked_until,
            last_login_at=u.last_login_at,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Internal User",
    description=(
        "Creates a new internal ADMIN, RECRUITER, or REVIEWER account with a temporary password and must_change_password=true. "
        "Requires Admin role, CSRF header, and valid Origin."
    ),
)
async def create_user(
    create_req: AdminUserCreateRequest,
    auth_ctx: AuthenticatedContext = Depends(verify_csrf_and_origin),
    admin_auth: AuthenticatedContext = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    now = datetime.now(timezone.utc)

    # Check for existing email
    stmt = select(UserRecord).where(UserRecord.email == create_req.email)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "USER_ALREADY_EXISTS",
                "message": f"A user with email '{create_req.email}' already exists.",
            },
        )

    # Hash temporary password with versioned scrypt
    encoded_hash = hash_password(
        plaintext_password=create_req.temporary_password,
        n=settings.scrypt_n,
        r=settings.scrypt_r,
        p=settings.scrypt_p,
        dklen=settings.scrypt_dklen,
    )

    new_user = UserRecord(
        user_id=uuid.uuid4(),
        email=create_req.email,
        display_name=create_req.display_name,
        password_hash=encoded_hash,
        role=create_req.role,
        is_active=True,
        must_change_password=True,
        failed_login_count=0,
    )
    db.add(new_user)

    _record_audit_event(
        db=db,
        event_type=AuditEventType.USER_BOOTSTRAPPED,
        result=AuditResult.SUCCESS,
        reason_code=AuditReasonCode.SYSTEM_BOOTSTRAP,
        actor_user_id=admin_auth.user.user_id,
        resource_type="user",
        resource_id=str(new_user.user_id),
        safe_metadata={
            "created_email": new_user.email,
            "created_role": new_user.role.value,
        },
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "USER_ALREADY_EXISTS",
                "message": f"A user with email '{create_req.email}' already exists.",
            },
        )

    return UserResponse(
        user_id=new_user.user_id,
        email=new_user.email,
        display_name=new_user.display_name,
        role=new_user.role,
        is_active=new_user.is_active,
        must_change_password=new_user.must_change_password,
        locked_until=new_user.locked_until,
        last_login_at=new_user.last_login_at,
        created_at=new_user.created_at,
        updated_at=new_user.updated_at,
    )


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update User Account",
    description="Updates display name, role, or active status. If role or active state changes, all active sessions for the target user are revoked immediately.",
)
async def update_user(
    user_id: uuid.UUID,
    update_req: AdminUserUpdateRequest,
    auth_ctx: AuthenticatedContext = Depends(verify_csrf_and_origin),
    admin_auth: AuthenticatedContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    now = datetime.now(timezone.utc)

    stmt = select(UserRecord).where(UserRecord.user_id == user_id)
    target_user = db.execute(stmt).scalar_one_or_none()

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User not found."},
        )

    # Prevent demoting or deactivating the last active Admin
    is_demoting_or_deactivating_admin = (
        target_user.role == UserRole.ADMIN
        and target_user.is_active
        and (
            (update_req.role is not None and update_req.role != UserRole.ADMIN)
            or (update_req.is_active is False)
        )
    )

    if is_demoting_or_deactivating_admin:
        # Check active admin count
        count_stmt = select(func.count()).select_from(UserRecord).where(
            UserRecord.role == UserRole.ADMIN,
            UserRecord.is_active.is_(True),
        )
        active_admin_count = db.execute(count_stmt).scalar_one()
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "CANNOT_DEMOTE_LAST_ADMIN",
                    "message": "Cannot deactivate or demote the final active Administrator.",
                },
            )

    role_changed = update_req.role is not None and update_req.role != target_user.role
    active_changed = update_req.is_active is not None and update_req.is_active != target_user.is_active

    if update_req.display_name is not None:
        target_user.display_name = update_req.display_name

    if role_changed:
        old_role = target_user.role
        target_user.role = update_req.role
        _record_audit_event(
            db=db,
            event_type=AuditEventType.SESSION_REVOKED,
            result=AuditResult.SUCCESS,
            reason_code=AuditReasonCode.SYSTEM_BOOTSTRAP,
            actor_user_id=admin_auth.user.user_id,
            resource_type="user",
            resource_id=str(target_user.user_id),
            safe_metadata={
                "action": "ROLE_CHANGED",
                "old_role": old_role.value,
                "new_role": update_req.role.value,
            },
        )

    if active_changed:
        target_user.is_active = update_req.is_active
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCOUNT_LOCKED if not update_req.is_active else AuditEventType.ACCOUNT_UNLOCKED,
            result=AuditResult.SUCCESS,
            reason_code=AuditReasonCode.ACCOUNT_LOCKED if not update_req.is_active else AuditReasonCode.SUCCESSFUL_AUTHENTICATION,
            actor_user_id=admin_auth.user.user_id,
            resource_type="user",
            resource_id=str(target_user.user_id),
            safe_metadata={"is_active": update_req.is_active},
        )

    # If role or active status changed, revoke all active sessions for this target user
    if role_changed or active_changed:
        revoke_reason = SessionRevokeReason.ADMIN_REVOKED
        revoke_stmt = (
            update(UserSessionRecord)
            .where(
                UserSessionRecord.user_id == target_user.user_id,
                UserSessionRecord.revoked_at.is_(None),
            )
            .values(
                revoked_at=now,
                revoke_reason=revoke_reason,
            )
        )
        db.execute(revoke_stmt)

    db.commit()
    db.refresh(target_user)

    return UserResponse(
        user_id=target_user.user_id,
        email=target_user.email,
        display_name=target_user.display_name,
        role=target_user.role,
        is_active=target_user.is_active,
        must_change_password=target_user.must_change_password,
        locked_until=target_user.locked_until,
        last_login_at=target_user.last_login_at,
        created_at=target_user.created_at,
        updated_at=target_user.updated_at,
    )


@router.post(
    "/users/{user_id}/reset-password",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin Reset Temporary Password",
    description="Resets a target user's password to a temporary password, enforces must_change_password=true, clears cooldowns, and revokes all active sessions.",
)
async def reset_password(
    user_id: uuid.UUID,
    reset_req: AdminPasswordResetRequest,
    auth_ctx: AuthenticatedContext = Depends(verify_csrf_and_origin),
    admin_auth: AuthenticatedContext = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    now = datetime.now(timezone.utc)

    stmt = select(UserRecord).where(UserRecord.user_id == user_id)
    target_user = db.execute(stmt).scalar_one_or_none()

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User not found."},
        )

    # Hash new temporary password
    new_hash = hash_password(
        plaintext_password=reset_req.temporary_password,
        n=settings.scrypt_n,
        r=settings.scrypt_r,
        p=settings.scrypt_p,
        dklen=settings.scrypt_dklen,
    )

    target_user.password_hash = new_hash
    target_user.must_change_password = True
    target_user.failed_login_count = 0
    target_user.locked_until = None

    # Revoke all active sessions for the target user
    revoke_stmt = (
        update(UserSessionRecord)
        .where(
            UserSessionRecord.user_id == target_user.user_id,
            UserSessionRecord.revoked_at.is_(None),
        )
        .values(
            revoked_at=now,
            revoke_reason=SessionRevokeReason.PASSWORD_CHANGED,
        )
    )
    db.execute(revoke_stmt)

    _record_audit_event(
        db=db,
        event_type=AuditEventType.PASSWORD_CHANGED,
        result=AuditResult.SUCCESS,
        reason_code=AuditReasonCode.SYSTEM_BOOTSTRAP,
        actor_user_id=admin_auth.user.user_id,
        resource_type="user",
        resource_id=str(target_user.user_id),
        safe_metadata={"action": "ADMIN_PASSWORD_RESET"},
    )

    db.commit()
    db.refresh(target_user)

    return UserResponse(
        user_id=target_user.user_id,
        email=target_user.email,
        display_name=target_user.display_name,
        role=target_user.role,
        is_active=target_user.is_active,
        must_change_password=target_user.must_change_password,
        locked_until=target_user.locked_until,
        last_login_at=target_user.last_login_at,
        created_at=target_user.created_at,
        updated_at=target_user.updated_at,
    )


@router.get(
    "/security-events",
    response_model=PaginatedSecurityAuditEventsResponse,
    status_code=status.HTTP_200_OK,
    summary="List Security Audit Events",
    description="Returns safely bounded, paginated security audit events for Administrator inspection, ordered by occurred_at descending.",
)
async def list_security_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    auth_ctx: AuthenticatedContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PaginatedSecurityAuditEventsResponse:
    count_stmt = select(func.count()).select_from(SecurityAuditEventRecord)
    total = db.execute(count_stmt).scalar_one()

    stmt = (
        select(SecurityAuditEventRecord)
        .order_by(SecurityAuditEventRecord.occurred_at.desc())
        .limit(limit)
        .offset(offset)
    )
    records = db.execute(stmt).scalars().all()

    items = [
        SecurityAuditEventResponse(
            event_id=r.event_id,
            actor_user_id=r.actor_user_id,
            event_type=r.event_type,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            result=r.result,
            reason_code=r.reason_code,
            safe_metadata=r.safe_metadata,
            occurred_at=r.occurred_at,
        )
        for r in records
    ]

    return PaginatedSecurityAuditEventsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
