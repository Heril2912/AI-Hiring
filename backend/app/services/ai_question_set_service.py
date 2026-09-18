"""Domain service for Phase 3D.5 Dedicated AI Interview Questions Workspace.

Separates deterministic interview template authoring from AI question generation.
Preserves the deterministic blueprint as authoritative foundation while maintaining
strict data boundary: never leaking deterministic question wording into AI responses.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.models.auth import UserRecord, UserRole
from app.models.interview import (
    AiInterviewQuestionSetRecord,
    InterviewQuestionRecord,
    JobInterviewTemplateRecord,
)
from app.models.job import JobLifecycleStatus, JobRequisition, JobVersion
from app.schemas.ai_question_set import (
    AiQuestionSetApproveResponse,
    AiQuestionSetDetailResponse,
    AiQuestionSetDirectoryResponse,
    AiQuestionSetGenerateRequest,
    AiQuestionSetSummaryResponse,
    AiQuestionSetValidateResponse,
    AiQuestionSlotItemResponse,
    AiQuestionSlotUpdateRequest,
    EligibleJobItemResponse,
    EligibleJobsResponse,
    SafeRubricResponse,
)
from app.schemas.phase3_enums import AuthoringOrigin, PlanLifecycle
from app.services.provider_registry import ProviderRegistry, get_provider_registry
from app.services.wording_assistance_service import (
    RecruiterWordingAssistRequest,
    request_question_wording_assistance,
)
from app.services.wording_provider import BaseWordingProvider


class AiQuestionSetError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _check_recruiter_access(actor: UserRecord, job: JobRequisition) -> None:
    if actor.role == UserRole.RECRUITER and job.created_by_user_id != actor.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Access to requisition denied."},
        )


def _map_rubric_to_safe(q_rec: InterviewQuestionRecord) -> Optional[SafeRubricResponse]:
    if not hasattr(q_rec, "rubric") or not q_rec.rubric:
        return None
    r = q_rec.rubric
    return SafeRubricResponse(
        rubric_id=r.rubric_id,
        rubric_version=r.rubric_version,
        competency_definition=r.competency_definition or "",
        question_intent=r.question_intent or "",
        observable_indicators=list(r.observable_indicators or []),
        rating_anchors={str(k): str(v) for k, v in (r.rating_anchors or {}).items()},
        sufficient_evidence_guidance=r.sufficient_evidence_guidance,
        insufficient_evidence_guidance=r.insufficient_evidence_guidance,
        permitted_probes=list(r.permitted_probes or []),
    )


def _map_record_to_detail_dto(
    ai_set: AiInterviewQuestionSetRecord,
    template: JobInterviewTemplateRecord,
    db: Session,
) -> AiQuestionSetDetailResponse:
    # Check staleness
    current_hash = template.content_hash or ""
    is_stale = False
    stale_reason = None
    if current_hash and ai_set.source_content_hash != current_hash:
        is_stale = True
        stale_reason = "Deterministic blueprint was modified since AI question set generation."
        if ai_set.lifecycle_status not in ("APPROVED", "STALE"):
            ai_set.lifecycle_status = "STALE"
            db.commit()

    # Map slot items
    slot_dtos: List[AiQuestionSlotItemResponse] = []
    questions_by_id = {q.question_id: q for q in (template.questions or [])}

    reviewed_count = 0
    generated_count = 0

    for item in ai_set.items:
        slot_uuid = UUID(item["slot_id"]) if isinstance(item["slot_id"], str) else item["slot_id"]
        q_rec = questions_by_id.get(slot_uuid)
        safe_rubric = _map_rubric_to_safe(q_rec) if q_rec else None

        ai_wording = item.get("ai_wording")
        if ai_wording:
            generated_count += 1

        review_state = item.get("review_state", "UNREVIEWED")
        if review_state in ("KEPT", "EDITED", "RECRUITER_AUTHORED"):
            reviewed_count += 1

        up_at = None
        if item.get("updated_at"):
            try:
                up_at = datetime.fromisoformat(item["updated_at"])
            except Exception:
                up_at = None

        slot_dtos.append(
            AiQuestionSlotItemResponse(
                slot_id=slot_uuid,
                display_order=item.get("display_order", 0),
                competency_name=item.get("competency_name", "Core Competency"),
                question_type=item.get("question_type", "TECHNICAL"),
                estimated_time_minutes=item.get("estimated_time_minutes", 5),
                permitted_probes=list(item.get("permitted_probes", [])),
                rubric=safe_rubric,
                ai_wording=ai_wording,
                review_state=review_state,
                authoring_origin=item.get("authoring_origin", "AI_GENERATED"),
                validation_status=item.get("validation_status", "PASSED"),
                safe_failure_code=item.get("safe_failure_code"),
                rationale_code=item.get("rationale_code"),
                updated_at=up_at,
            )
        )

    # Sort slots by display_order
    slot_dtos.sort(key=lambda s: s.display_order)

    # Job title
    job_title = "Job Requisition"
    if template.requisition:
        job_title = getattr(template.requisition, "title", None) or f"Job #{str(template.job_id)[:8]}"
    if hasattr(template, "job_version") and template.job_version:
        job_title = template.job_version.title or job_title

    return AiQuestionSetDetailResponse(
        ai_set_id=ai_set.ai_set_id,
        set_version=ai_set.set_version,
        template_id=ai_set.template_id,
        source_template_version=ai_set.source_template_version,
        source_content_hash=ai_set.source_content_hash,
        job_id=ai_set.job_id,
        job_title=job_title,
        job_revision=template.revision,
        lifecycle_status=ai_set.lifecycle_status,
        is_immutable=ai_set.is_immutable,
        content_hash=ai_set.content_hash,
        slots=slot_dtos,
        total_slots_count=len(slot_dtos),
        generated_slots_count=generated_count,
        reviewed_slots_count=reviewed_count,
        is_source_stale=is_stale,
        stale_reason=stale_reason,
        created_at=ai_set.created_at,
        updated_at=ai_set.updated_at,
        approved_at=ai_set.approved_at,
    )


def list_ai_question_sets(
    actor: UserRecord,
    db: Session,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    sort_by: str = "updated_at",
) -> AiQuestionSetDirectoryResponse:
    """Lists organization-scoped AI question sets with search, filter, and metrics."""
    # Find templates belonging to actor / organization
    stmt = (
        select(AiInterviewQuestionSetRecord)
        .join(JobInterviewTemplateRecord, AiInterviewQuestionSetRecord.template_id == JobInterviewTemplateRecord.template_id)
        .join(JobRequisition, JobInterviewTemplateRecord.job_id == JobRequisition.job_id)
        .options(
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.questions),
        )
    )
    if actor.role == UserRole.RECRUITER:
        stmt = stmt.where(JobRequisition.created_by_user_id == actor.user_id)
    stmt = stmt.order_by(desc(AiInterviewQuestionSetRecord.updated_at))

    records = db.execute(stmt).scalars().all()

    # Deduplicate to latest version per template_id
    latest_by_template: Dict[UUID, AiInterviewQuestionSetRecord] = {}
    for r in records:
        if r.template_id not in latest_by_template or r.set_version > latest_by_template[r.template_id].set_version:
            latest_by_template[r.template_id] = r

    summaries: List[AiQuestionSetSummaryResponse] = []
    total_count = 0
    awaiting_review = 0
    ready_for_approval = 0
    approved = 0

    for ai_set in latest_by_template.values():
        tmpl = ai_set.template
        if not tmpl or not tmpl.requisition:
            continue

        # Recruiter isolation
        if actor.role == UserRole.RECRUITER and tmpl.requisition.created_by_user_id != actor.user_id:
            continue

        # Check staleness
        is_stale = bool(tmpl.content_hash and ai_set.source_content_hash != tmpl.content_hash)
        eff_status = "STALE" if (is_stale and ai_set.lifecycle_status != "APPROVED") else ai_set.lifecycle_status

        total_count += 1
        if eff_status == "APPROVED":
            approved += 1
        elif eff_status == "VALIDATED":
            ready_for_approval += 1
        else:
            awaiting_review += 1

        # Title
        title = "Job Requisition"
        stmt_ver = select(JobVersion).where(JobVersion.job_version_id == tmpl.job_version_id)
        ver = db.execute(stmt_ver).scalar_one_or_none()
        if ver and ver.title:
            title = ver.title

        gen_count = sum(1 for it in ai_set.items if it.get("ai_wording"))
        total_slots = len(ai_set.items)

        # Filters
        if search and search.strip():
            if search.strip().lower() not in title.lower():
                continue

        if status_filter and status_filter.upper() != "ALL":
            if eff_status.upper() != status_filter.upper():
                continue

        summaries.append(
            AiQuestionSetSummaryResponse(
                ai_set_id=ai_set.ai_set_id,
                set_version=ai_set.set_version,
                template_id=ai_set.template_id,
                job_id=ai_set.job_id,
                job_title=title,
                lifecycle_status=eff_status,
                is_immutable=ai_set.is_immutable,
                is_source_stale=is_stale,
                generated_question_count=gen_count,
                total_blueprint_slots=total_slots,
                created_at=ai_set.created_at,
                updated_at=ai_set.updated_at,
            )
        )

    return AiQuestionSetDirectoryResponse(
        sets=summaries,
        total_count=total_count,
        awaiting_review_count=awaiting_review,
        ready_for_approval_count=ready_for_approval,
        approved_count=approved,
    )


def get_eligible_jobs_for_ai_questions(
    actor: UserRecord,
    db: Session,
) -> EligibleJobsResponse:
    """Retrieves organization-scoped jobs available to the recruiter for AI interview generation.
    
    Zero-leakage: exposes only job_id, job_title, and server-calculated requirement_count.
    """
    stmt = (
        select(JobRequisition)
        .options(
            selectinload(JobRequisition.versions).selectinload(JobVersion.requirements)
        )
        .where(JobRequisition.status == JobLifecycleStatus.ACTIVE)
    )
    if actor.role == UserRole.RECRUITER:
        stmt = stmt.where(JobRequisition.created_by_user_id == actor.user_id)
    stmt = stmt.order_by(desc(JobRequisition.updated_at))

    records = db.execute(stmt).scalars().all()
    items: List[EligibleJobItemResponse] = []
    for job in records:
        if not job.versions:
            continue
        latest_ver = job.versions[-1]
        req_count = len(latest_ver.requirements) if latest_ver.requirements else 0
        if req_count == 0:
            continue
        job_title = latest_ver.title or f"Job #{str(job.job_id)[:8]}"
        items.append(
            EligibleJobItemResponse(
                job_id=job.job_id,
                job_title=job_title,
                requirement_count=req_count,
            )
        )

    return EligibleJobsResponse(items=items)


def get_ai_question_set_by_template(
    actor: UserRecord,
    template_id: UUID,
    db: Session,
) -> AiQuestionSetDetailResponse:
    """Retrieves the latest AI question set for a template or ai_set_id, enforcing isolation and freshness."""
    stmt_tmpl = (
        select(JobInterviewTemplateRecord)
        .options(
            selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(JobInterviewTemplateRecord.template_id == template_id)
    )
    template = db.execute(stmt_tmpl).scalar_one_or_none()
    
    ai_set = None
    if not template:
        # Check if template_id is an ai_set_id
        stmt_set_direct = (
            select(AiInterviewQuestionSetRecord)
            .where(AiInterviewQuestionSetRecord.ai_set_id == template_id)
        )
        ai_set = db.execute(stmt_set_direct).scalars().first()
        if ai_set:
            stmt_tmpl2 = (
                select(JobInterviewTemplateRecord)
                .options(
                    selectinload(JobInterviewTemplateRecord.requisition),
                    selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
                )
                .where(JobInterviewTemplateRecord.template_id == ai_set.template_id)
            )
            template = db.execute(stmt_tmpl2).scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TEMPLATE_NOT_FOUND", "message": "Deterministic interview template not found."},
        )
    _check_recruiter_access(actor, template.requisition)

    if not ai_set:
        stmt_set = (
            select(AiInterviewQuestionSetRecord)
            .where(AiInterviewQuestionSetRecord.template_id == template.template_id)
            .order_by(desc(AiInterviewQuestionSetRecord.set_version))
        )
        ai_set = db.execute(stmt_set).scalars().first()

    if not ai_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AI_SET_NOT_FOUND", "message": "No AI question set generated for this template yet."},
        )

    return _map_record_to_detail_dto(ai_set, template, db)


async def generate_ai_questions_by_job_id(
    actor: UserRecord,
    job_id: UUID,
    force_regenerate: bool,
    db: Session,
    provider_registry: Optional[ProviderRegistry] = None,
    custom_provider: Optional[BaseWordingProvider] = None,
) -> AiQuestionSetDetailResponse:
    """Server-authoritative generation command given a selected job_id.
    
    1. Reloads job under authenticated recruiter scope.
    2. Resolves current approved/ready revision.
    3. Retrieves or creates deterministic interview blueprint.
    4. Uses deterministic blueprint inputs to generate AI questions.
    5. Persists and returns the AI question set.
    """
    stmt_job = (
        select(JobRequisition)
        .options(selectinload(JobRequisition.versions).selectinload(JobVersion.requirements))
        .where(JobRequisition.job_id == job_id)
    )
    job = db.execute(stmt_job).scalar_one_or_none()
    if not job or not job.versions or job.status != JobLifecycleStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_JOB", "message": "This job is not ready for interview generation."},
        )
    _check_recruiter_access(actor, job)

    latest_version = job.versions[-1]
    if not latest_version.requirements:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_JOB", "message": "This job is not ready for interview generation."},
        )

    # Find existing deterministic template for this revision
    stmt_tmpl = (
        select(JobInterviewTemplateRecord)
        .options(
            selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(
            JobInterviewTemplateRecord.job_id == job_id,
            JobInterviewTemplateRecord.revision == latest_version.version_number,
        )
        .order_by(desc(JobInterviewTemplateRecord.template_version))
    )
    template_rec = db.execute(stmt_tmpl).scalars().first()

    if not template_rec or not template_rec.questions:
        from app.services.interview_generator_service import create_deterministic_interview_template_draft
        template_rec, _ = create_deterministic_interview_template_draft(
            actor=actor,
            job_id=job.job_id,
            expected_revision=latest_version.version_number,
            db=db,
            organization_id=getattr(actor, "organization_id", None),
        )

    return await generate_or_open_ai_question_set(
        actor=actor,
        job_id=job.job_id,
        template_id=template_rec.template_id,
        force_regenerate=force_regenerate,
        db=db,
        provider_registry=provider_registry,
        custom_provider=custom_provider,
    )


async def generate_or_open_ai_question_set(
    actor: UserRecord,
    job_id: UUID,
    template_id: UUID,
    force_regenerate: bool,
    db: Session,
    provider_registry: Optional[ProviderRegistry] = None,
    custom_provider: Optional[BaseWordingProvider] = None,
) -> AiQuestionSetDetailResponse:
    """Generates a new AI question set or returns existing draft for the current source hash.
    
    Invariants:
    - If active set exists for the same content_hash and not force_regenerate: open it (no duplicate runs).
    - If force_regenerate: preserve prior version, increment set_version.
    - Sequentially queries local LM Studio bounded provider for eligible slots.
    - Saves slot items without altering deterministic questions in the template.
    """
    stmt_tmpl = (
        select(JobInterviewTemplateRecord)
        .options(
            selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(
            JobInterviewTemplateRecord.template_id == template_id,
            JobInterviewTemplateRecord.job_id == job_id,
        )
    )
    template = db.execute(stmt_tmpl).scalar_one_or_none()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TEMPLATE_NOT_FOUND", "message": "Interview template not found for job."},
        )
    _check_recruiter_access(actor, template.requisition)

    source_hash = template.content_hash or hashlib.sha256(str(template_id).encode("utf-8")).hexdigest()

    # Check for existing latest version
    stmt_latest = (
        select(AiInterviewQuestionSetRecord)
        .where(AiInterviewQuestionSetRecord.template_id == template_id)
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    latest_set = db.execute(stmt_latest).scalars().first()

    if latest_set and not force_regenerate:
        # If source hash is identical and not approved, return existing draft
        if latest_set.source_content_hash == source_hash:
            return _map_record_to_detail_dto(latest_set, template, db)

    # Next version number
    next_version = (latest_set.set_version + 1) if latest_set else 1

    # Order questions
    questions = sorted(template.questions or [], key=lambda q: q.display_order)
    items: List[Dict[str, Any]] = []

    reg = provider_registry or get_provider_registry()

    for q in questions:
        item: Dict[str, Any] = {
            "slot_id": str(q.question_id),
            "display_order": q.display_order,
            "competency_name": q.competency_id or "Core Competency",
            "question_type": q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type),
            "estimated_time_minutes": q.estimated_time_minutes,
            "permitted_probes": list(q.permitted_probes or []),
            "ai_wording": None,
            "review_state": "UNREVIEWED",
            "authoring_origin": "AI_GENERATED",
            "validation_status": "PASSED",
            "safe_failure_code": None,
            "rationale_code": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Request wording assistance from local provider using bounded request
        wording_req = RecruiterWordingAssistRequest(
            expected_question_version=q.question_version,
            source_content_hash=None,
            max_variants=1,
            target_tone="PROFESSIONAL",
        )
        try:
            cand = await request_question_wording_assistance(
                actor=actor,
                question_id=q.question_id,
                request_dto=wording_req,
                db=db,
                provider_registry=reg,
                custom_provider=custom_provider,
            )
            if cand.is_validated and cand.proposed_variants:
                chosen = cand.proposed_variants[0]
                item["ai_wording"] = chosen.variant_text.strip()
                item["validation_status"] = "PASSED"
                item["rationale_code"] = (
                    chosen.rationale_code.value
                    if hasattr(chosen.rationale_code, "value")
                    else str(chosen.rationale_code)
                )
            else:
                item["validation_status"] = "FAILED"
                item["safe_failure_code"] = "SEMANTIC_VALIDATION_FAILED"
        except Exception:
            item["validation_status"] = "FAILED"
            item["safe_failure_code"] = "PROVIDER_UNAVAILABLE"

        items.append(item)

    # Create new AiInterviewQuestionSetRecord
    new_set = AiInterviewQuestionSetRecord(
        ai_set_id=uuid.uuid4(),
        organization_id=template.organization_id,
        template_id=template.template_id,
        job_id=template.job_id,
        source_template_version=template.template_version,
        source_content_hash=source_hash,
        set_version=next_version,
        lifecycle_status="DRAFT",
        is_immutable=False,
        items=items,
        created_by_user_id=actor.user_id,
    )
    db.add(new_set)
    db.commit()
    db.refresh(new_set)

    return _map_record_to_detail_dto(new_set, template, db)


def update_ai_question_slot(
    actor: UserRecord,
    template_id: UUID,
    slot_id: UUID,
    payload: AiQuestionSlotUpdateRequest,
    db: Session,
) -> AiQuestionSetDetailResponse:
    """Updates the wording or review status of a single slot in an unsealed AI question set."""
    stmt_tmpl = (
        select(JobInterviewTemplateRecord)
        .options(
            selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(JobInterviewTemplateRecord.template_id == template_id)
    )
    template = db.execute(stmt_tmpl).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found.")
    _check_recruiter_access(actor, template.requisition)

    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .where(AiInterviewQuestionSetRecord.template_id == template_id)
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    ai_set = db.execute(stmt_set).scalars().first()
    if not ai_set:
        raise HTTPException(status_code=404, detail="AI question set not found.")

    if ai_set.is_immutable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SET_IS_IMMUTABLE", "message": "Approved AI question sets cannot be modified in-place."},
        )

    # Find slot
    str_slot_id = str(slot_id)
    target_item = None
    items_copy = list(ai_set.items)
    for idx, it in enumerate(items_copy):
        if str(it.get("slot_id")) == str_slot_id:
            target_item = it
            break

    if not target_item:
        raise HTTPException(status_code=404, detail="Slot not found in AI question set.")

    decision = payload.decision.upper()
    if decision == "KEEP":
        if not target_item.get("ai_wording"):
            raise HTTPException(status_code=422, detail="Cannot keep slot with no AI wording.")
        target_item["review_state"] = "KEPT"
        target_item["updated_at"] = datetime.now(timezone.utc).isoformat()
    elif decision == "EDIT":
        if not payload.wording or not payload.wording.strip():
            raise HTTPException(status_code=422, detail="Edited wording cannot be empty.")
        target_item["ai_wording"] = payload.wording.strip()
        target_item["review_state"] = "EDITED"
        target_item["authoring_origin"] = "RECRUITER_EDITED"
        target_item["validation_status"] = "PASSED"
        target_item["safe_failure_code"] = None
        target_item["updated_at"] = datetime.now(timezone.utc).isoformat()
    elif decision == "REVISE":
        target_item["review_state"] = "REVISED"
        target_item["updated_at"] = datetime.now(timezone.utc).isoformat()
    elif decision == "MANUAL_AUTHOR":
        if not payload.wording or not payload.wording.strip():
            raise HTTPException(status_code=422, detail="Manual question wording cannot be empty.")
        target_item["ai_wording"] = payload.wording.strip()
        target_item["review_state"] = "RECRUITER_AUTHORED"
        target_item["authoring_origin"] = "RECRUITER_AUTHORED"
        target_item["validation_status"] = "PASSED"
        target_item["safe_failure_code"] = None
        target_item["updated_at"] = datetime.now(timezone.utc).isoformat()
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported review decision '{payload.decision}'.")

    ai_set.items = items_copy
    flag_modified(ai_set, "items")
    db.commit()
    db.refresh(ai_set)

    return _map_record_to_detail_dto(ai_set, template, db)


async def regenerate_ai_question_slot(
    actor: UserRecord,
    template_id: UUID,
    slot_id: UUID,
    db: Session,
    provider_registry: Optional[ProviderRegistry] = None,
    custom_provider: Optional[BaseWordingProvider] = None,
) -> AiQuestionSetDetailResponse:
    """Regenerates AI wording for a single blueprint slot using the local LM Studio provider."""
    stmt_tmpl = (
        select(JobInterviewTemplateRecord)
        .options(
            selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(JobInterviewTemplateRecord.template_id == template_id)
    )
    template = db.execute(stmt_tmpl).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found.")
    _check_recruiter_access(actor, template.requisition)

    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .where(AiInterviewQuestionSetRecord.template_id == template_id)
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    ai_set = db.execute(stmt_set).scalars().first()
    if not ai_set:
        raise HTTPException(status_code=404, detail="AI question set not found.")
    if ai_set.is_immutable:
        raise HTTPException(status_code=409, detail="Approved AI question sets cannot be modified in-place.")

    # Find slot
    str_slot_id = str(slot_id)
    target_item = None
    items_copy = list(ai_set.items)
    for it in items_copy:
        if str(it.get("slot_id")) == str_slot_id:
            target_item = it
            break

    if not target_item:
        raise HTTPException(status_code=404, detail="Slot not found.")

    # Find underlying question
    q_rec = next((q for q in template.questions if q.question_id == slot_id), None)
    if not q_rec:
        raise HTTPException(status_code=404, detail="Blueprint question record not found.")

    reg = provider_registry or get_provider_registry()
    wording_req = RecruiterWordingAssistRequest(
        expected_question_version=q_rec.question_version,
        source_content_hash=None,
        max_variants=1,
        target_tone="PROFESSIONAL",
    )
    try:
        cand = await request_question_wording_assistance(
            actor=actor,
            question_id=q_rec.question_id,
            request_dto=wording_req,
            db=db,
            provider_registry=reg,
            custom_provider=custom_provider,
        )
        if cand.is_validated and cand.proposed_variants:
            chosen = cand.proposed_variants[0]
            target_item["ai_wording"] = chosen.variant_text.strip()
            target_item["validation_status"] = "PASSED"
            target_item["safe_failure_code"] = None
            target_item["review_state"] = "UNREVIEWED"
            target_item["authoring_origin"] = "AI_GENERATED"
            target_item["rationale_code"] = (
                chosen.rationale_code.value
                if hasattr(chosen.rationale_code, "value")
                else str(chosen.rationale_code)
            )
        else:
            target_item["validation_status"] = "FAILED"
            target_item["safe_failure_code"] = "SEMANTIC_VALIDATION_FAILED"
    except Exception:
        target_item["validation_status"] = "FAILED"
        target_item["safe_failure_code"] = "PROVIDER_UNAVAILABLE"

    target_item["updated_at"] = datetime.now(timezone.utc).isoformat()
    ai_set.items = items_copy
    flag_modified(ai_set, "items")
    db.commit()
    db.refresh(ai_set)

    return _map_record_to_detail_dto(ai_set, template, db)


def validate_ai_question_set(
    actor: UserRecord,
    template_id: UUID,
    db: Session,
) -> AiQuestionSetValidateResponse:
    """Validates the AI question set against readiness, staleness, and safety rules."""
    stmt_tmpl = (
        select(JobInterviewTemplateRecord)
        .options(selectinload(JobInterviewTemplateRecord.requisition))
        .where(JobInterviewTemplateRecord.template_id == template_id)
    )
    template = db.execute(stmt_tmpl).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found.")
    _check_recruiter_access(actor, template.requisition)

    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .where(AiInterviewQuestionSetRecord.template_id == template_id)
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    ai_set = db.execute(stmt_set).scalars().first()
    if not ai_set:
        raise HTTPException(status_code=404, detail="AI question set not found.")

    errors: List[str] = []

    # 1. Staleness check
    if template.content_hash and ai_set.source_content_hash != template.content_hash:
        errors.append("AI question set is stale: deterministic blueprint has changed since generation. Please regenerate.")

    # 2. All slots resolved check
    for it in ai_set.items:
        slot_num = it.get("display_order", 0) + 1
        wording = it.get("ai_wording")
        if not wording or not wording.strip():
            errors.append(f"Question #{slot_num} has no wording. Please generate, edit, or author manually.")
        if it.get("validation_status") == "FAILED":
            errors.append(f"Question #{slot_num} failed safety validation ({it.get('safe_failure_code')}).")

    # 3. Duplicate check across question texts
    seen_texts = set()
    for it in ai_set.items:
        w = (it.get("ai_wording") or "").strip().lower()
        if w:
            if w in seen_texts:
                errors.append(f"Duplicate question detected: multiple questions share identical wording.")
            seen_texts.add(w)

    is_valid = len(errors) == 0
    if is_valid and ai_set.lifecycle_status != "APPROVED":
        ai_set.lifecycle_status = "VALIDATED"
        db.commit()

    return AiQuestionSetValidateResponse(
        is_valid=is_valid,
        lifecycle_status=ai_set.lifecycle_status,
        blocking_errors=errors,
        safe_message="AI question set successfully validated." if is_valid else "Validation failed with blocking issues.",
    )


def approve_ai_question_set(
    actor: UserRecord,
    template_id: UUID,
    db: Session,
) -> AiQuestionSetApproveResponse:
    """Explicitly approves the AI question set, sealing its content hash and locking it as immutable."""
    # Run validation first
    val = validate_ai_question_set(actor, template_id, db)
    if not val.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_BLOCKED", "message": "Cannot approve invalid AI question set.", "errors": val.blocking_errors},
        )

    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .where(AiInterviewQuestionSetRecord.template_id == template_id)
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    ai_set = db.execute(stmt_set).scalars().first()
    if not ai_set:
        raise HTTPException(status_code=404, detail="AI question set not found.")

    if ai_set.is_immutable:
        return AiQuestionSetApproveResponse(
            ai_set_id=ai_set.ai_set_id,
            set_version=ai_set.set_version,
            lifecycle_status="APPROVED",
            is_immutable=True,
            content_hash=ai_set.content_hash or "",
            approved_at=ai_set.approved_at or datetime.now(timezone.utc),
            safe_message="AI question set is already approved and locked.",
        )

    # Compute sealed content hash over ordered wording and slots
    canonical_payload = []
    for it in sorted(ai_set.items, key=lambda x: x.get("display_order", 0)):
        canonical_payload.append({
            "slot_id": it.get("slot_id"),
            "display_order": it.get("display_order"),
            "wording": it.get("ai_wording"),
            "authoring_origin": it.get("authoring_origin"),
        })

    sealed_hash = hashlib.sha256(json.dumps(canonical_payload, sort_keys=True).encode("utf-8")).hexdigest()

    now = datetime.now(timezone.utc)
    ai_set.lifecycle_status = "APPROVED"
    ai_set.is_immutable = True
    ai_set.content_hash = sealed_hash
    ai_set.approved_at = now
    ai_set.approved_by_user_id = actor.user_id

    db.commit()
    db.refresh(ai_set)

    return AiQuestionSetApproveResponse(
        ai_set_id=ai_set.ai_set_id,
        set_version=ai_set.set_version,
        lifecycle_status="APPROVED",
        is_immutable=True,
        content_hash=sealed_hash,
        approved_at=now,
        safe_message="AI question set approved and locked. Immutability sealed.",
    )
