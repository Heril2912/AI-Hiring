import logging
import re
import uuid
from typing import Dict, List, Optional, Set, Tuple

from app.models.extraction import BlockType
from app.schemas.candidate import (
    ConfidenceBand,
    EvidenceSpan,
    ExtractedField,
    ReviewStatus,
)
from app.schemas.education_project_certification import (
    CertificationExtractionResult,
    CertificationWarning,
    CertificationWarningCode,
    DegreeLevel,
    EducationExtractionResult,
    EducationWarning,
    EducationWarningCode,
    ExtractedCertificationRecord,
    ExtractedEducationRecord,
    ExtractedLanguageRecord,
    ExtractedProjectRecord,
    LanguageExtractionResult,
    LanguageWarning,
    LanguageWarningCode,
    Phase1D4ExtractionResult,
    ProjectExtractionResult,
    ProjectWarning,
    ProjectWarningCode,
)
from app.schemas.employment import (
    DatePrecision,
    ExtractedDateInterval,
    NormalizedDate,
)
from app.schemas.extraction import ExtractionBlockData
from app.schemas.section_and_identity import (
    DetectedSection,
    SectionDetectionResult,
    SectionType,
)
from app.schemas.skill_and_summary import ExtractedSkillItem
from app.services.date_extraction import (
    DATE_RULES_VERSION,
    calculate_interval_duration_months,
    extract_date_range_matches,
    parse_as_of_date,
    parse_single_date,
)
from app.services.education_project_certification_rules import (
    CERTIFICATION_LABEL_PATTERNS,
    DEGREE_DEFINITIONS,
    DISQUALIFYING_EDUCATION_KEYWORDS,
    EDUCATION_PROJECT_CERTIFICATION_RULES_VERSION,
    FIELD_OF_STUDY_PREFIX_RE,
    GRADE_RE,
    INSTITUTION_INDICATORS,
    KNOWN_CERT_ISSUERS,
    NATURAL_LANGUAGES,
    PROFICIENCY_MAPPINGS,
    PROGRAMMING_LANGUAGES_REJECT_LIST,
    PROJECT_TITLE_DISQUALIFIERS,
    PROJECT_URL_RE,
)

logger = logging.getLogger("ai_hiring.services.education_project_certification_extraction")

EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION = "ed-proj-cert-lang-extract-v1.0"


def _create_evidence_span(
    artifact_id: str,
    block: ExtractionBlockData,
    char_start: int,
    char_end: int,
    method: str = "deterministic_rule",
) -> EvidenceSpan:
    """Creates a validated EvidenceSpan against block text."""
    orig_text = block.raw_text[char_start:char_end]
    if not orig_text or char_end <= char_start:
        raise ValueError("Invalid character offsets for evidence span")

    return EvidenceSpan(
        evidence_id=f"ev-{uuid.uuid4().hex[:12]}",
        resume_artifact_id=artifact_id,
        page_number=block.page_number,
        block_number=block.sequence_index,
        character_start=char_start,
        character_end=char_end,
        original_text=orig_text,
        extraction_method=method,
    )


def _build_extracted_field(
    value: Optional[str],
    normalized_value: Optional[str] = None,
    confidence: Optional[float] = None,
    evidence_spans: Optional[List[EvidenceSpan]] = None,
    field_name: str = "",
    method: str = "deterministic_rule",
) -> ExtractedField:
    """Builds a compliant ExtractedField."""
    if value is None or not value.strip():
        return ExtractedField(
            field_name=field_name,
            value=None,
            normalized_value=None,
            confidence=None,
            confidence_band=ConfidenceBand.UNKNOWN,
            evidence_ids=[],
            extraction_method=None,
            review_status=ReviewStatus.UNREVIEWED,
        )

    ev_ids = [s.evidence_id for s in evidence_spans] if evidence_spans else []
    conf = confidence if confidence is not None else 0.85
    return ExtractedField(
        field_name=field_name,
        value=value.strip(),
        normalized_value=normalized_value.strip() if normalized_value else value.strip(),
        confidence=conf,
        evidence_ids=ev_ids,
        extraction_method=method,
        review_status=ReviewStatus.UNREVIEWED,
    )


# =============================================================================
# 1. EDUCATION EXTRACTION SERVICE
# =============================================================================

