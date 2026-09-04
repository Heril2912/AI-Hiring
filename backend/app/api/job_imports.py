import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path as PathParam,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.api.auth import AuthenticatedContext, require_role
from app.database import get_db
from app.models.auth import UserRole
from app.models.job import (
    JobDescriptionImport,
    JobImportSourceType,
    JobImportStatus,
    JobLifecycleStatus,
    JobRequisition,
    JobVersion,
    JobVersionStatus,
)
from app.schemas.job import (
    JobImportAnalyzeResponse,
    JobImportAnalyzeTextRequest,
    JobImportApplyRequest,
    JobImportUpdateSuggestionRequest,
)
from app.services.job_description_parser import PARSER_VERSION, JobDescriptionParser
from app.services.job_document_extraction import (
    JobDocumentError,
    extract_text_from_document,
)

logger = logging.getLogger("ai_hiring.api.job_imports")

router = APIRouter(
    prefix="/api/v1/jobs/imports",
    tags=["job-imports"],
)

require_recruiter_or_admin = require_role({UserRole.RECRUITER, UserRole.ADMIN})


def _get_verified_job_and_version(
    db: Session,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    is_admin: bool,
) -> Tuple[JobRequisition, JobVersion]:
    stmt = (
        select(JobRequisition)
        .options(selectinload(JobRequisition.versions))
        .where(
            JobRequisition.job_id == job_id,
            JobRequisition.status == JobLifecycleStatus.ACTIVE,
        )
    )
    job = db.execute(stmt).scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job requisition not found."},
        )

    if not is_admin and job.created_by_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job requisition not found."},
        )

    latest_draft = next(
        (v for v in sorted(job.versions, key=lambda x: x.version_number, reverse=True) if v.version_status == JobVersionStatus.DRAFT),
        None,
    )
    if not latest_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_ACTIVE_DRAFT", "message": "Job does not have an editable draft version."},
        )

    return job, latest_draft


