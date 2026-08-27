import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.resume import ResumeArtifact


class BlockType(str, enum.Enum):
    PARAGRAPH = "PARAGRAPH"
    HEADING = "HEADING"
    LIST_ITEM = "LIST_ITEM"
    TABLE_CELL = "TABLE_CELL"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    UNKNOWN = "UNKNOWN"


class ExtractionMethod(str, enum.Enum):
    PDF_TEXT = "PDF_TEXT"
    DOCX_TEXT = "DOCX_TEXT"
    OCR = "OCR"


class ResumeExtraction(Base):
    __tablename__ = "resume_extractions"
    __table_args__ = (
        UniqueConstraint("artifact_id", name="uq_resume_extractions_artifact_id"),
        CheckConstraint(
            "length(trim(extractor_version)) > 0",
            name="ck_resume_extractions_extractor_version_not_empty",
        ),
    )

    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "resume_artifacts.artifact_id",
            ondelete="CASCADE",
            name="fk_resume_extractions_artifact_id_resume_artifacts",
        ),
        nullable=False,
    )
    extractor_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    artifact: Mapped["ResumeArtifact"] = relationship(
        "ResumeArtifact",
        back_populates="extraction",
    )
    blocks: Mapped[List["ExtractionBlock"]] = relationship(
        "ExtractionBlock",
        back_populates="extraction",
        order_by="ExtractionBlock.sequence_index",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ExtractionBlock(Base):
    __tablename__ = "extraction_blocks"
    __table_args__ = (
        UniqueConstraint(
            "extraction_id",
            "sequence_index",
            name="uq_extraction_blocks_extraction_id_sequence_index",
        ),
        CheckConstraint(
            "sequence_index >= 0",
            name="ck_extraction_blocks_sequence_index_non_negative",
        ),
        CheckConstraint(
            "page_number IS NULL OR page_number >= 1",
            name="ck_extraction_blocks_page_number_positive",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_extraction_blocks_confidence_range",
        ),
        Index("ix_extraction_blocks_extraction_id", "extraction_id"),
    )

    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "resume_extractions.extraction_id",
            ondelete="CASCADE",
            name="fk_extraction_blocks_extraction_id_resume_extractions",
        ),
        nullable=False,
    )
    sequence_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    structural_location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    block_type: Mapped[BlockType] = mapped_column(
        Enum(
            BlockType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_extraction_blocks_block_type",
        ),
        nullable=False,
    )
    raw_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    normalized_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(
            ExtractionMethod,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_extraction_blocks_extraction_method",
        ),
        nullable=False,
    )
    confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    extraction: Mapped["ResumeExtraction"] = relationship(
        "ResumeExtraction",
        back_populates="blocks",
    )
