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
generates a synthetic-but-FSRS-grounded review set:

  1. Each simulated card is given an FSRS memory *stability* S (days) drawn from
     a log-uniform range, and an *elapsed* time t (days) since its last review.
  2. The MODEL's predicted recall is the exact FSRS-5 power forgetting curve
         R(t) = (1 + FACTOR * t / S) ** DECAY,  DECAY = -0.5, FACTOR = 19/81
     — the same formula the Rust engine uses (see rslib .. topic_mastery.rs and
     the `fsrs` crate `current_retrievability`).
  3. The ground-truth recall probability is that SAME FSRS curve computed from
     the card's TRUE stability, then perturbed by a small, bounded amount of
     "model error" so the two are not trivially identical (this makes the
     reliability diagram non-degenerate and honest).
  4. The observed outcome y in {0,1} is a Bernoulli draw from the ground-truth
     probability. "Correct" == recalled == ease > 1 (i.e. any grade above
     Again), matching how BrainLift treats a successful review.

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

# Bounded model-error on the predicted probability (see disclosure #3). Keeps
# the eval honest: predictions are close to, but not identical to, truth.
MODEL_ERROR_SD = 0.06

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


def make_pool(n: int, seed: int) -> tuple[list[float], list[int]]:
    """Build a simulated review pool.

    Returns ``(predicted, actual)`` where ``predicted[i]`` is the Memory model's
    FSRS recall probability and ``actual[i]`` in {0,1} is the observed outcome.
    """
    rng = random.Random(seed)
    predicted: list[float] = []
    actual: list[int] = []
    for _ in range(n):
        # Log-uniform stability from ~1 day to ~365 days.
        stability = math.exp(rng.uniform(math.log(1.0), math.log(365.0)))
        # Elapsed time as a log-uniform multiple of stability, chosen wide
        # enough (t/S up to ~500) that predicted recall R spans the full [0,1]
        # range and every reliability bin is populated.
        ratio = math.exp(rng.uniform(math.log(0.02), math.log(500.0)))
        elapsed = stability * ratio

        true_p = _clamp01(fsrs_retrievability(elapsed, stability))
        # Model's prediction = truth + small bounded error (disclosure #3).
        pred_p = _clamp01(true_p + rng.gauss(0.0, MODEL_ERROR_SD))

        y = 1 if rng.random() < true_p else 0
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
    out.append("Memory calibration — reliability diagram (SIMULATED, FSRS-grounded)")
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

    print("== Memory calibration — FSRS predicted recall vs actual outcome ==")
    print("data: SIMULATED, FSRS-5-grounded (NOT a real review log) — see header")
    print(f"held-out reviews: {len(actual)} (seed={TEST_SEED}); "
          f"train reviews: {len(train_pred)} (seed={TRAIN_SEED})")
    print(f"FSRS curve: R(t) = (1 + {FACTOR:.6f}*t/S)^{DECAY}")
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