def extract_education_records(
    blocks: List[ExtractionBlockData],
    sections_result: SectionDetectionResult,
    artifact_id: str,
    as_of_date: Optional[str] = None,
) -> EducationExtractionResult:
    """
    Extracts education records strictly from detected EDUCATION sections.
    - Accurately captures degree, normalized degree level, field of study, institution, dates, grade.
    - Excludes non-degree certification courses.
    - Attaches exact evidence spans and tracks ambiguities with warning codes.
    """
    education_sections = [
        s for s in sections_result.sections if s.section_type == SectionType.EDUCATION
    ]

    all_evidence: List[EvidenceSpan] = []
    all_warnings: List[EducationWarning] = []
    records: List[ExtractedEducationRecord] = []

    if not education_sections:
        return EducationExtractionResult(
            parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
            records=[],
            evidence_spans=[],
            warnings=[],
        )

    block_map: Dict[int, ExtractionBlockData] = {b.sequence_index: b for b in blocks}

    for sec_idx, section in enumerate(education_sections):
        # Collect blocks in section
        sec_blocks: List[ExtractionBlockData] = []
        for idx in range(section.start_sequence_index, section.end_sequence_index + 1):
            if idx in block_map:
                blk = block_map[idx]
                if section.heading and section.heading.heading_sequence_index == idx:
                    continue
                sec_blocks.append(blk)

        # Parse records per block or group of lines
        for b_idx, block in enumerate(sec_blocks):
            raw_text = block.raw_text.strip()
            if not raw_text:
                continue

            lines = [l.strip() for l in block.raw_text.splitlines() if l.strip()]
            if not lines:
                continue

            # Check if block is disqualified as a certification course
            lower_raw = raw_text.lower()
            if any(dq in lower_raw for dq in DISQUALIFYING_EDUCATION_KEYWORDS):
                # Verify if it has formal degree. If not, ignore or warn
                has_formal_degree = False
                for deg_re, _, _ in DEGREE_DEFINITIONS:
                    if deg_re.search(raw_text):
                        has_formal_degree = True
                        break
                if not has_formal_degree:
                    continue

            # Process record in block (or multiple items if separated by empty lines/bullet structure)
            # Find degree match
            degree_val: Optional[str] = None
            norm_degree_level: Optional[DegreeLevel] = None
            degree_spans: List[EvidenceSpan] = []

            for deg_re, deg_level, canonical_name in DEGREE_DEFINITIONS:
                match = deg_re.search(block.raw_text)
                if match:
                    degree_val = match.group(0).strip()
                    norm_degree_level = deg_level
                    c_start = match.start()
                    c_end = match.end()
                    span = _create_evidence_span(artifact_id, block, c_start, c_end)
                    degree_spans.append(span)
                    all_evidence.append(span)
                    break

            # Find Field of Study
            field_of_study_val: Optional[str] = None
            field_spans: List[EvidenceSpan] = []
            fos_match = FIELD_OF_STUDY_PREFIX_RE.search(block.raw_text)
            if fos_match:
                # Capture group 1 is the major name
                field_of_study_val = fos_match.group(1).strip(" ,;|\n\t")
                c_start = fos_match.start(1)
                c_end = fos_match.start(1) + len(field_of_study_val)
                if c_end > c_start:
                    f_span = _create_evidence_span(artifact_id, block, c_start, c_end)
                    field_spans.append(f_span)
                    all_evidence.append(f_span)

            # Find Institution
            inst_val: Optional[str] = None
            inst_spans: List[EvidenceSpan] = []
            
            # Line-by-line inspection for institution indicators
            for line in lines:
                line_lower = line.lower()
                # Check for institution keywords
                words = [w.strip(".,:;/-()") for w in line_lower.split()]
                if any(w in INSTITUTION_INDICATORS for w in words):
                    # Clean line from dates or degrees if present
                    inst_line = line.strip(" •·-*–—\t")
                    # If degree is on the same line (e.g. "B.Tech from Stanford University"), isolate institution
                    if " from " in inst_line.lower():
                        from_idx = inst_line.lower().find(" from ")
                        inst_line = inst_line[from_idx + 6:].strip()
                    elif " at " in inst_line.lower():
                        at_idx = inst_line.lower().find(" at ")
                        inst_line = inst_line[at_idx + 4:].strip()
                    elif "|" in inst_line:
                        parts = inst_line.split("|")
                        for p in parts:
                            p_words = [w.strip(".,:;/-()") for w in p.lower().split()]
                            if any(w in INSTITUTION_INDICATORS for w in p_words):
                                inst_line = p.strip()
                                break

                    c_start = block.raw_text.find(inst_line)
                    if c_start != -1:
                        c_end = c_start + len(inst_line)
                        span = _create_evidence_span(artifact_id, block, c_start, c_end)
                        inst_spans.append(span)
                        all_evidence.append(span)
                        inst_val = inst_line
                        break

            # If institution not found via indicator words, check fallback (e.g. 2nd line or after |)
            if not inst_val and len(lines) > 1:
                # If first line has degree, second line is often institution
                potential_inst = lines[1].strip(" •·-*–—\t")
                # Ensure it's not just a date or grade
                if not GRADE_RE.search(potential_inst) and not extract_date_range_matches(potential_inst) and not parse_single_date(potential_inst):
                    c_start = block.raw_text.find(potential_inst)
                    if c_start != -1:
                        c_end = c_start + len(potential_inst)
                        span = _create_evidence_span(artifact_id, block, c_start, c_end)
                        inst_spans.append(span)
                        all_evidence.append(span)
                        inst_val = potential_inst

            # Find Dates (ranges or single graduation year)
            date_ranges = extract_date_range_matches(block.raw_text)
            date_interval: Optional[ExtractedDateInterval] = None
            start_date_field: ExtractedField
            end_date_field: ExtractedField

            if date_ranges:
                c_start, c_end, full_str, raw_start, raw_end = date_ranges[0]
                d_span = _create_evidence_span(artifact_id, block, c_start, c_end)
                all_evidence.append(d_span)

                norm_start = parse_single_date(raw_start)
                norm_end = parse_single_date(raw_end)

                date_interval = ExtractedDateInterval(
                    raw_text=full_str,
                    start_date=norm_start,
                    end_date=norm_end,
                    is_current=bool(norm_end and norm_end.is_current),
                    duration_months=None,
                    evidence_ids=[d_span.evidence_id],
                    confidence=0.95,
                )

                start_date_field = _build_extracted_field(
                    raw_start,
                    normalized_value=norm_start.raw_text if norm_start else raw_start,
                    confidence=0.95,
                    evidence_spans=[d_span],
                    field_name="start_date",
                )
                end_date_field = _build_extracted_field(
                    raw_end,
                    normalized_value=norm_end.raw_text if norm_end else raw_end,
                    confidence=0.95,
                    evidence_spans=[d_span],
                    field_name="end_date",
                )
            else:
                # Check for single year or single date (e.g. Graduation Year: 2021)
                # Look through lines
                single_date_found = None
                for line in lines:
                    single_d = parse_single_date(line)
                    if single_d:
                        c_start = block.raw_text.find(line)
                        if c_start != -1:
                            c_end = c_start + len(line)
                            d_span = _create_evidence_span(artifact_id, block, c_start, c_end)
                            all_evidence.append(d_span)
                            single_date_found = (line, single_d, d_span)
                            break

                if single_date_found:
                    raw_d_str, norm_d, d_span = single_date_found
                    start_date_field = _build_extracted_field(None, field_name="start_date")
                    end_date_field = _build_extracted_field(
                        raw_d_str,
                        normalized_value=norm_d.raw_text,
                        confidence=0.90,
                        evidence_spans=[d_span],
                        field_name="end_date",
                    )
                else:
                    start_date_field = _build_extracted_field(None, field_name="start_date")
                    end_date_field = _build_extracted_field(None, field_name="end_date")

            # Find Grade / GPA
            grade_val: Optional[str] = None
            grade_spans: List[EvidenceSpan] = []
            grade_match = GRADE_RE.search(block.raw_text)
            if grade_match:
                grade_val = grade_match.group(1).strip()
                c_start = grade_match.start(1)
                c_end = grade_match.start(1) + len(grade_val)
                span = _create_evidence_span(artifact_id, block, c_start, c_end)
                grade_spans.append(span)
                all_evidence.append(span)

            # Check for warnings & build fields
            rec_warnings: List[EducationWarning] = []
            if not degree_val:
                rec_warnings.append(EducationWarning(
                    code=EducationWarningCode.EDUCATION_DEGREE_MISSING,
                    record_index=len(records),
                    field_name="degree",
                ))
            if not inst_val:
                rec_warnings.append(EducationWarning(
                    code=EducationWarningCode.EDUCATION_INSTITUTION_MISSING,
                    record_index=len(records),
                    field_name="institution",
                ))

            # If both missing, it's ambiguous
            if not degree_val and not inst_val:
                rec_warnings.append(EducationWarning(
                    code=EducationWarningCode.EDUCATION_RECORD_AMBIGUOUS,
                    record_index=len(records),
                ))

            all_warnings.extend(rec_warnings)

            deg_field = _build_extracted_field(
                degree_val,
                normalized_value=degree_val,
                confidence=0.95 if degree_val else None,
                evidence_spans=degree_spans,
                field_name="degree",
            )
            fos_field = _build_extracted_field(
                field_of_study_val,
                normalized_value=field_of_study_val,
                confidence=0.90 if field_of_study_val else None,
                evidence_spans=field_spans,
                field_name="field_of_study",
            ) if field_of_study_val else None

            inst_field = _build_extracted_field(
                inst_val,
                normalized_value=inst_val,
                confidence=0.90 if inst_val else None,
                evidence_spans=inst_spans,
                field_name="institution",
            )
            grade_field = _build_extracted_field(
                grade_val,
                normalized_value=grade_val,
                confidence=0.95 if grade_val else None,
                evidence_spans=grade_spans,
                field_name="grade",
            )

            rec_evidence_ids = (
                [s.evidence_id for s in degree_spans]
                + [s.evidence_id for s in field_spans]
                + [s.evidence_id for s in inst_spans]
                + [s.evidence_id for s in grade_spans]
            )
            if date_interval:
                rec_evidence_ids.extend(date_interval.evidence_ids)

            # Compute overall record confidence
            rec_conf = 0.95 if (degree_val and inst_val) else (0.75 if (degree_val or inst_val) else 0.40)

            records.append(ExtractedEducationRecord(
                degree=deg_field,
                field_of_study=fos_field,
                normalized_degree_level=norm_degree_level,
                institution=inst_field,
                start_date=start_date_field,
                end_date=end_date_field,
                grade=grade_field,
                date_interval=date_interval,
                confidence=rec_conf,
                evidence_ids=rec_evidence_ids,
                warnings=rec_warnings,
            ))

    return EducationExtractionResult(
        parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
        records=records,
        evidence_spans=all_evidence,
        warnings=all_warnings,
    )


