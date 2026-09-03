import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.api.auth import AuthenticatedContext, require_role
from app.database import get_db
from app.models.auth import UserRole
from app.models.job import (
    JobLifecycleStatus,
    JobRequisition,
    JobVersion,
    JobVersionStatus,
)
from app.schemas.job import (
    JobCreateRequest,
    JobDetailResponse,
    JobDraftUpdateRequest,
    JobSummaryResponse,
    JobVersionDetailResponse,
    JobVersionSummaryResponse,
)

logger = logging.getLogger("ai_hiring.api.jobs")

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"],
)

# Role dependency allowing RECRUITER or ADMIN
require_recruiter_or_admin = require_role({UserRole.RECRUITER, UserRole.ADMIN})


def _compute_payload_hash(payload_dict: dict) -> str:
    """Computes deterministic SHA-256 digest of normalized payload."""
    serialized = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest().lower()


def _build_job_version_detail_response(version: JobVersion) -> JobVersionDetailResponse:
    return JobVersionDetailResponse(
        job_version_id=version.job_version_id,
        job_id=version.job_id,
        version_number=version.version_number,
        version_status=version.version_status,
        revision=version.revision,
        title=version.title,
        department=version.department,
        location=version.location,
        employment_type=version.employment_type,
        workplace_type=version.workplace_type,
        openings_count=version.openings_count,
        internal_reference=version.internal_reference,
        summary=version.summary,
        responsibilities=version.responsibilities,
        job_description_text=version.job_description_text,
        taxonomy_version=version.taxonomy_version,
        parser_version=version.parser_version,
        created_by_user_id=version.created_by_user_id,
        approved_by_user_id=version.approved_by_user_id,
        approved_at=version.approved_at,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


def _build_job_version_summary_response(version: JobVersion) -> JobVersionSummaryResponse:
    return JobVersionSummaryResponse(
        job_version_id=version.job_version_id,
        version_number=version.version_number,
        version_status=version.version_status,
        revision=version.revision,
        title=version.title,
        department=version.department,
        location=version.location,
        employment_type=version.employment_type,
        workplace_type=version.workplace_type,
        openings_count=version.openings_count,
        internal_reference=version.internal_reference,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


def _build_job_detail_response(req: JobRequisition, version: JobVersion) -> JobDetailResponse:
    return JobDetailResponse(
        job_id=req.job_id,
        created_by_user_id=req.created_by_user_id,
        status=req.status,
        created_at=req.created_at,
        updated_at=req.updated_at,
        current_version=_build_job_version_detail_response(version),
    )


@router.post(
    "",
    response_model=JobDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Job Requisition and Initial Draft",
    description=(
        "Atomically creates a new JobRequisition and its initial version-1 DRAFT JobVersion. "
        "Supports optional Idempotency-Key header to safely retry requests."
    ),
)
async def create_job(
    create_req: JobCreateRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> JobDetailResponse:
    actor = auth_ctx.user
    now = datetime.now(timezone.utc)

    payload_dict = create_req.model_dump(mode="json")
    payload_hash = _compute_payload_hash(payload_dict)

    # 1. Handle Idempotency-Key
    if idempotency_key:
        clean_key = idempotency_key.strip()
        if len(clean_key) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_IDEMPOTENCY_KEY", "message": "Idempotency-Key header exceeds maximum length of 255 characters."},
            )

        if clean_key:
            # Query existing requisition with same idempotency key for this creator
            stmt = (
                select(JobRequisition)
                .options(selectinload(JobRequisition.versions))
                .where(
                    JobRequisition.created_by_user_id == actor.user_id,
                    JobRequisition.idempotency_key == clean_key,
                )
            )
            existing = db.execute(stmt).scalar_one_or_none()
            if existing is not None:
                if existing.idempotency_payload_hash == payload_hash:
                    # Idempotent match: return existing job
                    v1 = next((v for v in existing.versions if v.version_number == 1), existing.versions[0] if existing.versions else None)
                    if v1 is not None:
                        return _build_job_detail_response(existing, v1)
                # Differing payload
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "IDEMPOTENCY_CONFLICT",
                        "message": "Idempotency key already used with a different job creation payload.",
                    },
                )

    # 2. Atomic creation of JobRequisition and JobVersion v1
    job_id = uuid.uuid4()
    version_id = uuid.uuid4()

    clean_idem_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None

    requisition = JobRequisition(
        job_id=job_id,
        created_by_user_id=actor.user_id,
        status=JobLifecycleStatus.ACTIVE,
        idempotency_key=clean_idem_key,
        idempotency_payload_hash=payload_hash if clean_idem_key else None,
        created_at=now,
        updated_at=now,
    )

    version_1 = JobVersion(
        job_version_id=version_id,
        job_id=job_id,
        version_number=1,
        version_status=JobVersionStatus.DRAFT,
        revision=1,
        title=create_req.title,
        department=create_req.department,
        location=create_req.location,
        employment_type=create_req.employment_type,
        workplace_type=create_req.workplace_type,
        openings_count=create_req.openings_count,
        internal_reference=create_req.internal_reference,
        summary=create_req.summary,
        responsibilities=create_req.responsibilities,
        job_description_text=create_req.job_description_text,
        created_by_user_id=actor.user_id,
        created_at=now,
        updated_at=now,
    )

    try:
        db.add(requisition)
        db.flush()
        db.add(version_1)
        db.commit()
        db.refresh(requisition)
        db.refresh(version_1)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to create job requisition and version", extra={"error_type": type(e).__name__})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "JOB_CREATION_FAILED", "message": "Failed to create job."},
        )

    return _build_job_detail_response(requisition, version_1)


