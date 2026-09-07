from datetime import datetime, timezone
import pytest

from app.schemas.evaluation import (
    EvaluationAccuracyStatus,
    EvaluationManifest,
    EvaluationManifestRecord,
    EvaluationSplit,
    RelevanceLabel,
    compute_manifest_checksum,
)
from app.schemas.matching import verify_no_prohibited_keys
from app.services.evaluation import (
    calculate_cohen_kappa,
    calculate_macro_f1,
    calculate_ndcg_at_k,
    calculate_spearman_correlation,
    evaluate_matching_manifest,
)


def test_manifest_validation_and_leakage_rejection():
    """Validates manifest integrity and ensures split leakage (candidate crossing splits) is rejected."""
    now = datetime.now(timezone.utc)
    rec1 = EvaluationManifestRecord(
        job_identifier="job_001",
        revision=1,
        candidate_identifier="cand_001",
        profile_version=1,
        reviewer_code="rev_a",
        relevance_label=RelevanceLabel.HIGHLY_RELEVANT,
        split=EvaluationSplit.DEVELOPMENT,
    )
    rec2 = EvaluationManifestRecord(
        job_identifier="job_001",
        revision=1,
        candidate_identifier="cand_002",
        profile_version=1,
        reviewer_code="rev_a",
        relevance_label=RelevanceLabel.NOT_RELEVANT,
        split=EvaluationSplit.HELD_OUT,
    )

    records = [rec1.model_dump(), rec2.model_dump()]
    chk = compute_manifest_checksum("dataset_valid", "Audit Corp", "Recruiter Board", records)

    manifest = EvaluationManifest(
        dataset_identifier="dataset_valid",
        provenance_note="Audit Corp",
        authorization_note="Recruiter Board",
        created_at=now,
        records=[rec1, rec2],
        manifest_checksum=chk,
    )
    assert manifest.dataset_identifier == "dataset_valid"

    # Test duplicate reviewer record rejected
    rec1_dup = EvaluationManifestRecord(
        job_identifier="job_001",
        revision=1,
        candidate_identifier="cand_001",
        profile_version=1,
        reviewer_code="rev_a",
        relevance_label=RelevanceLabel.RELEVANT,
        split=EvaluationSplit.DEVELOPMENT,
    )
    with pytest.raises(ValueError, match="Duplicate reviewer record"):
        EvaluationManifest(
            dataset_identifier="dataset_dup",
            provenance_note="Audit Corp",
            authorization_note="Recruiter Board",
            created_at=now,
            records=[rec1, rec1_dup],
            manifest_checksum="chk",
        )

    # Test split leakage rejected (same candidate variant in DEV and HELD_OUT)
    rec_leaked = EvaluationManifestRecord(
        job_identifier="job_002",
        revision=1,
        candidate_identifier="cand_001",  # Same candidate variant as rec1
        profile_version=1,
        reviewer_code="rev_b",
        relevance_label=RelevanceLabel.RELEVANT,
        split=EvaluationSplit.HELD_OUT,
    )
    with pytest.raises(ValueError, match="Split leakage detected"):
        EvaluationManifest(
            dataset_identifier="dataset_leak",
            provenance_note="Audit Corp",
            authorization_note="Recruiter Board",
            created_at=now,
            records=[rec1, rec_leaked],
            manifest_checksum="chk",
        )


