# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Performance-model held-out evaluation.

The audit found the Performance score was only ever a DIRECT measurement (score
the 12-question diagnostic, report the accuracy). There was no held-out check
that BrainLift's features actually PREDICT whether a student gets a *new*,
unseen exam-style question right. This eval adds exactly that.

We fit a small logistic-regression predictor on a FIT set of exam-style /
analog questions and then measure its accuracy on a disjoint HELD-OUT set it
never saw during fitting. The predictor uses only features BrainLift already
has for each question:

    * topic_mastery  - the student's mastery of the question's topic (0..1)
    * difficulty     - the question's difficulty (0 easy .. 1 hard)
    * timing         - normalised answer time (0 fast .. 1 slow / rushed)
    * coverage       - fraction of that topic's syllabus the student has covered

Reported:
    * held-out ACCURACY of the fitted model
    * a BASELINE (predict the majority class / base rate) on the same held-out
      set, so the model's lift is explicit
    * held-out log-loss and AUC for completeness

PASS cutoff (DECLARED UP FRONT): held-out accuracy must beat the majority-class
baseline by a clear margin (>= 0.05) AND exceed 0.65 absolute.

------------------------------------------------------------------------------
DATA DISCLOSURE — THE QUESTION OUTCOMES ARE **SIMULATED**, NOT REAL STUDENTS.
------------------------------------------------------------------------------
BrainLift has no large corpus of real students answering its analog bank, so a
"true" data-generating process is used and clearly labelled as simulated:

  1. Each question is assigned a topic, a difficulty, a student topic-mastery,
     a coverage value and a normalised timing value (all deterministic from the
     seed).
  2. The ground-truth probability of a correct answer is a fixed logistic
     function of those features (higher mastery/coverage -> more likely correct;
     higher difficulty/rushed-timing -> less likely). The exact weights are the
     TRUE_* constants below and are disclosed.
  3. The observed correctness y in {0,1} is a Bernoulli draw from that
     probability.