@router.get(
    "",
    response_model=List[JobSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List Accessible Jobs",
    description=(
        "Returns a list of concise job summaries accessible to the authenticated caller. "
        "Recruiters see only their own jobs; Admins see all jobs. Ordered newest updated first."
    ),
)
async def list_jobs(
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> List[JobSummaryResponse]:
    actor = auth_ctx.user

    stmt = select(JobRequisition).options(selectinload(JobRequisition.versions))

    # Recruiter sees only their own jobs; Admin sees all
    if actor.role == UserRole.RECRUITER:
        stmt = stmt.where(JobRequisition.created_by_user_id == actor.user_id)

    # Deterministic ordering: updated_at desc, job_id desc tie breaker
    stmt = stmt.order_by(JobRequisition.updated_at.desc(), JobRequisition.job_id.desc())

    requisitions = db.execute(stmt).scalars().all()

    items = []
    for req in requisitions:
        # Find latest version (highest version_number)
        if not req.versions:
            continue
        latest_version = max(req.versions, key=lambda v: v.version_number)
        items.append(
            JobSummaryResponse(
                job_id=req.job_id,
                created_by_user_id=req.created_by_user_id,
                status=req.status,
                created_at=req.created_at,
                updated_at=req.updated_at,
                current_version=_build_job_version_summary_response(latest_version),
            )
        )

    return items


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Job Detail",
    description="Returns the job requisition and its current version draft/details. Enforces creator ownership.",
)
async def get_job(
    job_id: uuid.UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> JobDetailResponse:
    actor = auth_ctx.user

    stmt = (
        select(JobRequisition)
        .options(selectinload(JobRequisition.versions))
        .where(JobRequisition.job_id == job_id)
    )
    req = db.execute(stmt).scalar_one_or_none()

    # Enforce ownership / conceal existence if recruiter is not owner
    if req is None or (actor.role == UserRole.RECRUITER and req.created_by_user_id != actor.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job not found."},
        )

    if not req.versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job version not found."},
        )

    latest_version = max(req.versions, key=lambda v: v.version_number)
    return _build_job_detail_response(req, latest_version)


@router.patch(
    "/{job_id}/draft",
    response_model=JobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Current Draft Job Version",
    description=(
        "Applies partial updates to the current DRAFT version only. "
        "Requires expected_revision matching the current draft revision. Increments revision upon success."
    ),
)
async def update_job_draft(
    job_id: uuid.UUID,
    update_req: JobDraftUpdateRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> JobDetailResponse:
    actor = auth_ctx.user
    now = datetime.now(timezone.utc)

    stmt = (
        select(JobRequisition)
        .options(selectinload(JobRequisition.versions))
        .where(JobRequisition.job_id == job_id)
    )
    req = db.execute(stmt).scalar_one_or_none()

    # Enforce ownership / conceal existence
    if req is None or (actor.role == UserRole.RECRUITER and req.created_by_user_id != actor.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job not found."},
        )

    if not req.versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job version not found."},
        )

    draft_version = max(req.versions, key=lambda v: v.version_number)

    # 1. Reject if not DRAFT
    if draft_version.version_status != JobVersionStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "JOB_NOT_DRAFT",
                "message": "Only job versions in DRAFT status can be updated.",
            },
        )

    # 2. Check expected revision conflict
    if draft_version.revision != update_req.expected_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "REVISION_CONFLICT",
                "message": f"Draft revision conflict. Expected revision {draft_version.revision}, but received {update_req.expected_revision}.",
            },
        )

    # 3. Apply partial updates
    fields_set = update_req.model_fields_set - {"expected_revision"}
    for field_name in fields_set:
        val = getattr(update_req, field_name)
        setattr(draft_version, field_name, val)

    # Increment revision and update timestamps
    draft_version.revision += 1
    draft_version.updated_at = now
    req.updated_at = now

    try:
        db.commit()
        db.refresh(req)
        db.refresh(draft_version)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to update job draft", extra={"job_id": str(job_id), "error_type": type(e).__name__})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "JOB_UPDATE_FAILED", "message": "Failed to update draft."},
        )

    return _build_job_detail_response(req, draft_version)
