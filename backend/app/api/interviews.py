import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import (
    AuthenticatedContext,
    _record_audit_event,
    require_recruiter,
)
from app.database import get_db
from app.models.auth import AuditEventType, AuditReasonCode, AuditResult
from app.schemas.interview_api import (
    BlueprintCoverageResponse,
    BlueprintValidationReportResponse,
    CompetencySelectionResponse,
    InterviewQuestionResponse,
    InterviewRubricResponse,
    InterviewTemplateDraftCreateResponse,
    InterviewTemplatePreviewResponse,
    RequirementClassificationResponse,
)
from app.schemas.phase3_audit import Phase3AuditEvent
from app.schemas.phase3_enums import AuditRetentionClass
from app.services.interview_generator_service import (
    BlueprintCoverageSummary,
    GeneratedDeterministicBlueprint,
    create_deterministic_interview_template_draft,
    preview_deterministic_interview_template,
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

