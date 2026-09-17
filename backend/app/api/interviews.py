import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.auth import (
    AuthenticatedContext,
    _record_audit_event,
    require_recruiter,
)
from app.database import get_db
from app.models.auth import AuditEventType, AuditReasonCode, AuditResult, UserRole
from app.models.interview import (
    CandidateInterviewPlanRecord,
    InterviewQuestionRecord,
    InterviewRubricRecord,
    JobInterviewTemplateRecord,
    SupplementalQuestionProvenanceRecord,
)
from app.models.job import JobRequisition
from app.schemas.interview_api import (
    ApprovalSummaryResponse,
    BlueprintCoverageResponse,
    BlueprintValidationReportResponse,
    CandidatePlanEditRequest,
    CandidateSupplementalQuestionResponse,
    CompetencySelectionResponse,
    InterviewApprovalRequest,
    InterviewQuestionResponse,
    InterviewRubricResponse,
    InterviewTemplateDraftCreateResponse,
    InterviewTemplateEditRequest,
    InterviewTemplatePreviewResponse,
    RequirementClassificationResponse,
    SuccessorDraftCreateRequest,
    ValidationSummaryResponse,
    VersionDiffResponse,
    VersionHistoryResponse,
)
from app.schemas.phase3_audit import Phase3AuditEvent
from app.schemas.phase3_enums import AuditRetentionClass
from app.services.interview_generator_service import (
    BlueprintCoverageSummary,
    GeneratedDeterministicBlueprint,
    create_deterministic_interview_template_draft,
    preview_deterministic_interview_template,
)
from app.services.interview_lifecycle_service import (
    LifecycleConflictError,
    LifecycleValidationError,
    approve_candidate_interview_plan,
    approve_job_interview_template,
    compute_candidate_plan_version_diff,
    compute_template_version_diff,
    create_candidate_interview_plan_successor,
    create_job_interview_template_successor,
    edit_candidate_interview_plan_draft,
    edit_job_interview_template_draft,
    get_candidate_plan_version_history,
    get_template_version_history,
    validate_candidate_interview_plan_draft,
    validate_job_interview_template_draft,
)
from app.services.interview_snapshot_service import (
    InterviewCandidateNotFoundError,
    InterviewJobNotReadyError,
    InterviewJobRevisionStaleError,
    InterviewMatchResultMismatchError,
    InterviewProfileVersionMismatchError,
    InterviewRequisitionNotFoundError,
    InterviewSnapshotError,
    InterviewSourceRelationshipInvalidError,
    InterviewUnauthorizedError,
)

logger = logging.getLogger("ai_hiring.api.interviews")

router = APIRouter(
    prefix="/api/v1/jobs/{job_id}/interview-templates",
    tags=["interview-templates"],
)


def _map_blueprint_to_preview_dto(
    blueprint: GeneratedDeterministicBlueprint,
    job_id: uuid.UUID,
    job_version_id: uuid.UUID,
    revision: int,
) -> InterviewTemplatePreviewResponse:
    cov = blueprint.coverage_summary
    questions_dto = []
    for q in blueprint.common_core_questions:
        rubric_dto = None
        if q.rubric:
            rubric_dto = InterviewRubricResponse(
                rubric_id=q.rubric.rubric_id,
                rubric_version=q.rubric.rubric_version,
                competency_definition=q.rubric.competency_definition,
                question_intent=q.rubric.question_intent,
                observable_indicators=list(q.rubric.observable_indicators),
                rating_anchors={int(k): str(v) for k, v in q.rubric.rating_anchors.items()},
                sufficient_evidence_guidance=q.rubric.sufficient_evidence_guidance,
                insufficient_evidence_guidance=q.rubric.insufficient_evidence_guidance,
                incomplete_answer_guidance=None,
                permitted_probes=list(q.rubric.permitted_probes),
                prohibited_inferences=list(q.rubric.prohibited_inferences),
                subject_matter_review_status="REVIEWED",
                validation_state=q.rubric.validation_state,
            )

        questions_dto.append(
            InterviewQuestionResponse(
                question_id=q.question_id,
                layer=q.layer,
                question_type=q.question_type,
                competency_id=q.competency_id,
                requirement_references=list(q.requirement_references),
                deterministic_template_id=q.deterministic_template_id,
                deterministic_template_version=q.deterministic_template_version,
                question_text=q.question_text,
                question_intent=q.question_intent,
                authoring_origin=q.authoring_origin,
                display_order=q.display_order,
                estimated_time_minutes=q.estimated_time_minutes,
                permitted_probes=list(q.permitted_probes),
                validation_state=q.validation_state,
                included_in_common_score=q.included_in_common_score,
                rubric=rubric_dto,
            )
        )

    coverage_dto = BlueprintCoverageResponse(
        total_requirements_count=cov.total_requirements_count,
        interview_eligible_requirements_count=cov.interview_eligible_requirements_count,
        covered_requirements_count=cov.covered_requirements_count,
        selected_competencies=[
            CompetencySelectionResponse(
                competency_key=c.competency_key,
                competency_label=c.competency_label,
                priority_score=c.priority_score,
                selection_reason=c.selection_reason,
                covered_requirement_ids=list(c.covered_requirement_ids),
            )
            for c in cov.selected_competencies
        ],
        uncovered_eligible_competencies=list(cov.uncovered_eligible_competencies),
        unsupported_competencies=list(cov.unsupported_competencies),
        document_verification_requirements=[
            RequirementClassificationResponse(
                requirement_id=d.requirement_id,
                label=d.label,
                category=d.category.value if hasattr(d.category, "value") else str(d.category),
                suitability=d.suitability.value if hasattr(d.suitability, "value") else str(d.suitability),
                reason=d.reason,
                mapped_competency_key=d.mapped_competency_key,
            )
            for d in cov.document_verification_requirements
        ],
        work_sample_requirements=[
            RequirementClassificationResponse(
                requirement_id=w.requirement_id,
                label=w.label,
                category=w.category.value if hasattr(w.category, "value") else str(w.category),
                suitability=w.suitability.value if hasattr(w.suitability, "value") else str(w.suitability),
                reason=w.reason,
                mapped_competency_key=w.mapped_competency_key,
            )
            for w in cov.work_sample_requirements
        ],
        out_of_interview_requirements=[
            RequirementClassificationResponse(
                requirement_id=o.requirement_id,
                label=o.label,
                category=o.category.value if hasattr(o.category, "value") else str(o.category),
                suitability=o.suitability.value if hasattr(o.suitability, "value") else str(o.suitability),
                reason=o.reason,
                mapped_competency_key=o.mapped_competency_key,
            )
            for o in cov.out_of_interview_requirements
        ],
        total_estimated_duration_minutes=cov.total_estimated_duration_minutes,
        question_count_by_type=dict(cov.question_count_by_type),
        coverage_percentage=cov.coverage_percentage,
        builder_version=cov.builder_version,
        question_catalogue_version=cov.question_catalogue_version,
        rubric_catalogue_version=cov.rubric_catalogue_version,
    )

    validation_dto = BlueprintValidationReportResponse(
        is_valid=blueprint.validation_report.is_valid,
        blocking_errors=list(blueprint.validation_report.blocking_errors),
        warnings=list(blueprint.validation_report.warnings),
        checked_rules_count=blueprint.validation_report.checked_rules_count,
    )

    return InterviewTemplatePreviewResponse(
        job_id=job_id,
        job_version_id=job_version_id,
        job_revision=revision,
        lifecycle_status=blueprint.lifecycle_status,
        input_snapshot_hash=blueprint.input_snapshot_hash,
        content_hash=blueprint.content_hash,
        common_core_questions=questions_dto,
        coverage_summary=coverage_dto,
        validation_report=validation_dto,
        builder_version=blueprint.builder_version,
        question_catalogue_version=blueprint.question_catalogue_version,
        rubric_catalogue_version=blueprint.rubric_catalogue_version,
        policy_id=blueprint.policy_reference.policy_id,
        policy_version=blueprint.policy_reference.policy_version,
        policy_hash=blueprint.policy_reference.policy_hash,
    )


