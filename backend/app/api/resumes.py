import hashlib
import logging
import os
import shutil
import urllib.parse
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models.resume import (
    ArtifactFormat,
    ArtifactValidationStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ResumeArtifact,
)
from app.schemas.resume import ResumeUploadResponse
from app.services.pdf_validation import PDFValidationError, validate_pdf_file

logger = logging.getLogger("ai_hiring.api.resumes")

router = APIRouter(
    prefix="/api/v1/resumes",
    tags=["resumes"],
)

CHUNK_SIZE_BYTES = 1024 * 1024  # 1 MiB chunk size

ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _normalize_filename(raw_filename: Optional[str]) -> str:
    """Normalize and validate filename metadata without exposing paths."""
    if raw_filename is None or not raw_filename.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILENAME", "message": "Filename is required and cannot be empty."},
        )

    # Check for raw or URL-encoded control characters / NUL bytes
    decoded_name = urllib.parse.unquote(raw_filename)
    if any(ord(c) < 32 or ord(c) == 127 for c in raw_filename) or any(ord(c) < 32 or ord(c) == 127 for c in decoded_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILENAME", "message": "Filename contains invalid characters."},
        )

    # Extract basename handling both POSIX (/) and Windows (\) separators
    basename = raw_filename.replace("\\", "/").split("/")[-1].strip()

    if not basename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILENAME", "message": "Filename cannot be empty."},
        )

    if len(basename) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILENAME", "message": "Filename exceeds maximum length of 255 characters."},
        )

    return basename


