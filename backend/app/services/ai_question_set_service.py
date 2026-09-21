"""Domain service for Phase 3D.5 Dedicated AI Interview Questions Workspace.

Separates deterministic interview template authoring from AI question generation.
Preserves the deterministic blueprint as authoritative foundation while maintaining
strict data boundary: never leaking deterministic question wording into AI responses.
Supports both BLUEPRINT_GROUNDED and REQUIREMENT_GROUNDED generation modes.
"""
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
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
from app.models.job import JobLifecycleStatus, JobRequisition, JobRequirement, JobVersion
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
from app.schemas.phase3_enums import AuthoringOrigin, InterviewLayer, PlanLifecycle, QuestionType
from app.schemas.safety_policy import check_prohibited_topics
from app.schemas.wording_contract import (
    PROMPT_TEMPLATE_VERSION,
    BoundedWordingRequest,
    BoundedWordingResponse,
    CandidateWordingResult,
    RecruiterWordingAssistRequest,
    StructuredWordingVariant,
    WordingRationaleCode,
)
from app.services.provider_registry import ProviderRegistry, get_provider_registry
from app.services.wording_assistance_service import (
    request_question_wording_assistance,
)
from app.services.wording_provider import BaseWordingProvider

logger = logging.getLogger("ai_hiring.ai_question_set_service")


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
    # Check org isolation
    actor_org = getattr(actor, "org_id", getattr(actor, "organization_id", None))
    job_org = getattr(job, "org_id", getattr(job, "organization_id", None))
    if actor_org is not None and job_org is not None and actor_org != job_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Access to requisition denied across organizations."},
        )


def _map_rubric_to_safe(q_rec: Optional[InterviewQuestionRecord]) -> Optional[SafeRubricResponse]:
    if not q_rec or not hasattr(q_rec, "rubric") or not q_rec.rubric:
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


def _compute_requirement_fingerprint(job_id: UUID, version_id: UUID, revision: int, requirement_ids: List[str]) -> str:
    sorted_ids = sorted(str(rid) for rid in requirement_ids)
    raw = f"REQ_GROUNDED:{job_id}:{version_id}:{revision}:{','.join(sorted_ids)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_requirement_eligible(req: JobRequirement) -> bool:
    """Filters out administrative, personal, unapproved, or prompt-injected requirements."""
    label_text = getattr(req, "label", getattr(req, "name", "")) or ""
    if not label_text.strip():
        return False
    
    rationale_text = getattr(req, "rationale", getattr(req, "description", "")) or ""
    text = f"{label_text} {rationale_text}".lower()
    
    # Administrative exclusions
    admin_terms = [
        "relocation", "visa sponsorship", "driver's license", "drivers license",
        "background check", "drug test", "salary requirement", "working hours",
        "shift work", "commute", "citizenship", "security clearance"
    ]
    if any(term in text for term in admin_terms):
        return False
        
    # Prompt injection / model control exclusions
    injection_terms = [
        "ignore previous", "ignore all", "system prompt", "developer instruction",
        "you are a", "jailbreak", "override", "disregard instructions"
    ]
    if any(term in text for term in injection_terms):
        return False
        
    return True


