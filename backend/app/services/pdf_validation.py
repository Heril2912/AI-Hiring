import dataclasses
from pathlib import Path
from typing import Any, Optional, Set
import pypdf
from pypdf.errors import EmptyFileError, PdfReadError, PyPdfError

from app.models.resume import ArtifactFormat

DISALLOWED_ACTION_TYPES = {
    "/javascript",
    "/launch",
    "/submitform",
    "/importdata",
    "/gotor",
    "/gotoe",
    "/rendition",
}


class PDFValidationError(Exception):
    """Base exception for controlled PDF validation failures."""

    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class InvalidPDFSignatureError(PDFValidationError):
    def __init__(self, message: str = "Invalid PDF file signature."):
        super().__init__(code="INVALID_PDF_SIGNATURE", message=message, status_code=415)


class MalformedPDFError(PDFValidationError):
    def __init__(self, message: str = "Malformed or unreadable PDF document."):
        super().__init__(code="MALFORMED_PDF", message=message, status_code=422)


class EncryptedPDFError(PDFValidationError):
    def __init__(self, message: str = "Encrypted or password-protected PDF is not accepted."):
        super().__init__(code="ENCRYPTED_PDF", message=message, status_code=422)


class EmptyPDFError(PDFValidationError):
    def __init__(self, message: str = "PDF document contains no pages."):
        super().__init__(code="EMPTY_PDF", message=message, status_code=422)


class PDFPageLimitExceededError(PDFValidationError):
    def __init__(self, message: str = "PDF document exceeds allowed page limit."):
        super().__init__(code="PDF_PAGE_LIMIT_EXCEEDED", message=message, status_code=422)


class UnsafePDFContentError(PDFValidationError):
    def __init__(self, message: str = "PDF contains unsupported active or embedded content."):
        super().__init__(code="UNSAFE_PDF_CONTENT", message=message, status_code=422)


@dataclasses.dataclass(frozen=True)
class PDFValidationResult:
    detected_format: ArtifactFormat
    page_count: int


def _resolve_obj(obj: Any) -> Any:
    """Safely dereference indirect PDF objects without recursive loops."""
    if obj is None:
        return None
    if hasattr(obj, "get_object"):
        try:
            return obj.get_object()
        except Exception:
            return obj
    return obj


def _check_action_dict(raw_action: Any, visited: Set[int]) -> None:
    """Inspect an action dictionary for unsafe action types (/S)."""
    action_dict = _resolve_obj(raw_action)
    if not isinstance(action_dict, dict):
        return

    obj_id = id(action_dict)
    if obj_id in visited:
        return
    visited.add(obj_id)

    # Check action type /S
    s_val = _resolve_obj(action_dict.get("/S"))
    if s_val is not None:
        s_str = str(s_val).lower().strip()
        if s_str in DISALLOWED_ACTION_TYPES:
            raise UnsafePDFContentError()

    # If action has /Next sub-actions, inspect them boundedly
    next_action = _resolve_obj(action_dict.get("/Next"))
    if next_action is not None:
        if isinstance(next_action, list):
            for sub_act in next_action:
                _check_action_dict(sub_act, visited)
        elif isinstance(next_action, dict):
            _check_action_dict(next_action, visited)


