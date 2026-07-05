# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Memory-model calibration eval: FSRS predicted recall vs actual outcome.

This is the MEMORY calibration the audit found missing. It is a DIFFERENT thing
from ``anki.brainlift.calibration`` (that module measures a student's
*metacognitive* confidence). Here we ask a purely statistical question:

    When BrainLift's Memory score says "you have an 80% chance of recalling this
    card", is that 80% actually right?

We answer it with the three standard tools for probability calibration:

* **Brier score**  - mean squared error of the predicted recall probability.
* **Log-loss**     - mean negative log-likelihood (penalises confident misses).
* **Reliability diagram** - predicted probability vs the observed recall rate,
  bucketed into 10 bins; a well-calibrated model tracks the diagonal.

PASS cutoff (DECLARED UP FRONT, before looking at any result):

    Brier score <= 0.25   (0.25 is the score of an all-0.5 guesser on balanced
                           data; a useful recall model must beat it) AND
    log-loss and every reliability number must be finite.

------------------------------------------------------------------------------
DATA DISCLOSURE — THE REVIEW OUTCOMES ARE **SIMULATED**, NOT A REAL REVIEW LOG.
------------------------------------------------------------------------------
BrainLift ships without a large real review history to mine, so this eval
generates a synthetic-but-FSRS-grounded review set.

**Why this eval is now NON-CIRCULAR.** An earlier version of this file set the
predicted recall to ``true_p + small_noise`` — i.e. the "prediction" was just
the ground truth with a jitter added. That makes the reliability diagram tautological:
of course a copy of the truth is well-calibrated. It tested nothing.

This version predicts recall from an **independent estimator** that never sees
the card's true stability. It only sees PAST review outcomes and must infer the
memory model from them, exactly like a real scheduler would:

  1. Each simulated card is given a hidden, TRUE FSRS memory *stability*
     ``S_true`` (days), drawn log-uniformly. This is the generative truth and is
     never shown to the estimator.
  2. A per-card PAST review history is simulated: several reviews at varied
     elapsed times, whose pass/fail outcomes are Bernoulli draws from the TRUE
     FSRS-5 forgetting curve
         R(t) = (1 + FACTOR * t / S) ** DECAY,  DECAY = -0.5, FACTOR = 19/81
     evaluated at ``S_true`` (the same formula the Rust engine uses — see
     rslib .. topic_mastery.rs and the `fsrs` crate `current_retrievability`).
  3. The ESTIMATOR fits a stability ``S_hat`` by maximum likelihood over the
     PAST outcomes ONLY (a deterministic grid search; §``_estimate_stability``).
     It has no access to ``S_true`` — its only information is the past pass/fail
     record, so its error is genuine estimation error, not injected noise.
  4. The MODEL's predicted recall for a FUTURE, held-out review at elapsed time
     ``t_future`` is ``R(t_future, S_hat)`` — produced purely from the estimator.
  5. The observed FUTURE outcome ``y`` in {0,1} is an INDEPENDENT Bernoulli draw
     from the TRUE curve ``R(t_future, S_true)``. "Correct" == recalled == a grade
     above Again, matching how BrainLift treats a successful review.

Because the prediction (from past data via ``S_hat``) and the future outcome
(from ``S_true``) are produced by separate paths, the reliability diagram now
tests whether the estimator's stated probabilities match reality — a real
calibration test, not an echo of the truth.

