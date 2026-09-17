import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.schemas.phase3_enums import (
    AuthoringOrigin,
    InterviewLayer,
    PlanLifecycle,
    PrivacyReviewStatus,
    ProviderCompatibilityStatus,
    ProviderEgressClass,
    ProviderOperation,
    ProviderType,
    QuestionType,
    ValidationState,
)

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

if TYPE_CHECKING:
    from app.models.auth import UserRecord
    from app.models.candidate import CandidateProfileRecord
    from app.models.gap_report import GapReportRecord
    from app.models.job import JobRequirement, JobRequisition, JobVersion
    from app.models.matching import MatchResultRecord


class JobInterviewTemplateRecord(Base):
    """Authoritative persistent record for a job interview template."""

    __tablename__ = "job_interview_templates"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "template_version",
            name="uq_job_interview_templates_job_id_template_version",
        ),
        CheckConstraint(
            "template_version >= 1",
            name="ck_job_interview_templates_template_version_positive",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_job_interview_templates_revision_positive",
        ),
        CheckConstraint(
            "record_version >= 1",
            name="ck_job_interview_templates_record_version_positive",
        ),
        CheckConstraint(
            "lifecycle_status IN ('DRAFT', 'VALIDATED', 'APPROVED', 'IN_USE', 'SUPERSEDED')",
            name="ck_job_interview_templates_lifecycle_status",
        ),
        Index("ix_job_interview_templates_job_id", "job_id"),
        Index("ix_job_interview_templates_job_version_id", "job_version_id"),
        Index("ix_job_interview_templates_organization_id", "organization_id"),
        Index("ix_job_interview_templates_created_by_user_id", "created_by_user_id"),
        Index("ix_job_interview_templates_lifecycle_status", "lifecycle_status"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_requisitions.job_id",
            ondelete="RESTRICT",
            name="fk_job_interview_templates_job_id_job_requisitions",
        ),
        nullable=False,
    )
    job_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_versions.job_version_id",
            ondelete="RESTRICT",
            name="fk_job_interview_templates_job_version_id_job_versions",
        ),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    template_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    parent_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_interview_templates.template_id",
            ondelete="SET NULL",
            name="fk_job_interview_templates_parent_template_id",
        ),
        nullable=True,
    )
    lifecycle_status: Mapped[PlanLifecycle] = mapped_column(
        Enum(
            PlanLifecycle,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_job_interview_templates_lifecycle_status_enum",
        ),
        nullable=False,
        default=PlanLifecycle.DRAFT,
        server_default=text("'DRAFT'"),
    )
    guardrail_policy_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    guardrail_policy_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    deterministic_builder_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    question_catalogue_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    rubric_catalogue_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    input_snapshot_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_job_interview_templates_created_by_user_id_users",
        ),
        nullable=False,
    )
    record_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    requisition: Mapped["JobRequisition"] = relationship("JobRequisition")
    job_version: Mapped["JobVersion"] = relationship("JobVersion")
    creator: Mapped["UserRecord"] = relationship("UserRecord", foreign_keys=[created_by_user_id])
    parent_template: Mapped[Optional["JobInterviewTemplateRecord"]] = relationship(
        "JobInterviewTemplateRecord",
        remote_side=[template_id],
    )
    questions: Mapped[List["InterviewQuestionRecord"]] = relationship(
        "InterviewQuestionRecord",
        back_populates="template",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InterviewQuestionRecord.display_order.asc()",
    )
    candidate_plans: Mapped[List["CandidateInterviewPlanRecord"]] = relationship(
        "CandidateInterviewPlanRecord",
        back_populates="template",
    )


