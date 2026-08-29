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

EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION = "ed-proj-cert-lang-extract-v1.1"

_ACTION_VERBS = {
    "developed", "built", "created", "managed", "designed", "led", "architected",
    "engineered", "integrated", "maintained", "implemented", "containerized",
    "wrote", "provided", "performed", "analyzed", "assisted", "collaborated",
    "delivered", "supported", "automated", "configured", "deployed", "spearheaded",
    "orchestrated", "optimized", "monitored", "refactored", "troubleshot", "tested",
}


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
# 1. EDUCATION EXTRACTION SERVICE (STATE MACHINE)
# =============================================================================

def extract_education_records(
    blocks: List[ExtractionBlockData],
    sections_result: SectionDetectionResult,
    artifact_id: str,
    as_of_date: Optional[str] = None,
) -> EducationExtractionResult:
    """
    Extracts education records strictly from detected EDUCATION sections using a pending-record state machine.
    - Assembles multi-line/multi-block items (degree, field of study, institution, dates, grade) into unified records.
    - Excludes non-degree certification courses.
    - Produces warnings only for finalized logical records.
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

    for section in education_sections:
        sec_blocks: List[ExtractionBlockData] = []
        for idx in range(section.start_sequence_index, section.end_sequence_index + 1):
            if idx in block_map:
                blk = block_map[idx]
                if section.heading and section.heading.heading_sequence_index == idx:
                    continue
                sec_blocks.append(blk)

        if not sec_blocks:
            continue

        # Extract ordered lines across the section
        LineEntry = Tuple[ExtractionBlockData, str, int, int]
        all_lines: List[LineEntry] = []
        for blk in sec_blocks:
            lines = blk.normalized_text.split("\n")
            curr_off = 0
            for line in lines:
                line_str = line.strip()
                line_len = len(line)
                line_start = blk.normalized_text.find(line, curr_off)
                if line_start == -1:
                    line_start = curr_off
                line_end = line_start + len(line_str)
                curr_off = line_start + line_len + 1
                if line_str:
                    all_lines.append((blk, line_str, line_start, line_end))

        # State machine pending record state
        class PendingEducation:
            def __init__(self):
                self.degree_val: Optional[str] = None
                self.norm_degree_level: Optional[DegreeLevel] = None
                self.degree_spans: List[EvidenceSpan] = []
                self.field_of_study_val: Optional[str] = None
                self.field_spans: List[EvidenceSpan] = []
                self.inst_val: Optional[str] = None
                self.inst_spans: List[EvidenceSpan] = []
                self.date_interval: Optional[ExtractedDateInterval] = None
                self.start_date_field: Optional[ExtractedField] = None
                self.end_date_field: Optional[ExtractedField] = None
                self.grade_val: Optional[str] = None
                self.grade_spans: List[EvidenceSpan] = []
                self.warnings: List[EducationWarning] = []

        pending_records: List[PendingEducation] = []
        current: Optional[PendingEducation] = None

        def finalize_pending():
            nonlocal current
            if current and (current.degree_val or current.inst_val):
                if not current.degree_val and not current.inst_val:
                    current.warnings.append(EducationWarning(
                        code=EducationWarningCode.EDUCATION_RECORD_AMBIGUOUS,
                        record_index=len(pending_records),
                    ))
                elif not current.degree_val:
                    current.warnings.append(EducationWarning(
                        code=EducationWarningCode.EDUCATION_DEGREE_MISSING,
                        record_index=len(pending_records),
                        field_name="degree",
                    ))
                elif not current.inst_val:
                    current.warnings.append(EducationWarning(
                        code=EducationWarningCode.EDUCATION_INSTITUTION_MISSING,
                        record_index=len(pending_records),
                        field_name="institution",
                    ))
                pending_records.append(current)
            current = None

        for blk, line_str, l_start, l_end in all_lines:
            lower_line = line_str.lower()

            # Check if disqualified non-degree course
            if any(dq in lower_line for dq in DISQUALIFYING_EDUCATION_KEYWORDS):
                has_formal = any(deg_re.search(line_str) for deg_re, _, _ in DEGREE_DEFINITIONS)
                if not has_formal:
                    continue

            # Detect degree
            matched_deg: Optional[str] = None
            matched_level: Optional[DegreeLevel] = None
            matched_deg_span: Optional[EvidenceSpan] = None

            for deg_re, deg_level, _ in DEGREE_DEFINITIONS:
                m = deg_re.search(line_str)
                if m:
                    matched_deg = m.group(0).strip()
                    matched_level = deg_level
                    c_start = blk.raw_text.find(matched_deg, l_start)
                    if c_start == -1:
                        c_start = l_start + m.start()
                    c_end = c_start + len(matched_deg)
                    matched_deg_span = _create_evidence_span(artifact_id, blk, c_start, c_end)
                    all_evidence.append(matched_deg_span)
                    break

            # If a degree is found and current pending record already has a degree, finalize previous record
            if matched_deg:
                if current and current.degree_val:
                    finalize_pending()
                if current is None:
                    current = PendingEducation()
                current.degree_val = matched_deg
                current.norm_degree_level = matched_level
                if matched_deg_span:
                    current.degree_spans.append(matched_deg_span)

            # Detect field of study
            fos_m = FIELD_OF_STUDY_PREFIX_RE.search(line_str)
            if fos_m:
                fos_val = fos_m.group(1).strip(" ,;|\n\t")
                if current is None:
                    current = PendingEducation()
                if not current.field_of_study_val and fos_val:
                    current.field_of_study_val = fos_val
                    c_start = blk.raw_text.find(fos_val, l_start)
                    if c_start == -1:
                        c_start = l_start + fos_m.start(1)
                    c_end = c_start + len(fos_val)
                    if c_end > c_start:
                        f_span = _create_evidence_span(artifact_id, blk, c_start, c_end)
                        all_evidence.append(f_span)
                        current.field_spans.append(f_span)

            # Detect dates (range or single year)
            date_ranges = extract_date_range_matches(line_str)
            single_date = parse_single_date(line_str) if not date_ranges else None
            is_date_line = bool(date_ranges) or bool(single_date)

            if is_date_line:
                if date_ranges:
                    c_start, c_end, full_str, raw_start, raw_end = date_ranges[0]
                    abs_start = blk.raw_text.find(full_str, l_start)
                    if abs_start == -1:
                        abs_start = l_start + c_start
                    abs_end = abs_start + len(full_str)
                    d_span = _create_evidence_span(artifact_id, blk, abs_start, abs_end)
                    all_evidence.append(d_span)

                    norm_start = parse_single_date(raw_start)
                    norm_end = parse_single_date(raw_end)

                    if current is None:
                        current = PendingEducation()
                    if not current.date_interval:
                        current.date_interval = ExtractedDateInterval(
                            raw_text=full_str,
                            start_date=norm_start,
                            end_date=norm_end,
                            is_current=bool(norm_end and norm_end.is_current),
                            duration_months=None,
                            evidence_ids=[d_span.evidence_id],
                            confidence=0.95,
                        )
                        current.start_date_field = _build_extracted_field(
                            raw_start,
                            normalized_value=f"{norm_start.year:04d}" if (norm_start and norm_start.year) else raw_start,
                            confidence=0.95,
                            evidence_spans=[d_span],
                            field_name="start_date",
                        )
                        current.end_date_field = _build_extracted_field(
                            raw_end,
                            normalized_value=f"{norm_end.year:04d}" if (norm_end and norm_end.year) else raw_end,
                            confidence=0.95,
                            evidence_spans=[d_span],
                            field_name="end_date",
                        )
                elif single_date:
                    abs_start = blk.raw_text.find(line_str, l_start)
                    if abs_start == -1:
                        abs_start = l_start
                    abs_end = abs_start + len(line_str)
                    d_span = _create_evidence_span(artifact_id, blk, abs_start, abs_end)
                    all_evidence.append(d_span)

                    if current is None:
                        current = PendingEducation()
                    if not current.date_interval:
                        current.date_interval = ExtractedDateInterval(
                            raw_text=line_str,
                            start_date=None,
                            end_date=single_date,
                            is_current=False,
                            duration_months=None,
                            evidence_ids=[d_span.evidence_id],
                            confidence=0.90,
                        )
                        current.start_date_field = _build_extracted_field(None, field_name="start_date")
                        current.end_date_field = _build_extracted_field(
                            line_str,
                            normalized_value=f"{single_date.year:04d}" if single_date.year else line_str,
                            confidence=0.90,
                            evidence_spans=[d_span],
                            field_name="end_date",
                        )
                continue

            # Detect grade / GPA
            grade_m = GRADE_RE.search(line_str)
            if grade_m:
                g_val = grade_m.group(1).strip(" ,;|\n\t") if grade_m.lastindex else grade_m.group(0).strip(" ,;|\n\t")
                if current is None:
                    current = PendingEducation()
                if not current.grade_val and g_val:
                    current.grade_val = g_val
                    c_start = blk.raw_text.find(g_val, l_start)
                    if c_start == -1:
                        c_start = l_start + grade_m.start()
                    c_end = c_start + len(g_val)
                    g_span = _create_evidence_span(artifact_id, blk, c_start, c_end)
                    all_evidence.append(g_span)
                    current.grade_spans.append(g_span)

            # Detect institution
            words = [w.strip(".,:;/-()") for w in lower_line.split()]
            has_inst_word = any(w in INSTITUTION_INDICATORS for w in words)
            if not is_date_line and (has_inst_word or (not matched_deg and len(line_str) < 80 and not fos_m and not grade_m)):
                inst_cand = line_str.strip(" •·-*–—\t")
                if " from " in inst_cand.lower():
                    from_idx = inst_cand.lower().find(" from ")
                    inst_cand = inst_cand[from_idx + 6:].strip()
                elif " at " in inst_cand.lower():
                    at_idx = inst_cand.lower().find(" at ")
                    inst_cand = inst_cand[at_idx + 4:].strip()
                elif "|" in inst_cand:
                    parts = inst_cand.split("|")
                    for p in parts:
                        p_words = [w.strip(".,:;/-()") for w in p.lower().split()]
                        if any(w in INSTITUTION_INDICATORS for w in p_words):
                            inst_cand = p.strip()
                            break

                if current is None:
                    current = PendingEducation()
                if not current.inst_val and inst_cand:
                    current.inst_val = inst_cand
                    c_start = blk.raw_text.find(inst_cand, l_start)
                    if c_start == -1:
                        c_start = l_start
                    c_end = c_start + len(inst_cand)
                    i_span = _create_evidence_span(artifact_id, blk, c_start, c_end)
                    all_evidence.append(i_span)
                    current.inst_spans.append(i_span)

        finalize_pending()

        # Build ExtractedEducationRecord list
        for p in pending_records:
            all_warnings.extend(p.warnings)

            deg_field = _build_extracted_field(
                p.degree_val,
                normalized_value=p.degree_val,
                confidence=0.95 if p.degree_val else None,
                evidence_spans=p.degree_spans,
                field_name="degree",
            )
            fos_field = _build_extracted_field(
                p.field_of_study_val,
                normalized_value=p.field_of_study_val,
                confidence=0.90 if p.field_of_study_val else None,
                evidence_spans=p.field_spans,
                field_name="field_of_study",
            ) if p.field_of_study_val else None
            inst_field = _build_extracted_field(
                p.inst_val,
                normalized_value=p.inst_val,
                confidence=0.90 if p.inst_val else None,
                evidence_spans=p.inst_spans,
                field_name="institution",
            )
            grade_field = _build_extracted_field(
                p.grade_val,
                normalized_value=p.grade_val,
                confidence=0.95 if p.grade_val else None,
                evidence_spans=p.grade_spans,
                field_name="grade",
            )

            start_field = p.start_date_field or _build_extracted_field(None, field_name="start_date")
            end_field = p.end_date_field or _build_extracted_field(None, field_name="end_date")

            rec_evidence_ids = (
                [s.evidence_id for s in p.degree_spans]
                + [s.evidence_id for s in p.field_spans]
                + [s.evidence_id for s in p.inst_spans]
                + [s.evidence_id for s in p.grade_spans]
            )
            if p.date_interval:
                rec_evidence_ids.extend(p.date_interval.evidence_ids)

            rec_conf = 0.95 if (p.degree_val and p.inst_val) else (0.75 if (p.degree_val or p.inst_val) else 0.40)

            records.append(ExtractedEducationRecord(
                degree=deg_field,
                field_of_study=fos_field,
                normalized_degree_level=p.norm_degree_level,
                institution=inst_field,
                start_date=start_field,
                end_date=end_field,
                grade=grade_field,
                date_interval=p.date_interval,
                confidence=rec_conf,
                evidence_ids=rec_evidence_ids,
                warnings=p.warnings,
            ))

    return EducationExtractionResult(
        parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
        records=records,
        evidence_spans=all_evidence,
        warnings=all_warnings,
    )


# =============================================================================
# 2. PROJECT EXTRACTION SERVICE (STATE MACHINE)
# =============================================================================

def extract_project_records(
    blocks: List[ExtractionBlockData],
    sections_result: SectionDetectionResult,
    artifact_id: str,
    skill_occurrences: Optional[List[ExtractedSkillItem]] = None,
) -> ProjectExtractionResult:
    """
    Extracts project records strictly from PROJECTS section blocks using a pending-record state machine.
    - Boundaries delimited by project headings, blank lines, and non-action project title lines.
    - Only associates skills whose evidence spans fall strictly within the project's sequence/character range.
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

        class PendingProject:
            def __init__(self):
                self.name_val: Optional[str] = None
                self.name_spans: List[EvidenceSpan] = []
                self.desc_lines: List[str] = []
                self.desc_spans: List[EvidenceSpan] = []
                self.url_val: Optional[str] = None
                self.url_spans: List[EvidenceSpan] = []
                self.tech_lines: List[str] = []
                self.participating_seqs: Set[int] = set()
                self.warnings: List[ProjectWarning] = []

        pending_projects: List[PendingProject] = []
        current: Optional[PendingProject] = None

        def finalize_pending_project():
            nonlocal current
            if current and (current.name_val or current.desc_lines or current.url_val):
                if not current.name_val:
                    current.warnings.append(ProjectWarning(
                        code=ProjectWarningCode.PROJECT_NAME_MISSING,
                        record_index=len(pending_projects),
                        field_name="name",
                    ))
                pending_projects.append(current)
            current = None

        for blk in sec_blocks:
            lines = [l.strip() for l in blk.raw_text.splitlines() if l.strip()]
            if not lines:
                continue

            for l_idx, line in enumerate(lines):
                line_clean = line.strip(" •-*·\t")
                if not line_clean:
                    continue

                first_word = line_clean.split()[0].lower().strip(".,:;/-") if line_clean.split() else ""
                is_action_verb = first_word in _ACTION_VERBS
                is_bullet = line.strip().startswith(("•", "-", "*", "·", "1.", "2.", "3."))
                has_label = bool(re.match(r"^Project(?:\s*Name)?\s*:\s*", line_clean, re.I))

                is_tech_label = bool(re.match(r"^(?:Technologies|Tech Stack|Tools|Built with)\s*:\s*", line_clean, re.I))

                # Check if this line starts a NEW project
                is_new_project_start = False
                if has_label or blk.block_type == BlockType.HEADING:
                    is_new_project_start = True
                elif (
                    not is_bullet
                    and not is_action_verb
                    and not is_tech_label
                    and not PROJECT_URL_RE.match(line_clean)
                    and len(line_clean) < 60
                    and line_clean.lower() not in PROJECT_TITLE_DISQUALIFIERS
                ):
                    # Short title line that is not a bullet and not an action sentence
                    # If current already has name and description, this is the start of the next project
                    if current and current.name_val and (current.desc_lines or current.participating_seqs != {blk.sequence_index}):
                        is_new_project_start = True
                    elif current is None:
                        is_new_project_start = True

                if is_new_project_start:
                    if current:
                        finalize_pending_project()
                    current = PendingProject()

                    # Extract name
                    clean_name = re.sub(r"^(?:Project(?:\s*Name)?\s*:\s*|[•\-*·\d\.]+\s*)", "", line_clean, flags=re.IGNORECASE).strip()
                    url_m = PROJECT_URL_RE.search(clean_name)
                    if url_m:
                        current.url_val = url_m.group(0).rstrip(".,;:)")
                        u_start = blk.raw_text.find(current.url_val)
                        if u_start != -1:
                            u_span = _create_evidence_span(artifact_id, blk, u_start, u_start + len(current.url_val))
                            current.url_spans.append(u_span)
                            all_evidence.append(u_span)
                        clean_name = clean_name.replace(current.url_val, "").strip(" -:|")

                    if "|" in clean_name:
                        clean_name = clean_name.split("|")[0].strip()
                    elif " - " in clean_name:
                        clean_name = clean_name.split(" - ")[0].strip()

                    current.name_val = clean_name
                    c_start = blk.raw_text.find(clean_name)
                    if c_start != -1:
                        n_span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(clean_name))
                        current.name_spans.append(n_span)
                        all_evidence.append(n_span)
                    current.participating_seqs.add(blk.sequence_index)
                    continue

                if current is None:
                    current = PendingProject()

                current.participating_seqs.add(blk.sequence_index)

                # Check for explicit tech label
                if is_tech_label:
                    tech_content = re.sub(r"^(?:Technologies|Tech Stack|Tools|Built with)\s*:\s*", "", line_clean, flags=re.IGNORECASE).strip()
                    current.tech_lines.append(tech_content)
                    current.desc_lines.append(line_clean)
                    continue

                # Check for URL
                url_m = PROJECT_URL_RE.search(line_clean)
                if url_m and not current.url_val:
                    current.url_val = url_m.group(0).rstrip(".,;:)")
                    u_start = blk.raw_text.find(current.url_val)
                    if u_start != -1:
                        u_span = _create_evidence_span(artifact_id, blk, u_start, u_start + len(current.url_val))
                        current.url_spans.append(u_span)
                        all_evidence.append(u_span)

                # Otherwise attach as description line
                current.desc_lines.append(line_clean)
                c_start = blk.raw_text.find(line_clean)
                if c_start != -1:
                    d_span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(line_clean))
                    current.desc_spans.append(d_span)
                    all_evidence.append(d_span)

        finalize_pending_project()

        # Build records
        for p in pending_projects:
            all_warnings.extend(p.warnings)

            name_field = _build_extracted_field(
                p.name_val,
                normalized_value=p.name_val,
                confidence=0.95 if p.name_val else None,
                evidence_spans=p.name_spans,
                field_name="name",
            )
            desc_text = "\n".join(p.desc_lines).strip()
            desc_field = _build_extracted_field(
                desc_text if desc_text else None,
                normalized_value=desc_text if desc_text else None,
                confidence=0.90 if desc_text else None,
                evidence_spans=p.desc_spans,
                field_name="description",
            )
            url_field = _build_extracted_field(
                p.url_val,
                normalized_value=p.url_val,
                confidence=0.95 if p.url_val else None,
                evidence_spans=p.url_spans,
                field_name="project_url",
            )

            # Scoped technologies from skill occurrences
            tech_fields: List[ExtractedField] = []
            seen_techs: Set[str] = set()
            if skill_occurrences:
                for skill_item in skill_occurrences:
                    for blk_seq in p.participating_seqs:
                        blk = block_map[blk_seq]
                        matched_val = None
                        for raw_val in skill_item.raw_values:
                            pattern = r"\b" + re.escape(raw_val) + r"\b"
                            m = re.search(pattern, blk.raw_text, re.IGNORECASE)
                            if m:
                                matched_val = m.group(0)
                                break
                        if not matched_val:
                            pattern = r"\b" + re.escape(skill_item.canonical_value) + r"\b"
                            m = re.search(pattern, blk.raw_text, re.IGNORECASE)
                            if m:
                                matched_val = m.group(0)

                        if matched_val and skill_item.canonical_value.lower() not in seen_techs:
                            seen_techs.add(skill_item.canonical_value.lower())
                            c_start = blk.raw_text.find(matched_val)
                            c_end = c_start + len(matched_val)
                            t_span = _create_evidence_span(artifact_id, blk, c_start, c_end)
                            all_evidence.append(t_span)
                            tech_fields.append(_build_extracted_field(
                                matched_val,
                                normalized_value=skill_item.canonical_value,
                                confidence=skill_item.confidence,
                                evidence_spans=[t_span],
                                field_name="technology",
                            ))
                            break

            rec_evidence_ids = (
                [s.evidence_id for s in p.name_spans]
                + [s.evidence_id for s in p.desc_spans]
                + [s.evidence_id for s in p.url_spans]
                + [ev for tf in tech_fields for ev in tf.evidence_ids]
            )

            rec_conf = 0.95 if p.name_val else 0.50

            records.append(ExtractedProjectRecord(
                name=name_field,
                description=desc_field,
                technologies=tech_fields,
                project_url=url_field,
                confidence=rec_conf,
                evidence_ids=rec_evidence_ids,
                warnings=p.warnings,
            ))

    return ProjectExtractionResult(
        parser_version=EDUCATION_PROJECT_CERTIFICATION_PARSER_VERSION,
        records=records,
        evidence_spans=all_evidence,
        warnings=all_warnings,
    )


