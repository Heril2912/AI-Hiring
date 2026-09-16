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


# =========================================================================
# Candidate Interview Plan Schemas (Phase 3B.3)
# =========================================================================

class SupplementalQuestionGuidanceResponse(FrozenSchema):
    """Safe, non-scored guidance for an evidence clarification question."""
    clarification_purpose: str
    facts_to_confirm: List[str]
    prohibited_inferences: List[str]


class SupplementalQuestionProvenanceResponse(FrozenSchema):
    """Provenance references binding a supplemental question to authoritative match results."""
    source_requirement_id: uuid.UUID
    source_match_result_id: uuid.UUID
    source_match_state: str
    allowlisted_evidence_ids: List[str]
    excluded_from_common_score: bool = True


class CandidateSupplementalQuestionResponse(FrozenSchema):
    """Supplemental evidence clarification question DTO."""
    question_id: uuid.UUID
    layer: InterviewLayer = InterviewLayer.SUPPLEMENTAL_EVIDENCE
    question_type: QuestionType = QuestionType.EVIDENCE_CLARIFICATION
    authoring_origin: AuthoringOrigin = AuthoringOrigin.DETERMINISTIC
    display_order: int
    requirement_references: List[uuid.UUID]
    deterministic_template_id: str
    deterministic_template_version: str
    question_text: str
    question_intent: str
    estimated_time_minutes: int
    included_in_common_score: bool = False
    validation_state: ValidationState
    guidance: SupplementalQuestionGuidanceResponse
    provenance: SupplementalQuestionProvenanceResponse


class CandidateInterviewPlanSummaryResponse(FrozenSchema):
    """Safe summary of the bound common-core template."""
    template_id: uuid.UUID
    template_version: int
    template_content_hash: str
    job_id: uuid.UUID
    job_revision: int
    common_core_questions_count: int
    common_core_duration_minutes: int


class CandidatePlanCoverageSummaryResponse(FrozenSchema):
    """Coverage summary for candidate-specific clarification questions."""
    selected_target_count: int
    target_selection_reasons: Dict[str, str]
    match_states_clarified: List[str]
    total_supplemental_duration_minutes: int


class CandidateInterviewPlanPreviewResponse(FrozenSchema):
    """Response DTO for candidate interview plan preview."""
    plan_id: uuid.UUID
    job_id: uuid.UUID
    job_revision: int
    template_id: uuid.UUID
    template_version: int
    candidate_id: uuid.UUID
    profile_id: uuid.UUID
    profile_version: int
    match_result_id: uuid.UUID
    match_result_fingerprint: str
    lifecycle_status: PlanLifecycle
    scoring_separation_policy: str
    input_snapshot_hash: str
    content_hash: str
    common_template_summary: CandidateInterviewPlanSummaryResponse
    supplemental_questions: List[CandidateSupplementalQuestionResponse]
    coverage_summary: CandidatePlanCoverageSummaryResponse
    validation_report: BlueprintValidationReportResponse
    supplemental_catalogue_version: str
    policy_version: str


class CandidateInterviewPlanDraftCreateResponse(FrozenSchema):
    """Response DTO for created candidate interview plan draft."""
    plan_id: uuid.UUID
    organization_id: uuid.UUID
    job_id: uuid.UUID
    job_revision: int
    template_id: uuid.UUID
    template_version: int
    candidate_id: uuid.UUID
    profile_id: uuid.UUID
    profile_version: int
    match_result_id: uuid.UUID
    match_result_fingerprint: str
    plan_version: int
    lifecycle_status: PlanLifecycle
    scoring_separation_policy: str
    input_snapshot_hash: str
    content_hash: str
    common_template_summary: CandidateInterviewPlanSummaryResponse
    supplemental_questions: List[CandidateSupplementalQuestionResponse]
    coverage_summary: CandidatePlanCoverageSummaryResponse
    validation_report: BlueprintValidationReportResponse
    supplemental_catalogue_version: str
    policy_version: str
    created_by_user_id: uuid.UUID
    created_at: datetime

