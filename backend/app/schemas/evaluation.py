import enum
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.candidate import StrictSchema
from app.schemas.matching import verify_no_prohibited_keys

EVALUATION_MANIFEST_SCHEMA_VERSION: str = "phase2c5_eval_manifest_v1"


class RelevanceLabel(str, enum.Enum):
    NOT_RELEVANT = "NOT_RELEVANT"
    PARTIALLY_RELEVANT = "PARTIALLY_RELEVANT"
    RELEVANT = "RELEVANT"
    HIGHLY_RELEVANT = "HIGHLY_RELEVANT"


RELEVANCE_GRADED_VALUES: Dict[RelevanceLabel, float] = {
    RelevanceLabel.NOT_RELEVANT: 0.0,
    RelevanceLabel.PARTIALLY_RELEVANT: 1.0,
    RelevanceLabel.RELEVANT: 2.0,
    RelevanceLabel.HIGHLY_RELEVANT: 3.0,
}


class EvaluationSplit(str, enum.Enum):
    DEVELOPMENT = "DEVELOPMENT"
    HELD_OUT = "HELD_OUT"


class EvaluationAccuracyStatus(str, enum.Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    INSUFFICIENT_AUTHORIZED_DATA = "INSUFFICIENT_AUTHORIZED_DATA"
    HELD_OUT_BELOW_TARGET = "HELD_OUT_BELOW_TARGET"
    VERIFIED = "VERIFIED"


class EvaluationErrorCategory(str, enum.Enum):
    FALSE_CREDIT_UNSAFE_ALIAS = "FALSE_CREDIT_UNSAFE_ALIAS"
    MISSED_APPROVED_EQUIVALENCE = "MISSED_APPROVED_EQUIVALENCE"
    EXPERIENCE_INTERVAL_ERROR = "EXPERIENCE_INTERVAL_ERROR"
    RECENCY_ERROR = "RECENCY_ERROR"
    IRRELEVANT_EVIDENCE_CREDIT = "IRRELEVANT_EVIDENCE_CREDIT"
    PARSER_PROFILE_ERROR = "PARSER_PROFILE_ERROR"
    TAXONOMY_GAP = "TAXONOMY_GAP"
    WEIGHT_THRESHOLD_ISSUE = "WEIGHT_THRESHOLD_ISSUE"
    REVIEWER_DISAGREEMENT = "REVIEWER_DISAGREEMENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvaluationManifestRecord(StrictSchema):
    job_identifier: str = Field(min_length=1)
    revision: int = Field(ge=1)
    candidate_identifier: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    reviewer_code: str = Field(min_length=1)
    relevance_label: RelevanceLabel
    adjudicated_label: Optional[RelevanceLabel] = None
    split: EvaluationSplit
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_safety(self) -> "EvaluationManifestRecord":
        verify_no_prohibited_keys(self.model_dump(mode="json"))
        return self


class EvaluationManifest(StrictSchema):
    manifest_version: str = EVALUATION_MANIFEST_SCHEMA_VERSION
    dataset_identifier: str = Field(min_length=1)
    provenance_note: str = Field(min_length=1)
    authorization_note: str = Field(min_length=1)
    created_at: datetime
    records: List[EvaluationManifestRecord] = Field(min_length=1)
    manifest_checksum: str

    @model_validator(mode="after")
    def validate_integrity(self) -> "EvaluationManifest":
        verify_no_prohibited_keys(self.model_dump(mode="json"))

        # Check for duplicate reviewer ratings on same pair
        seen_reviewer_pairs = set()
        dev_cands = set()
        held_cands = set()

        for r in self.records:
            pair_key = (r.job_identifier, r.revision, r.candidate_identifier, r.profile_version, r.reviewer_code)
            if pair_key in seen_reviewer_pairs:
                raise ValueError(
                    f"Duplicate reviewer record for pair {r.job_identifier}:v{r.revision} / "
                    f"{r.candidate_identifier}:v{r.profile_version} by {r.reviewer_code}"
                )
            seen_reviewer_pairs.add(pair_key)

            cand_key = (r.candidate_identifier, r.profile_version)
            if r.split == EvaluationSplit.DEVELOPMENT:
                dev_cands.add(cand_key)
            elif r.split == EvaluationSplit.HELD_OUT:
                held_cands.add(cand_key)

        # Check split leakage: candidate profile variants crossing splits
        leakage = dev_cands.intersection(held_cands)
        if leakage:
            raise ValueError(f"Split leakage detected! Candidate(s) present in both DEVELOPMENT and HELD_OUT splits: {leakage}")

        return self


def compute_manifest_checksum(dataset_id: str, provenance: str, authorization: str, records: List[Dict[str, Any]]) -> str:
    """Computes deterministic canonical checksum for an evaluation manifest."""
    # Sort records deterministically
    sorted_records = sorted(
        records,
        key=lambda r: (
            str(r.get("job_identifier", r.get("jobIdentifier", ""))),
            int(r.get("revision", 1)),
            str(r.get("candidate_identifier", r.get("candidateIdentifier", ""))),
            int(r.get("profile_version", r.get("profileVersion", 1))),
            str(r.get("reviewer_code", r.get("reviewerCode", ""))),
            str(r.get("split", "")),
        ),
    )
    payload = {
        "dataset_identifier": dataset_id,
        "provenance_note": provenance,
        "authorization_note": authorization,
        "records": sorted_records,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest().lower()


class MacroF1Report(StrictSchema):
    macro_f1: float
    per_label_f1: Dict[str, float]
    support_per_label: Dict[str, int]
    confusion_matrix: Dict[str, Dict[str, int]]
    zero_division_handled: bool = True


class NDCG5Report(StrictSchema):
    mean_ndcg_at_5: float
    per_job_ndcg: Dict[str, float]
    candidates_per_job: Dict[str, int]
    excluded_jobs_count: int


class SpearmanReport(StrictSchema):
    correlation: Optional[float] = None
    evaluated_pairs_count: int
    evaluated_jobs_count: int
    is_defined: bool
    undefined_reason: Optional[str] = None


class InterRaterAgreementReport(StrictSchema):
    percent_agreement: float
    cohen_kappa: Optional[float] = None
    total_overlapping_pairs: int
    rater1_code: str
    rater2_code: str


class EvaluationReport(StrictSchema):
    report_id: UUID
    evaluation_status: EvaluationAccuracyStatus
    dataset_identifier: str
    manifest_checksum: str
    scoring_policy_version: str
    matcher_algorithm_version: str
    threshold_policy_hash: str
    split_evaluated: EvaluationSplit
    macro_f1_report: Optional[MacroF1Report] = None
    ndcg_report: Optional[NDCG5Report] = None
    spearman_report: Optional[SpearmanReport] = None
    inter_rater_agreement: Optional[InterRaterAgreementReport] = None
    status_reason: str
    limitations: List[str]
    sample_sizes: Dict[str, int]
    reviewed_error_categories: Dict[str, int] = Field(default_factory=dict)
    evaluated_at: datetime
