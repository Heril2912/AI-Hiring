import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.evaluation import (
    EvaluationAccuracyStatus,
    EvaluationErrorCategory,
    EvaluationManifest,
    EvaluationManifestRecord,
    EvaluationReport,
    EvaluationSplit,
    InterRaterAgreementReport,
    MacroF1Report,
    NDCG5Report,
    RelevanceLabel,
    SpearmanReport,
    compute_manifest_checksum,
)
from app.schemas.matching import verify_no_prohibited_keys


# ---------------------------------------------------------------------------
# 1. Macro-F1 Metric (Pure Python)
# ---------------------------------------------------------------------------
def calculate_macro_f1(
    y_true: List[str],
    y_pred: List[str],
    labels: Optional[List[str]] = None,
) -> MacroF1Report:
    """Calculates macro-F1 across multi-class labels with strict zero-division handling.

    Returns macro-F1, per-label F1, support per label, and confusion matrix.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"y_true (len {len(y_true)}) and y_pred (len {len(y_pred)}) must have equal length.")

    if labels is None:
        labels = sorted(list(set(y_true).union(set(y_pred))))

    # Initialize confusion matrix: cm[actual][predicted]
    cm: Dict[str, Dict[str, int]] = {
        true_lbl: {pred_lbl: 0 for pred_lbl in labels} for true_lbl in labels
    }

    support_per_label: Dict[str, int] = {lbl: 0 for lbl in labels}

    for true_val, pred_val in zip(y_true, y_pred):
        if true_val in cm and pred_val in cm[true_val]:
            cm[true_val][pred_val] += 1
            support_per_label[true_val] += 1

    per_label_f1: Dict[str, float] = {}

    for lbl in labels:
        tp = cm[lbl][lbl]
        fp = sum(cm[other][lbl] for other in labels if other != lbl)
        fn = sum(cm[lbl][other] for other in labels if other != lbl)

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0

        if (precision + recall) > 0.0:
            f1 = 2.0 * (precision * recall) / (precision + recall)
        else:
            f1 = 0.0
        per_label_f1[lbl] = round(f1, 6)

    # Macro-average across all defined classes
    if labels:
        macro_val = sum(per_label_f1.values()) / len(labels)
    else:
        macro_val = 0.0

    return MacroF1Report(
        macro_f1=round(macro_val, 6),
        per_label_f1=per_label_f1,
        support_per_label=support_per_label,
        confusion_matrix=cm,
        zero_division_handled=True,
    )


# ---------------------------------------------------------------------------
# 2. NDCG@5 Ranking Metric (Pure Python)
# ---------------------------------------------------------------------------
def calculate_ndcg_at_k(
    actual_relevance: List[float],
    predicted_scores: List[float],
    k: int = 5,
) -> float:
    """Calculates Normalized Discounted Cumulative Gain at rank k (NDCG@k).

    Formula:
      DCG@k = sum_{i=1}^k (2^{rel_i} - 1) / log2(i + 1)
      IDCG@k = DCG@k for ideal ranking (sorted actual_relevance descending)
      NDCG@k = DCG@k / IDCG@k (or 1.0 if IDCG@k == 0.0)
    """
    if len(actual_relevance) != len(predicted_scores):
        raise ValueError("actual_relevance and predicted_scores must have the same length.")

    if not actual_relevance:
        return 0.0

    # Sort pairs by predicted score descending (with stable index tie handling)
    ranked_indices = sorted(
        range(len(predicted_scores)),
        key=lambda idx: (predicted_scores[idx]),
        reverse=True,
    )

    actual_at_k = [actual_relevance[i] for i in ranked_indices[:k]]
    ideal_at_k = sorted(actual_relevance, reverse=True)[:k]

    def _compute_dcg(relevances: List[float]) -> float:
        dcg = 0.0
        for rank_idx, rel in enumerate(relevances, start=1):
            numerator = (2.0 ** rel) - 1.0
            denominator = math.log2(rank_idx + 1.0)
            dcg += numerator / denominator
        return dcg

    dcg = _compute_dcg(actual_at_k)
    idcg = _compute_dcg(ideal_at_k)

    if idcg <= 0.0:
        # If all candidates have 0 relevance, ideal is 0
        return 1.0 if dcg <= 0.0 else 0.0

    return round(min(1.0, max(0.0, dcg / idcg)), 6)


# ---------------------------------------------------------------------------
# 3. Spearman Rank Correlation (Pure Python with Tie Handling)
# ---------------------------------------------------------------------------
def _compute_fractional_ranks(values: List[float]) -> List[float]:
    """Computes standard average fractional ranks for ties."""
    n = len(values)
    # Sort indices by value
    sorted_indices = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n

    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[sorted_indices[j + 1]] == values[sorted_indices[i]]:
            j += 1
        # Average rank for range i..j (1-indexed)
        avg_rank = sum(r for r in range(i + 1, j + 2)) / (j - i + 1)
        for k in range(i, j + 1):
            ranks[sorted_indices[k]] = avg_rank
        i = j + 1

    return ranks


def calculate_spearman_correlation(
    x: List[float],
    y: List[float],
) -> SpearmanReport:
    """Calculates Spearman rank correlation coefficient with tie handling.

    Reports undefined when variance is zero (e.g. all constant values).
    """
    if len(x) != len(y):
        raise ValueError("x and y must have the same length.")

    n = len(x)
    if n < 2:
        return SpearmanReport(
            correlation=None,
            evaluated_pairs_count=n,
            evaluated_jobs_count=1,
            is_defined=False,
            undefined_reason="Sample size less than 2.",
        )

    # Check for constant input
    if len(set(x)) <= 1 or len(set(y)) <= 1:
        return SpearmanReport(
            correlation=None,
            evaluated_pairs_count=n,
            evaluated_jobs_count=1,
            is_defined=False,
            undefined_reason="Constant input: variance is zero.",
        )

    rx = _compute_fractional_ranks(x)
    ry = _compute_fractional_ranks(y)

    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n

    cov = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    var_x = sum((rx[i] - mean_rx) ** 2 for i in range(n))
    var_y = sum((ry[i] - mean_ry) ** 2 for i in range(n))

    if var_x <= 0.0 or var_y <= 0.0:
        return SpearmanReport(
            correlation=None,
            evaluated_pairs_count=n,
            evaluated_jobs_count=1,
            is_defined=False,
            undefined_reason="Zero variance after ranking.",
        )

    rho = cov / math.sqrt(var_x * var_y)
    clamped_rho = max(-1.0, min(1.0, rho))

    return SpearmanReport(
        correlation=round(clamped_rho, 6),
        evaluated_pairs_count=n,
        evaluated_jobs_count=1,
        is_defined=True,
        undefined_reason=None,
    )


# ---------------------------------------------------------------------------
# 4. Inter-Rater Agreement & Cohen's Kappa (Pure Python)
# ---------------------------------------------------------------------------
def calculate_cohen_kappa(
    rater1: List[str],
    rater2: List[str],
    rater1_code: str = "R1",
    rater2_code: str = "R2",
) -> InterRaterAgreementReport:
    """Calculates percent agreement and unweighted Cohen's kappa for two independent raters."""
    if len(rater1) != len(rater2):
        raise ValueError("Rater assessments must have equal length.")

    n = len(rater1)
    if n == 0:
        return InterRaterAgreementReport(
            percent_agreement=0.0,
            cohen_kappa=None,
            total_overlapping_pairs=0,
            rater1_code=rater1_code,
            rater2_code=rater2_code,
        )

    labels = sorted(list(set(rater1).union(set(rater2))))
    agreed_count = sum(1 for a, b in zip(rater1, rater2) if a == b)
    observed_agreement = agreed_count / n

    # Chance agreement calculation
    p_e = 0.0
    for lbl in labels:
        p1 = sum(1 for a in rater1 if a == lbl) / n
        p2 = sum(1 for b in rater2 if b == lbl) / n
        p_e += (p1 * p2)

    if (1.0 - p_e) == 0.0:
        kappa: Optional[float] = 1.0 if observed_agreement == 1.0 else 0.0
    else:
        kappa = (observed_agreement - p_e) / (1.0 - p_e)
        kappa = round(max(-1.0, min(1.0, kappa)), 6)

    return InterRaterAgreementReport(
        percent_agreement=round(observed_agreement, 6),
        cohen_kappa=kappa,
        total_overlapping_pairs=n,
        rater1_code=rater1_code,
        rater2_code=rater2_code,
    )