@router.get(
    "/preview",
    response_model=InterviewTemplatePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview Deterministic Interview Template",
    description=(
        "Generates and returns an ephemeral preview of the deterministic common-core interview blueprint "
        "using server-side authoritative job requirements and versioned catalogues without persisting a template."
    ),
)
async def preview_job_interview_template(
    job_id: uuid.UUID,
    revision: Optional[int] = Query(default=None, ge=1),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> InterviewTemplatePreviewResponse:
    actor = auth_ctx.user
    try:
        blueprint = preview_deterministic_interview_template(
            actor=actor,
            job_id=job_id,
            expected_revision=revision,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="interview_template",
            resource_id=str(job_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        )
    except InterviewRequisitionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        )
    except (InterviewJobNotReadyError, InterviewJobRevisionStaleError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        )
    except InterviewSnapshotError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )

    # Safe audit log (Phase 3 schema verified)
    phase3_event = Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="INTERVIEW_TEMPLATE_PREVIEWED",
        resource_type="interview_template_preview",
        resource_id=str(job_id),
        policy_version=blueprint.builder_version,
        safe_metadata={
            "input_snapshot_hash": blueprint.input_snapshot_hash,
            "content_hash": blueprint.content_hash,
            "builder_version": blueprint.builder_version,
            "is_valid": blueprint.validation_report.is_valid,
        },
    )

    return _map_blueprint_to_preview_dto(
        blueprint=blueprint,
        job_id=job_id,
        job_version_id=blueprint.common_core_questions[0].requirement_references[0] if blueprint.common_core_questions else job_id,
        revision=revision or 1,
    )


@router.post(
    "/draft",
    response_model=InterviewTemplateDraftCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Deterministic Interview Template Draft",
    description=(
        "Authoritatively regenerates and persists a DRAFT JobInterviewTemplate with ordered common questions "
        "and anchored rubrics using server-side verified job requirements and versioned catalogues."
    ),
)
async def create_job_interview_template_draft(
    job_id: uuid.UUID,
    revision: Optional[int] = Query(default=None, ge=1),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> InterviewTemplateDraftCreateResponse:
    actor = auth_ctx.user
    try:
        template_record, blueprint = create_deterministic_interview_template_draft(
            actor=actor,
            job_id=job_id,
            expected_revision=revision,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="interview_template_draft",
            resource_id=str(job_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        )
    except InterviewRequisitionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        )
    except (InterviewJobNotReadyError, InterviewJobRevisionStaleError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        )
    except InterviewSnapshotError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )

    # Safe audit log for draft creation (Phase 3 schema verified)
    phase3_event = Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="INTERVIEW_TEMPLATE_DRAFT_CREATED",
        resource_type="job_interview_template",
        resource_id=str(template_record.template_id),
        policy_version=template_record.deterministic_builder_version,
        safe_metadata={
            "job_id": str(job_id),
            "template_version": template_record.template_version,
            "input_snapshot_hash": template_record.input_snapshot_hash,
            "content_hash": template_record.content_hash,
            "lifecycle_status": template_record.lifecycle_status.value if hasattr(template_record.lifecycle_status, "value") else str(template_record.lifecycle_status),
            "is_valid": blueprint.validation_report.is_valid,
        },
    )

    preview_dto = _map_blueprint_to_preview_dto(
        blueprint=blueprint,
        job_id=job_id,
        job_version_id=template_record.job_version_id,
        revision=template_record.revision,
    )

    return InterviewTemplateDraftCreateResponse(
        template_id=template_record.template_id,
        organization_id=template_record.organization_id,
        job_id=template_record.job_id,
        job_version_id=template_record.job_version_id,
        job_revision=template_record.revision,
        template_version=template_record.template_version,
        lifecycle_status=template_record.lifecycle_status,
        input_snapshot_hash=template_record.input_snapshot_hash,
        content_hash=template_record.content_hash or preview_dto.content_hash,
        common_core_questions=preview_dto.common_core_questions,
        coverage_summary=preview_dto.coverage_summary,
        validation_report=preview_dto.validation_report,
        builder_version=template_record.deterministic_builder_version,
        question_catalogue_version=template_record.question_catalogue_version,
        rubric_catalogue_version=template_record.rubric_catalogue_version,
        created_by_user_id=template_record.created_by_user_id,
        created_at=template_record.created_at,
    )


