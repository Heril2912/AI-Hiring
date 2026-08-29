import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

if TYPE_CHECKING:
    from app.models.extraction import ResumeExtraction
    from app.models.resume import ResumeArtifact


class CandidateIdentityRecord(Base):
    __tablename__ = "candidate_identities"
    __table_args__ = (
        UniqueConstraint("artifact_id", name="uq_candidate_identities_artifact_id"),
        Index("ix_candidate_identities_artifact_id", "artifact_id"),
    )

    identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "resume_artifacts.artifact_id",
            ondelete="CASCADE",
            name="fk_candidate_identities_artifact_id_resume_artifacts",
        ),
        nullable=False,
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    primary_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    primary_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    identity_payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    artifact: Mapped["ResumeArtifact"] = relationship(
        "ResumeArtifact",
    )
    profiles: Mapped[List["CandidateProfileRecord"]] = relationship(
        "CandidateProfileRecord",
        back_populates="identity",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CandidateProfileRecord(Base):
    __tablename__ = "candidate_profiles"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id",
            "parser_pipeline_version",
            "schema_version",
            name="uq_candidate_profiles_artifact_pipeline_schema",
        ),
        CheckConstraint(
            "profile_version >= 1",
            name="ck_candidate_profiles_profile_version_positive",
        ),
        CheckConstraint(
            "length(trim(schema_version)) > 0",
            name="ck_candidate_profiles_schema_version_not_empty",
        ),
        CheckConstraint(
            "length(trim(parser_pipeline_version)) > 0",
            name="ck_candidate_profiles_parser_pipeline_version_not_empty",
        ),
        Index("ix_candidate_profiles_artifact_id", "artifact_id"),
        Index("ix_candidate_profiles_extraction_id", "extraction_id"),
        Index("ix_candidate_profiles_identity_id", "identity_id"),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "resume_artifacts.artifact_id",
            ondelete="CASCADE",
            name="fk_candidate_profiles_artifact_id_resume_artifacts",
        ),
        nullable=False,
    )
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "resume_extractions.extraction_id",
            ondelete="CASCADE",
            name="fk_candidate_profiles_extraction_id_resume_extractions",
        ),
        nullable=False,
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "candidate_identities.identity_id",
            ondelete="CASCADE",
            name="fk_candidate_profiles_identity_id_candidate_identities",
        ),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0",
        server_default=text("'1.0'"),
    )
    parser_pipeline_version: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    professional_profile: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
    )
    evidence_spans: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    warning_metadata: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    artifact: Mapped["ResumeArtifact"] = relationship(
        "ResumeArtifact",
    )
    extraction: Mapped["ResumeExtraction"] = relationship(
        "ResumeExtraction",
    )
    identity: Mapped["CandidateIdentityRecord"] = relationship(
        "CandidateIdentityRecord",
        back_populates="profiles",
    )
