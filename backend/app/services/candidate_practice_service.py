"""Domain service for Candidate Practice Releases and Candidate-Safe Discovery in Phase 3F.2."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models.auth import UserRecord, UserRole
from app.models.candidate import CandidateIdentityRecord
from app.models.candidate_access import (
    CandidateAccountBindingRecord,
    CandidateBindingStatus,
    CandidatePracticeReleaseRecord,
)
from app.models.interview import AiInterviewQuestionSetRecord, JobInterviewTemplateRecord
from app.models.job import JobLifecycleStatus, JobRequisition, JobVersion
from app.schemas.mcq_contract import (
    CandidatePracticeDiscoveryResponse,
    CandidatePracticeJobSummary,
)
from app.schemas.phase3_enums import PracticeReleaseStatus


def _check_recruiter_access(actor: UserRecord, job: JobRequisition) -> None:
    if actor.role == UserRole.RECRUITER and job.created_by_user_id != actor.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Access to requisition denied."},
        )
    actor_org = getattr(actor, "org_id", getattr(actor, "organization_id", None))
    job_org = getattr(job, "org_id", getattr(job, "organization_id", None))
    if actor_org is not None and job_org is not None and actor_org != job_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Access to requisition denied across organizations."},
        )


def release_practice_to_candidate(
    actor: UserRecord,
    candidate_id: UUID,
    job_id: UUID,
    ai_set_id: Optional[UUID],
    db: Session,
) -> Dict[str, Any]:
    """Releases an approved practice question set for a candidate."""
    # 1. Candidate lookup
    stmt_cand = select(CandidateIdentityRecord).where(CandidateIdentityRecord.identity_id == candidate_id)
    cand = db.execute(stmt_cand).scalar_one_or_none()
    if not cand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CANDIDATE_NOT_FOUND", "message": "Candidate identity record not found."},
        )

    # 2. Check Candidate Account Binding
    stmt_binding = select(CandidateAccountBindingRecord).where(
        CandidateAccountBindingRecord.candidate_id == candidate_id,
        CandidateAccountBindingRecord.status == CandidateBindingStatus.ACTIVE.value,
    )
    binding = db.execute(stmt_binding).scalar_one_or_none()
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CANDIDATE_NOT_ACTIVATED",
                "message": "Candidate must activate their portal account before practice interviews can be released.",
            },
        )

    # 3. Job lookup & access check
    stmt_job = (
        select(JobRequisition)
        .options(selectinload(JobRequisition.versions).selectinload(JobVersion.requirements))
        .where(JobRequisition.job_id == job_id)
    )
    job = db.execute(stmt_job).scalar_one_or_none()
    if not job or not job.versions or job.status != JobLifecycleStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Active job requisition not found."},
        )
    _check_recruiter_access(actor, job)

    # Cross-org verification between candidate binding and job
    job_org = getattr(job, "organization_id", getattr(job, "org_id", None))
    actor_org = getattr(actor, "organization_id", None) or getattr(actor, "org_id", None)
    if job_org is not None and binding.organization_id != job_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN_ORGANIZATION", "message": "Cannot release practice across organization boundaries."},
        )
    if actor_org is not None and job_org is not None and actor_org != job_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN_ORGANIZATION", "message": "Cannot release practice across organization boundaries."},
        )

    latest_version = job.versions[-1]

    # 4. Load approved question set
    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .where(
            AiInterviewQuestionSetRecord.job_id == job.job_id,
            (AiInterviewQuestionSetRecord.job_version_id == latest_version.job_version_id)
            | (AiInterviewQuestionSetRecord.job_revision == latest_version.version_number),
            AiInterviewQuestionSetRecord.lifecycle_status == "APPROVED",
        )
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    if ai_set_id:
        stmt_set = select(AiInterviewQuestionSetRecord).where(
            AiInterviewQuestionSetRecord.ai_set_id == ai_set_id,
            AiInterviewQuestionSetRecord.lifecycle_status == "APPROVED",
        )

    ai_set = db.execute(stmt_set).scalars().first()
    if not ai_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NO_APPROVED_QUESTION_SET",
                "message": "Practice interview cannot be released until an AI question set is approved for this job revision.",
            },
        )

    # 5. Check existing release for this candidate + job
    stmt_existing = select(CandidatePracticeReleaseRecord).where(
        CandidatePracticeReleaseRecord.candidate_id == candidate_id,
        CandidatePracticeReleaseRecord.job_id == job.job_id,
        CandidatePracticeReleaseRecord.status == PracticeReleaseStatus.RELEASED.value,
    )
    existing_release = db.execute(stmt_existing).scalars().first()

    if existing_release:
        if existing_release.ai_set_id == ai_set.ai_set_id and existing_release.set_version == ai_set.set_version:
            # Already released this exact version
            return {
                "release_id": existing_release.release_id,
                "candidate_id": candidate_id,
                "job_id": job.job_id,
                "status": PracticeReleaseStatus.RELEASED.value,
                "message": "Practice interview is already active for this candidate.",
            }
        else:
            # Revoke old version release
            existing_release.status = PracticeReleaseStatus.REVOKED.value
            existing_release.revoked_by_user_id = actor.user_id
            existing_release.revoked_at = datetime.now(timezone.utc)

    items = ai_set.items or []
    conv_count = sum(1 for it in items if it.get("question_format", "CONVERSATION") == "CONVERSATION")
    mcq_count = sum(1 for it in items if it.get("question_format") == "MCQ_SINGLE_ANSWER")

    # 6. Create new release record
    new_release = CandidatePracticeReleaseRecord(
        release_id=uuid.uuid4(),
        organization_id=binding.organization_id,
        candidate_id=candidate_id,
        application_id=None,
        job_id=job.job_id,
        job_version_id=latest_version.job_version_id,
        job_revision=latest_version.version_number,
        template_id=ai_set.template_id,
        ai_set_id=ai_set.ai_set_id,
        set_version=ai_set.set_version,
        status=PracticeReleaseStatus.RELEASED.value,
        released_by_user_id=actor.user_id,
        released_at=datetime.now(timezone.utc),
    )
    db.add(new_release)
    db.commit()
    db.refresh(new_release)

    return {
        "release_id": new_release.release_id,
        "candidate_id": new_release.candidate_id,
        "job_id": new_release.job_id,
        "job_title": latest_version.title or job.title,
        "job_revision": new_release.job_revision,
        "set_version": new_release.set_version,
        "conversation_count": conv_count,
        "mcq_count": mcq_count,
        "status": new_release.status,
        "released_at": new_release.released_at,
        "message": f"Practice interview for '{latest_version.title or job.title}' (Rev #{new_release.job_revision}) released to candidate.",
    }


def list_candidate_practice_releases_for_recruiter(
    actor: UserRecord,
    candidate_id: UUID,
    db: Session,
) -> List[Dict[str, Any]]:
    """Lists practice release records for a given candidate identity."""
    actor_org = getattr(actor, "organization_id", None) or getattr(actor, "org_id", None)
    stmt = (
        select(CandidatePracticeReleaseRecord)
        .options(
            selectinload(CandidatePracticeReleaseRecord.job),
            selectinload(CandidatePracticeReleaseRecord.job_version),
            selectinload(CandidatePracticeReleaseRecord.ai_set),
        )
        .where(CandidatePracticeReleaseRecord.candidate_id == candidate_id)
        .order_by(desc(CandidatePracticeReleaseRecord.released_at))
    )
    records = db.execute(stmt).scalars().all()

    results = []
    for r in records:
        if actor_org and r.organization_id != actor_org:
            continue
        
        items = r.ai_set.items if r.ai_set else []
        conv_count = sum(1 for it in items if it.get("question_format", "CONVERSATION") == "CONVERSATION")
        mcq_count = sum(1 for it in items if it.get("question_format") == "MCQ_SINGLE_ANSWER")

        results.append({
            "release_id": r.release_id,
            "candidate_id": r.candidate_id,
            "job_id": r.job_id,
            "job_title": (r.job_version.title if r.job_version else (r.job.title if r.job else "Job Requisition")),
            "job_revision": r.job_revision,
            "set_version": r.set_version,
            "status": r.status,
            "conversation_count": conv_count,
            "mcq_count": mcq_count,
            "released_at": r.released_at,
            "revoked_at": r.revoked_at,
        })
    return results


def revoke_candidate_practice_release(
    actor: UserRecord,
    release_id: UUID,
    db: Session,
) -> Dict[str, Any]:
    """Revokes an active practice release."""
    stmt = select(CandidatePracticeReleaseRecord).where(CandidatePracticeReleaseRecord.release_id == release_id)
    release = db.execute(stmt).scalar_one_or_none()
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RELEASE_NOT_FOUND", "message": "Practice release record not found."},
        )

    actor_org = getattr(actor, "organization_id", None) or getattr(actor, "org_id", None)
    if actor_org and release.organization_id != actor_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Cannot revoke release across organizations."},
        )

    release.status = PracticeReleaseStatus.REVOKED.value
    release.revoked_by_user_id = actor.user_id
    release.revoked_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "release_id": release.release_id,
        "status": release.status,
        "revoked_at": release.revoked_at,
        "message": "Practice release revoked successfully.",
    }


def get_candidate_practice_discovery(
    candidate_user: UserRecord,
    db: Session,
) -> CandidatePracticeDiscoveryResponse:
    """Returns candidate-authorized practice interview jobs strictly omitting confidential data."""
    # 1. Resolve candidate account binding
    stmt_binding = select(CandidateAccountBindingRecord).where(
        CandidateAccountBindingRecord.user_id == candidate_user.user_id,
        CandidateAccountBindingRecord.status == CandidateBindingStatus.ACTIVE.value,
    )
    binding = db.execute(stmt_binding).scalar_one_or_none()
    if not binding:
        return CandidatePracticeDiscoveryResponse(items=[])

    # 2. Query active RELEASED records for this candidate identity and organization
    stmt_rel = (
        select(CandidatePracticeReleaseRecord)
        .options(
            selectinload(CandidatePracticeReleaseRecord.job),
            selectinload(CandidatePracticeReleaseRecord.job_version),
            selectinload(CandidatePracticeReleaseRecord.ai_set),
        )
        .where(
            CandidatePracticeReleaseRecord.candidate_id == binding.candidate_id,
            CandidatePracticeReleaseRecord.organization_id == binding.organization_id,
            CandidatePracticeReleaseRecord.status == PracticeReleaseStatus.RELEASED.value,
        )
        .order_by(desc(CandidatePracticeReleaseRecord.released_at))
    )
    releases = db.execute(stmt_rel).scalars().all()

    items: List[CandidatePracticeJobSummary] = []
    for rel in releases:
        job = rel.job
        version = rel.job_version
        ai_set = rel.ai_set

        job_title = (version.title if version else (job.title if job else "Job Requisition"))
        dept = getattr(job, "department", None)
        loc = getattr(job, "location", None)
        summary = getattr(version, "summary", None) or getattr(job, "description", None)
        if summary and len(summary) > 300:
            summary = summary[:297] + "..."

        set_items = ai_set.items if ai_set else []
        conv_count = sum(1 for it in set_items if it.get("question_format", "CONVERSATION") == "CONVERSATION")
        mcq_count = sum(1 for it in set_items if it.get("question_format") == "MCQ_SINGLE_ANSWER")

        items.append(
            CandidatePracticeJobSummary(
                release_id=rel.release_id,
                job_id=rel.job_id,
                job_title=job_title,
                department=dept,
                location=loc,
                summary=summary,
                conversation_question_count=conv_count,
                mcq_count=mcq_count,
                released_at=rel.released_at,
                status_label="Practice content ready",
            )
        )

    return CandidatePracticeDiscoveryResponse(items=items)