@router.get(
    "/latest",
    response_model=InterviewTemplateDraftCreateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Job Interview Template",
    description=(
        "Retrieves the latest persisted interview template (draft or approved) for the specified job requisition."
    ),
)
async def get_latest_job_interview_template(
    job_id: uuid.UUID,
    revision: Optional[int] = Query(default=None, ge=1),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> InterviewTemplateDraftCreateResponse:
    actor = auth_ctx.user

    # Verify job existence & recruiter access
    stmt_job = select(JobRequisition).where(JobRequisition.job_id == job_id)
    job = db.execute(stmt_job).scalar_one_or_none()
    if job is None or (actor.role == UserRole.RECRUITER and job.created_by_user_id != actor.user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job requisition not found or unauthorized."},
        )

    stmt = (
        select(JobInterviewTemplateRecord)
        .options(
            selectinload(JobInterviewTemplateRecord.questions).selectinload(InterviewQuestionRecord.rubric)
        )
        .where(JobInterviewTemplateRecord.job_id == job_id)
    )
    if revision is not None:
        stmt = stmt.where(JobInterviewTemplateRecord.revision == revision)
    stmt = stmt.order_by(JobInterviewTemplateRecord.template_version.desc())
    template_rec = db.execute(stmt).scalars().first()

    if template_rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TEMPLATE_NOT_FOUND", "message": "No interview template found for job."},
        )

    preview = preview_deterministic_interview_template(
        actor=actor,
        job_id=job_id,
        expected_revision=template_rec.revision,
        db=db,
    )
    preview_dto = _map_blueprint_to_preview_dto(preview, job_id, template_rec.job_version_id, template_rec.revision)

    # Map persisted questions
    questions_dto = []
    for q in sorted(template_rec.questions, key=lambda x: x.display_order):
        rubric_dto = None
        if q.rubric:
            rubric_dto = InterviewRubricResponse(
                rubric_id=q.rubric.rubric_id,
                rubric_version=q.rubric.rubric_version,
                competency_definition=q.rubric.competency_definition,
                question_intent=q.rubric.question_intent,
                observable_indicators=list(q.rubric.observable_indicators) if q.rubric.observable_indicators else [],
                rating_anchors={int(k): str(v) for k, v in q.rubric.rating_anchors.items()} if q.rubric.rating_anchors else {},
                sufficient_evidence_guidance=q.rubric.sufficient_evidence_guidance,
                insufficient_evidence_guidance=q.rubric.insufficient_evidence_guidance,
                incomplete_answer_guidance=q.rubric.incomplete_answer_guidance,
                permitted_probes=list(q.rubric.permitted_probes) if q.rubric.permitted_probes else [],
                prohibited_inferences=list(q.rubric.prohibited_inferences) if q.rubric.prohibited_inferences else [],
                subject_matter_review_status="REVIEWED",
                validation_state=q.rubric.validation_state,
            )
        questions_dto.append(
            InterviewQuestionResponse(
                question_id=q.question_id,
                layer=q.layer,
                question_type=q.question_type,
                competency_id=q.competency_id,
                requirement_references=[uuid.UUID(r) if isinstance(r, str) else r for r in (q.requirement_ids or [])],
                deterministic_template_id=q.deterministic_template_id,
                deterministic_template_version=q.deterministic_template_version,
                question_text=q.question_text,
                question_intent=q.question_intent,
                authoring_origin=q.authoring_origin,
                display_order=q.display_order,
                estimated_time_minutes=q.estimated_time_minutes,
                permitted_probes=list(q.permitted_probes) if q.permitted_probes else [],
                validation_state=q.validation_state,
                included_in_common_score=q.included_in_common_score,
                rubric=rubric_dto,
            )
        )

    return InterviewTemplateDraftCreateResponse(
        template_id=template_rec.template_id,
        organization_id=template_rec.organization_id,
        job_id=job_id,
        job_version_id=template_rec.job_version_id,
        job_revision=template_rec.revision,
        template_version=template_rec.template_version,
        lifecycle_status=template_rec.lifecycle_status,
        input_snapshot_hash=template_rec.input_snapshot_hash,
        content_hash=template_rec.content_hash or preview_dto.content_hash,
        common_core_questions=questions_dto,
        coverage_summary=preview_dto.coverage_summary,
        validation_report=preview_dto.validation_report,
        builder_version=template_rec.deterministic_builder_version,
        question_catalogue_version=template_rec.question_catalogue_version,
        rubric_catalogue_version=template_rec.rubric_catalogue_version,
        created_by_user_id=template_rec.created_by_user_id,
        created_at=template_rec.created_at,
    )


# =========================================================================
# Candidate Interview Plan Endpoints (Phase 3B.3)
# =========================================================================

from app.schemas.interview_api import (
    CandidateInterviewPlanDraftCreateResponse,
    CandidateInterviewPlanPreviewResponse,
    CandidateInterviewPlanSummaryResponse,
    CandidatePlanCoverageSummaryResponse,
    CandidateSupplementalQuestionResponse,
    SupplementalQuestionGuidanceResponse,
    SupplementalQuestionProvenanceResponse,
)
from app.services.candidate_plan_generator_service import (
    GeneratedDeterministicCandidatePlan,
    create_deterministic_candidate_interview_plan_draft,
    preview_deterministic_candidate_interview_plan,
)


