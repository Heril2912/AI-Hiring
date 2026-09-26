"""Candidate Job Discovery Service (Phase 4B.3).

Implements candidate-safe, deny-by-default job discovery operations.
Excludes drafts, archived, and deleted jobs. Returns only the latest approved version.
"""
import logging
import uuid
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.auth import AuditEventType, AuditReasonCode, AuditResult
from app.models.job import (
    JobLifecycleStatus,
    JobRequirement,
    JobRequisition,
    JobVersion,
    JobVersionStatus,
)
from app.schemas.candidate_job import (
    CandidateJobDetailResponse,
    CandidateJobListResponse,
    CandidateJobSummaryResponse,
)
from app.services.candidate_authorization_kernel import (
    CandidatePrincipal,
    _record_authz_audit,
)

logger = logging.getLogger("ai_hiring.services.candidate_job")


def list_candidate_open_jobs(
    principal: CandidatePrincipal,
    db: Session,
    query: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> CandidateJobListResponse:
    """Lists candidate-safe eligible jobs.
    
    A job is eligible if:
    - JobRequisition.status == ACTIVE
    - JobRequisition.deleted_at is NULL
    - Has an APPROVED JobVersion
    
    Returns the latest approved version per active requisition with bounded pagination and deterministic ordering.
    """
    page = max(1, page)
    limit = max(1, min(limit, 50))
    offset = (page - 1) * limit

    # Query active job requisitions that have at least one APPROVED version
    stmt = (
        select(JobRequisition)
        .join(JobVersion, JobRequisition.job_id == JobVersion.job_id)
        .where(
            JobRequisition.status == JobLifecycleStatus.ACTIVE,
            JobRequisition.deleted_at.is_(None),
            JobVersion.version_status == JobVersionStatus.APPROVED,
        )
        .options(
            selectinload(JobRequisition.versions).selectinload(JobVersion.requirements)
        )
        .distinct()
    )

    all_active_jobs = db.execute(stmt).scalars().all()

    # Collect latest approved version for each job
    eligible_items: List[CandidateJobSummaryResponse] = []

    for job in all_active_jobs:
        approved_versions = [
            v for v in job.versions if v.version_status == JobVersionStatus.APPROVED
        ]
        if not approved_versions:
            continue
        # Latest approved version by version_number desc, revision desc
        latest_approved = sorted(
            approved_versions,
            key=lambda v: (v.version_number, v.revision),
            reverse=True,
        )[0]

        # Optional search filter across title, department, location, summary
        if query:
            q_clean = query.strip().lower()
            t_match = latest_approved.title and q_clean in latest_approved.title.lower()
            d_match = latest_approved.department and q_clean in latest_approved.department.lower()
            l_match = latest_approved.location and q_clean in latest_approved.location.lower()
            s_match = latest_approved.summary and q_clean in latest_approved.summary.lower()
            if not (t_match or d_match or l_match or s_match):
                continue

        published_time = latest_approved.approved_at or latest_approved.updated_at or latest_approved.created_at

        eligible_items.append(
            CandidateJobSummaryResponse(
                job_id=job.job_id,
                job_version_id=latest_approved.job_version_id,
                version_number=latest_approved.version_number,
                revision=latest_approved.revision,
                title=latest_approved.title,
                department=latest_approved.department,
                location=latest_approved.location,
                employment_type=latest_approved.employment_type,
                workplace_type=latest_approved.workplace_type,
                openings_count=latest_approved.openings_count,
                summary=latest_approved.summary,
                published_at=published_time,
                updated_at=latest_approved.updated_at or latest_approved.created_at,
            )
        )

    # Deterministic sorting: published_at desc, job_id asc
    eligible_items.sort(key=lambda item: (item.published_at, str(item.job_id)), reverse=True)

    total_count = len(eligible_items)
    paginated_items = eligible_items[offset : offset + limit]

    return CandidateJobListResponse(
        items=paginated_items,
        total=total_count,
        page=page,
        limit=limit,
    )


def get_candidate_open_job_detail(
    principal: CandidatePrincipal,
    job_id: uuid.UUID,
    db: Session,
    requested_version_id: Optional[uuid.UUID] = None,
) -> CandidateJobDetailResponse:
    """Retrieves candidate-safe details for an approved job requisition.
    
    Ensures that only the latest approved version is returned. If a specific version_id
    is requested in the URL, it must match the latest approved version, otherwise safely returns 404.
    """
    stmt = (
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
    job = db.execute(stmt).scalar_one_or_none()

    if not job:
        _record_authz_audit(
            db=db,
            principal=principal,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.RESOURCE_NOT_FOUND,
            resource_type="candidate_job",
            resource_id=str(job_id),
            safe_metadata={"action": "GET_JOB_DETAIL", "denial": "JOB_NOT_FOUND_OR_INACTIVE"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job posting not found or unavailable."},
        )

    approved_versions = [
        v for v in job.versions if v.version_status == JobVersionStatus.APPROVED
    ]
    if not approved_versions:
        _record_authz_audit(
            db=db,
            principal=principal,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.RESOURCE_NOT_FOUND,
            resource_type="candidate_job",
            resource_id=str(job_id),
            safe_metadata={"action": "GET_JOB_DETAIL", "denial": "NO_APPROVED_VERSION"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job posting not found or unavailable."},
        )

    latest_approved = sorted(
        approved_versions,
        key=lambda v: (v.version_number, v.revision),
        reverse=True,
    )[0]

    # If caller specifically requested a version, verify it is the approved one
    if requested_version_id and requested_version_id != latest_approved.job_version_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Requested job version is not available."},
        )

    # Extract public qualifications (sorted by display_order)
    raw_reqs = latest_approved.requirements or []
    sorted_reqs = sorted(raw_reqs, key=lambda r: r.display_order)
    public_qualifications = [
        r.label for r in sorted_reqs if r.label and r.label.strip()
    ]

    published_time = latest_approved.approved_at or latest_approved.updated_at or latest_approved.created_at

    return CandidateJobDetailResponse(
        job_id=job.job_id,
        job_version_id=latest_approved.job_version_id,
        version_number=latest_approved.version_number,
        revision=latest_approved.revision,
        title=latest_approved.title,
        department=latest_approved.department,
        location=latest_approved.location,
        employment_type=latest_approved.employment_type,
        workplace_type=latest_approved.workplace_type,
        openings_count=latest_approved.openings_count,
        summary=latest_approved.summary,
        responsibilities=latest_approved.responsibilities,
        qualifications=public_qualifications,
        published_at=published_time,
        updated_at=latest_approved.updated_at or latest_approved.created_at,
    )
