import dataclasses
import io
from pathlib import Path
import pytest
import pypdf
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    TextStringObject,
)

from app.models.resume import ArtifactFormat
from app.services.pdf_validation import (
    EmptyPDFError,
    EncryptedPDFError,
    InvalidPDFSignatureError,
    MalformedPDFError,
    PDFPageLimitExceededError,
    PDFValidationError,
    UnsafePDFContentError,
    validate_pdf_file,
)


def _create_simple_pdf_bytes(page_count: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# 1. A neutral one-page PDF passes.
def test_valid_one_page_pdf(tmp_path):
    pdf_path = tmp_path / "valid.pdf"
    pdf_path.write_bytes(_create_simple_pdf_bytes(1))

    result = validate_pdf_file(pdf_path, max_pages=5)
    assert result.detected_format == ArtifactFormat.pdf
    assert result.page_count == 1


# 2. A PDF at exactly max_resume_pages passes.
def test_valid_max_pages_pdf(tmp_path):
    pdf_path = tmp_path / "exact_max.pdf"
    pdf_path.write_bytes(_create_simple_pdf_bytes(5))

    result = validate_pdf_file(pdf_path, max_pages=5)
    assert result.detected_format == ArtifactFormat.pdf
    assert result.page_count == 5


# 3. A PDF above the configured page limit fails.
def test_exceed_page_limit_pdf(tmp_path):
    pdf_path = tmp_path / "over_limit.pdf"
    pdf_path.write_bytes(_create_simple_pdf_bytes(6))

    with pytest.raises(PDFPageLimitExceededError) as exc_info:
        validate_pdf_file(pdf_path, max_pages=5)
    assert exc_info.value.code == "PDF_PAGE_LIMIT_EXCEEDED"
    assert exc_info.value.status_code == 422


# 4. A zero-page PDF fails.
def test_zero_page_pdf(tmp_path):
    writer = PdfWriter()
    buf = io.BytesIO()
    writer.write(buf)
    pdf_path = tmp_path / "zero_page.pdf"
    pdf_path.write_bytes(buf.getvalue())

    with pytest.raises((EmptyPDFError, MalformedPDFError)) as exc_info:
        validate_pdf_file(pdf_path, max_pages=5)
    assert exc_info.value.status_code == 422


# 5. A file with a .pdf claim but missing %PDF- fails.
def test_invalid_signature_pdf(tmp_path):
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"NOT_A_PDF_HEADER %PDF-1.4 inside")

    with pytest.raises(InvalidPDFSignatureError) as exc_info:
        validate_pdf_file(pdf_path, max_pages=5)
    assert exc_info.value.code == "INVALID_PDF_SIGNATURE"
    assert exc_info.value.status_code == 415


# 6. A header-only or truncated PDF fails as malformed.
def test_truncated_pdf(tmp_path):
    pdf_path = tmp_path / "truncated.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    with pytest.raises(MalformedPDFError) as exc_info:
        validate_pdf_file(pdf_path, max_pages=5)
    assert exc_info.value.code == "MALFORMED_PDF"
    assert exc_info.value.status_code == 422


# 7. An encrypted PDF fails.
def test_encrypted_pdf(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("secret_password")
    buf = io.BytesIO()
    writer.write(buf)

    pdf_path = tmp_path / "encrypted.pdf"
    pdf_path.write_bytes(buf.getvalue())

    with pytest.raises(EncryptedPDFError) as exc_info:
        validate_pdf_file(pdf_path, max_pages=5)
    assert exc_info.value.code == "ENCRYPTED_PDF"
    assert exc_info.value.status_code == 422


# 8. A JavaScript/OpenAction PDF fails.
def test_unsafe_open_action_javascript(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_js("app.alert('hello');")
    buf = io.BytesIO()
    writer.write(buf)

    pdf_path = tmp_path / "js.pdf"
    pdf_path.write_bytes(buf.getvalue())

    with pytest.raises(UnsafePDFContentError) as exc_info:
        validate_pdf_file(pdf_path, max_pages=5)
    assert exc_info.value.code == "UNSAFE_PDF_CONTENT"
    assert exc_info.value.status_code == 422


# 9. A PDF containing an embedded attachment fails.
def test_unsafe_embedded_file(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_attachment("sample.txt", b"attachment data")
    buf = io.BytesIO()
    writer.write(buf)

    pdf_path = tmp_path / "attachment.pdf"
    pdf_path.write_bytes(buf.getvalue())

    with pytest.raises(UnsafePDFContentError) as exc_info:
        validate_pdf_file(pdf_path, max_pages=5)
    assert exc_info.value.code == "UNSAFE_PDF_CONTENT"
    assert exc_info.value.status_code == 422


# 10. A PDF containing a normal URI link is not rejected solely for that link.
def test_safe_uri_link_annot(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_uri(
        page_number=0,
        uri="https://linkedin.com/in/example",
        rect=(10, 10, 50, 50),
    )
    buf = io.BytesIO()
    writer.write(buf)

    pdf_path = tmp_path / "safe_link.pdf"
    pdf_path.write_bytes(buf.getvalue())

    result = validate_pdf_file(pdf_path, max_pages=5)
    assert result.detected_format == ArtifactFormat.pdf
    assert result.page_count == 1


# 11. Validation does not return extracted text or metadata.
# 12. Raw parser exception messages are not included in public failures.
def test_validation_result_cleanliness_and_error_encapsulation(tmp_path):
    pdf_path = tmp_path / "clean.pdf"
    pdf_path.write_bytes(_create_simple_pdf_bytes(1))

    result = validate_pdf_file(pdf_path, max_pages=5)
    result_dict = dataclasses.asdict(result)
    assert set(result_dict.keys()) == {"detected_format", "page_count"}

    # Error code structure check
    err = MalformedPDFError()
    assert err.code == "MALFORMED_PDF"
    assert "pypdf" not in err.message.lower()