def _map_candidate_plan_to_preview_dto(
    plan: GeneratedDeterministicCandidatePlan,
) -> CandidateInterviewPlanPreviewResponse:
    supp_dtos = []
    for q in plan.supplemental_questions:
        guidance = SupplementalQuestionGuidanceResponse(
            clarification_purpose=q.clarification_purpose,
            facts_to_confirm=q.facts_to_confirm,
            prohibited_inferences=q.prohibited_inferences,
        )
        prov = SupplementalQuestionProvenanceResponse(
            source_requirement_id=q.source_requirement_id,
            source_match_result_id=q.source_match_result_id,
            source_match_state=q.source_match_state,
            allowlisted_evidence_ids=q.allowlisted_evidence_ids,
            excluded_from_common_score=True,
        )
        supp_dtos.append(
            CandidateSupplementalQuestionResponse(
                question_id=q.question_id,
                layer=q.layer,
                question_type=q.question_type,
                authoring_origin=q.authoring_origin,
                display_order=q.display_order,
                requirement_references=q.requirement_references,
                deterministic_template_id=q.deterministic_template_id,
                deterministic_template_version=q.deterministic_template_version,
                question_text=q.question_text,
                question_intent=q.question_intent,
                estimated_time_minutes=q.estimated_time_minutes,
                included_in_common_score=q.included_in_common_score,
                validation_state=q.validation_state,
                guidance=guidance,
                provenance=prov,
            )
        )

    common_summary = CandidateInterviewPlanSummaryResponse(
        template_id=plan.template_id,
        template_version=plan.template_version,
        template_content_hash=plan.template_content_hash,
        job_id=plan.job_id,
        job_revision=plan.job_revision,
        common_core_questions_count=plan.common_core_questions_count,
        common_core_duration_minutes=plan.common_core_duration_minutes,
    )

    cov_summary = CandidatePlanCoverageSummaryResponse(
        selected_target_count=plan.coverage_summary.selected_target_count,
        target_selection_reasons=plan.coverage_summary.target_selection_reasons,
        match_states_clarified=plan.coverage_summary.match_states_clarified,
        total_supplemental_duration_minutes=plan.coverage_summary.total_supplemental_duration_minutes,
    )

    return CandidateInterviewPlanPreviewResponse(
        plan_id=plan.plan_id,
        job_id=plan.job_id,
        job_revision=plan.job_revision,
        template_id=plan.template_id,
        template_version=plan.template_version,
        candidate_id=plan.candidate_id,
        profile_id=plan.profile_id,
        profile_version=plan.profile_version,
        match_result_id=plan.match_result_id,
        match_result_fingerprint=plan.match_result_fingerprint,
        lifecycle_status=plan.lifecycle_status,
        scoring_separation_policy=plan.scoring_separation_policy,
        input_snapshot_hash=plan.input_snapshot_hash,
        content_hash=plan.content_hash,
        common_template_summary=common_summary,
        supplemental_questions=supp_dtos,
        coverage_summary=cov_summary,
        validation_report=plan.validation_report,
        supplemental_catalogue_version=plan.supplemental_catalogue_version,
        policy_version=plan.policy_version,
    )


@router.get(
    "/{template_id}/candidate-plans/{candidate_id}/preview",
    response_model=CandidateInterviewPlanPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview Candidate Interview Plan",
    description=(
        "Generates an ephemeral preview of the candidate-tailored supplemental clarification questions "
        "using server-side authoritative candidate match results and versioned templates without persisting."
    ),
)
async def preview_candidate_interview_plan_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    candidate_id: uuid.UUID,
    revision: int = Query(..., ge=1),
    profile_version: int = Query(..., ge=1),
    match_result_id: uuid.UUID = Query(...),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> CandidateInterviewPlanPreviewResponse:
    actor = auth_ctx.user
    try:
        plan = preview_deterministic_candidate_interview_plan(
            actor=actor,
            template_id=template_id,
            candidate_id=candidate_id,
            expected_revision=revision,
            profile_version=profile_version,
            match_result_id=match_result_id,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="candidate_interview_plan_preview",
            resource_id=str(candidate_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        )
    except (InterviewRequisitionNotFoundError, InterviewCandidateNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        )
    except (
        InterviewJobNotReadyError,
        InterviewJobRevisionStaleError,
        InterviewProfileVersionMismatchError,
        InterviewMatchResultMismatchError,
        InterviewSourceRelationshipInvalidError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        )
    except InterviewSnapshotError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )

    # Safe audit log (Phase 3 schema verified)
    phase3_event = Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="CANDIDATE_INTERVIEW_PLAN_PREVIEWED",
        resource_type="candidate_interview_plan_preview",
        resource_id=str(plan.plan_id),
        policy_version=plan.policy_version,
        safe_metadata={
            "template_id": str(template_id),
            "candidate_id": str(candidate_id),
            "match_result_id": str(match_result_id),
            "input_snapshot_hash": plan.input_snapshot_hash,
            "content_hash": plan.content_hash,
            "supplemental_questions_count": len(plan.supplemental_questions),
            "is_valid": plan.validation_report.is_valid,
        },
    )

    return _map_candidate_plan_to_preview_dto(plan)


@router.post(
    "/{template_id}/candidate-plans/{candidate_id}/draft",
    response_model=CandidateInterviewPlanDraftCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Candidate Interview Plan Draft",
    description=(
        "Authoritatively regenerates and persists a DRAFT CandidateInterviewPlanRecord with exact supplemental "
        "question provenance binding to requirement results and evidence gaps."
    ),
)
async def create_candidate_interview_plan_draft_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    candidate_id: uuid.UUID,
    revision: int = Query(..., ge=1),
    profile_version: int = Query(..., ge=1),
    match_result_id: uuid.UUID = Query(...),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> CandidateInterviewPlanDraftCreateResponse:
    actor = auth_ctx.user
    try:
        plan_record, plan = create_deterministic_candidate_interview_plan_draft(
            actor=actor,
            template_id=template_id,
            candidate_id=candidate_id,
            expected_revision=revision,
            profile_version=profile_version,
            match_result_id=match_result_id,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="candidate_interview_plan_draft",
            resource_id=str(candidate_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        )
    except (InterviewRequisitionNotFoundError, InterviewCandidateNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        )
    except (
        InterviewJobNotReadyError,
        InterviewJobRevisionStaleError,
        InterviewProfileVersionMismatchError,
        InterviewMatchResultMismatchError,
        InterviewSourceRelationshipInvalidError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        )
    except InterviewSnapshotError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )

    # Safe audit log (Phase 3 schema verified)
    phase3_event = Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="CANDIDATE_INTERVIEW_PLAN_DRAFT_CREATED",
        resource_type="candidate_interview_plan",
        resource_id=str(plan_record.plan_id),
        policy_version=plan.policy_version,
        safe_metadata={
            "template_id": str(template_id),
            "candidate_id": str(candidate_id),
            "match_result_id": str(match_result_id),
            "input_snapshot_hash": plan_record.input_snapshot_hash,
            "content_hash": plan_record.content_hash,
            "supplemental_questions_count": len(plan.supplemental_questions),
            "is_valid": plan.validation_report.is_valid,
        },
    )

    preview_dto = _map_candidate_plan_to_preview_dto(plan)

    return CandidateInterviewPlanDraftCreateResponse(
        plan_id=plan_record.plan_id,
        organization_id=plan_record.organization_id,
        job_id=job_id,
        job_revision=plan_record.template.revision if plan_record.template else revision,
        template_id=plan_record.template_id,
        template_version=plan_record.template_version,
        candidate_id=plan_record.candidate_id,
        profile_id=plan_record.profile_id,
        profile_version=plan_record.profile_version,
        match_result_id=plan_record.match_result_id,
        match_result_fingerprint=plan_record.match_result_fingerprint,
        plan_version=plan_record.plan_version,
        lifecycle_status=plan_record.lifecycle_status,
        scoring_separation_policy=plan_record.scoring_separation_policy,
        input_snapshot_hash=plan_record.input_snapshot_hash,
        content_hash=plan_record.content_hash or preview_dto.content_hash,
        common_template_summary=preview_dto.common_template_summary,
        supplemental_questions=preview_dto.supplemental_questions,
        coverage_summary=preview_dto.coverage_summary,
        validation_report=preview_dto.validation_report,
        supplemental_catalogue_version=plan.supplemental_catalogue_version,
        policy_version=plan.policy_version,
        created_by_user_id=plan_record.created_by_user_id,
        created_at=plan_record.created_at,
    )