# =============================================================================
# 2. PROJECT EXTRACTION SERVICE
# =============================================================================

def extract_project_records(
    blocks: List[ExtractionBlockData],
    sections_result: SectionDetectionResult,
    artifact_id: str,
    skill_occurrences: Optional[List[ExtractedSkillItem]] = None,
) -> ProjectExtractionResult:
    """
    Extracts project records strictly from PROJECTS section blocks.
    - Boundaries delimited by project headings, blank lines, bullets.
    - Only associates skills whose evidence spans fall strictly within the project's sequence/character range.
    - Never uses an LLM to hallucinate or summarize.
    """
    project_sections = [
        s for s in sections_result.sections if s.section_type == SectionType.PROJECTS
    ]

    all_evidence: List[EvidenceSpan] = []
    all_warnings: List[ProjectWarning] = []
    records: List[ExtractedProjectRecord] = []

    if not project_sections:
        return ProjectExtractionResult(
            parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
            records=[],
            evidence_spans=[],
            warnings=[],
        )

    block_map: Dict[int, ExtractionBlockData] = {b.sequence_index: b for b in blocks}

    for section in project_sections:
        sec_blocks: List[ExtractionBlockData] = []
        for idx in range(section.start_sequence_index, section.end_sequence_index + 1):
            if idx in block_map:
                blk = block_map[idx]
                if section.heading and section.heading.heading_sequence_index == idx:
                    continue
                sec_blocks.append(blk)

        if not sec_blocks:
            continue

        # Group blocks into project items based on structure (e.g. HEADING blocks or bold lines or separate blocks)
        # If each block is a project, or block has multiple lines starting with project titles
        project_units: List[List[Tuple[ExtractionBlockData, List[str]]]] = []
        curr_unit: List[Tuple[ExtractionBlockData, List[str]]] = []

        for blk in sec_blocks:
            lines = [l.strip() for l in blk.raw_text.splitlines() if l.strip()]
            if not lines:
                continue

            # Check if block is a new project heading
            if blk.block_type == BlockType.HEADING or (len(lines) > 0 and lines[0].startswith("Project:")):
                if curr_unit:
                    project_units.append(curr_unit)
                    curr_unit = []
                curr_unit.append((blk, lines))
            elif not curr_unit:
                curr_unit.append((blk, lines))
            else:
                # Check if first line of block looks like a new project title (not a bullet and capitalized)
                first_line = lines[0]
                is_bullet = first_line.startswith(("•", "-", "*", "·", "1.", "2.", "3."))
                if not is_bullet and len(first_line) < 60 and not first_line.lower().startswith(("responsibilities:", "technologies:", "tech stack:", "tools:", "description:")):
                    # Potential new project
                    project_units.append(curr_unit)
                    curr_unit = [(blk, lines)]
                else:
                    curr_unit.append((blk, lines))

        if curr_unit:
            project_units.append(curr_unit)

        # Now parse each project unit
        for u_idx, unit in enumerate(project_units):
            # First block / line contains project name and potential URL / date
            first_blk, first_lines = unit[0]
            name_line = first_lines[0]

            # If the first line is a bullet point or starts with bullet chars without an explicit project label
            is_bullet_item = name_line.strip().startswith(("•", "-", "*", "·", "1.", "2.", "3."))
            has_project_label = bool(re.search(r"^Project\s*:\s*", name_line.strip(), re.IGNORECASE))

            # Remove prefixes like "Project:" or bullets
            clean_name = re.sub(r"^(?:Project\s*:\s*|[•\-*·\d\.]+\s*)", "", name_line, flags=re.IGNORECASE).strip()
            
            # If name line contains URL or pipe (e.g. "Smart Hiring | https://github.com/..." or "Smart Hiring - Python, React")
            url_match = PROJECT_URL_RE.search(name_line)
            url_val = None
            url_spans: List[EvidenceSpan] = []
            if url_match:
                url_val = url_match.group(0).rstrip(".,;:)")
                u_start = first_blk.raw_text.find(url_val)
                if u_start != -1:
                    u_span = _create_evidence_span(artifact_id, first_blk, u_start, u_start + len(url_val))
                    url_spans.append(u_span)
                    all_evidence.append(u_span)

            # Strip URL or pipe separators from name
            if "|" in clean_name:
                clean_name = clean_name.split("|")[0].strip()
            elif " - " in clean_name:
                clean_name = clean_name.split(" - ")[0].strip()
            if url_val and url_val in clean_name:
                clean_name = clean_name.replace(url_val, "").strip(" -:|")

            # Check if name is valid or missing
            name_spans: List[EvidenceSpan] = []
            rec_warnings: List[ProjectWarning] = []

            # If it was a bullet point without explicit project title, or starts with common responsibility verbs
            if is_bullet_item and not has_project_label:
                clean_name = None

            if not clean_name or clean_name.lower() in PROJECT_TITLE_DISQUALIFIERS:
                rec_warnings.append(ProjectWarning(
                    code=ProjectWarningCode.PROJECT_NAME_MISSING,
                    record_index=len(records),
                    field_name="name",
                ))
                clean_name = None
            else:
                n_start = first_blk.raw_text.find(clean_name)
                if n_start != -1:
                    n_span = _create_evidence_span(artifact_id, first_blk, n_start, n_start + len(clean_name))
                    name_spans.append(n_span)
                    all_evidence.append(n_span)

            # Description: all remaining lines across all blocks in this unit
            desc_lines: List[str] = []
            desc_spans: List[EvidenceSpan] = []

            # First block remaining lines
            if is_bullet_item and not has_project_label:
                # All lines including first are part of description
                for l in first_lines:
                    desc_lines.append(l)
            elif len(first_lines) > 1:
                for l in first_lines[1:]:
                    desc_lines.append(l)
            # Other blocks
            for blk, lines in unit[1:]:
                for l in lines:
                    desc_lines.append(l)

            desc_text = "\n".join(desc_lines).strip()
            if desc_text:
                # Find desc text or individual lines in their respective blocks
                for blk, _ in unit:
                    # Create evidence span for the whole block content if it participates
                    b_start = 0
                    b_end = len(blk.raw_text)
                    if b_end > b_start:
                        d_span = _create_evidence_span(artifact_id, blk, b_start, b_end)
                        desc_spans.append(d_span)
                        all_evidence.append(d_span)

            # Technologies association: strictly within this project's blocks and char ranges
            associated_tech_fields: List[ExtractedField] = []
            unit_block_ids = {blk.sequence_index for blk, _ in unit}

            if skill_occurrences:
                for skill_item in skill_occurrences:
                    # Check if skill's evidence was found in one of the unit's blocks
                    # A skill occurrence has raw_values and evidence_ids
                    # We also search for exact skill canonical name / raw values in this unit's blocks
                    for blk, _ in unit:
                        for raw_val in skill_item.raw_values:
                            # Match whole word
                            pattern = r"\b" + re.escape(raw_val) + r"\b"
                            match = re.search(pattern, blk.raw_text, re.IGNORECASE)
                            if match:
                                s_start = match.start()
                                s_end = match.end()
                                s_span = _create_evidence_span(artifact_id, blk, s_start, s_end)
                                all_evidence.append(s_span)
                                tech_field = _build_extracted_field(
                                    raw_val,
                                    normalized_value=skill_item.canonical_value,
                                    confidence=0.95,
                                    evidence_spans=[s_span],
                                    field_name="technology",
                                )
                                associated_tech_fields.append(tech_field)
                                break

            # Build Fields
            name_field = _build_extracted_field(
                clean_name,
                normalized_value=clean_name,
                confidence=0.95 if clean_name else None,
                evidence_spans=name_spans,
                field_name="name",
            )
            desc_field = _build_extracted_field(
                desc_text if desc_text else None,
                normalized_value=desc_text if desc_text else None,
                confidence=0.90 if desc_text else None,
                evidence_spans=desc_spans,
                field_name="description",
            )
            url_field = _build_extracted_field(
                url_val,
                normalized_value=url_val,
                confidence=0.95 if url_val else None,
                evidence_spans=url_spans,
                field_name="project_url",
            )

            rec_evidence_ids = (
                [s.evidence_id for s in name_spans]
                + [s.evidence_id for s in desc_spans]
                + [s.evidence_id for s in url_spans]
                + [ev for tf in associated_tech_fields for ev in tf.evidence_ids]
            )

            rec_conf = 0.95 if clean_name else 0.50
            all_warnings.extend(rec_warnings)

            records.append(ExtractedProjectRecord(
                name=name_field,
                description=desc_field,
                technologies=associated_tech_fields,
                project_url=url_field,
                confidence=rec_conf,
                evidence_ids=rec_evidence_ids,
                warnings=rec_warnings,
            ))

    return ProjectExtractionResult(
        parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
        records=records,
        evidence_spans=all_evidence,
        warnings=all_warnings,
    )