# =============================================================================
# 3. CERTIFICATION EXTRACTION SERVICE (STATE MACHINE)
# =============================================================================

def extract_certification_records(
    blocks: List[ExtractionBlockData],
    sections_result: SectionDetectionResult,
    artifact_id: str,
) -> CertificationExtractionResult:
    """
    Extracts certification records strictly from CERTIFICATIONS section blocks using a pending-record state machine.
    - Captures certification name, issuer, issue date, expiry date, credential ID, credential URL.
    - Labels like 'Issuer:', 'Issued:', 'Credential ID:' attach to the current pending certification record.
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

        if not sec_blocks:
            continue

        class PendingCert:
            def __init__(self):
                self.name_val: Optional[str] = None
                self.name_spans: List[EvidenceSpan] = []
                self.issuer_val: Optional[str] = None
                self.issuer_spans: List[EvidenceSpan] = []
                self.issued_date_val: Optional[str] = None
                self.issued_date_spans: List[EvidenceSpan] = []
                self.expiry_date_val: Optional[str] = None
                self.expiry_date_spans: List[EvidenceSpan] = []
                self.cred_id_val: Optional[str] = None
                self.cred_id_spans: List[EvidenceSpan] = []
                self.cred_url_val: Optional[str] = None
                self.cred_url_spans: List[EvidenceSpan] = []
                self.warnings: List[CertificationWarning] = []

        pending_certs: List[PendingCert] = []
        current: Optional[PendingCert] = None

        def finalize_pending_cert():
            nonlocal current
            if current and (current.name_val or current.issuer_val or current.cred_id_val):
                if not current.name_val:
                    current.warnings.append(CertificationWarning(
                        code=CertificationWarningCode.CERTIFICATION_NAME_MISSING,
                        record_index=len(pending_certs),
                        field_name="name",
                    ))
                if not current.issuer_val:
                    current.warnings.append(CertificationWarning(
                        code=CertificationWarningCode.CERTIFICATION_ISSUER_AMBIGUOUS,
                        record_index=len(pending_certs),
                        field_name="issuer",
                    ))
                pending_certs.append(current)
            current = None

        for blk in sec_blocks:
            lines = [l.strip() for l in blk.raw_text.splitlines() if l.strip()]
            if not lines:
                continue

            for line in lines:
                line_clean = line.strip(" •-*·\t")
                if not line_clean:
                    continue

                # Check if line is a metadata label
                is_issuer_line = bool(CERTIFICATION_LABEL_PATTERNS["issuer"].search(line_clean))
                is_issued_date_line = bool(CERTIFICATION_LABEL_PATTERNS["issued_date"].search(line_clean))
                is_expiry_date_line = bool(CERTIFICATION_LABEL_PATTERNS["expiry_date"].search(line_clean))
                is_cred_id_line = bool(CERTIFICATION_LABEL_PATTERNS["credential_id"].search(line_clean))
                is_cred_url_line = bool(CERTIFICATION_LABEL_PATTERNS["credential_url"].search(line_clean))

                is_label_line = (
                    is_issuer_line
                    or is_issued_date_line
                    or is_expiry_date_line
                    or is_cred_id_line
                    or is_cred_url_line
                )

                # Check if line is a new certification title
                if not is_label_line:
                    # Check if line is only a date
                    date_matches = extract_date_range_matches(line_clean)
                    is_date_only = bool(date_matches) or bool(parse_single_date(line_clean))

                    if not is_date_only:
                        # New certification title
                        if current and current.name_val:
                            finalize_pending_cert()
                        if current is None:
                            current = PendingCert()

                        current.name_val = line_clean
                        c_start = blk.raw_text.find(line_clean)
                        if c_start != -1:
                            span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(line_clean))
                            current.name_spans.append(span)
                            all_evidence.append(span)
                        continue

                if current is None:
                    current = PendingCert()

                # Process labels on the current certification
                if is_issuer_line:
                    m = CERTIFICATION_LABEL_PATTERNS["issuer"].search(line_clean)
                    if m:
                        val = m.group(1).strip()
                        current.issuer_val = val
                        c_start = blk.raw_text.find(val)
                        if c_start != -1:
                            span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(val))
                            current.issuer_spans.append(span)
                            all_evidence.append(span)
                    continue

                if is_issued_date_line:
                    m = CERTIFICATION_LABEL_PATTERNS["issued_date"].search(line_clean)
                    if m:
                        val = m.group(1).strip()
                        current.issued_date_val = val
                        c_start = blk.raw_text.find(val)
                        if c_start != -1:
                            span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(val))
                            current.issued_date_spans.append(span)
                            all_evidence.append(span)
                    continue

                if is_expiry_date_line:
                    m = CERTIFICATION_LABEL_PATTERNS["expiry_date"].search(line_clean)
                    if m:
                        val = m.group(1).strip()
                        current.expiry_date_val = val
                        c_start = blk.raw_text.find(val)
                        if c_start != -1:
                            span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(val))
                            current.expiry_date_spans.append(span)
                            all_evidence.append(span)
                    continue

                if is_cred_id_line:
                    m = CERTIFICATION_LABEL_PATTERNS["credential_id"].search(line_clean)
                    if m:
                        val = m.group(1).strip()
                        current.cred_id_val = val
                        c_start = blk.raw_text.find(val)
                        if c_start != -1:
                            span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(val))
                            current.cred_id_spans.append(span)
                            all_evidence.append(span)
                    continue

                if is_cred_url_line:
                    m = CERTIFICATION_LABEL_PATTERNS["credential_url"].search(line_clean)
                    if m:
                        val = m.group(1).strip()
                        current.cred_url_val = val
                        c_start = blk.raw_text.find(val)
                        if c_start != -1:
                            span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(val))
                            current.cred_url_spans.append(span)
                            all_evidence.append(span)
                    continue

                # Fallback issuer matching
                if not current.issuer_val:
                    for kw, canonical_issuer in KNOWN_CERT_ISSUERS.items():
                        pattern = r"\b" + re.escape(kw) + r"\b"
                        match = re.search(pattern, line_clean, re.IGNORECASE)
                        if match:
                            matched_str = match.group(0)
                            c_start = blk.raw_text.find(matched_str)
                            if c_start != -1:
                                span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(matched_str))
                                current.issuer_spans.append(span)
                                all_evidence.append(span)
                            current.issuer_val = canonical_issuer
                            break

                # Fallback unlabelled date matching
                if not current.issued_date_val:
                    date_ranges = extract_date_range_matches(line_clean)
                    if date_ranges:
                        c_start, c_end, full_str, raw_start, raw_end = date_ranges[0]
                        d_span = _create_evidence_span(artifact_id, blk, c_start, c_end)
                        all_evidence.append(d_span)
                        current.issued_date_val = raw_start
                        current.issued_date_spans.append(d_span)
                        current.expiry_date_val = raw_end
                        current.expiry_date_spans.append(d_span)
                    else:
                        s_d = parse_single_date(line_clean)
                        if s_d:
                            c_start = blk.raw_text.find(line_clean)
                            if c_start != -1:
                                d_span = _create_evidence_span(artifact_id, blk, c_start, c_start + len(line_clean))
                                all_evidence.append(d_span)
                                current.issued_date_val = line_clean
                                current.issued_date_spans.append(d_span)

        finalize_pending_cert()

        # Build records
        for p in pending_certs:
            all_warnings.extend(p.warnings)

            name_field = _build_extracted_field(
                p.name_val,
                normalized_value=p.name_val,
                confidence=0.95 if p.name_val else None,
                evidence_spans=p.name_spans,
                field_name="name",
            )
            issuer_field = _build_extracted_field(
                p.issuer_val,
                normalized_value=p.issuer_val,
                confidence=0.90 if p.issuer_val else None,
                evidence_spans=p.issuer_spans,
                field_name="issuer",
            )
            issued_date_field = _build_extracted_field(
                p.issued_date_val,
                normalized_value=p.issued_date_val,
                confidence=0.90 if p.issued_date_val else None,
                evidence_spans=p.issued_date_spans,
                field_name="issued_date",
            )
            expiry_date_field = _build_extracted_field(
                p.expiry_date_val,
                normalized_value=p.expiry_date_val,
                confidence=0.90 if p.expiry_date_val else None,
                evidence_spans=p.expiry_date_spans,
                field_name="expiry_date",
            ) if p.expiry_date_val else None

            cred_id_field = _build_extracted_field(
                p.cred_id_val,
                normalized_value=p.cred_id_val,
                confidence=0.95 if p.cred_id_val else None,
                evidence_spans=p.cred_id_spans,
                field_name="credential_id",
            ) if p.cred_id_val else None

            cred_url_field = _build_extracted_field(
                p.cred_url_val,
                normalized_value=p.cred_url_val,
                confidence=0.95 if p.cred_url_val else None,
                evidence_spans=p.cred_url_spans,
                field_name="credential_url",
            )

            rec_evidence_ids = (
                [s.evidence_id for s in p.name_spans]
                + [s.evidence_id for s in p.issuer_spans]
                + [s.evidence_id for s in p.issued_date_spans]
                + [s.evidence_id for s in p.expiry_date_spans]
                + [s.evidence_id for s in p.cred_id_spans]
                + [s.evidence_id for s in p.cred_url_spans]
            )

            rec_conf = 0.95 if (p.name_val and p.issuer_val) else (0.70 if p.name_val else 0.40)

            records.append(ExtractedCertificationRecord(
                name=name_field,
                issuer=issuer_field,
                issued_date=issued_date_field,
                expiry_date=expiry_date_field,
                credential_id=cred_id_field,
                credential_url=cred_url_field,
                confidence=rec_conf,
                evidence_ids=rec_evidence_ids,
                warnings=p.warnings,
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
    - Extracts natural language names and stated proficiency levels (separated by —, –, -, :, or parentheses).
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
            raw_text = block.raw_text.strip()
            if not raw_text:
                continue

            lines = [l.strip(" •-*·\t") for l in block.raw_text.splitlines() if l.strip()]

            items: List[str] = []
            for l in lines:
                if "," in l:
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

                # Check if programming language
                words = [w.strip(".,:;()/-").lower() for w in item_clean.split()]
                if any(w in PROGRAMMING_LANGUAGES_REJECT_LIST for w in words):
                    all_warnings.append(LanguageWarning(
                        code=LanguageWarningCode.NON_NATURAL_LANGUAGE_REJECTED,
                        record_index=len(records),
                        field_name="language",
                    ))
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
                        c_start = block.raw_text.find(item_clean)
                        if c_start != -1:
                            offset = item_clean.find(matched_lang_name)
                            s_start = c_start + offset
                            s_end = s_start + len(matched_lang_name)
                            lang_span = _create_evidence_span(artifact_id, block, s_start, s_end)
                            all_evidence.append(lang_span)
                        break

                if not matched_lang_name:
                    all_warnings.append(LanguageWarning(
                        code=LanguageWarningCode.LANGUAGE_ENTRY_AMBIGUOUS,
                        record_index=len(records),
                    ))
                    continue

                # Detect proficiency (supporting —, –, -, :, or parens)
                raw_prof: Optional[str] = None
                norm_prof: Optional[str] = None
                prof_span: Optional[EvidenceSpan] = None
                rec_warnings: List[LanguageWarning] = []

                for prof_re, norm_level in PROFICIENCY_MAPPINGS:
                    m = prof_re.search(item_clean)
                    if m:
                        raw_prof = m.group(0).strip()
                        norm_prof = norm_level
                        c_start = block.raw_text.find(item_clean)
                        if c_start != -1:
                            p_offset = item_clean.find(raw_prof)
                            p_start = c_start + p_offset
                            p_end = p_start + len(raw_prof)
                            prof_span = _create_evidence_span(artifact_id, block, p_start, p_end)
                            all_evidence.append(prof_span)
                        break

                if not raw_prof:
                    # Check for separator and trailing text (e.g. "English — Working proficiency" or "Hindi: Fluent")
                    sep_m = re.search(r"[—–\-:\(]\s*([A-Za-z0-9\s]+)[\)]?$", item_clean)
                    if sep_m:
                        candidate_prof = sep_m.group(1).strip()
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
                    normalized_value=norm_prof if norm_prof else (raw_prof if raw_prof else matched_canonical),
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
