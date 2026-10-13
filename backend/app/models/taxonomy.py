import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
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

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class TaxonomySnapshotState(str, enum.Enum):
    IMPORTING = "IMPORTING"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class TaxonomySnapshot(Base):
    __tablename__ = "taxonomy_snapshots"
    __table_args__ = (
        CheckConstraint(
            "state IN ('IMPORTING', 'ACTIVE', 'SUPERSEDED', 'FAILED')",
            name="ck_taxonomy_snapshots_state",
        ),
        Index("ix_taxonomy_snapshots_state", "state"),
        Index("ix_taxonomy_snapshots_source_version", "source", "source_version"),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ONET",
        server_default=text("'ONET'"),
    )
    source_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    combined_sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    state: Mapped[TaxonomySnapshotState] = mapped_column(
        Enum(
            TaxonomySnapshotState,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_taxonomy_snapshots_state_enum",
        ),
        nullable=False,
        default=TaxonomySnapshotState.IMPORTING,
        server_default=text("'IMPORTING'"),
    )
    record_counts: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    source_filenames: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    activated_at: Mapped[Optional[datetime]] = mapped_column(
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

    # Relationships
    occupations: Mapped[List["OccupationConcept"]] = relationship(
        "OccupationConcept",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    skills: Mapped[List["SkillConcept"]] = relationship(
        "SkillConcept",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OccupationConcept(Base):
    __tablename__ = "occupation_concepts"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "onet_soc_code",
            name="uq_occupation_concepts_snapshot_id_onet_soc_code",
        ),
        CheckConstraint(
            "length(trim(canonical_title)) > 0",
            name="ck_occupation_concepts_canonical_title_not_empty",
        ),
        Index("ix_occupation_concepts_snapshot_id", "snapshot_id"),
        Index("ix_occupation_concepts_onet_soc_code", "onet_soc_code"),
        Index("ix_occupation_concepts_normalized_title", "normalized_title"),
    )

    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "taxonomy_snapshots.snapshot_id",
            ondelete="CASCADE",
            name="fk_occupation_concepts_snapshot_id_taxonomy_snapshots",
        ),
        nullable=False,
    )
    onet_soc_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    canonical_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    normalized_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    source_provenance: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ONET_31_0",
        server_default=text("'ONET_31_0'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    snapshot: Mapped["TaxonomySnapshot"] = relationship(
        "TaxonomySnapshot",
        back_populates="occupations",
    )
    aliases: Mapped[List["OccupationAlias"]] = relationship(
        "OccupationAlias",
        back_populates="occupation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    skill_links: Mapped[List["OccupationSkillLink"]] = relationship(
        "OccupationSkillLink",
        back_populates="occupation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OccupationAlias(Base):
    __tablename__ = "occupation_aliases"
    __table_args__ = (
        UniqueConstraint(
            "occupation_concept_id",
            "normalized_alias",
            name="uq_occupation_aliases_concept_id_normalized_alias",
        ),
        CheckConstraint(
            "length(trim(job_title_alias)) > 0",
            name="ck_occupation_aliases_job_title_alias_not_empty",
        ),
        Index("ix_occupation_aliases_concept_id", "occupation_concept_id"),
        Index("ix_occupation_aliases_normalized_alias", "normalized_alias"),
    )

    alias_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    occupation_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "occupation_concepts.concept_id",
            ondelete="CASCADE",
            name="fk_occupation_aliases_occupation_concept_id_occupation_concepts",
        ),
        nullable=False,
    )
    job_title_alias: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    normalized_alias: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    source_provenance: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ONET_31_0_JOB_TITLES",
        server_default=text("'ONET_31_0_JOB_TITLES'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    occupation: Mapped["OccupationConcept"] = relationship(
        "OccupationConcept",
        back_populates="aliases",
    )


class SkillConcept(Base):
    __tablename__ = "skill_concepts"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "normalized_label",
            name="uq_skill_concepts_snapshot_id_normalized_label",
        ),
        CheckConstraint(
            "length(trim(canonical_label)) > 0",
            name="ck_skill_concepts_canonical_label_not_empty",
        ),
        Index("ix_skill_concepts_snapshot_id", "snapshot_id"),
        Index("ix_skill_concepts_normalized_label", "normalized_label"),
        Index("ix_skill_concepts_source", "source"),
        Index("ix_skill_concepts_source_family", "source_family"),
    )

    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "taxonomy_snapshots.snapshot_id",
            ondelete="CASCADE",
            name="fk_skill_concepts_snapshot_id_taxonomy_snapshots",
        ),
        nullable=False,
    )
    canonical_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    normalized_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ONET_31_0",
        server_default=text("'ONET_31_0'"),
    )
    source_family: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="software",
        server_default=text("'software'"),
    )
    external_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    snapshot: Mapped["TaxonomySnapshot"] = relationship(
        "TaxonomySnapshot",
        back_populates="skills",
    )
    aliases: Mapped[List["SkillAlias"]] = relationship(
        "SkillAlias",
        back_populates="skill",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    occupation_links: Mapped[List["OccupationSkillLink"]] = relationship(
        "OccupationSkillLink",
        back_populates="skill",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    __table_args__ = (
        UniqueConstraint(
            "skill_concept_id",
            "normalized_alias",
            name="uq_skill_aliases_concept_id_normalized_alias",
        ),
        CheckConstraint(
            "length(trim(alias_text)) > 0",
            name="ck_skill_aliases_alias_text_not_empty",
        ),
        Index("ix_skill_aliases_concept_id", "skill_concept_id"),
        Index("ix_skill_aliases_normalized_alias", "normalized_alias"),
    )

    alias_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    skill_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "skill_concepts.concept_id",
            ondelete="CASCADE",
            name="fk_skill_aliases_skill_concept_id_skill_concepts",
        ),
        nullable=False,
    )
    alias_text: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    normalized_alias: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    alias_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INTERNAL_CONTROLLED",
        server_default=text("'INTERNAL_CONTROLLED'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    skill: Mapped["SkillConcept"] = relationship(
        "SkillConcept",
        back_populates="aliases",
    )


class OccupationSkillLink(Base):
    __tablename__ = "occupation_skill_links"
    __table_args__ = (
        UniqueConstraint(
            "occupation_concept_id",
            "skill_concept_id",
            name="uq_occupation_skill_links_occupation_skill",
        ),
        Index("ix_occupation_skill_links_occupation_id", "occupation_concept_id"),
        Index("ix_occupation_skill_links_skill_id", "skill_concept_id"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    occupation_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "occupation_concepts.concept_id",
            ondelete="CASCADE",
            name="fk_occupation_skill_links_occupation_concept_id",
        ),
        nullable=False,
    )
    skill_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "skill_concepts.concept_id",
            ondelete="CASCADE",
            name="fk_occupation_skill_links_skill_concept_id",
        ),
        nullable=False,
    )
    source_family: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="software",
        server_default=text("'software'"),
    )
    hot_technology: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    in_demand: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    importance_value: Mapped[Optional[float]] = mapped_column(
        nullable=True,
    )
    level_value: Mapped[Optional[float]] = mapped_column(
        nullable=True,
    )
    recommend_suppress: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    not_relevant: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    element_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    element_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    occupation: Mapped["OccupationConcept"] = relationship(
        "OccupationConcept",
        back_populates="skill_links",
    )
    skill: Mapped["SkillConcept"] = relationship(
        "SkillConcept",
        back_populates="occupation_links",
    )
