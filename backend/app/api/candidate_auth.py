import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import (
    CandidateAuthenticatedContext,
    GENERIC_AUTH_ERROR,
    UNAUTHENTICATED_ERROR,
    _clear_candidate_session_cookie,
    _create_db_session_with_collision_handling,
    _record_audit_event,
    _set_candidate_session_cookie,
    get_candidate_authenticated_context,
    require_candidate,
    verify_candidate_csrf_and_origin,
)
from app.config import Settings, get_settings
from app.database import get_db
from app.models.auth import (
    AuditEventType,
    AuditReasonCode,
    AuditResult,
    SessionRevokeReason,
    UserRecord,
    UserRole,
)
from app.models.candidate_access import (
    CandidateAccountBindingRecord,
    CandidateBindingStatus,
)
from app.schemas.candidate_access import (
    CandidateActivationRequest,
    CandidateActivationResponse,
    CandidateLoginRequest,
    CandidateLoginResponse,
    CandidateMeResponse,
)
from app.services.candidate_access_service import activate_candidate_account
from app.services.security import (
    dummy_verify_password,
    generate_secure_token,
    hash_password,
    hash_token,
    needs_rehash,
    verify_password,
)

logger = logging.getLogger("ai_hiring.api.candidate_auth")

router = APIRouter(
    prefix="/api/v1/candidate/auth",
    tags=["candidate_auth"],
)


@router.post(
    "/activate",
    response_model=CandidateActivationResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate Candidate Account with Single-Use Token",
)
async def activate_account(
    req: CandidateActivationRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CandidateActivationResponse:
    user, binding, user_session, raw_session_token, raw_csrf_token = activate_candidate_account(
        db=db,
        req=req,
        settings=settings,
    )
    _set_candidate_session_cookie(response, raw_session_token, settings)

    return CandidateActivationResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        candidate_id=binding.candidate_id,
        organization_id=binding.organization_id,
        binding_status=binding.status,
        csrf_token=raw_csrf_token,
    )


