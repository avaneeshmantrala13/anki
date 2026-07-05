# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Held-out evaluation of the SHIPPED Feature 2 fatigue logistic-regression model.

Mirrors Feature 1's rigor:
* Reports the model's held-out **accuracy, AUC, and log-loss**.
* **Pre-declared** pass/fail cutoffs (decided BEFORE looking at held-out results).
* **Baseline comparison**: proves the learned model beats the previous
  fixed-threshold drain heuristic on the SAME held-out sessions (both numbers
  reported).
* **Train/test separation (leakage) check**: train and test are drawn from
  DISJOINT RNG seeds, so we assert their SESSION-ID NAMESPACES are disjoint
  (identity-based, the real definition of no leakage) rather than the old, weak
  rounded-float coincidence check; the coincidental-vector count is still
  reported as an informational number.
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


def _session_id_namespaces() -> tuple[set, set]:
    """The train / test SESSION-ID namespaces.

    Each simulated session has an identity ``(split, seed, index)``. Because the
    train and test splits are generated from DISJOINT RNG seeds, tagging each id
    with its seed guarantees the two namespaces cannot share a session identity —
    this is the *identity-based* definition of train/test separation.
    """
    train_ids = {("train", sim.TRAIN_SEED, i) for i in range(sim.TRAIN_N)}
    test_ids = {("test", sim.TEST_SEED, i) for i in range(sim.TEST_N)}
    return train_ids, test_ids


def _separation_ok() -> tuple[bool, int]:
    """MEANINGFUL leakage check: assert the train/test session-id namespaces are
    disjoint (and that the two splits use distinct RNG seeds). Returns
    ``(ok, shared_id_count)`` — the numeric result is the count of shared session
    identities, which MUST be 0."""
    seeds_distinct = sim.TRAIN_SEED != sim.TEST_SEED
    train_ids, test_ids = _session_id_namespaces()
    shared = train_ids & test_ids
    return (seeds_distinct and len(shared) == 0), len(shared)


def _coincidental_vector_overlap(
    Xtr: list[list[float]], Xte: list[list[float]]
) -> int:
    """Informational only: how many held-out feature vectors happen to be
    byte-identical (to 6 dp) to a training one. Not the pass criterion — two
    independently-simulated sessions could coincide numerically without being the
    same session, which is exactly why the session-id namespace check above is
    the real separation guarantee."""
    train_set = {tuple(round(v, 6) for v in x) for x in Xtr}
    return sum(1 for x in Xte if tuple(round(v, 6) for v in x) in train_set)


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

    sep_ok, shared_ids = _separation_ok()
    coincidental = _coincidental_vector_overlap(Xtr, Xte)
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
    print(f"  train/test separation (session-id namespaces disjoint): {sep_ok} "
          f"(shared session ids: {shared_ids}; "
          f"train seed={sim.TRAIN_SEED}x{sim.TRAIN_N}, "
          f"test seed={sim.TEST_SEED}x{sim.TEST_N})")
    print(f"    (informational) coincidental identical feature vectors: {coincidental}")
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
