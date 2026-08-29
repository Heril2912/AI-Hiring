import hashlib
import io
import uuid
from pathlib import Path
import pytest
from pypdf import PdfWriter

from app.config import get_settings
from app.models.extraction import BlockType, ExtractionMethod
from app.models.resume import ArtifactFormat, ArtifactValidationStatus, ResumeArtifact
from app.services.pdf_text_extraction import (
    PDF_DIRECT_EXTRACTOR_VERSION,
    extract_pdf_direct_text,
)
from app.services.profile_assembly import assemble_candidate_profile

TEST_PDF_PATH = Path("/Users/herilvyas/Downloads/resume_test_B_two_column.pdf")


def _setup_test_artifact(tmp_pdf_path: Path, settings) -> ResumeArtifact:
    art_id = uuid.uuid4()
    q_dir = settings.get_quarantine_path() / "pdf"
    q_dir.mkdir(parents=True, exist_ok=True)
    q_path = q_dir / f"{art_id}.pdf"
    data = tmp_pdf_path.read_bytes()
    q_path.write_bytes(data)

    sha256 = hashlib.sha256(data).hexdigest().lower()
    return ResumeArtifact(
        artifact_id=art_id,
        original_filename=tmp_pdf_path.name,
        detected_format=ArtifactFormat.pdf,
        quarantine_key=f"pdf/{art_id}.pdf",
        size_bytes=len(data),
        sha256_hash=sha256,
        validation_status=ArtifactValidationStatus.VALIDATED,
    )


def test_two_column_resume_extraction_and_profile_assembly():
    """Validates the exact two-column ReportLab PDF resume end-to-end."""
    if not TEST_PDF_PATH.exists():
        pytest.skip(f"Test fixture not found at {TEST_PDF_PATH}")

    settings = get_settings()
    artifact = _setup_test_artifact(TEST_PDF_PATH, settings)

    res = extract_pdf_direct_text(artifact, settings)

    # 1. Version check
    assert res.extractor_version == "pdf-layout-text-v1.1"

    # 2. Layout assessment
    assert len(res.pages) == 1
    page0 = res.pages[0]
    assert page0.layout_type == "TWO_COLUMN"
    assert page0.column_count == 2
    assert not page0.review_required

    # 3. Column isolation & no header merging
    block_texts = [b.raw_text for b in res.blocks]
    assert any("Rohan Iyer" == b.raw_text.strip() for b in res.blocks)
    assert any("Cloud Platform Engineer" == b.raw_text.strip() for b in res.blocks)
    assert any("CONTACT" in b.raw_text for b in res.blocks)
    assert any("rohan.iyer@example.com" in b.raw_text for b in res.blocks)

    # Confirm CONTACT and Rohan Iyer are in separate blocks
    rohan_blocks = [b for b in res.blocks if "Rohan Iyer" in b.raw_text]
    contact_blocks = [b for b in res.blocks if "rohan.iyer@example.com" in b.raw_text]
    assert rohan_blocks and contact_blocks
    assert rohan_blocks[0].sequence_index != contact_blocks[0].sequence_index

    # 4. Profile Assembly verification
    p_res = assemble_candidate_profile(res.blocks, str(artifact.artifact_id))
    ident = p_res.identity
    prof = p_res.professional_profile

    # Identity
    assert ident.full_name.value == "Rohan Iyer"
    assert len(ident.emails) == 1
    assert ident.emails[0].value == "rohan.iyer@example.com"
    assert len(ident.phone_numbers) == 1
    assert ident.phone_numbers[0].value == "+1 617-555-0129"
    assert ident.github.value == "github.com/rohan-iyer-example"

    # Headline & Summary
    assert prof.headline.value == "Cloud Platform Engineer"
    assert prof.summary.value is not None
    assert "reliable container orchestration" in prof.summary.value

    # Skills: all 9 skills present
    extracted_skill_names = [s.value for s in prof.skills]
    expected_skills = ["Go", "Python", "Flask", "AWS", "Kubernetes", "Docker", "Redis", "MongoDB", "Linux"]
    for sk in expected_skills:
        assert sk in extracted_skill_names

    # Employment: 2 records
    assert len(prof.employment) == 2
    emp1 = prof.employment[0]
    assert emp1.job_title.value == "Cloud Platform Engineer"
    assert emp1.organization.value == "Blue Harbor Systems"
    assert emp1.start_date.value == "February 2023"
    assert emp1.end_date.value == "Present"
    assert len(emp1.descriptions) >= 1

    emp2 = prof.employment[1]
    assert emp2.job_title.value == "Backend Engineer"
    assert emp2.organization.value == "Cedar Labs"
    assert emp2.start_date.value == "August 2020"
    assert emp2.end_date.value == "January 2023"
    assert len(emp2.descriptions) >= 1

    # Projects: 2 records
    assert len(prof.projects) == 2
    proj_names = [p.name.value for p in prof.projects]
    assert "Cluster Health Console" in proj_names
    assert "API Resilience Lab" in proj_names

    # Education: 1 record
    assert len(prof.education) == 1
    edu = prof.education[0]
    assert edu.institution.value == "Eastwood Institute of Engineering"
    assert edu.degree.value == "Bachelor of Engineering"
    assert edu.field_of_study.value == "Information Technology"

    # Certification: 1 record
    assert len(prof.certifications) == 1
    cert = prof.certifications[0]
    assert cert.name.value == "AWS Certified Solutions Architect - Associate"
    assert cert.issuer.value == "Amazon Web Services"
    assert cert.credential_id.value == "SAA-EXAMPLE-25"

    # Languages: 2 records
    assert len(prof.languages) == 2
    lang_map = {l.value: l.normalized_value for l in prof.languages}
    assert lang_map.get("English") == "FLUENT"
    assert lang_map.get("Tamil") == "NATIVE"

    # Footer exclusion
    assert not any("Fictional resume" in b for b in block_texts)
    assert not any("Test PDF-B" in b for b in block_texts)


def test_single_column_pdf_extraction(tmp_path):
    """Validates that single-column direct-text PDFs continue to extract accurately."""
    from tests.test_pdf_text_extraction import _generate_pdf_bytes

    pdf_bytes = _generate_pdf_bytes([
        "Jane Doe\nSenior Backend Engineer\njane.doe@example.com | +1 555-0100\n\nEXPERIENCE\nStaff Engineer at Acme Corp 2021 - Present\nBuilt scalable microservices in Python and Go."
    ])

    pdf_file = tmp_path / "single_column.pdf"
    pdf_file.write_bytes(pdf_bytes)

    settings = get_settings()
    artifact = _setup_test_artifact(pdf_file, settings)

    res = extract_pdf_direct_text(artifact, settings)
    assert res.extractor_version == "pdf-layout-text-v1.1"
    assert res.pages[0].layout_type == "SINGLE_COLUMN"
    assert res.pages[0].column_count == 1
    assert len(res.blocks) >= 1

    p_res = assemble_candidate_profile(res.blocks, str(artifact.artifact_id))
    assert p_res.identity.full_name.value == "Jane Doe"
    assert p_res.professional_profile.headline.value == "Senior Backend Engineer"
    assert len(p_res.professional_profile.employment) == 1