# =============================================================================
# 3. CERTIFICATION EXTRACTION SERVICE
# =============================================================================

def extract_certification_records(
    blocks: List[ExtractionBlockData],
    sections_result: SectionDetectionResult,
    artifact_id: str,
) -> CertificationExtractionResult:
    """
    Extracts certifications strictly from CERTIFICATIONS section blocks.
    - Captures name, issuer, issue date, expiry date, credential ID, credential URL.
    - Reuses Phase 1D.3 date parser.
    - Never fetches URLs.
    """
    cert_sections = [
        s for s in sections_result.sections if s.section_type == SectionType.CERTIFICATIONS
    ]

    all_evidence: List[EvidenceSpan] = []
    all_warnings: List[CertificationWarning] = []
    records: List[ExtractedCertificationRecord] = []

    if not cert_sections:
        return CertificationExtractionResult(
            parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
            records=[],
            evidence_spans=[],
            warnings=[],
        )

    block_map: Dict[int, ExtractionBlockData] = {b.sequence_index: b for b in blocks}

    for section in cert_sections:
        sec_blocks: List[ExtractionBlockData] = []
        for idx in range(section.start_sequence_index, section.end_sequence_index + 1):
            if idx in block_map:
                blk = block_map[idx]
                if section.heading and section.heading.heading_sequence_index == idx:
                    continue
                sec_blocks.append(blk)

        for b_idx, block in enumerate(sec_blocks):
            lines = [l.strip() for l in block.raw_text.splitlines() if l.strip()]
            if not lines:
                continue

            # Identify certification name
            # Usually the first line or before labelled fields
            first_line = lines[0].strip(" •-*·\t")
            cert_name_val: Optional[str] = None
            cert_name_spans: List[EvidenceSpan] = []

            # Check if first line is just a label or actual name
            if not any(pattern.search(first_line) for pattern in CERTIFICATION_LABEL_PATTERNS.values()):
                cert_name_val = first_line
                n_start = block.raw_text.find(cert_name_val)
                if n_start != -1:
                    span = _create_evidence_span(artifact_id, block, n_start, n_start + len(cert_name_val))
                    cert_name_spans.append(span)
                    all_evidence.append(span)

            # Issuer detection
            issuer_val: Optional[str] = None
            issuer_spans: List[EvidenceSpan] = []
            issuer_match = CERTIFICATION_LABEL_PATTERNS["issuer"].search(block.raw_text)
            if issuer_match:
                issuer_val = issuer_match.group(1).strip()
                c_start = issuer_match.start(1)
                span = _create_evidence_span(artifact_id, block, c_start, c_start + len(issuer_val))
                issuer_spans.append(span)
                all_evidence.append(span)
            else:
                # Look for known cert issuers in the text
                for kw, canonical_issuer in KNOWN_CERT_ISSUERS.items():
                    pattern = r"\b" + re.escape(kw) + r"\b"
                    match = re.search(pattern, block.raw_text, re.IGNORECASE)
                    if match:
                        matched_str = match.group(0)
                        c_start = match.start()
                        span = _create_evidence_span(artifact_id, block, c_start, c_start + len(matched_str))
                        issuer_spans.append(span)
                        all_evidence.append(span)
                        issuer_val = canonical_issuer
                        break

            # Date detection (Issued date & Expiry date)
            issued_date_val: Optional[str] = None
            issued_date_spans: List[EvidenceSpan] = []
            expiry_date_val: Optional[str] = None
            expiry_date_spans: List[EvidenceSpan] = []

            # Labelled dates
            issued_match = CERTIFICATION_LABEL_PATTERNS["issued_date"].search(block.raw_text)
            if issued_match:
                raw_d = issued_match.group(1).strip()
                norm_d = parse_single_date(raw_d)
                if norm_d:
                    c_start = issued_match.start(1)
                    span = _create_evidence_span(artifact_id, block, c_start, c_start + len(raw_d))
                    issued_date_spans.append(span)
                    all_evidence.append(span)
                    issued_date_val = raw_d

            expiry_match = CERTIFICATION_LABEL_PATTERNS["expiry_date"].search(block.raw_text)
            if expiry_match:
                raw_d = expiry_match.group(1).strip()
                norm_d = parse_single_date(raw_d)
                if norm_d:
                    c_start = expiry_match.start(1)
                    span = _create_evidence_span(artifact_id, block, c_start, c_start + len(raw_d))
                    expiry_date_spans.append(span)
                    all_evidence.append(span)
                    expiry_date_val = raw_d

            # If unlabelled date range
            if not issued_date_val and not expiry_date_val:
                date_ranges = extract_date_range_matches(block.raw_text)
                if date_ranges:
                    c_start, c_end, full_str, raw_start, raw_end = date_ranges[0]
                    d_span = _create_evidence_span(artifact_id, block, c_start, c_end)
                    all_evidence.append(d_span)
                    issued_date_val = raw_start
                    issued_date_spans.append(d_span)
                    expiry_date_val = raw_end
                    expiry_date_spans.append(d_span)
                else:
                    # Single unlabelled date
                    for line in lines:
                        s_d = parse_single_date(line)
                        if s_d:
                            c_start = block.raw_text.find(line)
                            if c_start != -1:
                                d_span = _create_evidence_span(artifact_id, block, c_start, c_start + len(line))
                                all_evidence.append(d_span)
                                issued_date_val = line
                                issued_date_spans.append(d_span)
                                break

            # Credential ID
            cred_id_val: Optional[str] = None
            cred_id_spans: List[EvidenceSpan] = []
            cred_id_match = CERTIFICATION_LABEL_PATTERNS["credential_id"].search(block.raw_text)
            if cred_id_match:
                cred_id_val = cred_id_match.group(1).strip()
                c_start = cred_id_match.start(1)
                span = _create_evidence_span(artifact_id, block, c_start, c_start + len(cred_id_val))
                cred_id_spans.append(span)
                all_evidence.append(span)

            # Credential URL
            cred_url_val: Optional[str] = None
            cred_url_spans: List[EvidenceSpan] = []
            cred_url_match = CERTIFICATION_LABEL_PATTERNS["credential_url"].search(block.raw_text)
            if cred_url_match:
                cred_url_val = cred_url_match.group(1).strip()
                c_start = cred_url_match.start(1)
                span = _create_evidence_span(artifact_id, block, c_start, c_start + len(cred_url_val))
                cred_url_spans.append(span)
                all_evidence.append(span)
            else:
                # Generic URL search
                url_m = PROJECT_URL_RE.search(block.raw_text)
                if url_m:
                    cred_url_val = url_m.group(0).rstrip(".,;:)")
                    c_start = url_m.start()
                    span = _create_evidence_span(artifact_id, block, c_start, c_start + len(cred_url_val))
                    cred_url_spans.append(span)
                    all_evidence.append(span)

            # Warnings & validation
            rec_warnings: List[CertificationWarning] = []
            if not cert_name_val:
                rec_warnings.append(CertificationWarning(
                    code=CertificationWarningCode.CERTIFICATION_NAME_MISSING,
                    record_index=len(records),
                    field_name="name",
                ))
            if not issuer_val:
                rec_warnings.append(CertificationWarning(
                    code=CertificationWarningCode.CERTIFICATION_ISSUER_AMBIGUOUS,
                    record_index=len(records),
                    field_name="issuer",
                ))

            all_warnings.extend(rec_warnings)

            name_field = _build_extracted_field(
                cert_name_val,
                normalized_value=cert_name_val,
                confidence=0.95 if cert_name_val else None,
                evidence_spans=cert_name_spans,
                field_name="name",
            )
            issuer_field = _build_extracted_field(
                issuer_val,
                normalized_value=issuer_val,
                confidence=0.90 if issuer_val else None,
                evidence_spans=issuer_spans,
                field_name="issuer",
            )
            issued_date_field = _build_extracted_field(
                issued_date_val,
                normalized_value=issued_date_val,
                confidence=0.90 if issued_date_val else None,
                evidence_spans=issued_date_spans,
                field_name="issued_date",
            )
            expiry_date_field = _build_extracted_field(
                expiry_date_val,
                normalized_value=expiry_date_val,
                confidence=0.90 if expiry_date_val else None,
                evidence_spans=expiry_date_spans,
                field_name="expiry_date",
            ) if expiry_date_val else None

            cred_id_field = _build_extracted_field(
                cred_id_val,
                normalized_value=cred_id_val,
                confidence=0.95 if cred_id_val else None,
                evidence_spans=cred_id_spans,
                field_name="credential_id",
            ) if cred_id_val else None

            cred_url_field = _build_extracted_field(
                cred_url_val,
                normalized_value=cred_url_val,
                confidence=0.95 if cred_url_val else None,
                evidence_spans=cred_url_spans,
                field_name="credential_url",
            )

            rec_evidence_ids = (
                [s.evidence_id for s in cert_name_spans]
                + [s.evidence_id for s in issuer_spans]
                + [s.evidence_id for s in issued_date_spans]
                + [s.evidence_id for s in expiry_date_spans]
                + [s.evidence_id for s in cred_id_spans]
                + [s.evidence_id for s in cred_url_spans]
            )

            rec_conf = 0.95 if (cert_name_val and issuer_val) else (0.70 if cert_name_val else 0.40)

            records.append(ExtractedCertificationRecord(
                name=name_field,
                issuer=issuer_field,
                issued_date=issued_date_field,
                expiry_date=expiry_date_field,
                credential_id=cred_id_field,
                credential_url=cred_url_field,
                confidence=rec_conf,
                evidence_ids=rec_evidence_ids,
                warnings=rec_warnings,
            ))

    return CertificationExtractionResult(
        parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
        records=records,
        evidence_spans=all_evidence,
        warnings=all_warnings,
    )