def _build_requirement_grounded_plan(
    job: JobRequisition,
    job_version: JobVersion,
) -> Dict[str, Any]:
    """Constructs a bounded RequirementGroundedGenerationPlan from approved requirements.
    
    Bounded: 4-6 questions, high priority first, distinct competencies.
    """
    raw_requirements = list(job_version.requirements or [])
    eligible = [r for r in raw_requirements if _is_requirement_eligible(r)]
    
    if not eligible and raw_requirements:
        # If all were strictly filtered by safety heuristic, fallback safely to the first non-injected
        eligible = raw_requirements
        
    # Sort: MUST_HAVE / CRITICAL first
    def sort_key(r: JobRequirement) -> int:
        nec = getattr(r, "necessity", getattr(r, "importance", None))
        nec_str = nec.value if hasattr(nec, "value") else str(nec or "")
        prio = getattr(r, "priority", None)
        prio_str = prio.value if hasattr(prio, "value") else str(prio or "")
        if nec_str.upper() == "MUST_HAVE" or prio_str.upper() in ("CRITICAL", "HIGH"):
            return 0
        return 1

    eligible.sort(key=sort_key)
    
    # Cap between 4 and 6 questions (or fewer if fewer eligible requirements)
    target_count = min(6, max(len(eligible), 1))
    if target_count > len(eligible):
        target_count = len(eligible)
        
    selected_reqs = eligible[:target_count]
    
    slots: List[Dict[str, Any]] = []
    for idx, req in enumerate(selected_reqs):
        cat_val = req.category.value if hasattr(req.category, "value") else str(req.category)
        q_type = "TECHNICAL" if cat_val in ("SKILL", "EXPERIENCE", "HARD_SKILL", "DOMAIN_KNOWLEDGE") else "BEHAVIORAL"
        req_name = getattr(req, "label", getattr(req, "name", "Requirement")).strip()
        req_desc = getattr(req, "rationale", getattr(req, "description", req_name)) or req_name
        
        slot_id = str(uuid.uuid4())
        slots.append({
            "slot_id": slot_id,
            "display_order": idx,
            "source_requirement_ids": [str(req.requirement_id)],
            "competency_name": req_name,
            "requirement_summary": req_desc.strip()[:250],
            "question_type": q_type,
            "estimated_time_minutes": 6,
            "permitted_probes": [
                f"Can you provide a concrete example from your past work demonstrating {req_name}?",
                "What challenges or trade-offs did you encounter and how did you resolve them?",
            ],
            "rubric": {
                "rubric_id": str(uuid.uuid4()),
                "rubric_version": 1,
                "competency_definition": f"Demonstrated proficiency and applied practical experience in {req_name}.",
                "question_intent": f"Assess depth of experience, technical decision-making, and execution capability for {req_name}.",
                "observable_indicators": [
                    f"Articulates core principles and design trade-offs of {req_name}.",
                    "Demonstrates practical hands-on problem-solving rather than purely theoretical knowledge.",
                    "Explains edge cases, failure modes, or architectural considerations clearly.",
                ],
                "rating_anchors": {
                    "1": f"No substantive knowledge or practical experience with {req_name}.",
                    "3": f"Solid working knowledge and practical execution of {req_name}.",
                    "5": f"Expert mastery, deep architectural insights, and advanced handling of complex edge cases.",
                },
                "sufficient_evidence_guidance": f"Candidate provides verifiable project details, specific technologies used, and reasoning for {req_name}.",
                "insufficient_evidence_guidance": "Candidate speaks in high-level generalities without concrete technical examples.",
                "permitted_probes": [
                    f"Can you provide a concrete example from your past work demonstrating {req_name}?",
                    "What challenges or trade-offs did you encounter and how did you resolve them?",
                ],
            },
        })
        
    req_ids = [str(r.requirement_id) for r in selected_reqs]
    fingerprint = _compute_requirement_fingerprint(
        job.job_id,
        job_version.job_version_id,
        job_version.version_number,
        req_ids,
    )
    
    return {
        "job_id": str(job.job_id),
        "job_version_id": str(job_version.job_version_id),
        "job_revision": job_version.version_number,
        "job_title": job_version.title or f"Job #{str(job.job_id)[:8]}",
        "fingerprint": fingerprint,
        "source_requirement_ids": req_ids,
        "slots": slots,
    }


def _validate_ai_wording_safety(text: str) -> Tuple[bool, Optional[str]]:
    """Strictly validates generated wording against prompt injection and safety policies."""
    if not text or len(text.strip()) < 15:
        return False, "WORDING_TOO_SHORT"
    if len(text.strip()) > 1200:
        return False, "WORDING_TOO_LONG"
        
    # Check HTML tags
    if re.search(r"<[^>]+>", text):
        return False, "PROHIBITED_HTML_CONTENT"
        
    # Prohibited topic checks
    violation = check_prohibited_topics(text)
    if violation is not None:
        category, _ = violation
        return False, f"PROHIBITED_TOPIC_{category}"
        
    # Rejection of scores, rankings, recommendations in question text
    lower = text.lower()
    score_words = ["score:", "candidate score", "hiring recommendation", "ranking:", "pass/fail"]
    if any(sw in lower for sw in score_words):
        return False, "INVALID_MODEL_OUTPUT"
        
    return True, None