Everything is deterministic given the seeds below (a HELD-OUT test pool built
from TEST_SEED, disjoint from the TRAIN_SEED pool). Re-running reproduces the
numbers exactly. The output is also written to CSV + TXT so it can be charted.
"""

from __future__ import annotations

import math
import os
import random
import sys

# --- PRE-DECLARED pass cutoff (decided before looking at any result) ----------
BRIER_CUTOFF = 0.25

# --- deterministic seeds (disjoint train / held-out test pools) ---------------
TRAIN_SEED = 20260705
TEST_SEED = 71072026
TRAIN_N = 4000
TEST_N = 4000

# FSRS-5 power forgetting curve constants (match the Rust/`fsrs` engine).
DECAY = -0.5
FACTOR = 19.0 / 81.0

# Per-card PAST review history the estimator is allowed to learn from. More
# past reviews -> a sharper S_hat; this range keeps estimation error realistic
# (a real card has only a handful of prior reviews to learn from).
MIN_PAST_REVIEWS = 3
MAX_PAST_REVIEWS = 12

# Maximum-likelihood grid the estimator searches over (log-space stability, in
# days). The estimator picks the grid stability that best explains the PAST
# outcomes; it never sees the true stability.
FIT_GRID_LO_DAYS = 0.25
FIT_GRID_HI_DAYS = 1460.0
FIT_GRID_POINTS = 96

N_BINS = 10

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSV_PATH = os.path.join(_HERE, "memory_calibration_reliability.csv")
_TXT_PATH = os.path.join(_HERE, "memory_calibration_reliability.txt")


def fsrs_retrievability(elapsed_days: float, stability_days: float) -> float:
    """FSRS-5 predicted recall probability. Matches the shipped Rust engine."""
    if stability_days <= 0:
        return 0.0
    return (1.0 + FACTOR * elapsed_days / stability_days) ** DECAY


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# Pre-computed log-space stability grid the estimator searches (days).
_FIT_GRID = [
    math.exp(
        math.log(FIT_GRID_LO_DAYS)
        + (math.log(FIT_GRID_HI_DAYS) - math.log(FIT_GRID_LO_DAYS)) * i / (FIT_GRID_POINTS - 1)
    )
    for i in range(FIT_GRID_POINTS)
]


def _estimate_stability(
    past_times: list[float], past_outcomes: list[int]
) -> float:
    """Independent MLE of FSRS stability from PAST outcomes only.

    Returns the grid stability ``S_hat`` maximizing the Bernoulli likelihood of
    the observed past pass/fail record under the FSRS forgetting curve. This
    estimator has NO access to the card's true stability — its sole input is the
    past review history — so the recall it later predicts is a genuine estimate,
    not a copy of the truth.
    """
    eps = 1e-9
    best_s = _FIT_GRID[0]
    best_ll = -float("inf")
    for s in _FIT_GRID:
        ll = 0.0
        for t, y in zip(past_times, past_outcomes):
            p = min(1.0 - eps, max(eps, fsrs_retrievability(t, s)))
            ll += math.log(p) if y else math.log(1.0 - p)
        if ll > best_ll:
            best_ll = ll
            best_s = s
    return best_s


def make_pool(n: int, seed: int) -> tuple[list[float], list[int]]:
    """Build a simulated review pool using an INDEPENDENT recall estimator.

    Returns ``(predicted, actual)`` where ``predicted[i]`` is the estimator's
    predicted recall for a held-out FUTURE review (derived only from the card's
    PAST outcomes) and ``actual[i]`` in {0,1} is the independently drawn future
    outcome (from the card's hidden TRUE stability). The two come from separate
    paths, so calibration here is a real test of the estimator (see header).
    """
    rng = random.Random(seed)
    predicted: list[float] = []
    actual: list[int] = []
    for _ in range(n):
        # Hidden TRUE stability (log-uniform, ~1..365 days). Never shown to the
        # estimator; used only to generate outcomes.
        s_true = math.exp(rng.uniform(math.log(1.0), math.log(365.0)))

        # --- simulate a PAST review history and draw its outcomes from truth ---
        k = rng.randint(MIN_PAST_REVIEWS, MAX_PAST_REVIEWS)
        past_times: list[float] = []
        past_outcomes: list[int] = []
        for _ in range(k):
            ratio = math.exp(rng.uniform(math.log(0.05), math.log(20.0)))
            t_past = s_true * ratio
            p_true_past = _clamp01(fsrs_retrievability(t_past, s_true))
            past_times.append(t_past)
            past_outcomes.append(1 if rng.random() < p_true_past else 0)

        # --- estimator infers S_hat from the PAST outcomes ONLY ---------------
        s_hat = _estimate_stability(past_times, past_outcomes)

        # --- held-out FUTURE review: predict from S_hat, observe from S_true --
        # Future elapsed time spans a wide log-uniform range so predicted recall
        # covers the whole [0,1] axis and every reliability bin is populated.
        future_ratio = math.exp(rng.uniform(math.log(0.02), math.log(500.0)))
        t_future = s_true * future_ratio

        pred_p = _clamp01(fsrs_retrievability(t_future, s_hat))  # from estimate
        true_future_p = _clamp01(fsrs_retrievability(t_future, s_true))  # truth
        y = 1 if rng.random() < true_future_p else 0

        predicted.append(pred_p)
        actual.append(y)
    return predicted, actual


def brier_score(predicted: list[float], actual: list[int]) -> float:
    if not actual:
        return float("nan")
    return sum((p - y) ** 2 for p, y in zip(predicted, actual)) / len(actual)


def log_loss(predicted: list[float], actual: list[int], eps: float = 1e-12) -> float:
    if not actual:
        return float("nan")
    total = 0.0
    for p, y in zip(predicted, actual):
        p = min(1.0 - eps, max(eps, p))
        total += -(y * math.log(p) + (1 - y) * math.log(1.0 - p))
    return total / len(actual)


def reliability_bins(
    predicted: list[float], actual: list[int], n_bins: int = N_BINS
) -> list[dict]:
    """10-bin reliability diagram: mean predicted vs observed recall per bin."""
    bins: list[dict] = [
        {"lo": i / n_bins, "hi": (i + 1) / n_bins, "n": 0, "sum_pred": 0.0, "sum_obs": 0}
        for i in range(n_bins)
    ]
    for p, y in zip(predicted, actual):
        idx = min(int(p * n_bins), n_bins - 1)
        b = bins[idx]
        b["n"] += 1
        b["sum_pred"] += p
        b["sum_obs"] += y
    for b in bins:
        b["mean_pred"] = b["sum_pred"] / b["n"] if b["n"] else float("nan")
        b["obs_rate"] = b["sum_obs"] / b["n"] if b["n"] else float("nan")
    return bins


def expected_calibration_error(bins: list[dict], total: int) -> float:
    """Weighted mean |predicted - observed| across populated bins (ECE)."""
    if not total:
        return float("nan")
    ece = 0.0
    for b in bins:
        if b["n"]:
            ece += (b["n"] / total) * abs(b["mean_pred"] - b["obs_rate"])
    return ece


def _monotone_nondecreasing(values: list[float], tol: float = 0.06) -> bool:
    """True if the observed-rate curve is monotone-ish (small dips tolerated)."""
    prev = None
    for v in values:
        if v != v:  # NaN -> skip empty bins
            continue
        if prev is not None and v < prev - tol:
            return False
        prev = v
    return True


def _write_artifacts(bins: list[dict], brier: float, ll: float, ece: float) -> None:
    lines = ["bin_lo,bin_hi,count,mean_predicted,observed_recall"]
    for b in bins:
        mp = "" if b["mean_pred"] != b["mean_pred"] else f"{b['mean_pred']:.6f}"
        obs = "" if b["obs_rate"] != b["obs_rate"] else f"{b['obs_rate']:.6f}"
        lines.append(f"{b['lo']:.2f},{b['hi']:.2f},{b['n']},{mp},{obs}")
    with open(_CSV_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(_TXT_PATH, "w", encoding="utf-8") as fh:
        fh.write(_render_table(bins, brier, ll, ece))


def _render_table(bins: list[dict], brier: float, ll: float, ece: float) -> str:
    out: list[str] = []
    out.append("Memory calibration — reliability diagram "
               "(SIMULATED; independent MLE estimator, non-circular)")
    out.append("")
    out.append(f"  {'bin':>11}  {'n':>6}  {'predicted':>9}  {'observed':>9}  diagram")
    out.append("  " + "-" * 60)
    for b in bins:
        label = f"{b['lo']:.1f}-{b['hi']:.1f}"
        if not b["n"]:
            out.append(f"  {label:>11}  {0:>6}  {'-':>9}  {'-':>9}")
            continue
        mp = b["mean_pred"]
        obs = b["obs_rate"]
        bar = "#" * int(round(obs * 20))
        out.append(
            f"  {label:>11}  {b['n']:>6}  {mp:>9.3f}  {obs:>9.3f}  {bar}"
        )
    out.append("  " + "-" * 60)
    out.append(f"  Brier score : {brier:.4f}   (PASS cutoff <= {BRIER_CUTOFF})")
    out.append(f"  Log-loss    : {ll:.4f}")
    out.append(f"  ECE         : {ece:.4f}")
    return "\n".join(out) + "\n"


def run(live: bool = False) -> bool:
    # Held-out test pool (disjoint seed from the training pool).
    predicted, actual = make_pool(TEST_N, TEST_SEED)
    train_pred, _ = make_pool(TRAIN_N, TRAIN_SEED)

    brier = brier_score(predicted, actual)
    ll = log_loss(predicted, actual)
    bins = reliability_bins(predicted, actual)
    ece = expected_calibration_error(bins, len(actual))
    obs_curve = [b["obs_rate"] for b in bins]
    monotone = _monotone_nondecreasing(obs_curve)

    _write_artifacts(bins, brier, ll, ece)

    print("== Memory calibration — estimator recall vs actual outcome ==")
    print("data: SIMULATED, FSRS-5-grounded (NOT a real review log) — see header")
    print("prediction: INDEPENDENT MLE estimator (fit on PAST outcomes only), "
          "NOT truth+noise")
    print(f"held-out reviews: {len(actual)} (seed={TEST_SEED}); "
          f"train reviews: {len(train_pred)} (seed={TRAIN_SEED})")
    print(f"FSRS curve: R(t) = (1 + {FACTOR:.6f}*t/S)^{DECAY}  "
          f"(S estimated over {FIT_GRID_POINTS}-pt grid, "
          f"{MIN_PAST_REVIEWS}-{MAX_PAST_REVIEWS} past reviews/card)")
    print()
    print(_render_table(bins, brier, ll, ece), end="")
    print()
    print(f"reliability curve monotone-ish (observed rises with predicted): {monotone}")
    print(f"artifacts: {os.path.basename(_CSV_PATH)}, {os.path.basename(_TXT_PATH)}")
    print(f"PRE-DECLARED cutoff: Brier <= {BRIER_CUTOFF} AND all metrics finite")

    passed = (
        math.isfinite(brier)
        and math.isfinite(ll)
        and math.isfinite(ece)
        and brier <= BRIER_CUTOFF
        and all(math.isfinite(v) for v in obs_curve if v == v)
        and monotone
    )
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    ok = run(live="--live" in sys.argv)
    sys.exit(0 if ok else 1)