def _inspect_active_and_embedded_content(reader: pypdf.PdfReader) -> None:
    """Inspect known document and page locations for active or embedded content."""
    visited_objects: Set[int] = set()

    try:
        trailer = reader.trailer
        if not trailer or not isinstance(trailer, dict):
            return

        root = _resolve_obj(trailer.get("/Root"))
        if root is None or not isinstance(root, dict):
            return

        # 1. Catalog /OpenAction
        if "/OpenAction" in root:
            open_action = _resolve_obj(root["/OpenAction"])
            if isinstance(open_action, dict):
                _check_action_dict(open_action, visited_objects)
            else:
                # Array or other OpenAction destination/action
                raise UnsafePDFContentError()

        # 2. Catalog /AA (Additional Actions)
        if "/AA" in root:
            raise UnsafePDFContentError()

        # 3. Catalog /Names (/JavaScript or /EmbeddedFiles)
        if "/Names" in root:
            names_dict = _resolve_obj(root["/Names"])
            if isinstance(names_dict, dict):
                if "/JavaScript" in names_dict or "/EmbeddedFiles" in names_dict:
                    raise UnsafePDFContentError()

        # 4. Catalog /AcroForm (XFA)
        if "/AcroForm" in root:
            acro_form = _resolve_obj(root["/AcroForm"])
            if isinstance(acro_form, dict) and "/XFA" in acro_form:
                raise UnsafePDFContentError()

        # 5. Inspect each page for /AA and /Annots actions
        for page in reader.pages:
            page_obj = _resolve_obj(page)
            if not isinstance(page_obj, dict):
                continue

            # Check Page /AA
            if "/AA" in page_obj:
                raise UnsafePDFContentError()

            # Check Page /Annots
            if "/Annots" in page_obj:
                annots = _resolve_obj(page_obj["/Annots"])
                if isinstance(annots, list):
                    for annot_ref in annots:
                        annot = _resolve_obj(annot_ref)
                        if not isinstance(annot, dict):
                            continue

                        # Check /A (Action)
                        if "/A" in annot:
                            action = _resolve_obj(annot["/A"])
                            _check_action_dict(action, visited_objects)

                        # Check /AA (Additional Actions)
                        if "/AA" in annot:
                            raise UnsafePDFContentError()

    except UnsafePDFContentError:
        raise
    except (PyPdfError, KeyError, ValueError, TypeError) as e:
        raise MalformedPDFError(f"Failed to inspect PDF catalog structure: {e}") from e


def validate_pdf_file(
    file_path: Path,
    max_pages: int,
) -> PDFValidationResult:
    """Validate PDF header signature, structure, encryption, page limits, and safety.

    Does not extract text, render pages, perform OCR, or modify the document.
    """
    # 1. Header signature check (%PDF-)
    try:
        with open(file_path, "rb") as f:
            header = f.read(5)
    except OSError as e:
        raise MalformedPDFError("Unable to read PDF file header.") from e

    if len(header) < 5 or header != b"%PDF-":
        raise InvalidPDFSignatureError()

    # 2. Strict PDF parsing with pypdf
    try:
        reader = pypdf.PdfReader(str(file_path), strict=True)
    except (EmptyFileError, PdfReadError, PyPdfError, ValueError, KeyError, EOFError, IndexError) as e:
        raise MalformedPDFError() from e
    except Exception as e:
        raise MalformedPDFError() from e

    # 3. Encryption check
    try:
        if reader.is_encrypted:
            raise EncryptedPDFError()
    except EncryptedPDFError:
        raise
    except Exception as e:
        raise MalformedPDFError() from e

    # 4. Page count and resolution
    try:
        page_count = len(reader.pages)
    except (PyPdfError, ValueError, KeyError, EOFError, IndexError) as e:
        raise MalformedPDFError() from e

    if page_count == 0:
        raise EmptyPDFError()

    if page_count > max_pages:
        raise PDFPageLimitExceededError(
            f"PDF exceeds maximum allowed page count of {max_pages} (found {page_count} pages)."
        )

    # 5. Resolve each page dictionary to confirm integrity
    try:
        for page in reader.pages:
            if page is None or not isinstance(page, dict):
                raise MalformedPDFError()
    except MalformedPDFError:
        raise
    except (PyPdfError, ValueError, KeyError, EOFError, IndexError) as e:
        raise MalformedPDFError() from e

    # 6. Active and embedded content inspection
    _inspect_active_and_embedded_content(reader)

    return PDFValidationResult(
        detected_format=ArtifactFormat.pdf,
        page_count=page_count,
    )