# =============================================================================
# 4. LANGUAGE EXTRACTION SERVICE
# =============================================================================

def extract_language_records(
    blocks: List[ExtractionBlockData],
    sections_result: SectionDetectionResult,
    artifact_id: str,
) -> LanguageExtractionResult:
    """
    Extracts natural languages strictly from LANGUAGES section blocks.
    - Strictly filters out programming languages (Python, Java, etc.).
    - Extracts natural language names and stated proficiency levels.
    - Does not assume proficiency if not explicitly written.
    """
    lang_sections = [
        s for s in sections_result.sections if s.section_type == SectionType.LANGUAGES
    ]

    all_evidence: List[EvidenceSpan] = []
    all_warnings: List[LanguageWarning] = []
    records: List[ExtractedLanguageRecord] = []

    if not lang_sections:
        return LanguageExtractionResult(
            parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
            languages=[],
            evidence_spans=[],
            warnings=[],
        )

    block_map: Dict[int, ExtractionBlockData] = {b.sequence_index: b for b in blocks}

    for section in lang_sections:
        sec_blocks: List[ExtractionBlockData] = []
        for idx in range(section.start_sequence_index, section.end_sequence_index + 1):
            if idx in block_map:
                blk = block_map[idx]
                if section.heading and section.heading.heading_sequence_index == idx:
                    continue
                sec_blocks.append(blk)

        for block in sec_blocks:
            # Handle comma separated items or line by line
            raw_text = block.raw_text.strip()
            if not raw_text:
                continue

            # Split into items by newline or semicolon or comma
            lines = [l.strip(" •-*·\t") for l in block.raw_text.splitlines() if l.strip()]

            items: List[str] = []
            for l in lines:
                if "," in l:
                    # Split on comma, but avoid splitting inside parentheses
                    parts = re.split(r",(?![^(]*\))", l)
                    for p in parts:
                        p_str = p.strip(" •-*·\t")
                        if p_str:
                            items.append(p_str)
                else:
                    items.append(l)

            for item in items:
                item_clean = item.strip()
                if not item_clean:
                    continue

                # Check if item is a programming language
                words = [w.strip(".,:;()/-").lower() for w in item_clean.split()]
                if any(w in PROGRAMMING_LANGUAGES_REJECT_LIST for w in words):
                    warn = LanguageWarning(
                        code=LanguageWarningCode.NON_NATURAL_LANGUAGE_REJECTED,
                        record_index=len(records),
                        field_name="language",
                    )
                    all_warnings.append(warn)
                    continue

                # Search for known natural language name
                matched_lang_name: Optional[str] = None
                matched_canonical: Optional[str] = None
                lang_span: Optional[EvidenceSpan] = None

                for l_key, l_canonical in NATURAL_LANGUAGES.items():
                    pattern = r"\b" + re.escape(l_key) + r"\b"
                    match = re.search(pattern, item_clean, re.IGNORECASE)
                    if match:
                        matched_lang_name = match.group(0)
                        matched_canonical = l_canonical
                        # Find span in block
                        c_start = block.raw_text.find(item_clean)
                        if c_start != -1:
                            offset = item_clean.find(matched_lang_name)
                            s_start = c_start + offset
                            s_end = s_start + len(matched_lang_name)
                            lang_span = _create_evidence_span(artifact_id, block, s_start, s_end)
                            all_evidence.append(lang_span)
                        break

                if not matched_lang_name:
                    # Entry is ambiguous / unclassified
                    all_warnings.append(LanguageWarning(
                        code=LanguageWarningCode.LANGUAGE_ENTRY_AMBIGUOUS,
                        record_index=len(records),
                    ))
                    continue

                # Detect proficiency
                raw_prof: Optional[str] = None
                norm_prof: Optional[str] = None
                prof_span: Optional[EvidenceSpan] = None
                rec_warnings: List[LanguageWarning] = []

                for prof_re, norm_level in PROFICIENCY_MAPPINGS:
                    m = prof_re.search(item_clean)
                    if m:
                        raw_prof = m.group(0)
                        norm_prof = norm_level
                        c_start = block.raw_text.find(item_clean)
                        if c_start != -1:
                            p_offset = item_clean.find(raw_prof)
                            p_start = c_start + p_offset
                            p_end = p_start + len(raw_prof)
                            prof_span = _create_evidence_span(artifact_id, block, p_start, p_end)
                            all_evidence.append(prof_span)
                        break

                # If proficiency text exists (like in parentheses or after colon) but didn't match known mappings
                if not raw_prof:
                    # Check if there is colon or parentheses: e.g. "English (B2)" or "Spanish: Conversational"
                    paren_m = re.search(r"[\(:\-–—]\s*([A-Za-z0-9\s]+)[\)]?", item_clean)
                    if paren_m:
                        candidate_prof = paren_m.group(1).strip()
                        if candidate_prof.lower() != matched_lang_name.lower():
                            raw_prof = candidate_prof
                            norm_prof = None
                            rec_warnings.append(LanguageWarning(
                                code=LanguageWarningCode.LANGUAGE_PROFICIENCY_UNKNOWN,
                                record_index=len(records),
                                field_name="proficiency",
                            ))
                            c_start = block.raw_text.find(candidate_prof)
                            if c_start != -1:
                                prof_span = _create_evidence_span(artifact_id, block, c_start, c_start + len(candidate_prof))
                                all_evidence.append(prof_span)

                all_warnings.extend(rec_warnings)

                lang_field = _build_extracted_field(
                    matched_lang_name,
                    normalized_value=matched_canonical,
                    confidence=0.95,
                    evidence_spans=[lang_span] if lang_span else [],
                    field_name="language",
                )
                prof_field = _build_extracted_field(
                    raw_prof,
                    normalized_value=norm_prof if norm_prof else raw_prof,
                    confidence=0.90 if raw_prof else None,
                    evidence_spans=[prof_span] if prof_span else [],
                    field_name="proficiency",
                ) if raw_prof else None

                rec_ev_ids = []
                if lang_span:
                    rec_ev_ids.append(lang_span.evidence_id)
                if prof_span:
                    rec_ev_ids.append(prof_span.evidence_id)

                records.append(ExtractedLanguageRecord(
                    language=lang_field,
                    proficiency=prof_field,
                    normalized_proficiency=norm_prof,
                    confidence=0.95,
                    evidence_ids=rec_ev_ids,
                    warnings=rec_warnings,
                ))

    return LanguageExtractionResult(
        parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
        languages=records,
        evidence_spans=all_evidence,
        warnings=all_warnings,
    )