@router.get(
    "/{template_id}/candidate-plans/{candidate_id}/latest",
    response_model=CandidateInterviewPlanDraftCreateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Candidate Interview Plan",
    description="Retrieves the latest persisted candidate interview plan for a specific candidate and template.",
)
async def get_latest_candidate_interview_plan(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    candidate_id: uuid.UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> CandidateInterviewPlanDraftCreateResponse:
    actor = auth_ctx.user

    stmt = (
        select(CandidateInterviewPlanRecord)
        .options(
            selectinload(CandidateInterviewPlanRecord.template).selectinload(JobInterviewTemplateRecord.requisition),
            selectinload(CandidateInterviewPlanRecord.template).selectinload(JobInterviewTemplateRecord.questions),
            selectinload(CandidateInterviewPlanRecord.supplemental_questions).selectinload(InterviewQuestionRecord.provenance),
        )
        .where(
            CandidateInterviewPlanRecord.template_id == template_id,
            CandidateInterviewPlanRecord.candidate_id == candidate_id,
        )
        .order_by(CandidateInterviewPlanRecord.plan_version.desc())
    )
    plan_rec = db.execute(stmt).scalars().first()

    if plan_rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PLAN_NOT_FOUND", "message": "No candidate interview plan found."},
        )

    # Check authorization
    _check_recruiter_authorization(actor, plan_rec.template.requisition)

    # Map supplemental questions DTO
    supp_dtos = []
    for q in sorted(plan_rec.supplemental_questions, key=lambda x: x.display_order):
        prov = q.provenance
        guidance_dto = SupplementalQuestionGuidanceResponse(
            clarification_purpose="Verify candidate experience against requirement.",
            facts_to_confirm=[],
            prohibited_inferences=[],
        )
        prov_dto = SupplementalQuestionProvenanceResponse(
            source_requirement_id=prov.source_requirement_id if prov else uuid.uuid4(),
            source_match_result_id=prov.source_match_result_id if prov else uuid.uuid4(),
            source_match_state=prov.source_match_state.value if prov and hasattr(prov.source_match_state, "value") else "GAP",
            allowlisted_evidence_ids=list(prov.allowlisted_evidence_ids) if prov and prov.allowlisted_evidence_ids else [],
            excluded_from_common_score=True,
        )
        supp_dtos.append(
            CandidateSupplementalQuestionResponse(
                question_id=q.question_id,
                layer=q.layer,
                question_type=q.question_type,
                authoring_origin=q.authoring_origin,
                display_order=q.display_order,
                requirement_references=[uuid.UUID(r) if isinstance(r, str) else r for r in (q.requirement_ids or [])],
                deterministic_template_id=q.deterministic_template_id,
                deterministic_template_version=q.deterministic_template_version,
                question_text=q.question_text,
                question_intent=q.question_intent,
                estimated_time_minutes=q.estimated_time_minutes,
                included_in_common_score=q.included_in_common_score,
                validation_state=q.validation_state,
                guidance=guidance_dto,
                provenance=prov_dto,
            )
        )

    common_summary = CandidateInterviewPlanSummaryResponse(
        template_id=plan_rec.template_id,
        template_version=plan_rec.template_version,
        template_content_hash=plan_rec.template.content_hash if plan_rec.template else "",
        job_id=job_id,
        job_revision=plan_rec.template.revision if plan_rec.template else 1,
        common_core_questions_count=len(plan_rec.template.questions) if plan_rec.template else 0,
        common_core_duration_minutes=sum(q.estimated_time_minutes for q in plan_rec.template.questions) if plan_rec.template else 45,
    )

    cov_summary = CandidatePlanCoverageSummaryResponse(
        selected_target_count=len(supp_dtos),
        target_selection_reasons={},
        match_states_clarified=[],
        total_supplemental_duration_minutes=sum(q.estimated_time_minutes for q in supp_dtos),
    )

    return CandidateInterviewPlanDraftCreateResponse(
        plan_id=plan_rec.plan_id,
        organization_id=plan_rec.organization_id,
        job_id=job_id,
        job_revision=plan_rec.template.revision if plan_rec.template else 1,
        template_id=plan_rec.template_id,
        template_version=plan_rec.template_version,
        candidate_id=plan_rec.candidate_id,
        profile_id=plan_rec.profile_id,
        profile_version=plan_rec.profile_version,
        match_result_id=plan_rec.match_result_id,
        match_result_fingerprint=plan_rec.match_result_fingerprint,
        plan_version=plan_rec.plan_version,
        lifecycle_status=plan_rec.lifecycle_status,
        scoring_separation_policy=plan_rec.scoring_separation_policy,
        input_snapshot_hash=plan_rec.input_snapshot_hash,
        content_hash=plan_rec.content_hash,
        common_template_summary=common_summary,
        supplemental_questions=supp_dtos,
        coverage_summary=cov_summary,
        validation_report={"is_valid": True, "blocking_errors": [], "warnings": []},
        supplemental_catalogue_version=plan_rec.supplemental_catalogue_version,
        policy_version=plan_rec.guardrail_policy_version,
        created_by_user_id=plan_rec.created_by_user_id,
        created_at=plan_rec.created_at,
    )