def _validate_extension_and_mime(filename: str, content_type: Optional[str]) -> tuple[str, str]:
    """Preliminary extension and MIME validation returning (ext, declared_mime)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": "Only PDF (.pdf) and DOCX (.docx) files are supported.",
            },
        )

    # Normalize declared MIME type (strip parameters like charset=utf-8)
    declared_mime = (content_type or "").split(";")[0].strip().lower()
    expected_mime = ALLOWED_EXTENSIONS[ext]

    if declared_mime != expected_mime:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "FILE_TYPE_MISMATCH",
                "message": "Declared MIME type does not match the file extension.",
            },
        )

    return ext, declared_mime


def _ensure_directory(dir_path: Path) -> None:
    """Ensure directory exists with restricted permissions."""
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        os.chmod(dir_path, 0o700)
    except OSError as e:
        logger.error("Failed to prepare storage directory", extra={"error_type": type(e).__name__})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "INTAKE_UNAVAILABLE",
                "message": "Storage is currently unavailable.",
            },
        )


def _cleanup_file(file_path: Path) -> None:
    """Tolerantly remove a file if it exists."""
    try:
        if file_path.exists():
            file_path.unlink()
    except OSError as e:
        logger.warning("Failed to remove file during cleanup", extra={"error_type": type(e).__name__})


@router.post(
    "",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Resume Document",
    description=(
        "Accepts a PDF or DOCX file, performs preliminary intake checks, streams the file into "
        "intake storage, validates PDF structure, moves accepted files to quarantine, creates "
        "ResumeArtifact and ProcessingJob persistence records atomically, and queues the document."
    ),
)
async def upload_resume(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ResumeUploadResponse:
    # 1. Preliminary filename and MIME validation
    normalized_filename = _normalize_filename(file.filename)
    ext, declared_mime = _validate_extension_and_mime(normalized_filename, file.content_type)

    # 2. Storage preparation
    intake_dir = settings.get_intake_path()
    _ensure_directory(intake_dir)

    artifact_id = uuid4()
    job_id = uuid4()

    storage_filename = f"{artifact_id}.upload"
    destination_path = (intake_dir / storage_filename).resolve()

    # Verify containment within configured intake directory
    if not str(destination_path).startswith(str(intake_dir)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILENAME", "message": "Invalid storage path resolution."},
        )

    quarantine_key = f"resume_intake/{storage_filename}"
    max_bytes = settings.max_resume_upload_bytes
    total_bytes = 0
    sha256 = hashlib.sha256()

    # 3. Stream upload in chunks with bounded reads and hashing
    file_created = False
    try:
        try:
            # Open in exclusive creation mode 'xb'
            out_file = open(destination_path, "xb")
            file_created = True
        except FileExistsError:
            logger.error("Generated artifact storage file already exists", extra={"artifact_id": str(artifact_id)})
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "INTAKE_UNAVAILABLE", "message": "Intake storage conflict."},
            )
        except OSError as e:
            logger.error("Failed to open destination file", extra={"error_type": type(e).__name__})
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "INTAKE_UNAVAILABLE", "message": "Intake storage is unavailable."},
            )

        with out_file:
            while True:
                chunk = await file.read(CHUNK_SIZE_BYTES)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail={
                            "code": "FILE_TOO_LARGE",
                            "message": f"File exceeds maximum allowed size of {max_bytes} bytes.",
                        },
                    )

                sha256.update(chunk)
                out_file.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "EMPTY_FILE", "message": "Uploaded file is empty."},
            )

    except Exception:
        await file.close()
        if file_created:
            _cleanup_file(destination_path)
        raise

    await file.close()

    # 4. Format-specific validation & quarantine move
    detected_format: Optional[ArtifactFormat] = None
    validation_status = ArtifactValidationStatus.PENDING
    final_file_path = destination_path

    if ext == ".pdf":
        try:
            val_result = validate_pdf_file(destination_path, settings.max_resume_pages)
            detected_format = val_result.detected_format
            validation_status = ArtifactValidationStatus.VALIDATED

            # Quarantine directory setup
            quarantine_base = settings.get_quarantine_path()
            quarantine_pdf_dir = quarantine_base / "pdf"
            _ensure_directory(quarantine_pdf_dir)

            quarantine_filename = f"{artifact_id}.pdf"
            quarantine_dest = (quarantine_pdf_dir / quarantine_filename).resolve()

            # Verify containment
            if not str(quarantine_dest).startswith(str(quarantine_pdf_dir)):
                _cleanup_file(destination_path)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={"code": "INTAKE_UNAVAILABLE", "message": "Quarantine path containment error."},
                )

            # Move intake file to quarantine (prevent overwriting)
            if quarantine_dest.exists():
                _cleanup_file(destination_path)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={"code": "INTAKE_UNAVAILABLE", "message": "Quarantine destination conflict."},
                )

            try:
                shutil.move(destination_path, quarantine_dest)
                final_file_path = quarantine_dest
                quarantine_key = f"pdf/{quarantine_filename}"
            except OSError as e:
                _cleanup_file(destination_path)
                _cleanup_file(quarantine_dest)
                logger.error("Failed to move PDF to quarantine", extra={"artifact_id": str(artifact_id), "error_type": type(e).__name__})
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={"code": "INTAKE_UNAVAILABLE", "message": "Failed to move document to quarantine."},
                )

        except PDFValidationError as e:
            _cleanup_file(destination_path)
            raise HTTPException(
                status_code=e.status_code,
                detail={"code": e.code, "message": e.message},
            )
        except HTTPException:
            raise
        except Exception as e:
            _cleanup_file(destination_path)
            logger.error("Unexpected PDF validator failure", extra={"artifact_id": str(artifact_id), "error_type": type(e).__name__})
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "PDF_VALIDATION_UNAVAILABLE", "message": "PDF validation is currently unavailable."},
            )

    # 5. Atomic persistence of ResumeArtifact and ProcessingJob
    sha256_hex = sha256.hexdigest().lower()

    artifact = ResumeArtifact(
        artifact_id=artifact_id,
        original_filename=normalized_filename,
        declared_mime_type=declared_mime,
        detected_format=detected_format,
        size_bytes=total_bytes,
        sha256_hash=sha256_hex,
        validation_status=validation_status,
        quarantine_key=quarantine_key,
    )

    job = ProcessingJob(
        job_id=job_id,
        artifact_id=artifact_id,
        status=ProcessingJobStatus.QUEUED,
        attempt_count=0,
    )

    try:
        db.add(artifact)
        db.add(job)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        _cleanup_file(final_file_path)
        logger.error("Database commit failed for resume intake", extra={"artifact_id": str(artifact_id)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "INTAKE_UNAVAILABLE",
                "message": "Failed to persist resume intake record.",
            },
        )
    except Exception:
        db.rollback()
        _cleanup_file(final_file_path)
        raise

    # 6. Success response
    return ResumeUploadResponse(
        artifact_id=artifact_id,
        job_id=job_id,
        status=ProcessingJobStatus.QUEUED,
    )
