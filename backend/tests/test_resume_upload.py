import hashlib
import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, get_settings
from app.database import get_db
from app.main import app
from app.models.resume import (
    ArtifactValidationStatus,
    ProcessingJob,
    ProcessingJobStatus,
    ResumeArtifact,
)
from app.schemas.resume import ResumeUploadResponse


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

    test_settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test_db",
        max_resume_upload_bytes=1024 * 1024,  # 1 MiB for tests
        resume_intake_directory=str(intake_dir),
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
    yield client, intake_dir, mock_db_session, test_settings

    app.dependency_overrides.clear()


# 1. A small .pdf upload with application/pdf returns 202.
def test_upload_pdf_success(test_client):
    client, intake_dir, db_session, _ = test_client
    content = b"%PDF-1.4 test generic fixture bytes"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("test_resume.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 202
    data = response.json()
    assert "artifactId" in data
    assert "jobId" in data
    assert data["status"] == "QUEUED"


# 2. A small .docx upload with the official DOCX MIME returns 202.
def test_upload_docx_success(test_client):
    client, intake_dir, db_session, _ = test_client
    content = b"PK\x03\x04 test generic docx bytes"
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("candidate_doc.docx", io.BytesIO(content), docx_mime)},
    )

    assert response.status_code == 202
    data = response.json()
    assert "artifactId" in data
    assert "jobId" in data
    assert data["status"] == "QUEUED"


# 3. Successful JSON contains only artifactId, jobId and status.
# 4. status equals QUEUED.
def test_response_payload_contract(test_client):
    client, intake_dir, db_session, _ = test_client
    content = b"%PDF-1.4 sample stream data"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("sample.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 202
    data = response.json()
    assert set(data.keys()) == {"artifactId", "jobId", "status"}
    assert data["status"] == "QUEUED"
    # Ensure valid UUIDs
    uuid.UUID(data["artifactId"])
    uuid.UUID(data["jobId"])


# 5. Data is streamed into an opaque generated filename.
# 6. The saved filename does not contain the original filename.
# 7. Saved bytes equal the submitted generic fixture bytes.
# 8. The recorded SHA-256 matches those bytes.
# 9. detected_format remains null.
# 10. validation_status remains PENDING.
# 11. One artifact and one linked job are created.
def test_streaming_storage_and_persistence_records(test_client):
    client, intake_dir, db_session, _ = test_client
    content = b"%PDF-1.4 raw binary stream content for hash and size checks"
    expected_hash = hashlib.sha256(content).hexdigest().lower()
    orig_name = "john_doe_confidential_resume.pdf"

    response = client.post(
        "/api/v1/resumes",
        files={"file": (orig_name, io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 202
    data = response.json()
    art_id_str = data["artifactId"]
    job_id_str = data["jobId"]

    # Verify physical file storage
    saved_files = list(intake_dir.iterdir())
    assert len(saved_files) == 1
    saved_file = saved_files[0]

    assert saved_file.name == f"{art_id_str}.upload"
    assert orig_name not in saved_file.name
    assert ".pdf" not in saved_file.name
    assert saved_file.read_bytes() == content

    # Verify persistence records in database session
    assert len(db_session.added_records) == 2
    artifact = next(r for r in db_session.added_records if isinstance(r, ResumeArtifact))
    job = next(r for r in db_session.added_records if isinstance(r, ProcessingJob))

    assert str(artifact.artifact_id) == art_id_str
    assert artifact.original_filename == orig_name
    assert artifact.declared_mime_type == "application/pdf"
    assert artifact.detected_format is None
    assert artifact.size_bytes == len(content)
    assert artifact.sha256_hash == expected_hash
    assert artifact.validation_status == ArtifactValidationStatus.PENDING
    assert artifact.quarantine_key == f"resume_intake/{art_id_str}.upload"

    assert str(job.job_id) == job_id_str
    assert str(job.artifact_id) == art_id_str
    assert job.status == ProcessingJobStatus.QUEUED
    assert job.attempt_count == 0
    assert job.safe_error_code is None

    assert db_session.committed is True
    assert db_session.closed is True


# 12. Unsupported extension returns 415.
def test_unsupported_extension_returns_415(test_client):
    client, intake_dir, db_session, _ = test_client
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
    client, intake_dir, db_session, _ = test_client
    content = b"%PDF-1.4 file with fake MIME"

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
    client, intake_dir, db_session, _ = test_client
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
    client, intake_dir, db_session, test_settings = test_client
    # Limit is 1 MiB in test_settings, send 1.5 MiB
    oversized_content = b"0" * (1024 * 1024 + 512 * 1024)

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("big_resume.pdf", io.BytesIO(oversized_content), "application/pdf")},
    )

    assert response.status_code == 413
    detail = response.json().get("detail", {})
    assert detail.get("code") == "FILE_TOO_LARGE"
    # Ensure partial file was completely cleaned up
    assert list(intake_dir.iterdir()) == []
    assert len(db_session.added_records) == 0


# 17. A traversal-style filename cannot escape tmp_path.
def test_traversal_filename_normalized_safely(test_client):
    client, intake_dir, db_session, _ = test_client
    content = b"%PDF-1.4 safe content"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("../../../../etc/passwd.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 202
    saved_files = list(intake_dir.iterdir())
    assert len(saved_files) == 1
    # File is saved inside intake_dir with opaque UUID name
    assert saved_files[0].parent == intake_dir
    # DB record contains normalized basename
    artifact = next(r for r in db_session.added_records if isinstance(r, ResumeArtifact))
    assert artifact.original_filename == "passwd.pdf"


# 18. Database commit failure returns 503.
# 19. Database failure deletes the intake file.
def test_db_failure_returns_503_and_deletes_file(test_client):
    client, intake_dir, db_session, _ = test_client
    db_session.should_fail_commit = True
    content = b"%PDF-1.4 test db rollback"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", io.BytesIO(content), "application/pdf")},
    )

    assert response.status_code == 503
    detail = response.json().get("detail", {})
    assert detail.get("code") == "INTAKE_UNAVAILABLE"
    assert db_session.rolled_back is True
    # Ensure physical file is deleted
    assert list(intake_dir.iterdir()) == []


# 20. Error responses do not contain paths or submitted byte content.
def test_error_responses_safe(test_client):
    client, intake_dir, db_session, _ = test_client
    secret_bytes = b"SECRET_INTERNAL_INFO"

    response = client.post(
        "/api/v1/resumes",
        files={"file": ("bad_type.exe", io.BytesIO(secret_bytes), "application/octet-stream")},
    )

    body_str = response.text
    assert str(intake_dir) not in body_str
    assert "SECRET_INTERNAL_INFO" not in body_str


# Invalid filenames testing
def test_invalid_filenames(test_client):
    client, intake_dir, db_session, _ = test_client

    # Whitespace only
    resp = client.post(
        "/api/v1/resumes",
        files={"file": ("   ", io.BytesIO(b"%PDF-1.4 a"), "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_FILENAME"

    # Control chars
    resp = client.post(
        "/api/v1/resumes",
        files={"file": ("bad\x00name.pdf", io.BytesIO(b"%PDF-1.4 a"), "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_FILENAME"