# =========================================================================
# Phase 3B.4: Template Endpoints (Edit, Validate, Approve, Successor, History, Diff)
# =========================================================================

@router.patch(
    "/{template_id}/edit",
    response_model=InterviewTemplateDraftCreateResponse,
    status_code=status.HTTP_200_OK,
    summary="Safe Edit Template Draft",
)
async def edit_template_draft_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    payload: InterviewTemplateEditRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> InterviewTemplateDraftCreateResponse:
    actor = auth_ctx.user
    try:
        updated_template = edit_job_interview_template_draft(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="interview_template_edit",
            resource_id=str(template_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        )
    except (InterviewRequisitionNotFoundError, InterviewSnapshotError) as exc:
        if getattr(exc, "status_code", None) == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message})
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail={"code": exc.code, "message": exc.message})
    except LifecycleValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message, "blocking_errors": exc.blocking_errors},
        )
    except LifecycleConflictError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )

    # Safe audit log
    Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="INTERVIEW_TEMPLATE_DRAFT_EDITED",
        resource_type="job_interview_template",
        resource_id=str(updated_template.template_id),
        policy_version=updated_template.guardrail_policy_version,
        safe_metadata={
            "job_id": str(job_id),
            "template_version": updated_template.template_version,
            "record_version": updated_template.record_version,
            "content_hash": updated_template.content_hash,
        },
    )

    preview = preview_deterministic_interview_template(
        actor=actor,
        job_id=job_id,
        expected_revision=updated_template.revision,
        db=db,
    )
    preview_dto = _map_blueprint_to_preview_dto(preview, job_id, updated_template.job_version_id, updated_template.revision)

    return InterviewTemplateDraftCreateResponse(
        template_id=updated_template.template_id,
        organization_id=updated_template.organization_id,
        job_id=job_id,
        job_version_id=updated_template.job_version_id,
        job_revision=updated_template.revision,
        template_version=updated_template.template_version,
        lifecycle_status=updated_template.lifecycle_status,
        input_snapshot_hash=updated_template.input_snapshot_hash,
        content_hash=updated_template.content_hash or preview_dto.content_hash,
        common_core_questions=preview_dto.common_core_questions,
        coverage_summary=preview_dto.coverage_summary,
        validation_report=preview_dto.validation_report,
        builder_version=updated_template.deterministic_builder_version,
        question_catalogue_version=updated_template.question_catalogue_version,
        rubric_catalogue_version=updated_template.rubric_catalogue_version,
        created_by_user_id=updated_template.created_by_user_id,
        created_at=updated_template.created_at,
    )


@router.post(
    "/{template_id}/validate",
    response_model=ValidationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate Template Draft",
)
async def validate_template_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> ValidationSummaryResponse:
    actor = auth_ctx.user
    try:
        report = validate_job_interview_template_draft(actor=actor, job_id=job_id, template_id=template_id, db=db)
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except LifecycleConflictError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})

    # Safe audit log
    Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="INTERVIEW_TEMPLATE_VALIDATED" if report.is_valid else "INTERVIEW_TEMPLATE_VALIDATION_FAILED",
        resource_type="job_interview_template",
        resource_id=str(template_id),
        policy_version=report.policy_version,
        safe_metadata={
            "job_id": str(job_id),
            "is_valid": report.is_valid,
            "blocking_errors_count": len(report.blocking_errors),
            "warnings_count": len(report.warnings),
            "content_hash": report.content_hash,
        },
    )

    return report


@router.post(
    "/{template_id}/approve",
    response_model=ApprovalSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve Template",
)
async def approve_template_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    payload: InterviewApprovalRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> ApprovalSummaryResponse:
    actor = auth_ctx.user
    try:
        summary = approve_job_interview_template(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except LifecycleConflictError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})

    # Safe audit log
    Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="INTERVIEW_TEMPLATE_APPROVED",
        resource_type="job_interview_template",
        resource_id=str(template_id),
        safe_metadata={
            "job_id": str(job_id),
            "template_version": summary.record_version,
            "content_hash": summary.content_hash,
            "superseded_parent_id": str(summary.superseded_parent_id) if summary.superseded_parent_id else None,
        },
    )

    return summary


@router.post(
    "/{template_id}/successor",
    response_model=InterviewTemplateDraftCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Successor Draft From Approved Template",
)
async def create_template_successor_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    payload: SuccessorDraftCreateRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> InterviewTemplateDraftCreateResponse:
    actor = auth_ctx.user
    try:
        successor = create_job_interview_template_successor(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except LifecycleConflictError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})

    preview = preview_deterministic_interview_template(
        actor=actor,
        job_id=job_id,
        expected_revision=successor.revision,
        db=db,
    )
    preview_dto = _map_blueprint_to_preview_dto(preview, job_id, successor.job_version_id, successor.revision)

    return InterviewTemplateDraftCreateResponse(
        template_id=successor.template_id,
        organization_id=successor.organization_id,
        job_id=job_id,
        job_version_id=successor.job_version_id,
        job_revision=successor.revision,
        template_version=successor.template_version,
        lifecycle_status=successor.lifecycle_status,
        input_snapshot_hash=successor.input_snapshot_hash,
        content_hash=successor.content_hash or preview_dto.content_hash,
        common_core_questions=preview_dto.common_core_questions,
        coverage_summary=preview_dto.coverage_summary,
        validation_report=preview_dto.validation_report,
        builder_version=successor.deterministic_builder_version,
        question_catalogue_version=successor.question_catalogue_version,
        rubric_catalogue_version=successor.rubric_catalogue_version,
        created_by_user_id=successor.created_by_user_id,
        created_at=successor.created_at,
    )