def test_macro_f1_metric_formula():
    """Validates pure-Python macro-F1 calculation against known edge cases."""
    # 1. Perfect predictions -> 1.0
    y_true = ["A", "B", "C", "A", "B"]
    y_pred = ["A", "B", "C", "A", "B"]
    rep = calculate_macro_f1(y_true, y_pred, labels=["A", "B", "C"])
    assert rep.macro_f1 == 1.0
    assert rep.per_label_f1 == {"A": 1.0, "B": 1.0, "C": 1.0}

    # 2. Complete mismatch -> 0.0
    y_true_mismatch = ["A", "A", "A"]
    y_pred_mismatch = ["B", "B", "B"]
    rep_m = calculate_macro_f1(y_true_mismatch, y_pred_mismatch, labels=["A", "B"])
    assert rep_m.macro_f1 == 0.0

    # 3. Class imbalance demonstrates macro (unweighted) average
    # For label A:
    # True A -> predicted A (TP=1, FP=1 from True B predicted A, FN=0) -> Precision = 1/2, Recall = 1/1 -> F1 = 2*(0.5*1.0)/1.5 = 2/3 = 0.666667
    # For label B:
    # True B -> predicted A (TP=0, FP=0, FN=1) -> Precision = 0, Recall = 0 -> F1 = 0.0
    # Macro F1 = (2/3 + 0) / 2 = 1/3 = 0.333333
    y_true_imb = ["A", "B"]
    y_pred_imb = ["A", "A"]
    rep_imb = calculate_macro_f1(y_true_imb, y_pred_imb, labels=["A", "B"])
    assert rep_imb.per_label_f1["A"] == 0.666667
    assert rep_imb.per_label_f1["B"] == 0.0
    assert abs(rep_imb.macro_f1 - (1.0 / 3.0)) < 1e-5


def test_ndcg_metric_formula():
    """Validates NDCG@5 calculation with ideal, reversed, and tie rankings."""
    # 1. Perfect ranking: higher relevance scores have higher predicted scores
    actual = [3.0, 2.0, 1.0, 0.0]
    preds = [95.0, 80.0, 60.0, 20.0]
    assert calculate_ndcg_at_k(actual, preds, k=5) == 1.0

    # 2. Reversed ranking: lowest relevance gets highest score
    preds_rev = [20.0, 60.0, 80.0, 95.0]
    ndcg_rev = calculate_ndcg_at_k(actual, preds_rev, k=5)
    assert ndcg_rev < 1.0
    assert ndcg_rev > 0.0

    # 3. Tied predictions: stable calculation
    preds_tied = [50.0, 50.0, 50.0, 50.0]
    ndcg_tied = calculate_ndcg_at_k(actual, preds_tied, k=5)
    assert ndcg_tied > 0.0


def test_spearman_correlation_formula():
    """Validates Spearman rank correlation with ties, monotonicity, and constant inputs."""
    # 1. Perfectly monotonic increasing -> 1.0
    x = [10.0, 20.0, 30.0, 40.0]
    y = [1.0, 2.0, 3.0, 4.0]
    rep = calculate_spearman_correlation(x, y)
    assert rep.is_defined is True
    assert rep.correlation == 1.0

    # 2. Perfectly monotonic decreasing -> -1.0
    y_inv = [4.0, 3.0, 2.0, 1.0]
    rep_inv = calculate_spearman_correlation(x, y_inv)
    assert rep_inv.correlation == -1.0

    # 3. Constant inputs -> undefined, not fabricated
    x_const = [5.0, 5.0, 5.0]
    y_const = [1.0, 2.0, 3.0]
    rep_c = calculate_spearman_correlation(x_const, y_const)
    assert rep_c.is_defined is False
    assert rep_c.correlation is None


def test_inter_rater_agreement_and_kappa():
    """Validates Cohen's kappa and percent agreement calculation."""
    # Perfect agreement
    r1 = ["RELEVANT", "NOT_RELEVANT", "HIGHLY_RELEVANT"]
    r2 = ["RELEVANT", "NOT_RELEVANT", "HIGHLY_RELEVANT"]
    rep = calculate_cohen_kappa(r1, r2)
    assert rep.percent_agreement == 1.0
    assert rep.cohen_kappa == 1.0

    # Known agreement
    r1_k = ["A", "A", "B", "B"]
    r2_k = ["A", "B", "B", "B"]
    rep_k = calculate_cohen_kappa(r1_k, r2_k)
    assert rep_k.percent_agreement == 0.75
    assert rep_k.cohen_kappa is not None