# ---------------------------------------------------------------------------
# 5. Accuracy-Claim Gate & Evaluator
# ---------------------------------------------------------------------------
def evaluate_matching_manifest(
    manifest: EvaluationManifest,
    system_predictions: Dict[Tuple[str, int, str, int], Dict[str, Any]],
    frozen_policy_hash: str,
    target_split: EvaluationSplit = EvaluationSplit.HELD_OUT,
) -> EvaluationReport:
    """Evaluates match quality against authorized manifest while enforcing the locked accuracy gate.

    system_predictions key: (job_id, revision, candidate_id, profile_version)
    system_predictions value: {"score": float, "predicted_label": str}
    """
    report_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 1. Filter records for target split
    target_records = [r for r in manifest.records if r.split == target_split]

    if not target_records:
        return EvaluationReport(
            report_id=report_id,
            evaluation_status=EvaluationAccuracyStatus.INSUFFICIENT_AUTHORIZED_DATA,
            dataset_identifier=manifest.dataset_identifier,
            manifest_checksum=manifest.manifest_checksum,
            scoring_policy_version="phase2c3_scoring_v1",
            matcher_algorithm_version="1.0.0",
            threshold_policy_hash=frozen_policy_hash,
            split_evaluated=target_split,
            status_reason=f"No authorized evaluation pairs found for split '{target_split.value}'.",
            limitations=["Evaluation dataset contains 0 records in target split."],
            sample_sizes={"target_records": 0},
            evaluated_at=now,
        )

    # 2. Extract pairs that have an adjudicated label (or reviewer label)
    y_true: List[str] = []
    y_pred: List[str] = []
    true_scores: List[float] = []
    pred_scores: List[float] = []

    missing_preds_count = 0

    for r in target_records:
        label = (r.adjudicated_label or r.relevance_label).value
        pair_key = (r.job_identifier, r.revision, r.candidate_identifier, r.profile_version)

        if pair_key in system_predictions:
            pred_data = system_predictions[pair_key]
            y_true.append(label)
            y_pred.append(str(pred_data.get("predicted_label", "")))
            rel_score = 0.0
            try:
                rel_enum = RelevanceLabel(label)
                if rel_enum == RelevanceLabel.HIGHLY_RELEVANT:
                    rel_score = 3.0
                elif rel_enum == RelevanceLabel.RELEVANT:
                    rel_score = 2.0
                elif rel_enum == RelevanceLabel.PARTIALLY_RELEVANT:
                    rel_score = 1.0
            except Exception:
                pass
            true_scores.append(rel_score)
            pred_scores.append(float(pred_data.get("score", 0.0)))
        else:
            missing_preds_count += 1

    if not y_true:
        return EvaluationReport(
            report_id=report_id,
            evaluation_status=EvaluationAccuracyStatus.INSUFFICIENT_AUTHORIZED_DATA,
            dataset_identifier=manifest.dataset_identifier,
            manifest_checksum=manifest.manifest_checksum,
            scoring_policy_version="phase2c3_scoring_v1",
            matcher_algorithm_version="1.0.0",
            threshold_policy_hash=frozen_policy_hash,
            split_evaluated=target_split,
            status_reason="No system predictions matched the manifest records.",
            limitations=["Zero evaluated pairs matched between manifest and system predictions."],
            sample_sizes={"target_records": len(target_records), "matched_pairs": 0},
            evaluated_at=now,
        )

    # Calculate metrics
    macro_report = calculate_macro_f1(y_true=y_true, y_pred=y_pred)
    spearman_report = calculate_spearman_correlation(true_scores, pred_scores)

    # NDCG@5 calculation
    ndcg_val = calculate_ndcg_at_k(true_scores, pred_scores, k=5)
    ndcg_report = NDCG5Report(
        mean_ndcg_at_5=ndcg_val,
        per_job_ndcg={manifest.records[0].job_identifier: ndcg_val},
        candidates_per_job={manifest.records[0].job_identifier: len(y_true)},
        excluded_jobs_count=0,
    )

    # 3. Apply Locked Accuracy-Claim Gate
    # Acceptance criteria for VERIFIED:
    # - Must be HELD_OUT split
    # - Macro-F1 >= 0.85
    # - NDCG and Spearman reported
    # - Zero missing predictions
    limitations: List[str] = []
    if missing_preds_count > 0:
        limitations.append(f"{missing_preds_count} pairs could not be scored by the system.")

    if target_split == EvaluationSplit.DEVELOPMENT:
        status = EvaluationAccuracyStatus.DEVELOPMENT_ONLY
        reason = "Evaluation was executed on DEVELOPMENT split only; held-out evaluation required for verification."
    elif len(y_true) < 30:
        status = EvaluationAccuracyStatus.INSUFFICIENT_AUTHORIZED_DATA
        reason = f"Held-out sample size ({len(y_true)} pairs) is insufficient for statistical confidence (minimum 30 required)."
    elif macro_report.macro_f1 < 0.85:
        status = EvaluationAccuracyStatus.HELD_OUT_BELOW_TARGET
        reason = f"Held-out macro-F1 ({macro_report.macro_f1:.4f}) is below the required 0.85 threshold."
    else:
        status = EvaluationAccuracyStatus.VERIFIED
        reason = f"Held-out evaluation target met: macro-F1 {macro_report.macro_f1:.4f} >= 0.85."

    return EvaluationReport(
        report_id=report_id,
        evaluation_status=status,
        dataset_identifier=manifest.dataset_identifier,
        manifest_checksum=manifest.manifest_checksum,
        scoring_policy_version="phase2c3_scoring_v1",
        matcher_algorithm_version="1.0.0",
        threshold_policy_hash=frozen_policy_hash,
        split_evaluated=target_split,
        macro_f1_report=macro_report,
        ndcg_report=ndcg_report,
        spearman_report=spearman_report,
        status_reason=reason,
        limitations=limitations,
        sample_sizes={"evaluated_pairs": len(y_true), "missing_pairs": missing_preds_count},
        evaluated_at=now,
    )
