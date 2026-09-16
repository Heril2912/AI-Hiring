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