# =============================================================================
# 5. MASTER ORCHESTRATION FUNCTION
# =============================================================================

def extract_education_projects_certifications_languages(
    blocks: List[ExtractionBlockData],
    sections_result: SectionDetectionResult,
    artifact_id: str,
    skill_occurrences: Optional[List[ExtractedSkillItem]] = None,
    as_of_date: Optional[str] = None,
) -> Phase1D4ExtractionResult:
    """Master function extracting Education, Projects, Certifications, and Languages."""
    ed_res = extract_education_records(blocks, sections_result, artifact_id, as_of_date=as_of_date)
    proj_res = extract_project_records(blocks, sections_result, artifact_id, skill_occurrences=skill_occurrences)
    cert_res = extract_certification_records(blocks, sections_result, artifact_id)
    lang_res = extract_language_records(blocks, sections_result, artifact_id)

    combined_evidence: List[EvidenceSpan] = (
        ed_res.evidence_spans
        + proj_res.evidence_spans
        + cert_res.evidence_spans
        + lang_res.evidence_spans
    )

    return Phase1D4ExtractionResult(
        parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
        rules_version=EDUCATION_PROJECT_CERTIFICATION_RULES_VERSION,
        education=ed_res,
        projects=proj_res,
        certifications=cert_res,
        languages=lang_res,
        evidence_spans=combined_evidence,
    )
