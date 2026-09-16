import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import Field

from app.schemas.matching import FrozenSchema
from app.schemas.phase3_enums import (
    AuthoringOrigin,
    InterviewLayer,
    PlanLifecycle,
    QuestionType,
    ValidationState,
)


class InterviewRubricAnchorResponse(FrozenSchema):
    point: int
    description: str


class InterviewRubricResponse(FrozenSchema):
    rubric_id: uuid.UUID
    rubric_version: int
    competency_definition: str
    question_intent: str
    observable_indicators: List[str]
    rating_anchors: Dict[int, str]
    sufficient_evidence_guidance: str
    insufficient_evidence_guidance: str
    incomplete_answer_guidance: Optional[str] = None
    permitted_probes: List[str]
    prohibited_inferences: List[str]
    subject_matter_review_status: str
    validation_state: ValidationState


class InterviewQuestionResponse(FrozenSchema):
    question_id: uuid.UUID
    layer: InterviewLayer
    question_type: QuestionType
    competency_id: Optional[str] = None
    requirement_references: List[uuid.UUID]
    deterministic_template_id: Optional[str] = None
    deterministic_template_version: Optional[str] = None
    question_text: str
    question_intent: str
    authoring_origin: AuthoringOrigin
    display_order: int
    estimated_time_minutes: int
    permitted_probes: List[str]
    validation_state: ValidationState
    included_in_common_score: bool
    rubric: Optional[InterviewRubricResponse] = None


class RequirementClassificationResponse(FrozenSchema):
    requirement_id: uuid.UUID
    label: str
    category: str
    suitability: str
    reason: str
    mapped_competency_key: Optional[str] = None


class CompetencySelectionResponse(FrozenSchema):
    competency_key: str
    competency_label: str
    priority_score: float
    selection_reason: str
    covered_requirement_ids: List[uuid.UUID]


class BlueprintCoverageResponse(FrozenSchema):
    total_requirements_count: int
    interview_eligible_requirements_count: int
    covered_requirements_count: int
    selected_competencies: List[CompetencySelectionResponse]
    uncovered_eligible_competencies: List[str]
    unsupported_competencies: List[str]
    document_verification_requirements: List[RequirementClassificationResponse]
    work_sample_requirements: List[RequirementClassificationResponse]
    out_of_interview_requirements: List[RequirementClassificationResponse]
    total_estimated_duration_minutes: int
    question_count_by_type: Dict[str, int]
    coverage_percentage: float
    builder_version: str
    question_catalogue_version: str
    rubric_catalogue_version: str


class BlueprintValidationReportResponse(FrozenSchema):
    is_valid: bool
    blocking_errors: List[str]
    warnings: List[str]
    checked_rules_count: int


class InterviewTemplatePreviewResponse(FrozenSchema):
    """Response DTO for deterministic interview template preview."""
    job_id: uuid.UUID
    job_version_id: uuid.UUID
    job_revision: int
    lifecycle_status: PlanLifecycle
    input_snapshot_hash: str
    content_hash: str
    common_core_questions: List[InterviewQuestionResponse]
    coverage_summary: BlueprintCoverageResponse
    validation_report: BlueprintValidationReportResponse
    builder_version: str
    question_catalogue_version: str
    rubric_catalogue_version: str
    policy_id: str
    policy_version: str
    policy_hash: str


class InterviewTemplateDraftCreateResponse(FrozenSchema):
    """Response DTO for created interview template draft."""
    template_id: uuid.UUID
    organization_id: uuid.UUID
    job_id: uuid.UUID
    job_version_id: uuid.UUID
    job_revision: int
    template_version: int
    lifecycle_status: PlanLifecycle
    input_snapshot_hash: str
    content_hash: str
    common_core_questions: List[InterviewQuestionResponse]
    coverage_summary: BlueprintCoverageResponse
    validation_report: BlueprintValidationReportResponse
    builder_version: str
    question_catalogue_version: str
    rubric_catalogue_version: str
    created_by_user_id: uuid.UUID
    created_at: datetime