def test_locked_accuracy_claim_gate():
    """Gate refuses to claim VERIFIED if split is DEVELOPMENT_ONLY, sample is small, or macro-F1 < 0.85."""
    now = datetime.now(timezone.utc)
    records = []
    # Create 35 pairs in HELD_OUT split
    for i in range(35):
        records.append(
            EvaluationManifestRecord(
                job_identifier="job_001",
                revision=1,
                candidate_identifier=f"cand_{i:03d}",
                profile_version=1,
                reviewer_code="rev_a",
                relevance_label=RelevanceLabel.HIGHLY_RELEVANT,
                split=EvaluationSplit.HELD_OUT,
            )
        )

    manifest = EvaluationManifest(
        dataset_identifier="corp_held_out_35",
        provenance_note="HR Oversight",
        authorization_note="Approved Protocol",
        created_at=now,
        records=records,
        manifest_checksum="chk_35",
    )

    # 1. Sub-target performance (< 0.85 macro-F1) -> HELD_OUT_BELOW_TARGET
    preds_low = {
        ("job_001", 1, f"cand_{i:03d}", 1): {
            "score": 40.0,
            "predicted_label": RelevanceLabel.NOT_RELEVANT.value if i < 20 else RelevanceLabel.HIGHLY_RELEVANT.value,
        }
        for i in range(35)
    }
    rep_low = evaluate_matching_manifest(manifest, preds_low, frozen_policy_hash="p_hash")
    assert rep_low.evaluation_status == EvaluationAccuracyStatus.HELD_OUT_BELOW_TARGET

    # 2. Target met (macro-F1 >= 0.85 on held-out with adequate sample) -> VERIFIED
    preds_high = {
        ("job_001", 1, f"cand_{i:03d}", 1): {
            "score": 90.0,
            "predicted_label": RelevanceLabel.HIGHLY_RELEVANT.value,
        }
        for i in range(35)
    }
    rep_high = evaluate_matching_manifest(manifest, preds_high, frozen_policy_hash="p_hash")
    assert rep_high.evaluation_status == EvaluationAccuracyStatus.VERIFIED
    assert rep_high.macro_f1_report.macro_f1 >= 0.85


def test_spearman_undefined_when_constant_labels():
    """Undefined cases such as constant human labels or constant system scores are reported, not fabricated."""
    # System scores constant
    preds_const = [75.0, 75.0, 75.0, 75.0]
    actual_varying = [1.0, 2.0, 3.0, 4.0]
    rep = calculate_spearman_correlation(actual_varying, preds_const)
    assert rep.is_defined is False
    assert rep.correlation is None
    assert "Constant input" in str(rep.undefined_reason)

    # Actual relevance constant
    actual_const = [2.0, 2.0, 2.0]
    preds_varying = [10.0, 50.0, 90.0]
    rep2 = calculate_spearman_correlation(actual_const, preds_varying)
    assert rep2.is_defined is False
    assert rep2.correlation is None


def test_ndcg_ranking_ties_handled():
    """NDCG@5 handles tied predictions without crashing or non-monotonic values."""
    actual = [3.0, 2.0, 2.0, 1.0, 0.0]
    preds = [80.0, 70.0, 70.0, 50.0, 30.0]
    ndcg = calculate_ndcg_at_k(actual, preds, k=5)
    assert 0.0 < ndcg <= 1.0


def test_accuracy_gate_development_only():
    """Manifest evaluated on DEVELOPMENT split results in DEVELOPMENT_ONLY status."""
    now = datetime.now(timezone.utc)
    rec = EvaluationManifestRecord(
        job_identifier="job_001",
        revision=1,
        candidate_identifier="cand_dev_01",
        profile_version=1,
        reviewer_code="rev_a",
        relevance_label=RelevanceLabel.HIGHLY_RELEVANT,
        split=EvaluationSplit.DEVELOPMENT,
    )
    manifest = EvaluationManifest(
        dataset_identifier="dev_dataset",
        provenance_note="Internal Dev Set",
        authorization_note="Authorized for tuning only",
        created_at=now,
        records=[rec],
        manifest_checksum="chk_dev",
    )
    preds = {
        ("job_001", 1, "cand_dev_01", 1): {
            "score": 95.0,
            "predicted_label": RelevanceLabel.HIGHLY_RELEVANT.value,
        }
    }
    rep = evaluate_matching_manifest(manifest, preds, frozen_policy_hash="p_hash", target_split=EvaluationSplit.DEVELOPMENT)
    assert rep.evaluation_status == EvaluationAccuracyStatus.DEVELOPMENT_ONLY
    assert "DEVELOPMENT split only" in rep.status_reason