@router.get(
    "/history",
    response_model=VersionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Template Version History",
)
async def get_template_history_endpoint(
    job_id: uuid.UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> VersionHistoryResponse:
    actor = auth_ctx.user
    try:
        return get_template_version_history(actor=actor, job_id=job_id, db=db)
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.get(
    "/diff",
    response_model=VersionDiffResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare Template Versions",
)
async def get_template_diff_endpoint(
    job_id: uuid.UUID,
    version_from: int = Query(..., ge=1),
    version_to: int = Query(..., ge=1),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> VersionDiffResponse:
    actor = auth_ctx.user
    try:
        return compute_template_version_diff(
            actor=actor,
            job_id=job_id,
            version_from=version_from,
            version_to=version_to,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except (InterviewSnapshotError, LifecycleConflictError) as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


# =========================================================================
# Phase 3B.4: Candidate Plan Endpoints (Edit, Validate, Approve, Successor, History, Diff)
# =========================================================================

@router.patch(
    "/{template_id}/candidate-plans/{plan_id}/edit",
    response_model=CandidateInterviewPlanDraftCreateResponse,
    status_code=status.HTTP_200_OK,
    summary="Safe Edit Candidate Plan Draft",
)
async def edit_candidate_plan_draft_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: CandidatePlanEditRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> CandidateInterviewPlanDraftCreateResponse:
    actor = auth_ctx.user
    try:
        updated_plan = edit_candidate_interview_plan_draft(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            plan_id=plan_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except LifecycleValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message, "blocking_errors": exc.blocking_errors},
        )
    except LifecycleConflictError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})

    # Safe audit log
    Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="CANDIDATE_INTERVIEW_PLAN_DRAFT_EDITED",
        resource_type="candidate_interview_plan",
        resource_id=str(updated_plan.plan_id),
        policy_version=updated_plan.guardrail_policy_version,
        safe_metadata={
            "job_id": str(job_id),
            "template_id": str(template_id),
            "candidate_id": str(updated_plan.candidate_id),
            "plan_version": updated_plan.plan_version,
            "record_version": updated_plan.record_version,
            "content_hash": updated_plan.content_hash,
        },
    )

    from app.services.candidate_plan_generator_service import preview_deterministic_candidate_interview_plan
    plan_preview = preview_deterministic_candidate_interview_plan(
        actor=actor,
        job_id=job_id,
        template_id=template_id,
        candidate_id=updated_plan.candidate_id,
        expected_revision=updated_plan.template.revision,
        profile_version=updated_plan.profile_version,
        match_result_id=updated_plan.match_result_id,
        db=db,
    )
    preview_dto = _map_candidate_plan_to_preview_dto(plan_preview)

    return CandidateInterviewPlanDraftCreateResponse(
        plan_id=updated_plan.plan_id,
        organization_id=updated_plan.organization_id,
        job_id=job_id,
        job_revision=updated_plan.template.revision,
        template_id=updated_plan.template_id,
        template_version=updated_plan.template_version,
        candidate_id=updated_plan.candidate_id,
        profile_id=updated_plan.profile_id,
        profile_version=updated_plan.profile_version,
        match_result_id=updated_plan.match_result_id,
        match_result_fingerprint=updated_plan.match_result_fingerprint,
        plan_version=updated_plan.plan_version,
        lifecycle_status=updated_plan.lifecycle_status,
        scoring_separation_policy=updated_plan.scoring_separation_policy,
        input_snapshot_hash=updated_plan.input_snapshot_hash,
        content_hash=updated_plan.content_hash or preview_dto.content_hash,
        common_template_summary=preview_dto.common_template_summary,
        supplemental_questions=preview_dto.supplemental_questions,
        coverage_summary=preview_dto.coverage_summary,
        validation_report=preview_dto.validation_report,
        supplemental_catalogue_version=plan_preview.supplemental_catalogue_version,
        policy_version=plan_preview.policy_version,
        created_by_user_id=updated_plan.created_by_user_id,
        created_at=updated_plan.created_at,
    )


@router.post(
    "/{template_id}/candidate-plans/{plan_id}/validate",
    response_model=ValidationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate Candidate Plan Draft",
)
async def validate_candidate_plan_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    plan_id: uuid.UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> ValidationSummaryResponse:
    actor = auth_ctx.user
    try:
        report = validate_candidate_interview_plan_draft(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            plan_id=plan_id,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except LifecycleConflictError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})

    # Safe audit log
    Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="CANDIDATE_INTERVIEW_PLAN_VALIDATED" if report.is_valid else "CANDIDATE_INTERVIEW_PLAN_VALIDATION_FAILED",
        resource_type="candidate_interview_plan",
        resource_id=str(plan_id),
        policy_version=report.policy_version,
        safe_metadata={
            "job_id": str(job_id),
            "template_id": str(template_id),
            "is_valid": report.is_valid,
            "blocking_errors_count": len(report.blocking_errors),
            "content_hash": report.content_hash,
        },
    )

    return report


@router.post(
    "/{template_id}/candidate-plans/{plan_id}/approve",
    response_model=ApprovalSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve Candidate Plan",
)
async def approve_candidate_plan_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: InterviewApprovalRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> ApprovalSummaryResponse:
    actor = auth_ctx.user
    try:
        summary = approve_candidate_interview_plan(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            plan_id=plan_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except LifecycleConflictError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})

    # Safe audit log
    Phase3AuditEvent(
        event_id=uuid.uuid4(),
        actor_user_id=actor.user_id,
        organization_id=getattr(actor, "org_id", getattr(actor, "organization_id", None)),
        event_type="CANDIDATE_INTERVIEW_PLAN_APPROVED",
        resource_type="candidate_interview_plan",
        resource_id=str(plan_id),
        safe_metadata={
            "job_id": str(job_id),
            "template_id": str(template_id),
            "plan_version": summary.record_version,
            "content_hash": summary.content_hash,
            "superseded_parent_id": str(summary.superseded_parent_id) if summary.superseded_parent_id else None,
        },
    )

    return summary