@router.post(
    "/analyze-text",
    response_model=JobImportAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze Pasted Job Description Text",
)
async def analyze_job_description_text(
    payload: JobImportAnalyzeTextRequest,
    job_id: Optional[uuid.UUID] = None,
    expected_revision: Optional[int] = None,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> JobImportAnalyzeResponse:
    job_version_id = None
    if job_id:
        _, draft_version = _get_verified_job_and_version(
            db=db,
            job_id=job_id,
            user_id=auth_ctx.user.user_id,
            is_admin=auth_ctx.user.role == UserRole.ADMIN,
        )
        job_version_id = draft_version.job_version_id
        if expected_revision is None:
            expected_revision = draft_version.revision

    # Parse JD text
    parser = JobDescriptionParser(db)
    parse_result = parser.parse(payload.text)

    session_record = JobDescriptionImport(
        session_id=uuid.uuid4(),
        job_id=job_id,
        job_version_id=job_version_id,
        expected_revision=expected_revision,
        created_by_user_id=auth_ctx.user.user_id,
        source_type=JobImportSourceType.PASTED_TEXT,
        source_filename=None,
        source_text=payload.text,
        parser_version=parse_result["parser_version"],
        taxonomy_version=parse_result["taxonomy_version"],
        status=JobImportStatus.PENDING_REVIEW,
        suggestions=parse_result["suggestions"],
    )
    db.add(session_record)
    db.commit()
    db.refresh(session_record)

    return JobImportAnalyzeResponse(
        session_id=session_record.session_id,
        job_id=session_record.job_id,
        job_version_id=session_record.job_version_id,
        expected_revision=session_record.expected_revision,
        source_type=session_record.source_type,
        source_filename=session_record.source_filename,
        source_text=session_record.source_text,
        parser_version=session_record.parser_version,
        taxonomy_version=session_record.taxonomy_version,
        status=session_record.status,
        suggestions=session_record.suggestions,
        warnings=parse_result.get("warnings", []),
        created_at=session_record.created_at,
        updated_at=session_record.updated_at,
    )


@router.post(
    "/analyze-file",
    response_model=JobImportAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze Uploaded Job Description File (.pdf, .docx)",
)
async def analyze_job_description_file(
    file: UploadFile = File(...),
    job_id: Optional[uuid.UUID] = Form(default=None),
    expected_revision: Optional[int] = Form(default=None),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> JobImportAnalyzeResponse:
    job_version_id = None
    if job_id:
        _, draft_version = _get_verified_job_and_version(
            db=db,
            job_id=job_id,
            user_id=auth_ctx.user.user_id,
            is_admin=auth_ctx.user.role == UserRole.ADMIN,
        )
        job_version_id = draft_version.job_version_id
        if expected_revision is None:
            expected_revision = draft_version.revision

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EMPTY_FILE", "message": "Uploaded file is empty."},
        )

    filename = file.filename or "uploaded_job_description"

    try:
        raw_text, detected_fmt = extract_text_from_document(file_bytes, filename)
    except JobDocumentError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.code, "message": e.message},
        )

    if len(raw_text.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INSUFFICIENT_EXTRACTED_TEXT",
                "message": "Extracted text is too short or empty. Please paste the job description manually.",
            },
        )

    source_type = JobImportSourceType.PDF if detected_fmt == "PDF" else JobImportSourceType.DOCX

    parser = JobDescriptionParser(db)
    parse_result = parser.parse(raw_text)

    session_record = JobDescriptionImport(
        session_id=uuid.uuid4(),
        job_id=job_id,
        job_version_id=job_version_id,
        expected_revision=expected_revision,
        created_by_user_id=auth_ctx.user.user_id,
        source_type=source_type,
        source_filename=filename,
        source_text=raw_text,
        parser_version=parse_result["parser_version"],
        taxonomy_version=parse_result["taxonomy_version"],
        status=JobImportStatus.PENDING_REVIEW,
        suggestions=parse_result["suggestions"],
    )
    db.add(session_record)
    db.commit()
    db.refresh(session_record)

    return JobImportAnalyzeResponse(
        session_id=session_record.session_id,
        job_id=session_record.job_id,
        job_version_id=session_record.job_version_id,
        expected_revision=session_record.expected_revision,
        source_type=session_record.source_type,
        source_filename=session_record.source_filename,
        source_text=session_record.source_text,
        parser_version=session_record.parser_version,
        taxonomy_version=session_record.taxonomy_version,
        status=session_record.status,
        suggestions=session_record.suggestions,
        warnings=parse_result.get("warnings", []),
        created_at=session_record.created_at,
        updated_at=session_record.updated_at,
    )


@router.get(
    "/{session_id}",
    response_model=JobImportAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Import Session Details and Suggestions",
)
async def get_import_session(
    session_id: uuid.UUID = PathParam(...),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> JobImportAnalyzeResponse:
    stmt = select(JobDescriptionImport).where(JobDescriptionImport.session_id == session_id)
    session_record = db.execute(stmt).scalar_one_or_none()
    if session_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IMPORT_SESSION_NOT_FOUND", "message": "Import session not found."},
        )

    if auth_ctx.user.role != UserRole.ADMIN and session_record.created_by_user_id != auth_ctx.user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IMPORT_SESSION_NOT_FOUND", "message": "Import session not found."},
        )

    return JobImportAnalyzeResponse(
        session_id=session_record.session_id,
        job_id=session_record.job_id,
        job_version_id=session_record.job_version_id,
        expected_revision=session_record.expected_revision,
        source_type=session_record.source_type,
        source_filename=session_record.source_filename,
        source_text=session_record.source_text,
        parser_version=session_record.parser_version,
        taxonomy_version=session_record.taxonomy_version,
        status=session_record.status,
        suggestions=session_record.suggestions,
        warnings=[],
        created_at=session_record.created_at,
        updated_at=session_record.updated_at,
    )