@router.post(
    "/login",
    response_model=CandidateLoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate Candidate and Create Isolated Candidate Session",
)
async def candidate_login(
    req: CandidateLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CandidateLoginResponse:
    now = datetime.now(timezone.utc)
    canonical_email = req.email

    stmt = select(UserRecord).where(UserRecord.email == canonical_email)
    user = db.execute(stmt).scalar_one_or_none()

    if user is None or user.role != UserRole.CANDIDATE:
        dummy_verify_password(req.password)
        _record_audit_event(
            db=db,
            event_type=AuditEventType.LOGIN_ATTEMPT,
            result=AuditResult.FAILURE,
            reason_code=AuditReasonCode.CREDENTIALS_INVALID,
            actor_user_id=None,
            safe_metadata={"attempted_email": canonical_email, "portal": "CANDIDATE"},
        )
        db.commit()
        raise GENERIC_AUTH_ERROR

    # Check cooldown / locked_until
    if user.locked_until is not None:
        locked_until_utc = user.locked_until
        if locked_until_utc.tzinfo is None:
            locked_until_utc = locked_until_utc.replace(tzinfo=timezone.utc)

        if now < locked_until_utc:
            dummy_verify_password(req.password)
            _record_audit_event(
                db=db,
                event_type=AuditEventType.LOGIN_ATTEMPT,
                result=AuditResult.DENIED,
                reason_code=AuditReasonCode.ACCOUNT_LOCKED,
                actor_user_id=user.user_id,
                safe_metadata={"cooldown_active": True, "portal": "CANDIDATE"},
            )
            db.commit()
            raise GENERIC_AUTH_ERROR
        else:
            user.locked_until = None
            user.failed_login_count = 0

    # Verify password with scrypt
    is_valid = verify_password(req.password, user.password_hash)

    if not is_valid or not user.is_active:
        user.failed_login_count += 1
        cooldown_applied = False
        if user.failed_login_count >= settings.login_failure_threshold:
            user.locked_until = now + timedelta(seconds=settings.login_cooldown_seconds)
            cooldown_applied = True
            _record_audit_event(
                db=db,
                event_type=AuditEventType.ACCOUNT_LOCKED,
                result=AuditResult.SUCCESS,
                reason_code=AuditReasonCode.ACCOUNT_LOCKED,
                actor_user_id=user.user_id,
                safe_metadata={"failure_count": user.failed_login_count, "portal": "CANDIDATE"},
            )

        _record_audit_event(
            db=db,
            event_type=AuditEventType.LOGIN_ATTEMPT,
            result=AuditResult.FAILURE,
            reason_code=AuditReasonCode.CREDENTIALS_INVALID if user.is_active else AuditReasonCode.UNAUTHORIZED,
            actor_user_id=user.user_id,
            safe_metadata={
                "cooldown_applied": cooldown_applied,
                "is_active": user.is_active,
                "portal": "CANDIDATE",
            },
        )
        db.commit()
        raise GENERIC_AUTH_ERROR

    # Verify active CandidateAccountBindingRecord
    binding_stmt = select(CandidateAccountBindingRecord).where(
        CandidateAccountBindingRecord.user_id == user.user_id
    )
    binding = db.execute(binding_stmt).scalar_one_or_none()
    if binding is None or binding.status != CandidateBindingStatus.ACTIVE.value:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.LOGIN_ATTEMPT,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.BINDING_SUSPENDED if (binding and binding.status == "SUSPENDED") else AuditReasonCode.UNAUTHORIZED,
            actor_user_id=user.user_id,
            safe_metadata={"status": binding.status if binding else "MISSING", "portal": "CANDIDATE"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CANDIDATE_ACCESS_SUSPENDED",
                "message": "Candidate account access is suspended.",
            },
        )

    # Successful login
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    # Rehash if necessary
    if needs_rehash(
        user.password_hash,
        target_n=settings.scrypt_n,
        target_r=settings.scrypt_r,
        target_p=settings.scrypt_p,
        target_dklen=settings.scrypt_dklen,
    ):
        user.password_hash = hash_password(
            plaintext_password=req.password,
            n=settings.scrypt_n,
            r=settings.scrypt_r,
            p=settings.scrypt_p,
            dklen=settings.scrypt_dklen,
        )

    user_session, raw_session_token, raw_csrf_token = _create_db_session_with_collision_handling(
        db=db,
        user_id=user.user_id,
        settings=settings,
        now=now,
    )

    _record_audit_event(
        db=db,
        event_type=AuditEventType.LOGIN_ATTEMPT,
        result=AuditResult.SUCCESS,
        reason_code=AuditReasonCode.SUCCESSFUL_AUTHENTICATION,
        actor_user_id=user.user_id,
        resource_type="user_session",
        resource_id=str(user_session.session_id),
        safe_metadata={"role": user.role.value, "portal": "CANDIDATE"},
    )

    db.commit()
    _set_candidate_session_cookie(response, raw_session_token, settings)

    return CandidateLoginResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        candidate_id=binding.candidate_id,
        organization_id=binding.organization_id,
        binding_status=binding.status,
        csrf_token=raw_csrf_token,
    )


@router.get(
    "/me",
    response_model=CandidateMeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current Authenticated Candidate Session",
)
async def get_candidate_me(
    cand_ctx: CandidateAuthenticatedContext = Depends(require_candidate),
    db: Session = Depends(get_db),
) -> CandidateMeResponse:
    user = cand_ctx.user
    session = cand_ctx.session
    binding = cand_ctx.binding

    # Generate fresh CSRF token
    raw_csrf_token = generate_secure_token()
    session.csrf_token_hash = hash_token(raw_csrf_token)
    db.commit()

    return CandidateMeResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        candidate_id=binding.candidate_id,
        organization_id=binding.organization_id,
        binding_status=binding.status,
        idle_expires_at=session.idle_expires_at,
        absolute_expires_at=session.absolute_expires_at,
        csrf_token=raw_csrf_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke Candidate Session and Clear Candidate Cookie",
)
async def candidate_logout(
    response: Response,
    cand_ctx: CandidateAuthenticatedContext = Depends(verify_candidate_csrf_and_origin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    now = datetime.now(timezone.utc)
    session = cand_ctx.session

    session.revoked_at = now
    session.revoke_reason = SessionRevokeReason.LOGOUT

    _record_audit_event(
        db=db,
        event_type=AuditEventType.LOGOUT,
        result=AuditResult.SUCCESS,
        reason_code=AuditReasonCode.SUCCESSFUL_AUTHENTICATION,
        actor_user_id=cand_ctx.user.user_id,
        resource_type="candidate_session",
        resource_id=str(session.session_id),
        safe_metadata={"revoke_reason": SessionRevokeReason.LOGOUT.value, "portal": "CANDIDATE"},
    )

    db.commit()
    _clear_candidate_session_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
