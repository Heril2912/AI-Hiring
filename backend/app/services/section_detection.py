import logging
import re
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.models.extraction import BlockType
from app.schemas.extraction import ExtractionBlockData
from app.schemas.section_and_identity import (
    DetectedSection,
    SectionDetectionResult,
    SectionHeadingMatch,
    SectionType,
)

logger = logging.getLogger("ai_hiring.services.section_detection")

SECTION_PARSER_VERSION = "section-detect-v1.0"

# Canonical heading alias map: normalized lowercase alias -> SectionType
HEADING_ALIASES: Dict[str, SectionType] = {
    # SUMMARY
    "summary": SectionType.SUMMARY,
    "professional summary": SectionType.SUMMARY,
    "career summary": SectionType.SUMMARY,
    "executive summary": SectionType.SUMMARY,
    "profile": SectionType.SUMMARY,
    "professional profile": SectionType.SUMMARY,
    "career profile": SectionType.SUMMARY,
    "personal profile": SectionType.SUMMARY,
    "career objective": SectionType.SUMMARY,
    "objective": SectionType.SUMMARY,
    "about me": SectionType.SUMMARY,
    "about": SectionType.SUMMARY,
    "summary of qualifications": SectionType.SUMMARY,

    # SKILLS
    "skills": SectionType.SKILLS,
    "technical skills": SectionType.SKILLS,
    "core skills": SectionType.SKILLS,
    "key skills": SectionType.SKILLS,
    "competencies": SectionType.SKILLS,
    "core competencies": SectionType.SKILLS,
    "key competencies": SectionType.SKILLS,
    "technologies": SectionType.SKILLS,
    "technical proficiencies": SectionType.SKILLS,
    "areas of expertise": SectionType.SKILLS,
    "skills & competencies": SectionType.SKILLS,
    "skills and competencies": SectionType.SKILLS,
    "tools and technologies": SectionType.SKILLS,
    "tools & technologies": SectionType.SKILLS,

    # EXPERIENCE
    "experience": SectionType.EXPERIENCE,
    "work experience": SectionType.EXPERIENCE,
    "professional experience": SectionType.EXPERIENCE,
    "employment history": SectionType.EXPERIENCE,
    "work history": SectionType.EXPERIENCE,
    "career history": SectionType.EXPERIENCE,
    "relevant experience": SectionType.EXPERIENCE,
    "professional background": SectionType.EXPERIENCE,
    "industry experience": SectionType.EXPERIENCE,

    # EDUCATION
    "education": SectionType.EDUCATION,
    "academic background": SectionType.EDUCATION,
    "academic qualifications": SectionType.EDUCATION,
    "qualifications": SectionType.EDUCATION,
    "educational background": SectionType.EDUCATION,
    "education and credentials": SectionType.EDUCATION,
    "degrees": SectionType.EDUCATION,

    # PROJECTS
    "projects": SectionType.PROJECTS,
    "personal projects": SectionType.PROJECTS,
    "academic projects": SectionType.PROJECTS,
    "key projects": SectionType.PROJECTS,
    "relevant projects": SectionType.PROJECTS,
    "technical projects": SectionType.PROJECTS,
    "selected projects": SectionType.PROJECTS,

    # CERTIFICATIONS
    "certifications": SectionType.CERTIFICATIONS,
    "certificates": SectionType.CERTIFICATIONS,
    "professional certifications": SectionType.CERTIFICATIONS,
    "licences": SectionType.CERTIFICATIONS,
    "licenses": SectionType.CERTIFICATIONS,
    "credentials": SectionType.CERTIFICATIONS,
    "licenses & certifications": SectionType.CERTIFICATIONS,
    "licenses and certifications": SectionType.CERTIFICATIONS,

    # LANGUAGES
    "languages": SectionType.LANGUAGES,
    "languages known": SectionType.LANGUAGES,
    "language proficiency": SectionType.LANGUAGES,
    "language skills": SectionType.LANGUAGES,
}

_COLON_TRAIL_RE = re.compile(r"[:\s]+$")
_WHITESPACE_COLLAPSE_RE = re.compile(r"\s+")


def _normalize_for_heading_match(text: str) -> str:
    """Normalizes candidate text for heading lookup: lowercase, strip, remove trailing colon, collapse spaces."""
    cleaned = text.strip()
    cleaned = _COLON_TRAIL_RE.sub("", cleaned)
    cleaned = _WHITESPACE_COLLAPSE_RE.sub(" ", cleaned)
    return cleaned.lower()


