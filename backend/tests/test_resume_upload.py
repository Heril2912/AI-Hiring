import hashlib
import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, get_settings
from app.database import get_db
from app.main import app
from app.models.resume import (
    ArtifactFormat,
    ArtifactValidationStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ResumeArtifact,
)
from app.schemas.resume import ResumeUploadResponse


def _create_valid_pdf_bytes(page_count: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class MockDBSession:
    def __init__(self, should_fail_commit: bool = False):
        self.added_records = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.should_fail_commit = should_fail_commit

    def add(self, instance):
        self.added_records.append(instance)

    def commit(self):
        if self.should_fail_commit:
            raise SQLAlchemyError("Simulated database failure")
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def mock_db_session():
    return MockDBSession()


@pytest.fixture
def test_client(tmp_path, mock_db_session):
    intake_dir = tmp_path / "intake"
    quarantine_dir = tmp_path / "quarantine"

    test_settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test_db",
        max_resume_upload_bytes=1024 * 1024,  # 1 MiB for tests
        max_resume_pages=5,
        resume_intake_directory=str(intake_dir),
        resume_quarantine_directory=str(quarantine_dir),
    )

    def override_get_settings():
        return test_settings

    def override_get_db():
        try:
            yield mock_db_session
        finally:
            mock_db_session.close()

    app.dependency_overrides[get_settings] = override_get_settings
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    yield client, intake_dir, quarantine_dir, mock_db_session, test_settings

    app.dependency_overrides.clear()


