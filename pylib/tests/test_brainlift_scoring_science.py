# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Area 2 (score accuracy & honest uncertainty) science tests.

Covers three things the audit flagged as missing:

1. **Memory calibration** — the FSRS predicted-recall calibration eval computes a
   finite Brier score + log-loss and a monotone-ish reliability curve.
2. **Performance held-out eval** — a fitted predictor beats a majority baseline
   on a disjoint held-out set.
3. **Per-score metadata parity** — Memory & Performance expose the same
   confidence / coverage / reasons metadata that Readiness has, using thresholds
   mirrored in the Android engine (BrainLiftEngine.kt / BrainLiftParityTest.kt).

It also cross-checks the desktop Rust ``TopicMastery`` semantics
(``total_reviews`` = sum of reps) that the Android ``aggregateTopicMastery``
mirrors.
"""

from __future__ import annotations

import math
import os
import sys

from anki.brainlift import diagnostic as dx
from anki.brainlift import exam_p, measurements
from tests.shared import getEmptyCol

# Make the eval scripts (repo-root/brainlift_eval) importable.
_EVAL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "brainlift_eval")
)
if _EVAL_DIR not in sys.path:
    sys.path.insert(0, _EVAL_DIR)

import memory_calibration_eval as mce  # noqa: E402
import performance_holdout_eval as phe  # noqa: E402


# --- 1. Memory calibration eval ---------------------------------------------


def test_memory_calibration_metrics_finite_and_monotone():
    pred, act = mce.make_pool(mce.TEST_N, mce.TEST_SEED)
    brier = mce.brier_score(pred, act)
    ll = mce.log_loss(pred, act)
    bins = mce.reliability_bins(pred, act)

    assert math.isfinite(brier) and 0.0 <= brier <= 1.0
    assert math.isfinite(ll) and ll >= 0.0
    assert brier <= mce.BRIER_CUTOFF
    # Every populated bin has finite predicted/observed values.
    populated = [b for b in bins if b["n"] > 0]
    assert len(populated) >= 8  # the diagram spans essentially the whole [0,1]
    for b in populated:
        assert math.isfinite(b["mean_pred"]) and math.isfinite(b["obs_rate"])
    # Observed recall rises with predicted recall (monotone-ish).
    obs = [b["obs_rate"] for b in bins]
    assert mce._monotone_nondecreasing(obs)


def test_memory_calibration_metric_helpers():
    # Perfect predictions -> Brier 0.
    assert mce.brier_score([1.0, 0.0, 1.0], [1, 0, 1]) == 0.0
    # A constant 0.5 guesser on balanced data -> Brier 0.25.
    assert abs(mce.brier_score([0.5, 0.5], [1, 0]) - 0.25) < 1e-12
    assert math.isfinite(mce.log_loss([0.9, 0.1], [1, 0]))


def test_memory_calibration_eval_run_passes():
    assert mce.run() is True


# --- 2. Performance held-out eval -------------------------------------------


def test_performance_holdout_beats_baseline():
    x_fit, y_fit = phe.make_dataset(phe.FIT_N, phe.FIT_SEED)
    x_test, y_test = phe.make_dataset(phe.TEST_N, phe.TEST_SEED)
    w, b = phe.fit_logreg(x_fit, y_fit)
    probs = phe.predict_proba(x_test, w, b)

    acc = phe.accuracy(probs, y_test)
    base_acc, _ = phe.majority_baseline_accuracy(y_fit, y_test)

    assert math.isfinite(acc)
    assert acc >= phe.ACC_ABS_CUTOFF
    assert acc - base_acc >= phe.ACC_LIFT_CUTOFF
    # Held-out (test) seed must be disjoint from the fit seed.
    assert phe.FIT_SEED != phe.TEST_SEED


def test_performance_holdout_eval_run_passes():
    assert phe.run() is True


# --- 3a. Per-score metadata: Memory -----------------------------------------


def _coverage_with(reviewed_cards: int, studied_coverage: float, avg_r: float):
    topic = exam_p.TopicReport(
        key="GeneralProbability",
        name="General Probability",
        weight=26.5,
        total_cards=300,
        reviewed_cards=reviewed_cards,
        mastered_cards=200,
        total_reviews=900,
        average_retrievability=avg_r,
        covered=True,
        status=exam_p.COVERED,
    )
    return exam_p.CoverageReport(
        topics=[topic],
        coverage_percent=100.0,
        studied_coverage_percent=studied_coverage,
        mastered_percent=66.7,
    )


def test_memory_exposes_full_metadata():
    m = measurements.compute_memory(_coverage_with(250, 85.0, 0.8))
    assert m.available
    assert m.confidence_level == "high"
    assert m.coverage_percent == 85.0
    assert m.last_updated > 0
    assert m.reasons == [
        "FSRS recall over 250 reviewed cards",
        "85% of the syllabus studied",
        "High confidence: broad, well-reviewed coverage",
    ]


def test_memory_confidence_thresholds():
    assert measurements._memory_confidence(200, 80.0) == "high"
    assert measurements._memory_confidence(50, 50.0) == "medium"
    # High review volume but low coverage -> only medium.
    assert measurements._memory_confidence(500, 50.0) == "medium"
    assert measurements._memory_confidence(49, 90.0) == "low"
    assert measurements._memory_confidence(0, 0.0) == "low"


# --- 3b. Per-score metadata: Performance ------------------------------------


def test_performance_exposes_full_metadata():
    col = getEmptyCol()
    responses = [dx.DiagnosticResponse(q.id, q.correct_index) for q in dx.QUESTION_BANK]
    dx.run_diagnostic(col, responses)
    p = measurements.compute_performance(col)
    assert p.available
    assert p.answered == 12
    assert p.confidence_level == "high"
    assert p.coverage_percent == 100.0
    assert p.last_updated > 0
    assert p.reasons == [
        "Transfer accuracy over 12 diagnostic questions",
        "12 of 12 question bank answered (100%)",
        "High confidence: full diagnostic completed",
    ]


def test_performance_confidence_thresholds():
    assert measurements._performance_confidence(12) == "high"
    assert measurements._performance_confidence(6) == "medium"
    assert measurements._performance_confidence(11) == "medium"
    assert measurements._performance_confidence(5) == "low"
    assert measurements._performance_confidence(0) == "low"


def test_partial_diagnostic_reports_medium_confidence_and_coverage():
    col = getEmptyCol()
    # Answer 6 of 12 questions -> medium confidence, 50% coverage.
    responses = [
        dx.DiagnosticResponse(q.id, q.correct_index) for q in dx.QUESTION_BANK[:6]
    ]
    dx.run_diagnostic(col, responses)
    p = measurements.compute_performance(col)
    assert p.answered == 6
    assert p.confidence_level == "medium"
    assert p.coverage_percent == 50.0


# --- Kotlin<->Rust coverage parity: total_reviews = sum(reps) ----------------


def test_rust_topic_mastery_total_reviews_is_sum_of_reps():
    """Desktop Rust semantics the Android `aggregateTopicMastery` mirrors.

    The identical Kotlin fixture is in BrainLiftParityTest.kt
    (`topicMasteryAggregationMatchesRustSemantics` /
    `perTopicTotalReviewsIsRepsSumNotCardCount`).
    """
    col = getEmptyCol()

    def _add(tag: str):
        note = col.newNote()
        note["Front"] = tag
        note.tags = [tag]
        col.addNote(note)

    _add("ExamP::GeneralProbability")
    _add("ExamP::GeneralProbability")
    _add("ExamP::GeneralProbability")

    # Give the three cards known rep counts: 10, 3, 0.
    cids = sorted(col.find_cards("tag:ExamP::GeneralProbability"))
    for cid, reps in zip(cids, (10, 3, 0)):
        col.db.execute("update cards set reps=? where id=?", reps, cid)

    resp = col.topic_mastery(
        [("General Probability", exam_p.SYLLABUS[0].search)], 0.0
    )
    topic = resp.topics[0]

    assert topic.total_cards == 3
    assert topic.reviewed_cards == 2  # reps>0: two cards
    assert topic.total_reviews == 13  # SUM of reps 10+3+0 (NOT the card count)
    assert topic.total_reviews != topic.reviewed_cards
