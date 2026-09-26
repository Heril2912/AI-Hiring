"""Candidate Application Service (Phase 4B.4).

Implements transactional, deny-by-default application submission, retrieval,
listing, and withdrawal for authenticated candidates.
Freezes authoritative job revision and profile version snapshots upon submission.
Enforces single-active-application constraints and idempotency protection.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.auth import AuditEventType, AuditReasonCode, AuditResult
from app.models.candidate import CandidateProfileRecord
from app.models.candidate_access import (
    CandidateApplicationRecord,
    CandidateApplicationStatus,
    CandidateBindingStatus,
)
from app.models.job import (
    JobLifecycleStatus,
    JobRequisition,
    JobVersion,
    JobVersionStatus,
)
from app.schemas.candidate_application import (
    CandidateApplicationListResponse,
    CandidateApplicationResponse,
    CandidateApplicationSubmitRequest,
)
from app.schemas.candidate_job import CandidateJobSummaryResponse
from app.services.candidate_authorization_kernel import (
    CandidatePrincipal,
    _record_authz_audit,
    load_scoped_candidate_application,
    load_scoped_candidate_profile,
)

logger = logging.getLogger("ai_hiring.services.candidate_application")


def _build_candidate_job_summary(job: JobRequisition, version: JobVersion) -> CandidateJobSummaryResponse:
    published_time = version.approved_at or version.updated_at or version.created_at
    return CandidateJobSummaryResponse(
        job_id=job.job_id,
        job_version_id=version.job_version_id,
        version_number=version.version_number,
        revision=version.revision,
        title=version.title,
        department=version.department,
        location=version.location,
        employment_type=version.employment_type,
        workplace_type=version.workplace_type,
        openings_count=version.openings_count,
        summary=version.summary,
        published_at=published_time,
        updated_at=version.updated_at or version.created_at,
    )


def _build_candidate_application_response(app_rec: CandidateApplicationRecord) -> CandidateApplicationResponse:
    job_summary = _build_candidate_job_summary(app_rec.job, app_rec.job_version)
    can_withdraw = app_rec.status == CandidateApplicationStatus.SUBMITTED.value
    return CandidateApplicationResponse(
        application_id=app_rec.application_id,
        job_id=app_rec.job_id,
        job_version_id=app_rec.job_version_id,
        job_revision=app_rec.job_revision,
        profile_version=app_rec.profile_version,
        status=CandidateApplicationStatus(app_rec.status),
        submitted_at=app_rec.submitted_at,
        withdrawn_at=app_rec.withdrawn_at,
        can_withdraw=can_withdraw,
        job=job_summary,
    )


def submit_candidate_application(
    principal: CandidatePrincipal,
    job_id: uuid.UUID,
    payload: CandidateApplicationSubmitRequest,
    db: Session,
) -> CandidateApplicationResponse:
    """Submits an application to an open, candidate-visible job with transactional consistency.
    
    1. Validates candidate account and binding are ACTIVE.
    2. Resolves candidate's latest profile and freezes profile_id / profile_version.
    3. Resolves active job requisition and latest APPROVED job revision.
    4. Validates optional expected_revision for stale-view detection.
    5. Checks idempotency: if key is provided and already exists with same intent, returns existing record.
    6. Ensures no existing active (SUBMITTED) application exists for (binding_id, job_id).
    7. Atomically creates CandidateApplicationRecord and records security audit event.
    """
    now = datetime.now(timezone.utc)

    # 1. Candidate binding check
    if principal.binding_status != CandidateBindingStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CANDIDATE_ACCESS_DENIED", "message": "Candidate account or binding is not active."},
        )

    # 2. Idempotency fast-path
    if payload.idempotency_key:
        stmt_idem = select(CandidateApplicationRecord).options(
            selectinload(CandidateApplicationRecord.job),
            selectinload(CandidateApplicationRecord.job_version),
            selectinload(CandidateApplicationRecord.profile),
        ).where(
            CandidateApplicationRecord.binding_id == principal.binding_id,
            CandidateApplicationRecord.idempotency_key == payload.idempotency_key,
        )
        existing_idem = db.execute(stmt_idem).scalar_one_or_none()
        if existing_idem:
            if existing_idem.job_id != job_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "IDEMPOTENCY_KEY_CONFLICT",
                        "message": "This idempotency key was previously used for a different job application.",
                    },
                )
            return _build_candidate_application_response(existing_idem)

    # 3. Resolve latest bound candidate profile
    stmt_profile = (
        select(CandidateProfileRecord)
        .where(CandidateProfileRecord.identity_id == principal.candidate_id)
        .order_by(desc(CandidateProfileRecord.profile_version))
    )
    profile = db.execute(stmt_profile).scalars().first()
    if not profile:
        _record_authz_audit(
            db=db,
            principal=principal,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.UNAUTHORIZED,
            resource_type="candidate_application",
            resource_id=str(job_id),
            safe_metadata={"action": "SUBMIT_APPLICATION", "denial": "MISSING_BOUND_PROFILE"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "PROFILE_NOT_INITIALIZED",
                "message": "Your candidate profile has not been initialized. Please contact your recruiter or administrator.",
            },
        )

    # 4. Resolve Job Requisition and latest approved revision
    stmt_job = (
        select(JobRequisition)
        .options(
            selectinload(JobRequisition.versions).selectinload(JobVersion.requirements)
        )
        .where(
            JobRequisition.job_id == job_id,
            JobRequisition.status == JobLifecycleStatus.ACTIVE,
            JobRequisition.deleted_at.is_(None),
        )
    )
    job = db.execute(stmt_job).scalar_one_or_none()
    if not job:
        _record_authz_audit(
            db=db,
            principal=principal,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.RESOURCE_NOT_FOUND,
            resource_type="candidate_application",
            resource_id=str(job_id),
            safe_metadata={"action": "SUBMIT_APPLICATION", "denial": "JOB_NOT_FOUND_OR_INACTIVE"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job posting not found or unavailable."},
        )

    approved_versions = [v for v in job.versions if v.version_status == JobVersionStatus.APPROVED]
    if not approved_versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job posting not found or unavailable."},
        )

    latest_approved = sorted(
        approved_versions,
        key=lambda v: (v.version_number, v.revision),
        reverse=True,
    )[0]

    # Stale expected revision check
    if payload.expected_revision is not None and payload.expected_revision != latest_approved.revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STALE_JOB_REVISION",
                "message": f"Job requisition revision has changed (current: {latest_approved.revision}, expected: {payload.expected_revision}). Please refresh before applying.",
            },
        )

    # 5. Check for existing active application for this (binding_id, job_id)
    stmt_active = select(CandidateApplicationRecord).where(
        CandidateApplicationRecord.binding_id == principal.binding_id,
        CandidateApplicationRecord.job_id == job_id,
        CandidateApplicationRecord.status == CandidateApplicationStatus.SUBMITTED.value,
    )
    existing_active = db.execute(stmt_active).scalar_one_or_none()
    if existing_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_APPLICATION",
                "message": "You already have an active application submitted for this job requisition.",
            },
        )

    # 6. Create application record
    app_record = CandidateApplicationRecord(
        application_id=uuid.uuid4(),
        organization_id=principal.organization_id,
        binding_id=principal.binding_id,
        candidate_id=principal.candidate_id,
        job_id=job.job_id,
        job_version_id=latest_approved.job_version_id,
        job_revision=latest_approved.revision,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        status=CandidateApplicationStatus.SUBMITTED.value,
        submission_source="CANDIDATE_PORTAL",
        idempotency_key=payload.idempotency_key,
        submitted_at=now,
        withdrawn_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(app_record)

    # 7. Audit event
    _record_authz_audit(
        db=db,
        principal=principal,
        event_type=AuditEventType.CANDIDATE_APPLICATION_SUBMITTED,
        result=AuditResult.SUCCESS,
        reason_code=AuditReasonCode.APPLICATION_SUBMITTED,
        resource_type="candidate_application",
        resource_id=str(app_record.application_id),
        safe_metadata={
            "action": "SUBMIT_APPLICATION",
            "job_id": str(job.job_id),
            "job_version_id": str(latest_approved.job_version_id),
            "job_revision": latest_approved.revision,
            "profile_version": profile.profile_version,
        },
    )

    try:
        db.commit()
        db.refresh(app_record)
    except IntegrityError as err:
        db.rollback()
        # Handle concurrent double submission
        logger.warning(
            "Integrity error during application submission",
            extra={"candidate_id": str(principal.candidate_id), "job_id": str(job_id), "error": str(err)},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_APPLICATION",
                "message": "An application was already submitted concurrently.",
            },
        )

    # Reload relationships for DTO assembly
    app_record.job = job
    app_record.job_version = latest_approved
    app_record.profile = profile

    return _build_candidate_application_response(app_record)


def list_candidate_applications(
    principal: CandidatePrincipal,
    db: Session,
    page: int = 1,
    limit: int = 20,
) -> CandidateApplicationListResponse:
    """Lists all submitted and withdrawn applications for the authenticated candidate principal."""
    page = max(1, page)
    limit = max(1, min(limit, 50))
    offset = (page - 1) * limit

    stmt = (
        select(CandidateApplicationRecord)
        .options(
            selectinload(CandidateApplicationRecord.job),
            selectinload(CandidateApplicationRecord.job_version),
            selectinload(CandidateApplicationRecord.profile),
        )
        .where(
            CandidateApplicationRecord.binding_id == principal.binding_id,
            CandidateApplicationRecord.candidate_id == principal.candidate_id,
        )
        .order_by(desc(CandidateApplicationRecord.submitted_at), desc(CandidateApplicationRecord.created_at))
    )

    all_records = db.execute(stmt).scalars().all()
    total_count = len(all_records)
    paginated_records = all_records[offset : offset + limit]

    items = [_build_candidate_application_response(r) for r in paginated_records]

    return CandidateApplicationListResponse(
        items=items,
        total=total_count,
        page=page,
        limit=limit,
    )


def get_candidate_application_detail(
    principal: CandidatePrincipal,
    application_id: uuid.UUID,
    db: Session,
) -> CandidateApplicationResponse:
    """Retrieves full safe details for a single candidate application owned by the candidate principal."""
    app_rec = load_scoped_candidate_application(
        principal=principal,
        application_id=application_id,
        db=db,
        action="GET_APPLICATION_DETAIL",
    )
    return _build_candidate_application_response(app_rec)


def withdraw_candidate_application(
    principal: CandidatePrincipal,
    application_id: uuid.UUID,
    db: Session,
) -> CandidateApplicationResponse:
    """Withdraws an eligible application owned by the authenticated candidate.
    
    1. Loads application in candidate scope.
    2. Validates current status is SUBMITTED.
    3. Atomically sets status to WITHDRAWN and records withdrawn_at.
    4. Records security audit event and commits.
    """
    now = datetime.now(timezone.utc)
    app_rec = load_scoped_candidate_application(
        principal=principal,
        application_id=application_id,
        db=db,
        for_update=True,
        action="WITHDRAW_APPLICATION",
    )

    if app_rec.status == CandidateApplicationStatus.WITHDRAWN.value:
        # Idempotent response if already withdrawn
        return _build_candidate_application_response(app_rec)

    if app_rec.status != CandidateApplicationStatus.SUBMITTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "APPLICATION_NOT_WITHDRAWABLE",
                "message": f"Application cannot be withdrawn from status '{app_rec.status}'.",
            },
        )

    app_rec.status = CandidateApplicationStatus.WITHDRAWN.value
    app_rec.withdrawn_at = now
    app_rec.updated_at = now

    _record_authz_audit(
        db=db,
        principal=principal,
        event_type=AuditEventType.CANDIDATE_APPLICATION_WITHDRAWN,
        result=AuditResult.SUCCESS,
        reason_code=AuditReasonCode.APPLICATION_WITHDRAWN,
        resource_type="candidate_application",
        resource_id=str(app_rec.application_id),
        safe_metadata={
            "action": "WITHDRAW_APPLICATION",
            "job_id": str(app_rec.job_id),
            "withdrawn_at": now.isoformat(),
        },
    )

    db.commit()
    db.refresh(app_rec)

    return _build_candidate_application_response(app_rec)