The FIT set (FIT_SEED) and HELD-OUT set (TEST_SEED) are generated from disjoint
seeds; the model is fit ONLY on the fit set and scored ONLY on the held-out set.
Deterministic and reproducible. This proves the *harness + feature set* recover
a predictive signal on data they did not fit — it does not claim a measured
real-world accuracy.
"""

from __future__ import annotations

import math
import os
import random
import sys

# --- PRE-DECLARED pass cutoffs (decided before looking at any result) ---------
ACC_ABS_CUTOFF = 0.65      # held-out accuracy must clear this
ACC_LIFT_CUTOFF = 0.05     # ...and beat the majority baseline by at least this

# --- deterministic seeds (disjoint fit / held-out pools) ----------------------
FIT_SEED = 424242
TEST_SEED = 909090
FIT_N = 3000
TEST_N = 3000

# True data-generating logistic weights (disclosure #2). intercept + 4 features.
TRUE_BIAS = -0.30
TRUE_W_MASTERY = 3.20      # more mastery -> more likely correct
TRUE_W_DIFFICULTY = -2.60  # harder -> less likely correct
TRUE_W_TIMING = -1.10      # slower/rushed -> less likely correct
TRUE_W_COVERAGE = 1.40     # more coverage -> more likely correct

# Logistic-regression fit hyperparameters (deterministic gradient descent).
LR = 0.3
EPOCHS = 400

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSV_PATH = os.path.join(_HERE, "performance_holdout_results.csv")


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def make_dataset(n: int, seed: int) -> tuple[list[list[float]], list[int]]:
    """Simulated exam-style questions -> (feature rows, correctness labels)."""
    rng = random.Random(seed)
    X: list[list[float]] = []
    y: list[int] = []
    for _ in range(n):
        mastery = rng.random()
        difficulty = rng.random()
        timing = rng.random()
        coverage = rng.random()
        z = (
            TRUE_BIAS
            + TRUE_W_MASTERY * mastery
            + TRUE_W_DIFFICULTY * difficulty
            + TRUE_W_TIMING * timing
            + TRUE_W_COVERAGE * coverage
        )
        p = sigmoid(z)
        label = 1 if rng.random() < p else 0
        X.append([mastery, difficulty, timing, coverage])
        y.append(label)
    return X, y


def fit_logreg(X: list[list[float]], y: list[int]) -> tuple[list[float], float]:
    """Plain batch gradient-descent logistic regression (no third-party deps)."""
    n_features = len(X[0])
    w = [0.0] * n_features
    b = 0.0
    n = len(X)
    for _ in range(EPOCHS):
        grad_w = [0.0] * n_features
        grad_b = 0.0
        for xi, yi in zip(X, y):
            z = b + sum(wj * xij for wj, xij in zip(w, xi))
            err = sigmoid(z) - yi
            for j in range(n_features):
                grad_w[j] += err * xi[j]
            grad_b += err
        for j in range(n_features):
            w[j] -= LR * grad_w[j] / n
        b -= LR * grad_b / n
    return w, b


def predict_proba(X: list[list[float]], w: list[float], b: float) -> list[float]:
    return [sigmoid(b + sum(wj * xij for wj, xij in zip(w, xi))) for xi in X]


def accuracy(probs: list[float], y: list[int], threshold: float = 0.5) -> float:
    if not y:
        return 0.0
    correct = sum(1 for p, yi in zip(probs, y) if (1 if p >= threshold else 0) == yi)
    return correct / len(y)


def log_loss(probs: list[float], y: list[int], eps: float = 1e-12) -> float:
    if not y:
        return float("nan")
    total = 0.0
    for p, yi in zip(probs, y):
        p = min(1.0 - eps, max(eps, p))
        total += -(yi * math.log(p) + (1 - yi) * math.log(1.0 - p))
    return total / len(y)


def auc(probs: list[float], y: list[int]) -> float:
    """ROC-AUC via the Mann-Whitney rank-sum identity (with tie handling)."""
    pos = [p for p, yi in zip(probs, y) if yi == 1]
    neg = [p for p, yi in zip(probs, y) if yi == 0]
    if not pos or not neg:
        return float("nan")
    paired = sorted(zip(probs, range(len(probs))), key=lambda t: t[0])
    ranks = [0.0] * len(probs)
    i = 0
    while i < len(paired):
        j = i
        while j + 1 < len(paired) and paired[j + 1][0] == paired[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[paired[k][1]] = avg_rank
        i = j + 1
    sum_pos = sum(r for r, yi in zip(ranks, y) if yi == 1)
    return (sum_pos - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg))


def majority_baseline_accuracy(y_fit: list[int], y_test: list[int]) -> tuple[float, int]:
    """Predict the majority class learned on the FIT set; score on held-out."""
    majority = 1 if sum(y_fit) >= len(y_fit) / 2.0 else 0
    acc = sum(1 for yi in y_test if yi == majority) / len(y_test)
    return acc, majority


def _write_csv(w: list[float], b: float, acc: float, base_acc: float,
               ll: float, roc: float) -> None:
    names = ["mastery", "difficulty", "timing", "coverage"]
    with open(_CSV_PATH, "w", encoding="utf-8") as fh:
        fh.write("metric,value\n")
        fh.write(f"held_out_accuracy,{acc:.6f}\n")
        fh.write(f"baseline_accuracy,{base_acc:.6f}\n")
        fh.write(f"accuracy_lift,{acc - base_acc:.6f}\n")
        fh.write(f"held_out_log_loss,{ll:.6f}\n")
        fh.write(f"held_out_auc,{roc:.6f}\n")
        fh.write(f"fitted_bias,{b:.6f}\n")
        for name, wj in zip(names, w):
            fh.write(f"fitted_w_{name},{wj:.6f}\n")


def run(live: bool = False) -> bool:
    X_fit, y_fit = make_dataset(FIT_N, FIT_SEED)
    X_test, y_test = make_dataset(TEST_N, TEST_SEED)

    w, b = fit_logreg(X_fit, y_fit)
    probs = predict_proba(X_test, w, b)

    acc = accuracy(probs, y_test)
    ll = log_loss(probs, y_test)
    roc = auc(probs, y_test)
    base_acc, majority = majority_baseline_accuracy(y_fit, y_test)
    lift = acc - base_acc

    _write_csv(w, b, acc, base_acc, ll, roc)

    names = ["mastery", "difficulty", "timing", "coverage"]
    print("== Performance model — held-out correctness prediction ==")
    print("data: SIMULATED exam-style questions (NOT real students) — see header")
    print(f"fit questions: {len(y_fit)} (seed={FIT_SEED}); "
          f"held-out questions: {len(y_test)} (seed={TEST_SEED})")
    print("fitted logistic-regression predictor:")
    print(f"    bias = {b:+.4f}")
    for name, wj in zip(names, w):
        print(f"    w[{name:10s}] = {wj:+.4f}")
    print("-- held-out (never seen during fit) --")
    print(f"  accuracy: {acc:.4f}")
    print(f"  log-loss: {ll:.4f}")
    print(f"  AUC:      {roc:.4f}")
    print(f"-- baseline: predict majority class (={majority}) --")
    print(f"  accuracy: {base_acc:.4f}")
    print(f"  model lift over baseline: {lift:+.4f}")
    print(f"artifact: {os.path.basename(_CSV_PATH)}")
    print(f"PRE-DECLARED cutoffs: accuracy >= {ACC_ABS_CUTOFF} "
          f"AND lift >= {ACC_LIFT_CUTOFF}")

    passed = (
        math.isfinite(acc)
        and math.isfinite(ll)
        and acc >= ACC_ABS_CUTOFF
        and lift >= ACC_LIFT_CUTOFF
    )
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    ok = run(live="--live" in sys.argv)
    sys.exit(0 if ok else 1)
