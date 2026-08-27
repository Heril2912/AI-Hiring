import dataclasses
import enum
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Set
import pypdf
from pypdf.errors import EmptyFileError, PdfReadError, PyPdfError

from app.config import Settings
from app.models.extraction import BlockType, ExtractionMethod
from app.models.resume import ArtifactFormat, ArtifactValidationStatus, ResumeArtifact
from app.schemas.extraction import ExtractionBlockData, ExtractionResult

logger = logging.getLogger("ai_hiring.services.pdf_text_extraction")

PDF_DIRECT_EXTRACTOR_VERSION = "pdf-direct-text-v1.0"


class PageClassification(str, enum.Enum):
    TEXT = "TEXT"
    MIXED = "MIXED"
    OCR_REQUIRED = "OCR_REQUIRED"
    EMPTY = "EMPTY"
    UNREADABLE = "UNREADABLE"


class PDFExtractionError(Exception):
    """Base exception for controlled PDF text extraction failures."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ArtifactIntegrityError(PDFExtractionError):
    def __init__(self, message: str = "Artifact integrity verification failed."):
        super().__init__(code="ARTIFACT_INTEGRITY_FAILED", message=message)


class PDFTextLimitExceededError(PDFExtractionError):
    def __init__(self, message: str = "Extracted PDF character limit exceeded."):
        super().__init__(code="PDF_TEXT_LIMIT_EXCEEDED", message=message)


class PDFExtractionFailedError(PDFExtractionError):
    def __init__(self, message: str = "Failed to extract text from PDF document."):
        super().__init__(code="PDF_EXTRACTION_FAILED", message=message)


class PDFDirectTextUnavailableError(PDFExtractionError):
    def __init__(self, message: str = "No direct text could be extracted from the document."):
        super().__init__(code="PDF_DIRECT_TEXT_UNAVAILABLE", message=message)


@dataclasses.dataclass(frozen=True)
class PageAssessment:
    page_number: int
    classification: PageClassification
    extracted_character_count: int
    printable_character_ratio: float
    replacement_character_count: int
    has_visual_content: bool
    requires_ocr: bool
    review_required: bool


@dataclasses.dataclass(frozen=True)
class PDFDirectExtractionResult:
    extractor_version: str
    blocks: List[ExtractionBlockData]
    pages: List[PageAssessment]
    requires_ocr: bool
    review_required: bool
    total_character_count: int
    extraction_result: Optional[ExtractionResult]


def _verify_and_resolve_quarantined_pdf(
    artifact: ResumeArtifact,
    settings: Settings,
) -> Path:
    """
    Verifies artifact preconditions and returns the resolved quarantined file path.

    Preconditions:
    1. ResumeArtifact is in VALIDATED state.
    2. detected_format is PDF.
    3. quarantine_key uses expected opaque PDF form ("pdf/{artifact_id}.pdf").
    4. resolved file remains inside the trusted PDF quarantine directory.
    5. file exists and is a regular file (not a symlink or directory).
    6. actual file size matches the stored artifact size_bytes.
    7. recalculated SHA-256 matches stored artifact sha256_hash.
    """
    if not isinstance(artifact, ResumeArtifact):
        raise ArtifactIntegrityError("Invalid resume artifact supplied.")

    if artifact.validation_status != ArtifactValidationStatus.VALIDATED:
        raise ArtifactIntegrityError("Resume artifact must be in VALIDATED state.")

    if artifact.detected_format != ArtifactFormat.pdf:
        raise ArtifactIntegrityError("Resume artifact format must be PDF.")

    if not artifact.quarantine_key or not isinstance(artifact.quarantine_key, str):
        raise ArtifactIntegrityError("Quarantine key is missing.")

    expected_key_suffix = f"{artifact.artifact_id}.pdf"
    if artifact.quarantine_key != f"pdf/{expected_key_suffix}":
        raise ArtifactIntegrityError("Quarantine key format mismatch.")

    quarantine_base = settings.get_quarantine_path()
    quarantine_pdf_dir = (quarantine_base / "pdf").resolve()

    # First check if the path itself is a symlink before resolving
    raw_target_path = quarantine_base / artifact.quarantine_key
    if raw_target_path.is_symlink():
        raise ArtifactIntegrityError("Quarantined file cannot be a symlink.")

    target_path = raw_target_path.resolve()

    # Verify containment within trusted PDF quarantine directory
    try:
        target_path.relative_to(quarantine_pdf_dir)
    except ValueError:
        raise ArtifactIntegrityError("Quarantine file path is outside trusted directory.")

    # Must exist, be a regular file, and NOT be a symlink
    if target_path.is_symlink() or not target_path.is_file():
        raise ArtifactIntegrityError("Quarantined file is missing, invalid, or a symlink.")

    # Size check
    try:
        actual_size = os.path.getsize(target_path)
    except OSError:
        raise ArtifactIntegrityError("Unable to inspect quarantined file size.")

    if artifact.size_bytes is not None and actual_size != artifact.size_bytes:
        raise ArtifactIntegrityError("Quarantined file size mismatch.")

    # SHA-256 recalculation check
    sha256 = hashlib.sha256()
    try:
        with open(target_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
    except OSError:
        raise ArtifactIntegrityError("Unable to read quarantined file for hash verification.")

    actual_hash = sha256.hexdigest().lower()
    if artifact.sha256_hash is not None and actual_hash != artifact.sha256_hash.lower():
        raise ArtifactIntegrityError("Quarantined file SHA-256 hash mismatch.")

    return target_path


def _resolve_obj(obj: Any) -> Any:
    """Safely dereference indirect PDF objects."""
    if obj is None:
        return None
    if hasattr(obj, "get_object"):
        try:
            return obj.get_object()
        except Exception:
            return obj
    return obj


def _detect_visual_content(page: pypdf.PageObject) -> bool:
    """
    Safely inspects whether a PDF page contains meaningful visual/image content.
    Checks /Resources -> /XObject dictionaries for /Subtype == /Image, or
    page.images property if accessible.
    """
    try:
        # First try pypdf's safe images collection if available
        if hasattr(page, "images") and len(page.images) > 0:
            return True
    except Exception:
        pass

    try:
        page_dict = _resolve_obj(page)
        if not isinstance(page_dict, dict):
            return False

        resources = _resolve_obj(page_dict.get("/Resources"))
        if not isinstance(resources, dict):
            return False

        xobjects = _resolve_obj(resources.get("/XObject"))
        if not isinstance(xobjects, dict):
            return False

        for _, xobj_ref in xobjects.items():
            xobj = _resolve_obj(xobj_ref)
            if isinstance(xobj, dict):
                subtype = _resolve_obj(xobj.get("/Subtype"))
                if str(subtype) == "/Image":
                    return True
    except Exception:
        pass

    return False


def _split_text_into_blocks(
    text: str,
    page_number: int,
    start_sequence_index: int,
) -> List[ExtractionBlockData]:
    """
    Splits page text into conservative paragraph-like blocks.
    - Normalizes line endings to \n.
    - Splits at blank-line boundaries (\n\s*\n+).
    - Preserves line breaks inside blocks.
    - Strips surrounding whitespace.
    - Discards empty whitespace-only chunks.
    - Uses PARAGRAPH block_type (or UNKNOWN if degenerate).
    - Sets normalized_text = raw_text (Phase 1C.5 will perform semantic normalization).
    """
    # Normalize \r\n and \r to \n
    normalized_newlines = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split by blank lines
    raw_chunks = normalized_newlines.split("\n\n")
    blocks: List[ExtractionBlockData] = []
    current_index = start_sequence_index

    for chunk in raw_chunks:
        cleaned = chunk.strip()
        if not cleaned:
            continue

        # Single paragraph block
        # normalized_text equals raw_text for Phase 1C.2; Phase 1C.5 will perform normalization.
        block = ExtractionBlockData(
            sequence_index=current_index,
            page_number=page_number,
            structural_location=None,
            block_type=BlockType.PARAGRAPH,
            raw_text=cleaned,
            normalized_text=cleaned,
            extraction_method=ExtractionMethod.PDF_TEXT,
            confidence=None,
            review_required=False,
        )
        blocks.append(block)
        current_index += 1

    return blocks


def extract_pdf_direct_text(
    artifact: ResumeArtifact,
    settings: Optional[Settings] = None,
) -> PDFDirectExtractionResult:
    """
    Bounded, direct-text PDF extractor for validated and quarantined PDF artifacts.

    Reads a trusted PDF page-by-page, produces ordered PDF_TEXT blocks, computes
    safe page-quality signals, and classifies each page (TEXT, MIXED, OCR_REQUIRED, EMPTY, UNREADABLE).
    """
    if settings is None:
        settings = Settings()

    # 1. Verify artifact preconditions & get trusted path
    quarantined_path = _verify_and_resolve_quarantined_pdf(artifact, settings)

    min_text_chars = settings.min_pdf_direct_text_chars
    max_chars = settings.max_pdf_extracted_chars

    # 2. Open PDF defensively with pypdf
    try:
        reader = pypdf.PdfReader(str(quarantined_path), strict=False)
        if reader.is_encrypted:
            raise PDFExtractionFailedError("Quarantined PDF is unexpectedly encrypted.")
        num_pages = len(reader.pages)
        if num_pages == 0:
            raise PDFExtractionFailedError("Quarantined PDF contains no pages.")
    except PDFExtractionError:
        raise
    except (EmptyFileError, PdfReadError, PyPdfError, ValueError, KeyError, EOFError, IndexError) as e:
        logger.warning(
            "Failed to open quarantined PDF with pypdf",
            extra={"artifact_id": str(artifact.artifact_id), "error_type": type(e).__name__},
        )
        raise PDFExtractionFailedError("Failed to open PDF document.") from e
    except Exception as e:
        logger.warning(
            "Unexpected error opening quarantined PDF",
            extra={"artifact_id": str(artifact.artifact_id), "error_type": type(e).__name__},
        )
        raise PDFExtractionFailedError("Unexpected failure opening PDF document.") from e

    all_blocks: List[ExtractionBlockData] = []
    page_assessments: List[PageAssessment] = []
    total_extracted_chars = 0
    any_page_requires_ocr = False
    any_page_review_required = False

    # 3. Process pages in original order
    for page_idx in range(num_pages):
        page_number = page_idx + 1

        try:
            page = reader.pages[page_idx]
            # Extract text using layout mode if supported, fallback to plain
            try:
                page_raw_text = page.extract_text(extraction_mode="layout") or ""
            except Exception:
                page_raw_text = page.extract_text() or ""
        except Exception as e:
            logger.warning(
                "Page extraction failed on page",
                extra={"artifact_id": str(artifact.artifact_id), "page_number": page_number, "error_type": type(e).__name__},
            )
            # Mark page as UNREADABLE and requires OCR / review
            page_assessments.append(
                PageAssessment(
                    page_number=page_number,
                    classification=PageClassification.UNREADABLE,
                    extracted_character_count=0,
                    printable_character_ratio=0.0,
                    replacement_character_count=0,
                    has_visual_content=True,
                    requires_ocr=True,
                    review_required=True,
                )
            )
            any_page_requires_ocr = True
            any_page_review_required = True
            continue

        # Compute safe metrics
        has_visual = _detect_visual_content(page)
        extracted_len = len(page_raw_text.strip())
        replacement_count = page_raw_text.count("\ufffd")

        total_chars_in_page = len(page_raw_text)
        if total_chars_in_page > 0:
            printable_count = sum(1 for c in page_raw_text if c.isprintable() or c in "\n\r\t")
            printable_ratio = round(printable_count / total_chars_in_page, 4)
        else:
            printable_ratio = 1.0

        # Check total character limit boundedly
        if total_extracted_chars + extracted_len > max_chars:
            logger.warning(
                "PDF extracted character limit exceeded",
                extra={"artifact_id": str(artifact.artifact_id), "max_chars": max_chars},
            )
            raise PDFTextLimitExceededError(f"PDF character limit of {max_chars} exceeded.")

        # Classify page
        page_review = False
        page_requires_ocr = False

        if extracted_len >= min_text_chars:
            # Significant direct text
            if replacement_count > 10 or printable_ratio < 0.85:
                # Poor quality direct text -> unreadable/corrupt font encoding
                classification = PageClassification.UNREADABLE
                page_requires_ocr = has_visual
                page_review = True
            elif has_visual:
                classification = PageClassification.MIXED
                page_requires_ocr = False
            else:
                classification = PageClassification.TEXT
                page_requires_ocr = False
        else:
            # Low or no direct text (< min_text_chars)
            if has_visual:
                classification = PageClassification.OCR_REQUIRED
                page_requires_ocr = True
            elif extracted_len > 0:
                # Some slight text, no visual
                classification = PageClassification.TEXT
                page_requires_ocr = False
                page_review = True  # Flag for review due to very low character count
            else:
                classification = PageClassification.EMPTY
                page_requires_ocr = False

        if page_requires_ocr:
            any_page_requires_ocr = True
        if page_review:
            any_page_review_required = True

        assessment = PageAssessment(
            page_number=page_number,
            classification=classification,
            extracted_character_count=extracted_len,
            printable_character_ratio=printable_ratio,
            replacement_character_count=replacement_count,
            has_visual_content=has_visual,
            requires_ocr=page_requires_ocr,
            review_required=page_review,
        )
        page_assessments.append(assessment)

        # Form blocks if readable text exists
        if extracted_len > 0 and classification in (PageClassification.TEXT, PageClassification.MIXED):
            page_blocks = _split_text_into_blocks(
                text=page_raw_text,
                page_number=page_number,
                start_sequence_index=len(all_blocks),
            )
            all_blocks.extend(page_blocks)
            total_extracted_chars += extracted_len

    # If all pages are EMPTY or no blocks extracted and no OCR required
    if not all_blocks and not any_page_requires_ocr:
        # Document contains only blank pages or unusable text without images
        logger.info(
            "PDF document contains no usable text or visual content",
            extra={"artifact_id": str(artifact.artifact_id)},
        )

    # If all blocks exist and NO OCR is required, construct shared ExtractionResult
    shared_extraction_result: Optional[ExtractionResult] = None
    if all_blocks and not any_page_requires_ocr:
        shared_extraction_result = ExtractionResult(
            extractor_version=PDF_DIRECT_EXTRACTOR_VERSION,
            review_required=any_page_review_required,
            blocks=all_blocks,
        )

    return PDFDirectExtractionResult(
        extractor_version=PDF_DIRECT_EXTRACTOR_VERSION,
        blocks=all_blocks,
        pages=page_assessments,
        requires_ocr=any_page_requires_ocr,
        review_required=any_page_review_required,
        total_character_count=total_extracted_chars,
        extraction_result=shared_extraction_result,
    )
