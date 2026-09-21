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


class ATSAdapterType(str, enum.Enum):
    MOCK = "MOCK"
    CSV = "CSV"
    JSON = "JSON"
    LOCAL_FOLDER_DEMO = "LOCAL_FOLDER_DEMO"


class ATSHealthStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class ATSObjectType(str, enum.Enum):
    JOB = "JOB"
    CANDIDATE = "CANDIDATE"
    ATTACHMENT = "ATTACHMENT"


class ATSImportRunType(str, enum.Enum):
    MOCK = "MOCK"
    CSV = "CSV"
    JSON = "JSON"
    LOCAL_FOLDER_DEMO = "LOCAL_FOLDER_DEMO"


class ATSImportStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


class ATSItemResultStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    DUPLICATE = "DUPLICATE"
    CHANGED = "CHANGED"
    FAILED = "FAILED"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class ATSExportStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ATSReconciliationStatus(str, enum.Enum):
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"


class ATSConnectionRecord(Base):
    __tablename__ = "ats_connections"
    __table_args__ = (
        CheckConstraint(
            "adapter_type IN ('MOCK', 'CSV', 'JSON', 'LOCAL_FOLDER_DEMO')",
            name="ck_ats_connections_adapter_type",
        ),
        CheckConstraint(
            "health_status IN ('HEALTHY', 'DEGRADED', 'UNHEALTHY', 'UNKNOWN')",
            name="ck_ats_connections_health_status",
        ),
        Index("ix_ats_connections_org_id", "organization_id"),
        Index("ix_ats_connections_adapter_type", "adapter_type"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    adapter_type: Mapped[ATSAdapterType] = mapped_column(
        Enum(
            ATSAdapterType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_connections_adapter_type_enum",
        ),
        nullable=False,
    )
    tenant_label: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    scopes: Mapped[List[str]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    health_status: Mapped[ATSHealthStatus] = mapped_column(
        Enum(
            ATSHealthStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_connections_health_status_enum",
        ),
        nullable=False,
        default=ATSHealthStatus.UNKNOWN,
        server_default=text("'UNKNOWN'"),
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    secret_ref: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    encrypted_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON_TYPE,
        nullable=True,
    )
    kill_switch_active: Mapped[bool] = mapped_column(
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ATSExternalJobRecord(Base):
    __tablename__ = "ats_external_jobs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connection_id",
            "external_id",
            name="uq_ats_external_jobs_conn_ext_id",
        ),
        Index("ix_ats_external_jobs_org_conn", "organization_id", "connection_id"),
    )

    external_job_pk: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    department: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(
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


class ATSExternalCandidateRecord(Base):
    __tablename__ = "ats_external_candidates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connection_id",
            "external_candidate_id",
            name="uq_ats_external_candidates_conn_ext_id",
        ),
        Index("ix_ats_external_candidates_org_conn", "organization_id", "connection_id"),
    )

    external_candidate_pk: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    external_candidate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    external_application_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    external_job_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    stage: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(
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


class ATSExternalAttachmentRecord(Base):
    __tablename__ = "ats_external_attachments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connection_id",
            "external_attachment_id",
            name="uq_ats_external_attachments_conn_ext_id",
        ),
        Index("ix_ats_external_attachments_org_conn", "organization_id", "connection_id"),
    )

    external_attachment_pk: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    external_candidate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    external_attachment_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    download_url: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(
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


class ATSObjectMappingRecord(Base):
    __tablename__ = "ats_object_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connection_id",
            "object_type",
            "external_id",
            name="uq_ats_object_mappings_unique",
        ),
        Index("ix_ats_object_mappings_internal_id", "internal_id"),
        Index("ix_ats_object_mappings_org_conn", "organization_id", "connection_id"),
    )

    mapping_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    object_type: Mapped[ATSObjectType] = mapped_column(
        Enum(
            ATSObjectType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_object_mappings_object_type_enum",
        ),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    internal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    canonical_content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ATSImportRunRecord(Base):
    __tablename__ = "ats_import_runs"
    __table_args__ = (
        Index("ix_ats_import_runs_org_conn", "organization_id", "connection_id"),
        Index("ix_ats_import_runs_status", "status"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    run_type: Mapped[ATSImportRunType] = mapped_column(
        Enum(
            ATSImportRunType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_import_runs_run_type_enum",
        ),
        nullable=False,
    )
    is_dry_run: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    status: Mapped[ATSImportStatus] = mapped_column(
        Enum(
            ATSImportStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_import_runs_status_enum",
        ),
        nullable=False,
        default=ATSImportStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    total_jobs_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_candidates_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_attachments_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    successful_items_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    failed_items_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    duplicate_items_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    changed_items_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    summary_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    items: Mapped[List["ATSImportItemResultRecord"]] = relationship(
        "ATSImportItemResultRecord",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ATSImportItemResultRecord(Base):
    __tablename__ = "ats_import_item_results"
    __table_args__ = (
        Index("ix_ats_import_item_results_run_id", "run_id"),
        Index("ix_ats_import_item_results_org_id", "organization_id"),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_import_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    item_type: Mapped[ATSObjectType] = mapped_column(
        Enum(
            ATSObjectType,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_import_item_results_item_type_enum",
        ),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[ATSItemResultStatus] = mapped_column(
        Enum(
            ATSItemResultStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_import_item_results_status_enum",
        ),
        nullable=False,
    )
    safe_error_message: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    internal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    run: Mapped["ATSImportRunRecord"] = relationship(
        "ATSImportRunRecord",
        back_populates="items",
    )


class ATSSyncCheckpointRecord(Base):
    __tablename__ = "ats_sync_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connection_id",
            "entity_type",
            name="uq_ats_sync_checkpoints_conn_entity",
        ),
    )

    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    cursor_token: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    last_synced_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="HEALTHY",
        server_default=text("'HEALTHY'"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ATSExportReceiptRecord(Base):
    __tablename__ = "ats_export_receipts"
    __table_args__ = (
        Index("ix_ats_export_receipts_org_conn", "organization_id", "connection_id"),
        Index("ix_ats_export_receipts_candidate", "internal_candidate_id"),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    internal_candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    external_candidate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    preview_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    destination: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    exported_note_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[ATSExportStatus] = mapped_column(
        Enum(
            ATSExportStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_export_receipts_status_enum",
        ),
        nullable=False,
    )
    response_receipt: Mapped[Dict[str, Any]] = mapped_column(
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


class ATSReconciliationRecord(Base):
    __tablename__ = "ats_reconciliation_records"
    __table_args__ = (
        Index("ix_ats_reconciliation_records_org_conn", "organization_id", "connection_id"),
    )

    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_connections.connection_id", ondelete="CASCADE"),
        nullable=False,
    )
    export_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ats_export_receipts.receipt_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ATSReconciliationStatus] = mapped_column(
        Enum(
            ATSReconciliationStatus,
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
            name="ck_ats_reconciliation_records_status_enum",
        ),
        nullable=False,
        default=ATSReconciliationStatus.PENDING,
        server_default=text("'PENDING'"),
    )
    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
