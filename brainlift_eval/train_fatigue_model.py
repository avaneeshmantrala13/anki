# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""OFFLINE trainer for the Feature 2 fatigue logistic-regression classifier.

Run this to (re)produce the shipped model weights:

    python3 train_fatigue_model.py

It trains a logistic regression (batch gradient descent, L2 regularized, pure
Python — no numpy/sklearn) on the research-grounded SIMULATED training split
(`fatigue_sim.make_dataset(TRAIN_N, TRAIN_SEED)`), prints the learned bias +
weights in the exact form used by `anki.brainlift.fatigue` and the Kotlin engine,
and reports train-split metrics + the chosen decision threshold.

The printed constants are copied VERBATIM into:
  * anki/pylib/anki/brainlift/fatigue.py  (FATIGUE_MODEL_BIAS / _WEIGHTS)
  * Anki-Android/.../brainlift/BrainLiftFatigue.kt
  * anki/BRAINLIFT_AI_SPEC.md §5.5
so desktop and mobile run byte-identical inference. The held-out evaluation of
the *shipped* weights lives in `fatigue_model_eval.py` (wired into run_all.py).

Training is fully deterministic (fixed seed, zero-initialized weights).
"""

from __future__ import annotations

import math

import fatigue_metrics as metrics
import fatigue_sim as sim

# --- training hyperparameters (fixed, deterministic) -------------------------
LR = 0.3
ITERS = 20000
L2 = 3e-3
# Pre-declared production decision threshold on p(drained). 0.50 is the natural
# logistic operating point; declared BEFORE looking at held-out results.
DECISION_THRESHOLD = 0.50


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def train(X: list[list[float]], y: list[int]) -> tuple[float, list[float]]:
    n = len(X)
    dim = len(X[0])
    w = [0.0] * dim
    b = 0.0
    for _ in range(ITERS):
        gw = [0.0] * dim
        gb = 0.0
        for xi, yi in zip(X, y):
            z = b + sum(w[j] * xi[j] for j in range(dim))
            err = _sigmoid(z) - yi
            for j in range(dim):
                gw[j] += err * xi[j]
            gb += err
        for j in range(dim):
            w[j] -= LR * (gw[j] / n + L2 * w[j])
        b -= LR * (gb / n)
    return b, w


def main() -> None:
    Xtr, ytr = sim.make_dataset(sim.TRAIN_N, sim.TRAIN_SEED)
    b, w = train(Xtr, ytr)

    probs = [_sigmoid(b + sum(w[j] * xi[j] for j in range(len(xi)))) for xi in Xtr]
    acc = metrics.accuracy(probs, ytr, DECISION_THRESHOLD)
    auc = metrics.auc(probs, ytr)
    ll = metrics.log_loss(probs, ytr)

    print("== Fatigue model — OFFLINE training (research-grounded simulated data) ==")
    print(f"train sessions: {len(Xtr)}  (seed={sim.TRAIN_SEED})")
    print(f"features (order): {', '.join(sim.fx.FATIGUE_MODEL_FEATURES)}")
    print(f"train accuracy @ {DECISION_THRESHOLD:.2f}: {acc:.4f}")
    print(f"train AUC:      {auc:.4f}")
    print(f"train log-loss: {ll:.4f}")
    print()
    print("Copy the following VERBATIM into fatigue.py / BrainLiftFatigue.kt / spec:")
    print(f"FATIGUE_MODEL_BIAS = {b:.6f}")
    print("FATIGUE_MODEL_WEIGHTS = (")
    for name, wj in zip(sim.fx.FATIGUE_MODEL_FEATURES, w):
        print(f"    {wj:.6f},   # {name}")
    print(")")
    print(f"MODEL_INTERVENE = {DECISION_THRESHOLD:.2f}")


if __name__ == "__main__":
    main()