class InterviewQuestionRecord(Base):
    """Authoritative persistent record for an interview question inside a template."""

    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "display_order",
            name="uq_interview_questions_template_id_display_order",
        ),
        CheckConstraint(
            "display_order >= 0",
            name="ck_interview_questions_display_order_non_negative",
        ),
        CheckConstraint(
            "question_version >= 1",
            name="ck_interview_questions_question_version_positive",
        ),
        CheckConstraint(
            "estimated_time_minutes >= 1 AND estimated_time_minutes <= 60",
            name="ck_interview_questions_estimated_time_bounded",
        ),
        CheckConstraint(
            "length(trim(question_text)) > 0",
            name="ck_interview_questions_question_text_not_empty",
        ),
        CheckConstraint(
            "length(trim(question_intent)) > 0",
            name="ck_interview_questions_question_intent_not_empty",
        ),
        CheckConstraint(
            "(layer = 'COMMON_CORE' AND included_in_common_score = true) OR (layer = 'SUPPLEMENTAL_EVIDENCE' AND included_in_common_score = false)",
            name="ck_interview_questions_layer_scoring_integrity",
        ),
        Index("ix_interview_questions_template_id", "template_id"),
        Index("ix_interview_questions_layer", "layer"),
        Index("ix_interview_questions_question_type", "question_type"),
        Index("ix_interview_questions_validation_state", "validation_state"),
    )

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_interview_templates.template_id",
            ondelete="CASCADE",
            name="fk_interview_questions_template_id_job_interview_templates",
        ),
        nullable=False,
    )
    question_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    layer: Mapped[InterviewLayer] = mapped_column(
        Enum(
            InterviewLayer,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_interview_questions_layer_enum",
        ),
        nullable=False,
    )
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(
            QuestionType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_interview_questions_question_type_enum",
        ),
        nullable=False,
    )
    authoring_origin: Mapped[AuthoringOrigin] = mapped_column(
        Enum(
            AuthoringOrigin,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_interview_questions_authoring_origin_enum",
        ),
        nullable=False,
        default=AuthoringOrigin.DETERMINISTIC,
        server_default=text("'DETERMINISTIC'"),
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    competency_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    requirement_ids: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    deterministic_template_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    deterministic_template_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    question_intent: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    estimated_time_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=text("5"),
    )
    included_in_common_score: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    validation_state: Mapped[ValidationState] = mapped_column(
        Enum(
            ValidationState,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_interview_questions_validation_state_enum",
        ),
        nullable=False,
        default=ValidationState.PENDING,
        server_default=text("'PENDING'"),
    )
    permitted_probes: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    safe_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    template: Mapped["JobInterviewTemplateRecord"] = relationship(
        "JobInterviewTemplateRecord",
        back_populates="questions",
    )
    rubric: Mapped[Optional["InterviewRubricRecord"]] = relationship(
        "InterviewRubricRecord",
        back_populates="question",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    provenance: Mapped[Optional["SupplementalQuestionProvenanceRecord"]] = relationship(
        "SupplementalQuestionProvenanceRecord",
        back_populates="question",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class InterviewRubricRecord(Base):
    """Authoritative scoring and evaluation rubric record linked to an interview question."""

    __tablename__ = "interview_rubrics"
    __table_args__ = (
        CheckConstraint(
            "rubric_version >= 1",
            name="ck_interview_rubrics_rubric_version_positive",
        ),
        CheckConstraint(
            "length(trim(competency_definition)) > 0",
            name="ck_interview_rubrics_competency_def_not_empty",
        ),
        CheckConstraint(
            "length(trim(question_intent)) > 0",
            name="ck_interview_rubrics_question_intent_not_empty",
        ),
        CheckConstraint(
            "length(trim(sufficient_evidence_guidance)) > 0",
            name="ck_interview_rubrics_sufficient_evidence_not_empty",
        ),
        CheckConstraint(
            "length(trim(insufficient_evidence_guidance)) > 0",
            name="ck_interview_rubrics_insufficient_evidence_not_empty",
        ),
        Index("ix_interview_rubrics_question_id", "question_id"),
    )

    rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "interview_questions.question_id",
            ondelete="CASCADE",
            name="fk_interview_rubrics_question_id_interview_questions",
        ),
        nullable=False,
        unique=True,
    )
    rubric_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    competency_definition: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    question_intent: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    observable_indicators: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    rating_anchors: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
    )
    sufficient_evidence_guidance: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    insufficient_evidence_guidance: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    incomplete_answer_guidance: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    permitted_probes: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    prohibited_inferences: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    subject_matter_review_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="NOT_REQUIRED",
        server_default=text("'NOT_REQUIRED'"),
    )
    validation_state: Mapped[ValidationState] = mapped_column(
        Enum(
            ValidationState,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_interview_rubrics_validation_state_enum",
        ),
        nullable=False,
        default=ValidationState.PASSED,
        server_default=text("'PASSED'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    question: Mapped["InterviewQuestionRecord"] = relationship(
        "InterviewQuestionRecord",
        back_populates="rubric",
    )


class CandidateInterviewPlanRecord(Base):
    """Authoritative candidate-tailored interview plan record linking template and frozen match results."""

    __tablename__ = "candidate_interview_plans"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "template_id",
            "plan_version",
            name="uq_cand_plans_candidate_template_version",
        ),
        CheckConstraint(
            "plan_version >= 1",
            name="ck_cand_plans_plan_version_positive",
        ),
        CheckConstraint(
            "template_version >= 1",
            name="ck_cand_plans_template_version_positive",
        ),
        CheckConstraint(
            "profile_version >= 1",
            name="ck_cand_plans_profile_version_positive",
        ),
        CheckConstraint(
            "record_version >= 1",
            name="ck_cand_plans_record_version_positive",
        ),
        CheckConstraint(
            "lifecycle_status IN ('DRAFT', 'VALIDATED', 'APPROVED', 'IN_USE', 'SUPERSEDED')",
            name="ck_cand_plans_lifecycle_status",
        ),
        Index("ix_candidate_interview_plans_template_id", "template_id"),
        Index("ix_candidate_interview_plans_candidate_id", "candidate_id"),
        Index("ix_candidate_interview_plans_profile_id", "profile_id"),
        Index("ix_candidate_interview_plans_match_result_id", "match_result_id"),
        Index("ix_candidate_interview_plans_organization_id", "organization_id"),
        Index("ix_candidate_interview_plans_created_by_user_id", "created_by_user_id"),
        Index("ix_candidate_interview_plans_lifecycle_status", "lifecycle_status"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_interview_templates.template_id",
            ondelete="RESTRICT",
            name="fk_cand_plans_template_id_job_interview_templates",
        ),
        nullable=False,
    )
    template_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "candidate_profiles.profile_id",
            ondelete="RESTRICT",
            name="fk_cand_plans_profile_id_candidate_profiles",
        ),
        nullable=False,
    )
    profile_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    match_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "match_results.result_id",
            ondelete="RESTRICT",
            name="fk_cand_plans_match_result_id_match_results",
        ),
        nullable=False,
    )
    match_result_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    plan_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    parent_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "candidate_interview_plans.plan_id",
            ondelete="SET NULL",
            name="fk_cand_plans_parent_plan_id",
        ),
        nullable=True,
    )
    lifecycle_status: Mapped[PlanLifecycle] = mapped_column(
        Enum(
            PlanLifecycle,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_candidate_interview_plans_lifecycle_status_enum",
        ),
        nullable=False,
        default=PlanLifecycle.DRAFT,
        server_default=text("'DRAFT'"),
    )
    guardrail_policy_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    scoring_separation_policy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="STRICT_COMMON_CORE_SEPARATION",
        server_default=text("'STRICT_COMMON_CORE_SEPARATION'"),
    )
    input_snapshot_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.user_id",
            ondelete="RESTRICT",
            name="fk_cand_plans_created_by_user_id_users",
        ),
        nullable=False,
    )
    record_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    template: Mapped["JobInterviewTemplateRecord"] = relationship(
        "JobInterviewTemplateRecord",
        back_populates="candidate_plans",
    )
    profile: Mapped["CandidateProfileRecord"] = relationship("CandidateProfileRecord")
    match_result: Mapped["MatchResultRecord"] = relationship("MatchResultRecord")
    creator: Mapped["UserRecord"] = relationship("UserRecord", foreign_keys=[created_by_user_id])
    parent_plan: Mapped[Optional["CandidateInterviewPlanRecord"]] = relationship(
        "CandidateInterviewPlanRecord",
        remote_side=[plan_id],
    )
    provenances: Mapped[List["SupplementalQuestionProvenanceRecord"]] = relationship(
        "SupplementalQuestionProvenanceRecord",
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SupplementalQuestionProvenanceRecord(Base):
    """Authoritative provenance record binding supplemental clarification questions to exact requirement and evidence gaps."""

    __tablename__ = "supplemental_question_provenances"
    __table_args__ = (
        CheckConstraint(
            "excluded_from_common_score = true",
            name="ck_supp_prov_excluded_from_common_score",
        ),
        Index("ix_supp_prov_question_id", "question_id"),
        Index("ix_supp_prov_plan_id", "plan_id"),
        Index("ix_supp_prov_source_requirement_id", "source_requirement_id"),
        Index("ix_supp_prov_source_match_result_id", "source_match_result_id"),
        Index("ix_supp_prov_source_gap_report_id", "source_gap_report_id"),
    )

    provenance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "interview_questions.question_id",
            ondelete="CASCADE",
            name="fk_supp_prov_question_id_interview_questions",
        ),
        nullable=False,
        unique=True,
    )
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "candidate_interview_plans.plan_id",
            ondelete="CASCADE",
            name="fk_supp_prov_plan_id_cand_plans",
        ),
        nullable=True,
    )
    source_requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "job_requirements.requirement_id",
            ondelete="RESTRICT",
            name="fk_supp_prov_source_req_id_job_reqs",
        ),
        nullable=False,
    )
    source_match_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "match_results.result_id",
            ondelete="RESTRICT",
            name="fk_supp_prov_source_match_result_id_match_results",
        ),
        nullable=True,
    )
    source_gap_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "gap_reports.report_id",
            ondelete="RESTRICT",
            name="fk_supp_prov_source_gap_report_id_gap_reports",
        ),
        nullable=True,
    )
    source_match_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    allowlisted_evidence_ids: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    excluded_from_common_score: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    question: Mapped["InterviewQuestionRecord"] = relationship(
        "InterviewQuestionRecord",
        back_populates="provenance",
    )
    plan: Mapped[Optional["CandidateInterviewPlanRecord"]] = relationship(
        "CandidateInterviewPlanRecord",
        back_populates="provenances",
    )
    source_requirement: Mapped["JobRequirement"] = relationship("JobRequirement")
    source_match_result: Mapped[Optional["MatchResultRecord"]] = relationship("MatchResultRecord")
    source_gap_report: Mapped[Optional["GapReportRecord"]] = relationship("GapReportRecord")


