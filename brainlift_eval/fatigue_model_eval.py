# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Held-out evaluation of the SHIPPED Feature 2 fatigue logistic-regression model.

Mirrors Feature 1's rigor:
* Reports the model's held-out **accuracy, AUC, and log-loss**.
* **Pre-declared** pass/fail cutoffs (decided BEFORE looking at held-out results).
* **Baseline comparison**: proves the learned model beats the previous
  fixed-threshold drain heuristic on the SAME held-out sessions (both numbers
  reported).
* **Train/test separation (leakage) check**: train and test come from DISJOINT
  RNG seeds; we assert their feature-vector sets do not overlap.
* Asserts the model's **named source** (the three peer-reviewed papers) is
  documented in BRAINLIFT_AI_SPEC.md.

Runs fully offline (deterministic simulated sessions, no key/network). The
weights under test are the ones shipped in `anki.brainlift.fatigue` — so this
proves the *shipped* model (identical on desktop + mobile) clears the bar.
"""

from __future__ import annotations

import os
import sys

# --- PRE-DECLARED cutoffs (decided before looking at held-out results) -------
MODEL_ACCURACY_CUTOFF = 0.80   # held-out accuracy must be >= this
MODEL_AUC_CUTOFF = 0.85        # held-out ROC-AUC must be >= this

import fatigue_metrics as metrics  # noqa: E402
import fatigue_sim as sim  # noqa: E402

fx = sim.fx  # the shipped engine (anki.brainlift.fatigue)

_SPEC = os.path.join(sim._HERE, "..", "BRAINLIFT_AI_SPEC.md")
_NAMED_SOURCES = ("Fortenbaugh", "Hanzal", "Hassanzadeh")


def _named_source_documented() -> bool:
    try:
        with open(_SPEC, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    return all(name in text for name in _NAMED_SOURCES)


def _separation_ok(Xtr: list[list[float]], Xte: list[list[float]]) -> tuple[bool, int]:
    """No held-out feature vector may coincide with a training one (no leakage)."""
    train_set = {tuple(round(v, 6) for v in x) for x in Xtr}
    overlap = sum(1 for x in Xte if tuple(round(v, 6) for v in x) in train_set)
    return overlap == 0, overlap


def run(live: bool = False) -> bool:
    # held-out test split (disjoint seed from training)
    Xte, yte, drains = sim.make_dataset_full(sim.TEST_N, sim.TEST_SEED)
    Xtr, _ = sim.make_dataset(sim.TRAIN_N, sim.TRAIN_SEED)

    # --- learned model (shipped weights) ---
    probs = [fx.predict_drain_probability(x) for x in Xte]
    acc = metrics.accuracy(probs, yte, fx.MODEL_INTERVENE)
    auc = metrics.auc(probs, yte)
    ll = metrics.log_loss(probs, yte)

    # --- baseline: previous fixed-threshold drain heuristic on the SAME set ---
    base_pred = [1 if d >= fx.DRAIN_INTERVENE else 0 for d in drains]
    base_acc = sum(1 for p, y in zip(base_pred, yte) if p == y) / len(yte)
    base_auc = metrics.auc(drains, yte)

    sep_ok, overlap = _separation_ok(Xtr, Xte)
    named_ok = _named_source_documented()
    beats = (acc > base_acc) and (auc > base_auc)

    print("== Fatigue model — held-out eval (LEARNED logistic regression) ==")
    print(f"model: {fx.FATIGUE_MODEL_VERSION}  bias={fx.FATIGUE_MODEL_BIAS:+.4f}")
    for name, w in zip(fx.FATIGUE_MODEL_FEATURES, fx.FATIGUE_MODEL_WEIGHTS):
        print(f"    w[{name:11s}] = {w:+.4f}")
    print(f"training data: research-grounded SIMULATED sessions (NOT live students)")
    print(f"  named sources: Fortenbaugh 2015, Hanzal 2024, Hassanzadeh-Behbaha 2018")
    print(f"held-out sessions: {len(yte)} (seed={sim.TEST_SEED}); "
          f"train sessions: {len(Xtr)} (seed={sim.TRAIN_SEED})")
    print("-- learned model --")
    print(f"  accuracy @ {fx.MODEL_INTERVENE:.2f}: {acc:.4f}")
    print(f"  AUC:               {auc:.4f}")
    print(f"  log-loss:          {ll:.4f}")
    print(f"PRE-DECLARED cutoffs: accuracy >= {MODEL_ACCURACY_CUTOFF:.2f} "
          f"AND AUC >= {MODEL_AUC_CUTOFF:.2f}")
    print("-- baseline: previous fixed-threshold heuristic (drain >= "
          f"{fx.DRAIN_INTERVENE:.2f}) --")
    print(f"  accuracy: {base_acc:.4f}   AUC: {base_auc:.4f}")
    print(f"  learned model BEATS baseline: {beats} "
          f"(acc +{acc - base_acc:.4f}, AUC +{auc - base_auc:.4f})")
    print("-- integrity --")
    print(f"  train/test separation (no leakage): {sep_ok} "
          f"(overlapping held-out vectors: {overlap})")
    print(f"  named-source documented in BRAINLIFT_AI_SPEC.md: {named_ok}")

    passed = (
        acc >= MODEL_ACCURACY_CUTOFF
        and auc >= MODEL_AUC_CUTOFF
        and beats
        and sep_ok
        and named_ok
    )
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    ok = run(live="--live" in sys.argv)
    sys.exit(0 if ok else 1)
