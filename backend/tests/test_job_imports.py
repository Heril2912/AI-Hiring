import csv
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli.import_onet import import_onet_taxonomy
from app.database import get_db
from app.main import app
from app.models.auth import Base, UserRecord, UserRole
from app.models.job import (
    EmploymentType,
    JobDescriptionImport,
    JobImportSourceType,
    JobImportStatus,
    JobLifecycleStatus,
    JobRequirement,
    JobRequisition,
    JobVersion,
    JobVersionStatus,
    RequirementCategory,
    RequirementNecessity,
    RequirementOrigin,
    RequirementPriority,
    WorkplaceType,
)
from app.models.taxonomy import (
    OccupationConcept,
    SkillConcept,
    TaxonomySnapshot,
    TaxonomySnapshotState,
)
from app.services.security import canonicalize_email, hash_password


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, base_url="https://testserver")
    app.dependency_overrides.clear()


def _seed_user(
    db,
    email="recruiter.import@company.test",
    password="Password123!",
    role=UserRole.RECRUITER,
    is_active=True,
    must_change_password=False,
):
    encoded_hash = hash_password(password)
    user = UserRecord(
        user_id=uuid.uuid4(),
        email=canonicalize_email(email),
        display_name="Test Recruiter",
        password_hash=encoded_hash,
        role=role,
        is_active=is_active,
        must_change_password=must_change_password,
        failed_login_count=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login_user(client, email="recruiter.import@company.test", password="Password123!"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == status.HTTP_200_OK
    return resp.json()["csrfToken"], resp.json()["user"]


@pytest.fixture
def synthetic_taxonomy(tmp_path, test_db):
    d = tmp_path / "synthetic_onet_imports"
    d.mkdir()

    occ_rows = [
        ["O*NET-SOC Code", "Title", "Description"],
        ["15-1252.00", "Software Developers", "Develop software applications."],
    ]
    with open(d / "occupation_data.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(occ_rows)

    title_rows = [
        ["O*NET-SOC Code", "Title", "Job Title", "Short Title", "Source(s)"],
        ["15-1252.00", "Software Developers", "Full Stack Developer", "", "08"],
    ]
    with open(d / "job_titles.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(title_rows)

    skill_rows = [
        ["O*NET-SOC Code", "Title", "Workplace Example", "Element ID", "Element Name", "Hot Technology", "In Demand"],
        ["15-1252.00", "Software Developers", "Python", "2.E.1.a", "Programming language", "Y", "Y"],
        ["15-1252.00", "Software Developers", "PostgreSQL", "2.E.6.f", "Database", "Y", "N"],
        ["15-1252.00", "Software Developers", "Docker", "2.E.1.a", "DevOps", "Y", "Y"],
    ]
    with open(d / "software_skills.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(skill_rows)

    import_onet_taxonomy(source_dir=d, version="31.0", session=test_db)
    return d


# =========================================================================
# 1. Pasted Text Analysis & Extraction Tests
# =========================================================================

def test_pasted_text_analysis_success(client, test_db, synthetic_taxonomy):
    _seed_user(test_db, email="recruiter.jd@company.test", role=UserRole.RECRUITER)
    _login_user(client, email="recruiter.jd@company.test")

    jd_text = """Job Title: Senior Backend Developer
Department: Engineering
Location: San Francisco, CA
Employment Type: Full-Time
Workplace Type: Remote
Openings: 2

About the role
Build and scale cloud backend microservices for our core platform.

Responsibilities
- Design and develop scalable REST APIs.
- Maintain and optimize PostgreSQL database schemas.
- Collaborate with frontend engineers to integrate services.

Required qualifications
- Minimum 3 years of professional backend engineering experience.
- Strong proficiency in Python and PostgreSQL.

Preferred qualifications
- Experience with Docker is preferred.
- AWS certification is a plus.
"""

    resp = client.post("/api/v1/jobs/imports/analyze-text", json={"text": jd_text})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["sourceType"] == "PASTED_TEXT"
    assert data["status"] == "PENDING_REVIEW"
    assert data["parserVersion"] == "1.0.0"
    assert data["taxonomyVersion"] == "31.0"

    suggestions = data["suggestions"]
    assert len(suggestions) >= 7

    # 1. Job details verification
    title_sug = next(s for s in suggestions if s["targetField"] == "TITLE")
    assert title_sug["proposedValue"] == "Senior Backend Developer"
    assert title_sug["sourceExcerpt"] == "Job Title: Senior Backend Developer"
    assert title_sug["startOffset"] >= 0

    dept_sug = next(s for s in suggestions if s["targetField"] == "DEPARTMENT")
    assert dept_sug["proposedValue"] == "Engineering"

    loc_sug = next(s for s in suggestions if s["targetField"] == "LOCATION")
    assert loc_sug["proposedValue"] == "San Francisco, CA"

    emp_sug = next(s for s in suggestions if s["targetField"] == "EMPLOYMENT_TYPE")
    assert emp_sug["proposedValue"] == "FULL_TIME"

    wp_sug = next(s for s in suggestions if s["targetField"] == "WORKPLACE_TYPE")
    assert wp_sug["proposedValue"] == "REMOTE"

    open_sug = next(s for s in suggestions if s["targetField"] == "OPENINGS_COUNT")
    assert open_sug["proposedValue"] == 2

    # 2. Summary verification
    sum_sug = next(s for s in suggestions if s["targetField"] == "SUMMARY")
    assert "Build and scale cloud backend" in sum_sug["proposedValue"]

    # 3. Responsibilities verification
    resp_sugs = [s for s in suggestions if s["targetField"] == "RESPONSIBILITY"]
    assert len(resp_sugs) == 3
    assert any("Design and develop scalable REST APIs" in r["proposedValue"] for r in resp_sugs)

    # 4. Requirements & O*NET verification
    req_sugs = [s for s in suggestions if s["targetField"] == "REQUIREMENT"]
    assert len(req_sugs) >= 4

    # Experience requirement
    exp_sug = next(s for s in req_sugs if s["proposedValue"]["category"] == "EXPERIENCE")
    assert exp_sug["proposedValue"]["minExperienceMonths"] == 36
    assert exp_sug["proposedValue"]["necessity"] == "MUST_HAVE"

    # Python skill (O*NET match)
    py_sug = next(s for s in req_sugs if s["proposedValue"]["label"] == "Python")
    assert py_sug["proposedValue"]["category"] == "SKILL"
    assert py_sug["proposedValue"]["necessity"] == "MUST_HAVE"
    assert py_sug["proposedValue"]["taxonomySkillConceptId"] is not None
    assert py_sug["proposedValue"]["origin"] == "TAXONOMY_SUGGESTED_RECRUITER_CONFIRMED"
    assert py_sug["proposedValue"]["rationale"] is None  # Never invented!

    # Docker skill (Preferred)
    dock_sug = next(s for s in req_sugs if s["proposedValue"]["label"] == "Docker")
    assert dock_sug["proposedValue"]["necessity"] == "PREFERRED"

    # Certification
    cert_sug = next(s for s in req_sugs if "AWS" in s["proposedValue"]["label"])
    assert cert_sug["proposedValue"]["category"] == "CERTIFICATION"
    assert cert_sug["proposedValue"]["necessity"] == "PREFERRED"


def test_empty_and_oversized_input_validation(client, test_db):
    _seed_user(test_db, email="recruiter.bounds@company.test", role=UserRole.RECRUITER)
    _login_user(client, email="recruiter.bounds@company.test")

    # Empty text -> 422
    resp_empty = client.post("/api/v1/jobs/imports/analyze-text", json={"text": "   "})
    assert resp_empty.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Too short -> 422
    resp_short = client.post("/api/v1/jobs/imports/analyze-text", json={"text": "Short"})
    assert resp_short.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Oversized (>100k chars) -> 422
    oversized = "a" * 100005
    resp_over = client.post("/api/v1/jobs/imports/analyze-text", json={"text": oversized})
    assert resp_over.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =========================================================================
# 2. Protected Information Safeguard & Warnings
# =========================================================================

def test_protected_information_produces_warning_and_not_requirement(client, test_db):
    _seed_user(test_db, email="recruiter.protect@company.test", role=UserRole.RECRUITER)
    _login_user(client, email="recruiter.protect@company.test")

    jd_text = """Job Title: Operations Associate

Required qualifications
- Must be a young and energetic candidate.
- Bachelor degree in Business Administration.
"""

    resp = client.post("/api/v1/jobs/imports/analyze-text", json={"text": jd_text})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # Warning produced for sensitive term
    warnings = data["warnings"]
    assert len(warnings) >= 1
    assert any(w["code"] == "POTENTIALLY_SENSITIVE_CRITERIA" for w in warnings)

    # Sensitive item must NOT become a structured requirement
    req_labels = [s["proposedValue"]["label"] for s in data["suggestions"] if s["targetField"] == "REQUIREMENT"]
    assert not any("young" in l.lower() for l in req_labels)
    assert any("Bachelor" in l for l in req_labels)


# =========================================================================
# 3. Suggestion Review, Edit, and Atomic Apply Flow
# =========================================================================

def test_suggestion_review_edit_and_apply_flow(client, test_db, synthetic_taxonomy):
    recruiter = _seed_user(test_db, email="recruiter.flow@company.test", role=UserRole.RECRUITER)
    _login_user(client, email="recruiter.flow@company.test")

    # 1. Create a Draft Job Requisition (Rev 1)
    create_job_resp = client.post("/api/v1/jobs", json={"title": "Draft Backend Job"})
    assert create_job_resp.status_code == status.HTTP_201_CREATED
    job_id = create_job_resp.json()["jobId"]

    # 2. Analyze JD text linked to this job draft
    jd_text = """Job Title: Senior Platform Engineer
Department: Infrastructure

About the role
Maintain core cloud services.

Required qualifications
- Experience with Python.
"""
    analyze_resp = client.post(
        f"/api/v1/jobs/imports/analyze-text?job_id={job_id}&expected_revision=1",
        json={"text": jd_text},
    )
    assert analyze_resp.status_code == status.HTTP_200_OK
    session_data = analyze_resp.json()
    session_id = session_data["sessionId"]
    suggestions = session_data["suggestions"]

    title_sug = next(s for s in suggestions if s["targetField"] == "TITLE")
    py_sug = next(s for s in suggestions if s["targetField"] == "REQUIREMENT")

    # 3. Edit and Update a suggestion status
    patch_resp = client.patch(
        f"/api/v1/jobs/imports/{session_id}/suggestions/{title_sug['suggestionId']}",
        json={"review_status": "ACCEPTED", "edited_value": "Lead Platform Engineer"},
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    updated_title = next(s for s in patch_resp.json()["suggestions"] if s["suggestionId"] == title_sug["suggestionId"])
    assert updated_title["reviewStatus"] == "ACCEPTED"
    assert updated_title["proposedValue"] == "Lead Platform Engineer"

    # 4. Apply selected suggestions atomically
    apply_payload = {
        "expectedRevision": 1,
        "acceptedSuggestionIds": [title_sug["suggestionId"], py_sug["suggestionId"]],
        "editedSuggestions": {
            title_sug["suggestionId"]: "Lead Platform Engineer",
        },
    }
    apply_resp = client.post(f"/api/v1/jobs/imports/{session_id}/apply", json=apply_payload)
    assert apply_resp.status_code == status.HTTP_200_OK
    assert apply_resp.json()["status"] == "APPLIED"
    assert apply_resp.json()["appliedCount"] == 2

    # 5. Verify Stale Revision Conflict Protection
    # If the draft revision moves forward (e.g. to 2), applying with expectedRevision=1 must fail with 409
    save_req_resp = client.put(
        f"/api/v1/jobs/{job_id}/draft/requirements",
        json={"expectedRevision": 1, "requirements": [{"label": "Go", "category": "SKILL"}]},
    )
    assert save_req_resp.status_code == status.HTTP_200_OK
    assert save_req_resp.json()["currentVersion"]["revision"] == 2

    conflict_resp = client.post(f"/api/v1/jobs/imports/{session_id}/apply", json=apply_payload)
    assert conflict_resp.status_code == status.HTTP_409_CONFLICT
    assert conflict_resp.json()["detail"]["code"] == "REVISION_CONFLICT"


# =========================================================================
# 4. Authorization & Cross-Recruiter Isolation Tests
# =========================================================================

def test_cross_recruiter_import_session_access_denied(client, test_db):
    user_a = _seed_user(test_db, email="recruiter.a@company.test", role=UserRole.RECRUITER)
    user_b = _seed_user(test_db, email="recruiter.b@company.test", role=UserRole.RECRUITER)

    # User A creates import session
    _login_user(client, email="recruiter.a@company.test")
    resp_a = client.post(
        "/api/v1/jobs/imports/analyze-text",
        json={"text": "Job Title: Data Scientist\n\nRequired qualifications\n- Python experience."},
    )
    session_id = resp_a.json()["sessionId"]

    # User B tries to view or modify User A's session -> 404
    _login_user(client, email="recruiter.b@company.test")
    resp_b = client.get(f"/api/v1/jobs/imports/{session_id}")
    assert resp_b.status_code == status.HTTP_404_NOT_FOUND

    resp_b_patch = client.patch(
        f"/api/v1/jobs/imports/{session_id}/suggestions/some-id",
        json={"review_status": "ACCEPTED"},
    )
    assert resp_b_patch.status_code == status.HTTP_404_NOT_FOUND


# =========================================================================
# 5. Document Upload and Image-Only Rejection Tests
# =========================================================================

def test_image_only_pdf_rejected_without_ocr(client, test_db):
    import pypdf

    _seed_user(test_db, email="recruiter.doc@company.test", role=UserRole.RECRUITER)
    _login_user(client, email="recruiter.doc@company.test")

    # Create empty/blank PDF with no text
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)
    pdf_bytes.seek(0)

    files = {"file": ("scanned_jd.pdf", pdf_bytes.getvalue(), "application/pdf")}
    resp = client.post("/api/v1/jobs/imports/analyze-file", files=files)
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert resp.json()["detail"]["code"] == "IMAGE_ONLY_DOCUMENT_NO_OCR"
    assert "OCR is not supported" in resp.json()["detail"]["message"]


def test_corrupted_document_rejected(client, test_db):
    _seed_user(test_db, email="recruiter.corrupt@company.test", role=UserRole.RECRUITER)
    _login_user(client, email="recruiter.corrupt@company.test")

    # Fake corrupted PDF
    corrupt_bytes = b"%PDF-1.4 garbage corrupted binary content here"
    files = {"file": ("corrupt.pdf", corrupt_bytes, "application/pdf")}
    resp = client.post("/api/v1/jobs/imports/analyze-file", files=files)
    assert resp.status_code in (status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST)


def test_reviewer_forbidden_from_imports(client, test_db):
    _seed_user(test_db, email="reviewer.imports@company.test", role=UserRole.REVIEWER)
    _login_user(client, email="reviewer.imports@company.test")

    resp = client.post("/api/v1/jobs/imports/analyze-text", json={"text": "Job Title: Test"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# =========================================================================
# 6. Migration Isolated Upgrade and Downgrade Test
# =========================================================================

def test_migration_d1e4f6a8b2c3_upgrade_and_downgrade_isolated(capsys):
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://dummy:dummy@localhost:5432/dummy_isolated_test")

    # Test upgrade SQL generation
    command.upgrade(alembic_cfg, "c9d3e5f7a2b1:d1e4f6a8b2c3", sql=True)
    captured_upgrade = capsys.readouterr()
    assert "CREATE TABLE job_description_imports" in captured_upgrade.out
    assert "ix_job_description_imports_created_by_user_id" in captured_upgrade.out

    # Test downgrade SQL generation
    command.downgrade(alembic_cfg, "d1e4f6a8b2c3:c9d3e5f7a2b1", sql=True)
    captured_downgrade = capsys.readouterr()
    assert "DROP TABLE job_description_imports" in captured_downgrade.out