class ProviderProfileRecord(Base):
    """Authoritative persistent record for an Admin-configured AI provider profile."""

    __tablename__ = "provider_profiles"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_provider_profiles_version_positive"),
        Index("ix_provider_profiles_organization_id", "organization_id"),
        Index("ix_provider_profiles_enabled", "enabled"),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    provider_type: Mapped[ProviderType] = mapped_column(
        Enum(
            ProviderType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_provider_profiles_provider_type_enum",
        ),
        nullable=False,
    )
    api_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="CHAT_COMPLETIONS",
    )
    base_url: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    model_identifier: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    secret_ref: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    supported_operations: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    connect_timeout_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=5.0,
    )
    request_timeout_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=30.0,
    )
    max_input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=4096,
    )
    max_output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=600,
    )
    max_response_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=262144,
    )
    max_concurrency: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    retry_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    egress_class: Mapped[ProviderEgressClass] = mapped_column(
        Enum(
            ProviderEgressClass,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_provider_profiles_egress_class_enum",
        ),
        nullable=False,
        default=ProviderEgressClass.LOCAL_ONLY,
    )
    privacy_review_status: Mapped[PrivacyReviewStatus] = mapped_column(
        Enum(
            PrivacyReviewStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_provider_profiles_privacy_review_status_enum",
        ),
        nullable=False,
        default=PrivacyReviewStatus.PENDING_REVIEW,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    compatibility_status: Mapped[ProviderCompatibilityStatus] = mapped_column(
        Enum(
            ProviderCompatibilityStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_provider_profiles_compatibility_status_enum",
        ),
        nullable=False,
        default=ProviderCompatibilityStatus.NOT_TESTED,
    )
    tested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    model_source: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    model_licence: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    model_checksum: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    last_compatibility_report: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    activated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deactivated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