@router.patch(
    "/{session_id}/suggestions/{suggestion_id}",
    response_model=JobImportAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Update or Review a Single Suggestion",
)
async def update_suggestion(
    session_id: uuid.UUID = PathParam(...),
    suggestion_id: str = PathParam(...),
    payload: JobImportUpdateSuggestionRequest = ...,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> JobImportAnalyzeResponse:
    stmt = select(JobDescriptionImport).where(JobDescriptionImport.session_id == session_id)
    session_record = db.execute(stmt).scalar_one_or_none()
    if session_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IMPORT_SESSION_NOT_FOUND", "message": "Import session not found."},
        )

    if auth_ctx.user.role != UserRole.ADMIN and session_record.created_by_user_id != auth_ctx.user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IMPORT_SESSION_NOT_FOUND", "message": "Import session not found."},
        )

    found = False
    updated_suggestions = []
    for s in session_record.suggestions:
        if s.get("suggestion_id") == suggestion_id:
            found = True
            s["review_status"] = payload.review_status
            if payload.edited_value is not None:
                s["proposed_value"] = payload.edited_value
        updated_suggestions.append(s)

    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SUGGESTION_NOT_FOUND", "message": "Suggestion not found in session."},
        )

    session_record.suggestions = updated_suggestions
    flag_modified(session_record, "suggestions")
    db.commit()
    db.refresh(session_record)

    return JobImportAnalyzeResponse(
        session_id=session_record.session_id,
        job_id=session_record.job_id,
        job_version_id=session_record.job_version_id,
        expected_revision=session_record.expected_revision,
        source_type=session_record.source_type,
        source_filename=session_record.source_filename,
        source_text=session_record.source_text,
        parser_version=session_record.parser_version,
        taxonomy_version=session_record.taxonomy_version,
        status=session_record.status,
        suggestions=session_record.suggestions,
        warnings=[],
        created_at=session_record.created_at,
        updated_at=session_record.updated_at,
    )


@router.post(
    "/{session_id}/apply",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Apply Selected Suggestions to Draft",
)
async def apply_suggestions(
    session_id: uuid.UUID = PathParam(...),
    payload: JobImportApplyRequest = ...,
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    stmt = select(JobDescriptionImport).where(JobDescriptionImport.session_id == session_id)
    session_record = db.execute(stmt).scalar_one_or_none()
    if session_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IMPORT_SESSION_NOT_FOUND", "message": "Import session not found."},
        )

    if auth_ctx.user.role != UserRole.ADMIN and session_record.created_by_user_id != auth_ctx.user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IMPORT_SESSION_NOT_FOUND", "message": "Import session not found."},
        )

    # If linked to an existing job, verify optimistic concurrency
    if session_record.job_id:
        _, draft_version = _get_verified_job_and_version(
            db=db,
            job_id=session_record.job_id,
            user_id=auth_ctx.user.user_id,
            is_admin=auth_ctx.user.role == UserRole.ADMIN,
        )
        if payload.expected_revision is not None and draft_version.revision != payload.expected_revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "REVISION_CONFLICT",
                    "message": f"Job draft was modified (current revision {draft_version.revision}, expected {payload.expected_revision}). Please reload and review.",
                },
            )

    # Filter accepted suggestions
    accepted_set = set(payload.accepted_suggestion_ids)
    applied_items: List[Dict[str, Any]] = []

    for s in session_record.suggestions:
        s_id = s.get("suggestion_id")
        if s_id in accepted_set:
            val = payload.edited_suggestions.get(s_id, s.get("proposed_value")) if payload.edited_suggestions else s.get("proposed_value")
            applied_items.append({
                "target_field": s.get("target_field"),
                "value": val,
                "source_excerpt": s.get("source_excerpt"),
                "extraction_method": s.get("extraction_method"),
            })

    session_record.status = JobImportStatus.APPLIED
    db.commit()

    return {
        "status": "APPLIED",
        "sessionId": str(session_record.session_id),
        "appliedCount": len(applied_items),
        "appliedItems": applied_items,
    }


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Discard Import Session",
)
async def discard_import_session(
    session_id: uuid.UUID = PathParam(...),
    auth_ctx: AuthenticatedContext = Depends(require_recruiter_or_admin),
    db: Session = Depends(get_db),
) -> None:
    stmt = select(JobDescriptionImport).where(JobDescriptionImport.session_id == session_id)
    session_record = db.execute(stmt).scalar_one_or_none()
    if session_record is None:
        return

    if auth_ctx.user.role != UserRole.ADMIN and session_record.created_by_user_id != auth_ctx.user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IMPORT_SESSION_NOT_FOUND", "message": "Import session not found."},
        )

    session_record.status = JobImportStatus.DISCARDED
    db.commit()