def match_heading_candidate(text: str) -> Optional[Tuple[SectionType, str, float]]:
    """
    Checks if text is a recognized section heading.
    Returns (SectionType, normalized_heading, confidence) or None.
    """
    if not text:
        return None

    norm = _normalize_for_heading_match(text)
    if not norm:
        return None

    # Length guard: section headings are short (<= 60 chars and <= 6 words)
    if len(norm) > 60 or len(norm.split()) > 6:
        return None

    if norm in HEADING_ALIASES:
        return HEADING_ALIASES[norm], norm, 1.0

    return None


def detect_sections_from_blocks(
    blocks: List[ExtractionBlockData],
) -> SectionDetectionResult:
    """
    Deterministically partitions an ordered list of ExtractionBlockData into detected sections.

    Rules:
    1. A block classified as HEADING, or any short block whose text matches HEADING_ALIASES exactly,
       triggers the start of a new section.
    2. Any content prior to the first recognized heading is grouped into a HEADER section.
    3. Blocks following a heading belong to that section until the next recognized heading.
    4. Headings occurring on the first line of a multiline block (e.g. 'SKILLS:\nPython, C++') are detected
       as section triggers without mutating or splitting the block.
    5. Unknown/unrecognized blocks are retained in their respective section range.
    6. Returns stable, non-overlapping section ranges.
    """
    if not blocks:
        return SectionDetectionResult(
            parser_version=SECTION_PARSER_VERSION,
            sections=[],
            warnings=[],
        )

    # 1. Identify section boundary anchors: (block_idx, SectionType, SectionHeadingMatch)
    anchors: List[Tuple[int, SectionType, SectionHeadingMatch]] = []

    for idx, block in enumerate(blocks):
        norm_text = block.normalized_text.strip()
        if not norm_text:
            continue

        # Strategy A: Full block match
        match_result = match_heading_candidate(norm_text)

        # Strategy B: If not full block, check first line if block is multiline or has colon prefix
        first_line = norm_text.split("\n")[0].strip() if "\n" in norm_text else ""
        if not match_result and first_line:
            first_line_match = match_heading_candidate(first_line)
            if first_line_match:
                match_result = first_line_match

        # Strategy C: Check prefix before colon if present in single-line block (e.g. "Skills: Python, TypeScript")
        if not match_result and ":" in norm_text:
            colon_prefix = norm_text.split(":")[0].strip()
            prefix_match = match_heading_candidate(colon_prefix)
            if prefix_match:
                match_result = prefix_match

        if match_result:
            sec_type, matched_norm, conf = match_result
            heading_match = SectionHeadingMatch(
                matched_heading_text=norm_text if not first_line else first_line,
                normalized_heading_text=matched_norm,
                section_type=sec_type,
                heading_block_id=block.block_id,
                heading_sequence_index=block.sequence_index,
                confidence=conf,
            )
            anchors.append((idx, sec_type, heading_match))

    sections: List[DetectedSection] = []
    warnings: List[str] = []

    # 2. Build sections from anchors
    if not anchors:
        # No headings detected: entire document is treated as HEADER
        all_block_ids = [b.block_id for b in blocks if b.block_id is not None]
        sections.append(
            DetectedSection(
                section_type=SectionType.HEADER,
                start_sequence_index=blocks[0].sequence_index,
                end_sequence_index=blocks[-1].sequence_index,
                block_ids=all_block_ids,
                heading=None,
            )
        )
        return SectionDetectionResult(
            parser_version=SECTION_PARSER_VERSION,
            sections=sections,
            warnings=["NO_SECTION_HEADINGS_DETECTED"],
        )

    # Handle content before first heading -> HEADER section
    first_anchor_idx = anchors[0][0]
    if first_anchor_idx > 0:
        header_blocks = blocks[:first_anchor_idx]
        sections.append(
            DetectedSection(
                section_type=SectionType.HEADER,
                start_sequence_index=header_blocks[0].sequence_index,
                end_sequence_index=header_blocks[-1].sequence_index,
                block_ids=[b.block_id for b in header_blocks if b.block_id is not None],
                heading=None,
            )
        )

    # Build sections for each anchor
    for i, (anchor_block_idx, sec_type, heading_match) in enumerate(anchors):
        start_idx = anchor_block_idx
        # End index is up to next anchor - 1, or end of document
        if i + 1 < len(anchors):
            end_idx = anchors[i + 1][0] - 1
        else:
            end_idx = len(blocks) - 1

        sec_blocks = blocks[start_idx : end_idx + 1]
        sections.append(
            DetectedSection(
                section_type=sec_type,
                start_sequence_index=sec_blocks[0].sequence_index,
                end_sequence_index=sec_blocks[-1].sequence_index,
                block_ids=[b.block_id for b in sec_blocks if b.block_id is not None],
                heading=heading_match,
            )
        )

    return SectionDetectionResult(
        parser_version=SECTION_PARSER_VERSION,
        sections=sections,
        warnings=warnings,
    )