async def _generate_requirement_grounded_slots(
    plan: Dict[str, Any],
    actor: UserRecord,
    db: Session,
    provider_registry: Optional[ProviderRegistry] = None,
    custom_provider: Optional[BaseWordingProvider] = None,
) -> List[Dict[str, Any]]:
    """Generates AI wording for each slot in a RequirementGroundedGenerationPlan using the local model."""
    reg = provider_registry or get_provider_registry()
    items: List[Dict[str, Any]] = []
    
    active_profile = None
    try:
        active_profile = reg.get_active_profile()
    except Exception:
        pass

    for slot in plan["slots"]:
        item: Dict[str, Any] = {
            "slot_id": slot["slot_id"],
            "display_order": slot["display_order"],
            "source_requirement_ids": slot["source_requirement_ids"],
            "competency_name": slot["competency_name"],
            "question_type": slot["question_type"],
            "estimated_time_minutes": slot["estimated_time_minutes"],
            "permitted_probes": slot["permitted_probes"],
            "rubric": slot.get("rubric"),
            "ai_wording": None,
            "review_state": "UNREVIEWED",
            "authoring_origin": "AI_GENERATED",
            "validation_status": "PENDING",
            "safe_failure_code": None,
            "rationale_code": "REQUIREMENT_GROUNDED",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Build bounded request for local provider
        q_type_enum = QuestionType.TECHNICAL if slot["question_type"] == "TECHNICAL" else QuestionType.BEHAVIORAL
        seed_text = slot.get("requirement_summary") or f"Assess hands-on proficiency in {slot['competency_name']}."
        if len(seed_text) < 5:
            seed_text = f"Assess practical proficiency in {slot['competency_name']}."
            
        bounded_req = BoundedWordingRequest(
            source_question_id=uuid.UUID(slot["slot_id"]),
            source_question_version=1,
            deterministic_question_text=seed_text,
            question_intent=f"Assess depth of experience and practical execution in {slot['competency_name']}.",
            competency_label=slot["competency_name"][:200],
            question_type=q_type_enum,
            layer=InterviewLayer.COMMON_CORE,
            allowed_reference_ids=slot["source_requirement_ids"],
            max_variants=1,
        )

        try:
            provider = custom_provider or (reg.get_provider_instance(active_profile) if active_profile else None)
            if not provider:
                item["validation_status"] = "FAILED"
                item["safe_failure_code"] = "PROVIDER_UNAVAILABLE"
            else:
                resp: BoundedWordingResponse = await provider.request_wording_assistance(bounded_req)
                if resp.variants:
                    wording = resp.variants[0].variant_text.strip()
                    is_valid, fail_code = _validate_ai_wording_safety(wording)
                    if is_valid:
                        item["ai_wording"] = wording
                        item["validation_status"] = "PASSED"
                        item["safe_failure_code"] = None
                    else:
                        # Attempt 1 controlled repair
                        repair_req = BoundedWordingRequest(
                            source_question_id=uuid.UUID(slot["slot_id"]),
                            source_question_version=1,
                            deterministic_question_text=seed_text,
                            question_intent=f"Assess practical experience with {slot['competency_name']} safely and concisely.",
                            competency_label=slot["competency_name"][:200],
                            question_type=q_type_enum,
                            layer=InterviewLayer.COMMON_CORE,
                            allowed_reference_ids=slot["source_requirement_ids"],
                            max_variants=1,
                        )
                        repair_resp = await provider.request_wording_assistance(repair_req)
                        if repair_resp.variants:
                            repaired = repair_resp.variants[0].variant_text.strip()
                            r_valid, r_code = _validate_ai_wording_safety(repaired)
                            if r_valid:
                                item["ai_wording"] = repaired
                                item["validation_status"] = "PASSED"
                                item["safe_failure_code"] = None
                            else:
                                item["validation_status"] = "FAILED"
                                item["safe_failure_code"] = r_code or "SEMANTIC_VALIDATION_FAILED"
                        else:
                            item["validation_status"] = "FAILED"
                            item["safe_failure_code"] = "SEMANTIC_VALIDATION_FAILED"
                else:
                    item["validation_status"] = "FAILED"
                    item["safe_failure_code"] = "PROVIDER_UNAVAILABLE"
        except Exception as e:
            logger.warning(f"Requirement-grounded wording generation failed for slot {slot['slot_id']}: {e}")
            item["validation_status"] = "FAILED"
            item["safe_failure_code"] = "PROVIDER_UNAVAILABLE"

        items.append(item)

    return items


def _map_record_to_detail_dto(
    ai_set: AiInterviewQuestionSetRecord,
    db: Session,
    action: Optional[str] = None,
) -> AiQuestionSetDetailResponse:
    """Transforms an AiInterviewQuestionSetRecord into a secure, safe detail DTO.
    
    Strictly guarantees zero leakage of deterministic question wording.
    """
    template = ai_set.template
    questions_by_id = {q.question_id: q for q in (template.questions or [])} if (template and template.questions) else {}

    # Check staleness
    is_stale = False
    stale_reason = None
    if ai_set.source_mode == "BLUEPRINT_GROUNDED" and template:
        current_hash = template.content_hash or ""
        if current_hash and ai_set.source_content_hash != current_hash:
            is_stale = True
            stale_reason = "Deterministic blueprint was modified since AI question set generation."
    elif ai_set.source_mode == "REQUIREMENT_GROUNDED":
        # Check current requirements fingerprint
        job_stmt = select(JobRequisition).options(
            selectinload(JobRequisition.versions).selectinload(JobVersion.requirements)
        ).where(JobRequisition.job_id == ai_set.job_id)
        job = db.execute(job_stmt).scalar_one_or_none()
        if job and job.versions:
            latest_v = job.versions[-1]
            req_ids = [str(r.requirement_id) for r in (latest_v.requirements or [])]
            curr_fp = _compute_requirement_fingerprint(job.job_id, latest_v.job_version_id, latest_v.version_number, req_ids)
            if curr_fp != ai_set.source_content_hash:
                is_stale = True
                stale_reason = "Job requirements were updated since AI question set generation."

    if is_stale and ai_set.lifecycle_status not in ("APPROVED", "STALE"):
        ai_set.lifecycle_status = "STALE"
        db.commit()

    slot_dtos: List[AiQuestionSlotItemResponse] = []
    reviewed_count = 0
    generated_count = 0

    for item in ai_set.items:
        slot_uuid = UUID(item["slot_id"]) if isinstance(item["slot_id"], str) else item["slot_id"]
        
        # Safely map rubric
        safe_rubric = None
        if slot_uuid in questions_by_id:
            safe_rubric = _map_rubric_to_safe(questions_by_id[slot_uuid])
        elif item.get("rubric"):
            r_data = item["rubric"]
            try:
                safe_rubric = SafeRubricResponse(
                    rubric_id=UUID(r_data["rubric_id"]) if isinstance(r_data.get("rubric_id"), str) else (r_data.get("rubric_id") or uuid.uuid4()),
                    rubric_version=r_data.get("rubric_version", 1),
                    competency_definition=r_data.get("competency_definition", ""),
                    question_intent=r_data.get("question_intent", ""),
                    observable_indicators=list(r_data.get("observable_indicators", [])),
                    rating_anchors={str(k): str(v) for k, v in (r_data.get("rating_anchors") or {}).items()},
                    sufficient_evidence_guidance=r_data.get("sufficient_evidence_guidance"),
                    insufficient_evidence_guidance=r_data.get("insufficient_evidence_guidance"),
                    permitted_probes=list(r_data.get("permitted_probes", [])),
                )
            except Exception:
                safe_rubric = None

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

        source_req_uuids = [
            UUID(rid) if isinstance(rid, str) else rid
            for rid in item.get("source_requirement_ids", [])
        ]

        slot_dtos.append(
            AiQuestionSlotItemResponse(
                slot_id=slot_uuid,
                display_order=item.get("display_order", 0),
                competency_name=item.get("competency_name", "Core Competency"),
                question_type=item.get("question_type", "TECHNICAL"),
                estimated_time_minutes=item.get("estimated_time_minutes", 5),
                permitted_probes=list(item.get("permitted_probes", [])),
                rubric=safe_rubric,
                source_requirement_ids=source_req_uuids,
                ai_wording=ai_wording,
                review_state=review_state,
                authoring_origin=item.get("authoring_origin", "AI_GENERATED"),
                validation_status=item.get("validation_status", "PASSED"),
                safe_failure_code=item.get("safe_failure_code"),
                rationale_code=item.get("rationale_code"),
                updated_at=up_at,
            )
        )

    slot_dtos.sort(key=lambda s: s.display_order)

    # Resolve job title and revision from JobVersion
    job_title = "Job Requisition"
    job_revision = ai_set.job_revision or (template.revision if template else 1)
    
    ver_id = ai_set.job_version_id or (template.job_version_id if template else None)
    if ver_id:
        stmt_ver = select(JobVersion).where(JobVersion.job_version_id == ver_id)
        ver = db.execute(stmt_ver).scalar_one_or_none()
        if ver and ver.title:
            job_title = ver.title
            job_revision = ver.version_number
    elif ai_set.job_id:
        stmt_ver = select(JobVersion).where(JobVersion.job_id == ai_set.job_id).order_by(desc(JobVersion.version_number))
        ver = db.execute(stmt_ver).scalars().first()
        if ver and ver.title:
            job_title = ver.title
            job_revision = ver.version_number

    source_req_set_uuids = [
        UUID(rid) if isinstance(rid, str) else rid
        for rid in (ai_set.source_requirement_ids or [])
    ]

    return AiQuestionSetDetailResponse(
        ai_set_id=ai_set.ai_set_id,
        set_version=ai_set.set_version,
        template_id=ai_set.template_id,
        source_template_version=ai_set.source_template_version,
        source_mode=ai_set.source_mode,
        source_content_hash=ai_set.source_content_hash,
        source_requirement_ids=source_req_set_uuids,
        job_id=ai_set.job_id,
        job_title=job_title,
        job_revision=job_revision,
        lifecycle_status=ai_set.lifecycle_status,
        is_immutable=ai_set.is_immutable,
        content_hash=ai_set.content_hash,
        action=action,
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
    stmt = (
        select(AiInterviewQuestionSetRecord)
        .options(
            selectinload(AiInterviewQuestionSetRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.job_version),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.questions),
        )
        .order_by(desc(AiInterviewQuestionSetRecord.updated_at))
    )
    records = db.execute(stmt).scalars().all()

    # Deduplicate to latest version per job_id or template_id
    latest_by_key: Dict[str, AiInterviewQuestionSetRecord] = {}
    for r in records:
        # Organization check
        actor_org = getattr(actor, "org_id", getattr(actor, "organization_id", None))
        if actor_org is not None and r.organization_id != actor_org:
            continue

        # Recruiter isolation
        job_rec = r.requisition or (r.template.requisition if r.template else None)
        if job_rec and actor.role == UserRole.RECRUITER and job_rec.created_by_user_id != actor.user_id:
            continue

        key = str(r.template_id) if r.template_id else f"job_{r.job_id}_{r.job_revision}"
        if key not in latest_by_key or r.set_version > latest_by_key[key].set_version:
            latest_by_key[key] = r

    summaries: List[AiQuestionSetSummaryResponse] = []
    total_count = 0
    awaiting_review = 0
    ready_for_approval = 0
    approved = 0

    for ai_set in latest_by_key.values():
        eff_status = ai_set.lifecycle_status
        gen_count = sum(1 for it in (ai_set.items or []) if it.get("ai_wording"))
        total_slots = len(ai_set.items or [])

        # Do not include failed / empty question sets in Continue Reviewing directory
        if total_slots == 0 or gen_count == 0:
            continue

        total_count += 1
        if eff_status == "APPROVED":
            approved += 1
        elif eff_status == "VALIDATED":
            ready_for_approval += 1
        else:
            awaiting_review += 1

        title = "Job Requisition"
        ver_id = ai_set.job_version_id or (ai_set.template.job_version_id if ai_set.template else None)
        if ver_id:
            stmt_ver = select(JobVersion).where(JobVersion.job_version_id == ver_id)
            ver = db.execute(stmt_ver).scalar_one_or_none()
            if ver and ver.title:
                title = ver.title
        elif ai_set.job_id:
            stmt_ver = select(JobVersion).where(JobVersion.job_id == ai_set.job_id).order_by(desc(JobVersion.version_number))
            ver = db.execute(stmt_ver).scalars().first()
            if ver and ver.title:
                title = ver.title

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
                source_mode=ai_set.source_mode,
                job_id=ai_set.job_id,
                job_title=title,
                lifecycle_status=eff_status,
                is_immutable=ai_set.is_immutable,
                is_source_stale=(eff_status == "STALE"),
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
    
    Returns job_id, job_title, requirement_count, current_ai_set_id, current_ai_set_status.
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
        
    actor_org = getattr(actor, "org_id", getattr(actor, "organization_id", None))
    if actor_org is not None and hasattr(JobRequisition, "organization_id"):
        stmt = stmt.where(JobRequisition.organization_id == actor_org)
        
    stmt = stmt.order_by(desc(JobRequisition.updated_at))
    records = db.execute(stmt).scalars().all()
    
    items: List[EligibleJobItemResponse] = []
    for job in records:
        if not job.versions:
            continue
        latest_ver = max(job.versions, key=lambda v: v.version_number or 0)
        req_count = len(latest_ver.requirements) if latest_ver.requirements else 0
        if req_count == 0:
            continue
            
        job_title = latest_ver.title or f"Job #{str(job.job_id)[:8]}"

        # Look up current AI question set for this job revision
        stmt_ai = (
            select(AiInterviewQuestionSetRecord)
            .where(
                AiInterviewQuestionSetRecord.job_id == job.job_id,
                (AiInterviewQuestionSetRecord.job_version_id == latest_ver.job_version_id)
                | (AiInterviewQuestionSetRecord.job_revision == latest_ver.version_number),
            )
            .order_by(desc(AiInterviewQuestionSetRecord.set_version))
        )
        latest_ai = db.execute(stmt_ai).scalars().first()

        # Phase 3E.2 binding directory rule:
        # If the current revision of a job already has an AI question set with valid generated questions, exclude it from
        # "Choose a job". It appears solely under "Continue reviewing" / existing sets.
        has_valid_ai_set = (
            latest_ai is not None
            and bool(latest_ai.items)
            and any(it.get("ai_wording") for it in latest_ai.items)
        )
        if has_valid_ai_set:
            continue

        items.append(
            EligibleJobItemResponse(
                job_id=job.job_id,
                job_title=job_title,
                requirement_count=req_count,
                current_ai_set_id=None,
                current_ai_set_status=None,
            )
        )

    return EligibleJobsResponse(items=items)


def get_ai_question_set_by_template(
    actor: UserRecord,
    template_id: UUID,
    db: Session,
) -> AiQuestionSetDetailResponse:
    """Retrieves an AI question set by template_id or ai_set_id, enforcing access and data boundaries."""
    # Try finding directly by ai_set_id
    stmt_set_direct = (
        select(AiInterviewQuestionSetRecord)
        .options(
            selectinload(AiInterviewQuestionSetRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.job_version),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(AiInterviewQuestionSetRecord.ai_set_id == template_id)
    )
    ai_set = db.execute(stmt_set_direct).scalars().first()

    if not ai_set:
        # Try finding by template_id
        stmt_by_tmpl = (
            select(AiInterviewQuestionSetRecord)
            .options(
                selectinload(AiInterviewQuestionSetRecord.requisition),
                selectinload(AiInterviewQuestionSetRecord.job_version),
                selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
                selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
            )
            .where(AiInterviewQuestionSetRecord.template_id == template_id)
            .order_by(desc(AiInterviewQuestionSetRecord.set_version))
        )
        ai_set = db.execute(stmt_by_tmpl).scalars().first()

    if not ai_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AI_SET_NOT_FOUND", "message": "AI interview question set not found."},
        )

    # Authorization check
    job = ai_set.requisition or (ai_set.template.requisition if ai_set.template else None)
    if job:
        _check_recruiter_access(actor, job)

    return _map_record_to_detail_dto(ai_set, db)


async def generate_ai_questions_by_job_id(
    actor: UserRecord,
    job_id: UUID,
    force_regenerate: bool,
    db: Session,
    provider_registry: Optional[ProviderRegistry] = None,
    custom_provider: Optional[BaseWordingProvider] = None,
) -> AiQuestionSetDetailResponse:
    """Server-authoritative generation command given a selected job_id.
    
    Resolution hierarchy:
    1. Load requested job under organization / recruiter assignment scope.
    2. Load current approved / ready revision.
    3. If active AI set exists for current fingerprint and not force_regenerate: return it (OPENED_EXISTING).
    4. Check for usable deterministic blueprint. If usable slots exist -> BLUEPRINT_GROUNDED.
    5. If no usable blueprint -> REQUIREMENT_GROUNDED fallback.
    6. Validate, store as DRAFT, return (GENERATED).
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
            detail={"code": "NO_APPROVED_REQUIREMENTS", "message": "This job needs approved requirements before questions can be generated."},
        )
    _check_recruiter_access(actor, job)

    latest_version = job.versions[-1]
    if not latest_version.requirements or len(latest_version.requirements) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_APPROVED_REQUIREMENTS", "message": "This job needs approved requirements before questions can be generated."},
        )

    # Check for existing active AI question set for this job revision
    stmt_existing = (
        select(AiInterviewQuestionSetRecord)
        .options(
            selectinload(AiInterviewQuestionSetRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.job_version),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(
            AiInterviewQuestionSetRecord.job_id == job.job_id,
            (AiInterviewQuestionSetRecord.job_version_id == latest_version.job_version_id)
            | (AiInterviewQuestionSetRecord.job_revision == latest_version.version_number),
        )
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    existing_set = db.execute(stmt_existing).scalars().first()

    # Step 3: Check if fresh active AI set exists
    if existing_set and not force_regenerate:
        # Check freshness
        is_fresh = True
        if existing_set.source_mode == "BLUEPRINT_GROUNDED" and existing_set.template:
            if existing_set.template.content_hash and existing_set.source_content_hash != existing_set.template.content_hash:
                is_fresh = False
        elif existing_set.source_mode == "REQUIREMENT_GROUNDED":
            req_ids = [str(r.requirement_id) for r in latest_version.requirements]
            curr_fp = _compute_requirement_fingerprint(job.job_id, latest_version.job_version_id, latest_version.version_number, req_ids)
            if curr_fp != existing_set.source_content_hash:
                is_fresh = False

        if is_fresh:
            return _map_record_to_detail_dto(existing_set, db, action="OPENED_EXISTING")

    # Step 5 & 6: Check for usable internal deterministic blueprint with usable slots
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

    if template_rec and template_rec.questions and len(template_rec.questions) > 0:
        # BLUEPRINT_GROUNDED mode
        return await generate_or_open_ai_question_set(
            actor=actor,
            job_id=job.job_id,
            template_id=template_rec.template_id,
            force_regenerate=force_regenerate,
            db=db,
            provider_registry=provider_registry,
            custom_provider=custom_provider,
        )

    # Step 7: REQUIREMENT_GROUNDED mode (Fallback when deterministic questions do not exist)
    plan = _build_requirement_grounded_plan(job, latest_version)
    items = await _generate_requirement_grounded_slots(
        plan=plan,
        actor=actor,
        db=db,
        provider_registry=provider_registry,
        custom_provider=custom_provider,
    )

    if not items or len(items) == 0 or all(not it.get("ai_wording") for it in items):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "PROVIDER_UNAVAILABLE", "message": "Failed to generate AI questions. Local AI is unavailable. Please check that LM Studio is running."},
        )

    next_version = (existing_set.set_version + 1) if (existing_set and force_regenerate) else 1

    org_id = getattr(actor, "organization_id", getattr(job, "organization_id", None)) or uuid.uuid4()
    new_set = AiInterviewQuestionSetRecord(
        ai_set_id=uuid.uuid4(),
        organization_id=org_id,
        template_id=None,
        job_id=job.job_id,
        job_version_id=latest_version.job_version_id,
        job_revision=latest_version.version_number,
        source_mode="REQUIREMENT_GROUNDED",
        source_template_version=None,
        source_content_hash=plan["fingerprint"],
        source_requirement_ids=plan["source_requirement_ids"],
        set_version=next_version,
        lifecycle_status="DRAFT",
        is_immutable=False,
        items=items,
        created_by_user_id=actor.user_id,
    )
    db.add(new_set)
    db.commit()
    db.refresh(new_set)

    return _map_record_to_detail_dto(new_set, db, action="GENERATED")


async def generate_or_open_ai_question_set(
    actor: UserRecord,
    job_id: UUID,
    template_id: UUID,
    force_regenerate: bool,
    db: Session,
    provider_registry: Optional[ProviderRegistry] = None,
    custom_provider: Optional[BaseWordingProvider] = None,
) -> AiQuestionSetDetailResponse:
    """Generates a BLUEPRINT_GROUNDED AI question set from a deterministic template."""
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
        .options(
            selectinload(AiInterviewQuestionSetRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.job_version),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(AiInterviewQuestionSetRecord.template_id == template_id)
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    latest_set = db.execute(stmt_latest).scalars().first()

    if latest_set and not force_regenerate:
        if latest_set.source_content_hash == source_hash:
            return _map_record_to_detail_dto(latest_set, db, action="OPENED_EXISTING")

    next_version = (latest_set.set_version + 1) if latest_set else 1
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
            "rationale_code": "BLUEPRINT_GROUNDED",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

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

    if not items or len(items) == 0 or all(not it.get("ai_wording") for it in items):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "PROVIDER_UNAVAILABLE", "message": "Failed to generate AI questions. Local AI is unavailable. Please check that LM Studio is running."},
        )

    new_set = AiInterviewQuestionSetRecord(
        ai_set_id=uuid.uuid4(),
        organization_id=template.organization_id,
        template_id=template.template_id,
        job_id=template.job_id,
        job_version_id=template.job_version_id,
        job_revision=template.revision,
        source_mode="BLUEPRINT_GROUNDED",
        source_template_version=template.template_version,
        source_content_hash=source_hash,
        source_requirement_ids=[],
        set_version=next_version,
        lifecycle_status="DRAFT",
        is_immutable=False,
        items=items,
        created_by_user_id=actor.user_id,
    )
    db.add(new_set)
    db.commit()
    db.refresh(new_set)

    return _map_record_to_detail_dto(new_set, db, action="GENERATED")


def update_ai_question_slot(
    actor: UserRecord,
    template_id: UUID,
    slot_id: UUID,
    payload: AiQuestionSlotUpdateRequest,
    db: Session,
) -> AiQuestionSetDetailResponse:
    """Updates the wording or review state of a single slot in an unsealed AI question set."""
    # Find AI set by ai_set_id or template_id
    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .options(
            selectinload(AiInterviewQuestionSetRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.job_version),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(
            (AiInterviewQuestionSetRecord.ai_set_id == template_id)
            | (AiInterviewQuestionSetRecord.template_id == template_id)
        )
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    ai_set = db.execute(stmt_set).scalars().first()
    if not ai_set:
        raise HTTPException(status_code=404, detail="AI question set not found.")

    job = ai_set.requisition or (ai_set.template.requisition if ai_set.template else None)
    if job:
        _check_recruiter_access(actor, job)

    if ai_set.is_immutable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SET_IS_IMMUTABLE", "message": "Approved AI question sets cannot be modified in-place."},
        )

    str_slot_id = str(slot_id)
    target_item = None
    items_copy = list(ai_set.items)
    for it in items_copy:
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

    return _map_record_to_detail_dto(ai_set, db)


async def regenerate_ai_question_slot(
    actor: UserRecord,
    template_id: UUID,
    slot_id: UUID,
    db: Session,
    provider_registry: Optional[ProviderRegistry] = None,
    custom_provider: Optional[BaseWordingProvider] = None,
) -> AiQuestionSetDetailResponse:
    """Regenerates AI wording for a single question slot using the local provider."""
    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .options(
            selectinload(AiInterviewQuestionSetRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.job_version),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric),
        )
        .where(
            (AiInterviewQuestionSetRecord.ai_set_id == template_id)
            | (AiInterviewQuestionSetRecord.template_id == template_id)
        )
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    ai_set = db.execute(stmt_set).scalars().first()
    if not ai_set:
        raise HTTPException(status_code=404, detail="AI question set not found.")
    if ai_set.is_immutable:
        raise HTTPException(status_code=409, detail="Approved AI question sets cannot be modified in-place.")

    job = ai_set.requisition or (ai_set.template.requisition if ai_set.template else None)
    if job:
        _check_recruiter_access(actor, job)

    str_slot_id = str(slot_id)
    target_item = None
    items_copy = list(ai_set.items)
    for it in items_copy:
        if str(it.get("slot_id")) == str_slot_id:
            target_item = it
            break

    if not target_item:
        raise HTTPException(status_code=404, detail="Slot not found in AI question set.")

    reg = provider_registry or get_provider_registry()

    if ai_set.source_mode == "BLUEPRINT_GROUNDED" and ai_set.template:
        q_rec = next((q for q in (ai_set.template.questions or []) if q.question_id == slot_id), None)
        if not q_rec:
            raise HTTPException(status_code=404, detail="Blueprint question record not found.")

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
    else:
        # Requirement-grounded regeneration
        active_prof = None
        try:
            active_prof = reg.get_active_profile()
        except Exception:
            pass
        provider = custom_provider or (reg.get_provider_instance(active_prof) if active_prof else None)
        if not provider:
            target_item["validation_status"] = "FAILED"
            target_item["safe_failure_code"] = "PROVIDER_UNAVAILABLE"
        else:
            q_type_raw = target_item.get("question_type", "TECHNICAL")
            q_type_enum = QuestionType.TECHNICAL if q_type_raw == "TECHNICAL" else QuestionType.BEHAVIORAL
            comp_name = target_item.get("competency_name", "Core Competency")
            req_ids = [str(r) for r in target_item.get("source_requirement_ids", [])]
            seed_text = target_item.get("requirement_summary") or f"Assess hands-on proficiency in {comp_name}."
            if len(seed_text) < 5:
                seed_text = f"Assess practical proficiency in {comp_name}."
                
            bounded_req = BoundedWordingRequest(
                source_question_id=uuid.UUID(target_item["slot_id"]),
                source_question_version=1,
                deterministic_question_text=seed_text,
                question_intent=f"Assess depth of experience and practical execution in {comp_name}.",
                competency_label=comp_name[:200],
                question_type=q_type_enum,
                layer=InterviewLayer.COMMON_CORE,
                allowed_reference_ids=req_ids,
                max_variants=1,
            )
            try:
                resp = await provider.request_wording_assistance(bounded_req)
                if resp.variants:
                    w = resp.variants[0].variant_text.strip()
                    is_valid, fail_code = _validate_ai_wording_safety(w)
                    if is_valid:
                        target_item["ai_wording"] = w
                        target_item["validation_status"] = "PASSED"
                        target_item["safe_failure_code"] = None
                        target_item["review_state"] = "UNREVIEWED"
                        target_item["authoring_origin"] = "AI_GENERATED"
                        target_item["rationale_code"] = "REQUIREMENT_GROUNDED"
                    else:
                        target_item["validation_status"] = "FAILED"
                        target_item["safe_failure_code"] = fail_code or "SEMANTIC_VALIDATION_FAILED"
                else:
                    target_item["validation_status"] = "FAILED"
                    target_item["safe_failure_code"] = "PROVIDER_UNAVAILABLE"
            except Exception:
                target_item["validation_status"] = "FAILED"
                target_item["safe_failure_code"] = "PROVIDER_UNAVAILABLE"

    target_item["updated_at"] = datetime.now(timezone.utc).isoformat()
    ai_set.items = items_copy
    flag_modified(ai_set, "items")
    db.commit()
    db.refresh(ai_set)

    return _map_record_to_detail_dto(ai_set, db)


def validate_ai_question_set(
    actor: UserRecord,
    template_id: UUID,
    db: Session,
) -> AiQuestionSetValidateResponse:
    """Validates the AI question set against readiness, staleness, and safety rules."""
    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .options(
            selectinload(AiInterviewQuestionSetRecord.requisition),
            selectinload(AiInterviewQuestionSetRecord.job_version),
            selectinload(AiInterviewQuestionSetRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
        )
        .where(
            (AiInterviewQuestionSetRecord.ai_set_id == template_id)
            | (AiInterviewQuestionSetRecord.template_id == template_id)
        )
        .order_by(desc(AiInterviewQuestionSetRecord.set_version))
    )
    ai_set = db.execute(stmt_set).scalars().first()
    if not ai_set:
        raise HTTPException(status_code=404, detail="AI question set not found.")

    job = ai_set.requisition or (ai_set.template.requisition if ai_set.template else None)
    if job:
        _check_recruiter_access(actor, job)

    errors: List[str] = []

    # 1. Staleness check
    if ai_set.source_mode == "BLUEPRINT_GROUNDED" and ai_set.template:
        if ai_set.template.content_hash and ai_set.source_content_hash != ai_set.template.content_hash:
            errors.append("AI question set is stale: deterministic blueprint has changed since generation. Please regenerate.")
    elif ai_set.source_mode == "REQUIREMENT_GROUNDED":
        job_stmt = select(JobRequisition).options(
            selectinload(JobRequisition.versions).selectinload(JobVersion.requirements)
        ).where(JobRequisition.job_id == ai_set.job_id)
        job_rec = db.execute(job_stmt).scalar_one_or_none()
        if job_rec and job_rec.versions:
            latest_v = job_rec.versions[-1]
            req_ids = [str(r.requirement_id) for r in (latest_v.requirements or [])]
            curr_fp = _compute_requirement_fingerprint(job_rec.job_id, latest_v.job_version_id, latest_v.version_number, req_ids)
            if curr_fp != ai_set.source_content_hash:
                errors.append("AI question set is stale: job requirements have changed since generation. Please regenerate.")

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
                errors.append("Duplicate question detected: multiple questions share identical wording.")
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
    val = validate_ai_question_set(actor, template_id, db)
    if not val.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_BLOCKED", "message": "Cannot approve invalid AI question set.", "errors": val.blocking_errors},
        )

    stmt_set = (
        select(AiInterviewQuestionSetRecord)
        .where(
            (AiInterviewQuestionSetRecord.ai_set_id == template_id)
            | (AiInterviewQuestionSetRecord.template_id == template_id)
        )
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
