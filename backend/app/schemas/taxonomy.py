import uuid
from typing import Optional
from pydantic import Field

from app.schemas.candidate import StrictSchema


class OccupationSearchItemResponse(StrictSchema):
    concept_id: uuid.UUID
    onet_soc_code: str
    canonical_title: str
    matched_alias: Optional[str] = None
    source: str
    source_version: str


class SkillSearchItemResponse(StrictSchema):
    concept_id: uuid.UUID
    canonical_label: str
    matched_alias: Optional[str] = None
    category: Optional[str] = None
    source: str
    source_version: Optional[str] = None