@router.post(
    "/{template_id}/candidate-plans/{plan_id}/successor",
    response_model=CandidateInterviewPlanDraftCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Successor Draft From Approved Candidate Plan",
)
async def create_candidate_plan_successor_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: SuccessorDraftCreateRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> CandidateInterviewPlanDraftCreateResponse:
    actor = auth_ctx.user
    try:
        successor = create_candidate_interview_plan_successor(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            plan_id=plan_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except LifecycleConflictError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})

    from app.services.candidate_plan_generator_service import preview_deterministic_candidate_interview_plan
    plan_preview = preview_deterministic_candidate_interview_plan(
        actor=actor,
        job_id=job_id,
        template_id=template_id,
        candidate_id=successor.candidate_id,
        expected_revision=successor.template.revision,
        profile_version=successor.profile_version,
        match_result_id=successor.match_result_id,
        db=db,
    )
    preview_dto = _map_candidate_plan_to_preview_dto(plan_preview)

    return CandidateInterviewPlanDraftCreateResponse(
        plan_id=successor.plan_id,
        organization_id=successor.organization_id,
        job_id=job_id,
        job_revision=successor.template.revision,
        template_id=successor.template_id,
        template_version=successor.template_version,
        candidate_id=successor.candidate_id,
        profile_id=successor.profile_id,
        profile_version=successor.profile_version,
        match_result_id=successor.match_result_id,
        match_result_fingerprint=successor.match_result_fingerprint,
        plan_version=successor.plan_version,
        lifecycle_status=successor.lifecycle_status,
        scoring_separation_policy=successor.scoring_separation_policy,
        input_snapshot_hash=successor.input_snapshot_hash,
        content_hash=successor.content_hash or preview_dto.content_hash,
        common_template_summary=preview_dto.common_template_summary,
        supplemental_questions=preview_dto.supplemental_questions,
        coverage_summary=preview_dto.coverage_summary,
        validation_report=preview_dto.validation_report,
        supplemental_catalogue_version=plan_preview.supplemental_catalogue_version,
        policy_version=plan_preview.policy_version,
        created_by_user_id=successor.created_by_user_id,
        created_at=successor.created_at,
    )


@router.get(
    "/{template_id}/candidate-plans/{candidate_id}/history",
    response_model=VersionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Candidate Plan Version History",
)
async def get_candidate_plan_history_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    candidate_id: uuid.UUID,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> VersionHistoryResponse:
    actor = auth_ctx.user
    try:
        return get_candidate_plan_version_history(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            candidate_id=candidate_id,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.get(
    "/{template_id}/candidate-plans/{candidate_id}/diff",
    response_model=VersionDiffResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare Candidate Plan Versions",
)
async def get_candidate_plan_diff_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    candidate_id: uuid.UUID,
    version_from: int = Query(..., ge=1),
    version_to: int = Query(..., ge=1),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> VersionDiffResponse:
    actor = auth_ctx.user
    try:
        return compute_candidate_plan_version_diff(
            actor=actor,
            job_id=job_id,
            template_id=template_id,
            candidate_id=candidate_id,
            version_from=version_from,
            version_to=version_to,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except (InterviewSnapshotError, LifecycleConflictError) as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


# =========================================================================
# Phase 3C.2: Recruiter Question Wording Assistance
# =========================================================================

from app.schemas.interview_api import (
    ApplyWordingSuggestionRequest,
    GenerateTemplateAiWordingRequest,
    GenerateTemplateAiWordingResponse,
    QuestionActionResponse,
    RestoreDeterministicWordingRequest,
)
from app.schemas.wording_contract import (
    CandidateWordingResult,
    RecruiterWordingAssistRequest,
)
from app.services.wording_assistance_service import (
    QuestionNotDraftError,
    QuestionNotFoundError,
    QuestionWordingError,
    apply_wording_suggestion,
    generate_template_ai_wording,
    request_question_wording_assistance,
    restore_deterministic_wording,
)


@router.post(
    "/{template_id}/questions/{question_id}/assist-wording",
    response_model=CandidateWordingResult,
    status_code=status.HTTP_200_OK,
    summary="Request Bounded Question Wording Assistance",
    description=(
        "Requests bounded wording assistance for one authorized DRAFT interview question. "
        "The model proposes alternative wording; all authoritative metadata, intent, competency, "
        "and layer constraints are loaded strictly by the server. Does not alter lifecycle or persist results."
    ),
)
async def request_question_wording_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: RecruiterWordingAssistRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> CandidateWordingResult:
    actor = auth_ctx.user
    try:
        return await request_question_wording_assistance(
            actor=actor,
            question_id=question_id,
            request_dto=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="question_wording_assistance",
            resource_id=str(question_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message})
    except QuestionNotDraftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})
    except QuestionWordingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post(
    "/{template_id}/questions/{question_id}/apply-suggestion",
    response_model=QuestionActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Apply Validated Wording Suggestion",
    description="Applies a validated AI wording suggestion to an authorized DRAFT question. Sets authoring_origin to AI_ASSISTED and invalidates validation state.",
)
async def apply_question_wording_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: ApplyWordingSuggestionRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> QuestionActionResponse:
    actor = auth_ctx.user
    try:
        return apply_wording_suggestion(
            actor=actor,
            question_id=question_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="apply_wording_suggestion",
            resource_id=str(question_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message})
    except QuestionNotDraftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})
    except QuestionWordingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post(
    "/{template_id}/questions/{question_id}/restore-deterministic",
    response_model=QuestionActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Restore Deterministic Question Wording",
    description="Restores original deterministic text on an authorized DRAFT question and sets origin to DETERMINISTIC.",
)
async def restore_question_wording_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: RestoreDeterministicWordingRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> QuestionActionResponse:
    actor = auth_ctx.user
    try:
        return restore_deterministic_wording(
            actor=actor,
            question_id=question_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="restore_deterministic_wording",
            resource_id=str(question_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message})
    except QuestionNotDraftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})
    except QuestionWordingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post(
    "/{template_id}/generate-ai-wording",
    response_model=GenerateTemplateAiWordingResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate AI Wording For Entire Interview Template",
    description="Sequentially requests and validates AI wording for all questions in an authorized DRAFT template.",
)
async def generate_template_ai_wording_endpoint(
    job_id: uuid.UUID,
    template_id: uuid.UUID,
    payload: GenerateTemplateAiWordingRequest,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> GenerateTemplateAiWordingResponse:
    actor = auth_ctx.user
    try:
        return await generate_template_ai_wording(
            actor=actor,
            template_id=template_id,
            request=payload,
            db=db,
        )
    except InterviewUnauthorizedError as exc:
        _record_audit_event(
            db=db,
            event_type=AuditEventType.ACCESS_DENIED,
            result=AuditResult.DENIED,
            reason_code=AuditReasonCode.ACCESS_DENIED,
            actor_user_id=actor.user_id,
            resource_type="generate_template_ai_wording",
            resource_id=str(template_id),
            safe_metadata={"error_code": exc.code},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": exc.code, "message": exc.message})
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message})
    except QuestionNotDraftError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})
    except QuestionWordingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    except InterviewSnapshotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})