# 1. A small .pdf upload with application/pdf returns 202.
# 13. A valid PDF returns 202.
# 14. Its artifact has detected_format PDF.
# 15. Its validation status is VALIDATED.
# 16. Its job remains QUEUED.
# 17. The intake file was moved to quarantine/pdf.
# 18. The database key is relative and opaque.
# 19. The physical name does not contain the original filename.
# 20. No intake copy remains after success.
def test_upload_pdf_success_and_quarantine(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    content = _create_valid_pdf_bytes(1)
    expected_hash = hashlib.sha256(content).hexdigest().lower()
    orig_filename = "candidate_resume_confidential.pdf"

    response = client.post(
        "/api/v1/resumes",
        files={"file": (orig_filename, io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 202
    data = response.json()
    assert "artifactId" in data
    assert "jobId" in data
    assert data["status"] == "QUEUED"

    art_id_str = data["artifactId"]
    job_id_str = data["jobId"]

    # Intake directory should have no lingering file
    if intake_dir.exists():
        assert len(list(intake_dir.iterdir())) == 0

    # Quarantine directory should contain the moved file
    quarantine_pdf_dir = quarantine_dir / "pdf"
    assert quarantine_pdf_dir.exists()
    quarantined_files = list(quarantine_pdf_dir.iterdir())
    assert len(quarantined_files) == 1
    quarantined_file = quarantined_files[0]

    assert quarantined_file.name == f"{art_id_str}.pdf"
    assert orig_filename not in quarantined_file.name
    assert quarantined_file.read_bytes() == content

    # Database records verification
    assert len(db_session.added_records) == 2
    artifact = next(r for r in db_session.added_records if isinstance(r, ResumeArtifact))
    job = next(r for r in db_session.added_records if isinstance(r, ProcessingJob))

    assert str(artifact.artifact_id) == art_id_str
    assert artifact.original_filename == orig_filename
    assert artifact.declared_mime_type == "application/pdf"
    assert artifact.detected_format == ArtifactFormat.pdf
    assert artifact.validation_status == ArtifactValidationStatus.VALIDATED
    assert artifact.size_bytes == len(content)
    assert artifact.sha256_hash == expected_hash
    assert artifact.quarantine_key == f"pdf/{art_id_str}.pdf"

    assert str(job.job_id) == job_id_str
    assert str(job.artifact_id) == art_id_str
    assert job.status == ProcessingJobStatus.QUEUED
    assert job.attempt_count == 0

    assert db_session.committed is True
    assert db_session.closed is True


# 2. A small .docx upload with the official DOCX MIME returns 202.
# 29. Existing DOCX intake tests remain unchanged.
def test_upload_docx_success(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    content = b"PK\x03\x04 test generic docx bytes"
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    orig_name = "candidate_doc.docx"

    response = client.post(
        "/api/v1/resumes",
        files={"file": (orig_name, io.BytesIO(content), docx_mime)},
    )

    assert response.status_code == 202
    data = response.json()
    assert "artifactId" in data
    assert "jobId" in data
    assert data["status"] == "QUEUED"

    art_id_str = data["artifactId"]
    # DOCX stays in intake as pending in this phase
    saved_files = list(intake_dir.iterdir())
    assert len(saved_files) == 1
    assert saved_files[0].name == f"{art_id_str}.upload"

    artifact = next(r for r in db_session.added_records if isinstance(r, ResumeArtifact))
    assert artifact.detected_format is None
    assert artifact.validation_status == ArtifactValidationStatus.PENDING
    assert artifact.quarantine_key == f"resume_intake/{art_id_str}.upload"


# 3. Successful JSON contains only artifactId, jobId and status.
# 4. status equals QUEUED.
def test_response_payload_contract(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    content = _create_valid_pdf_bytes(1)

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("sample.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 202
    data = response.json()
    assert set(data.keys()) == {"artifactId", "jobId", "status"}
    assert data["status"] == "QUEUED"
    uuid.UUID(data["artifactId"])
    uuid.UUID(data["jobId"])


# 12. Unsupported extension returns 415.
def test_unsupported_extension_returns_415(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    content = b"plain text resume"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("resume.txt", io.BytesIO(content), "text/plain")},
    )

    assert response.status_code == 415
    detail = response.json().get("detail", {})
    assert detail.get("code") == "UNSUPPORTED_FILE_TYPE"
    if intake_dir.exists():
        assert len(list(intake_dir.iterdir())) == 0


# 13. Extension/MIME mismatch returns 415.
def test_extension_mime_mismatch_returns_415(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    content = _create_valid_pdf_bytes(1)

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", io.BytesIO(content), "text/html")},
    )

    assert response.status_code == 415
    detail = response.json().get("detail", {})
    assert detail.get("code") == "FILE_TYPE_MISMATCH"
    if intake_dir.exists():
        assert len(list(intake_dir.iterdir())) == 0


# 14. Empty file returns 400.
def test_empty_file_returns_400(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    content = b""

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("empty_resume.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 400
    detail = response.json().get("detail", {})
    assert detail.get("code") == "EMPTY_FILE"
    if intake_dir.exists():
        assert len(list(intake_dir.iterdir())) == 0


# 15. Oversized upload returns 413.
# 16. Oversized partial file is deleted.
def test_oversized_file_returns_413_and_cleans_up(test_client):
    client, intake_dir, quarantine_dir, db_session, test_settings = test_client
    oversized_content = b"0" * (1024 * 1024 + 512 * 1024)

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("big_resume.pdf", io.BytesIO(oversized_content), "application/pdf")},
    )

    assert response.status_code == 413
    detail = response.json().get("detail", {})
    assert detail.get("code") == "FILE_TOO_LARGE"
    if intake_dir.exists():
        assert list(intake_dir.iterdir()) == []
    assert len(db_session.added_records) == 0


# 21. Invalid-signature PDF returns 415.
# 26. Every rejected PDF leaves no intake/quarantine file.
# 27. Every rejected PDF creates no artifact or job.
def test_invalid_signature_pdf_returns_415(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    fake_content = b"NOT_A_PDF_BUT_CLAIMING_IT"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("fake.pdf", io.BytesIO(fake_content), "application/pdf")},
    )

    assert response.status_code == 415
    detail = response.json().get("detail", {})
    assert detail.get("code") == "INVALID_PDF_SIGNATURE"
    if intake_dir.exists():
        assert list(intake_dir.iterdir()) == []
    if quarantine_dir.exists():
        assert list(quarantine_dir.rglob("*.*")) == []
    assert len(db_session.added_records) == 0


# 22. Malformed PDF returns 422.
def test_malformed_pdf_returns_422(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    truncated_content = b"%PDF-1.4 header without trailer"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("malformed.pdf", io.BytesIO(truncated_content), "application/pdf")},
    )

    assert response.status_code == 422
    detail = response.json().get("detail", {})
    assert detail.get("code") == "MALFORMED_PDF"
    if intake_dir.exists():
        assert list(intake_dir.iterdir()) == []
    if quarantine_dir.exists():
        assert list(quarantine_dir.rglob("*.*")) == []
    assert len(db_session.added_records) == 0


# 23. Encrypted PDF returns 422.
def test_encrypted_pdf_returns_422(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("mypassword")
    buf = io.BytesIO()
    writer.write(buf)

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("locked.pdf", io.BytesIO(buf.getvalue()), "application/pdf")},
    )

    assert response.status_code == 422
    detail = response.json().get("detail", {})
    assert detail.get("code") == "ENCRYPTED_PDF"
    if intake_dir.exists():
        assert list(intake_dir.iterdir()) == []
    if quarantine_dir.exists():
        assert list(quarantine_dir.rglob("*.*")) == []
    assert len(db_session.added_records) == 0


# 24. Over-page-limit PDF returns 422.
def test_over_page_limit_pdf_returns_422(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    content = _create_valid_pdf_bytes(6)  # limit is 5

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("too_long.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 422
    detail = response.json().get("detail", {})
    assert detail.get("code") == "PDF_PAGE_LIMIT_EXCEEDED"
    if intake_dir.exists():
        assert list(intake_dir.iterdir()) == []
    if quarantine_dir.exists():
        assert list(quarantine_dir.rglob("*.*")) == []
    assert len(db_session.added_records) == 0


# 25. Unsafe-content PDF returns 422.
def test_unsafe_content_pdf_returns_422(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_js("app.alert('evil');")
    buf = io.BytesIO()
    writer.write(buf)

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("unsafe.pdf", io.BytesIO(buf.getvalue()), "application/pdf")},
    )

    assert response.status_code == 422
    detail = response.json().get("detail", {})
    assert detail.get("code") == "UNSAFE_PDF_CONTENT"
    if intake_dir.exists():
        assert list(intake_dir.iterdir()) == []
    if quarantine_dir.exists():
        assert list(quarantine_dir.rglob("*.*")) == []
    assert len(db_session.added_records) == 0


# 17. A traversal-style filename cannot escape tmp_path.
def test_traversal_filename_normalized_safely(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    content = _create_valid_pdf_bytes(1)

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("../../../../etc/passwd.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 202
    quarantine_pdf_dir = quarantine_dir / "pdf"
    saved_files = list(quarantine_pdf_dir.iterdir())
    assert len(saved_files) == 1
    assert saved_files[0].parent == quarantine_pdf_dir
    artifact = next(r for r in db_session.added_records if isinstance(r, ResumeArtifact))
    assert artifact.original_filename == "passwd.pdf"


# 28. Database failure after quarantine deletes the quarantined file.
def test_db_failure_deletes_quarantined_file(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    db_session.should_fail_commit = True
    content = _create_valid_pdf_bytes(1)

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 503
    detail = response.json().get("detail", {})
    assert detail.get("code") == "INTAKE_UNAVAILABLE"
    assert db_session.rolled_back is True
    # Ensure both intake and quarantine are clean
    if intake_dir.exists():
        assert list(intake_dir.iterdir()) == []
    if quarantine_dir.exists():
        assert list(quarantine_dir.rglob("*.*")) == []


# 20. Error responses do not contain paths or submitted byte content.
def test_error_responses_safe(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client
    secret_bytes = b"SECRET_INTERNAL_INFO"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("bad_type.exe", io.BytesIO(secret_bytes), "application/octet-stream")},
    )

    body_str = response.text
    assert str(intake_dir) not in body_str
    assert str(quarantine_dir) not in body_str
    assert "SECRET_INTERNAL_INFO" not in body_str


# Invalid filenames testing
def test_invalid_filenames(test_client):
    client, intake_dir, quarantine_dir, db_session, _ = test_client

    # Whitespace only
    resp = client.post(
        "/api/v1/resumes",
        files={"file": ("   ", io.BytesIO(_create_valid_pdf_bytes(1)), "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_FILENAME"

    # Control chars
    resp = client.post(
        "/api/v1/resumes",
        files={"file": ("bad\x00name.pdf", io.BytesIO(_create_valid_pdf_bytes(1)), "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_FILENAME"
