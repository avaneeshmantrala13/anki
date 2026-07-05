# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Research-grounded SIMULATED training/eval data for the Feature 2 fatigue model.

HONESTY NOTE
------------
There is **no live student data**. This module generates a labeled dataset of
simulated study sessions whose per-answer signal distributions and effect sizes
are calibrated to three peer-reviewed papers on sustained attention / vigilance
decrement (the "named source" for the learned model). The model is therefore
trained on research-grounded *simulated* data, NOT on real students. Per-user
online adaptation on real response streams is explicitly future work.

Named sources (effect sizes below are calibrated to these):
* Fortenbaugh, DeGutis, Germine, et al. (2015), *Psychological Science* —
  sustained attention across the lifespan: reliable vigilance decrement, with
  response-time slowing and rising RT variability as time-on-task increases.
* Hanzal, Studer, Dresler, et al. (2024), *PLOS ONE* — SART: subjective/state
  fatigue is tightly coupled to an accuracy decrement during sustained tasks.
* Hassanzadeh-Behbaha, Rezania, et al. (2018), *Frontiers in Psychology* —
  vigilance decrement and progressive RT slowing across successive task blocks
  (resource-control account of time-on-task fatigue).

Each simulated session is folded through the SHIPPED feature pipeline
(`anki.brainlift.fatigue.update_state`) and read out with
`anki.brainlift.fatigue.model_feature_vector`, so the training features are
byte-identical to what the desktop/mobile engines compute at inference time.
Sessions are drawn from a seeded RNG; train and test use DISJOINT seeds and
DISJOINT session-id namespaces (no leakage — see the eval's separation check).
"""

from __future__ import annotations

import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "pylib"))

from anki.brainlift import fatigue as fx  # noqa: E402

# --- effect sizes (calibrated to the three papers; see module docstring) -----
# "drained" sessions show progressive RT slowing, higher RT variability, and an
# accuracy decrement that grows with time-on-task; "fresh" sessions stay fast,
# accurate and low-variance. Ranges deliberately OVERLAP so the task is
# non-trivial (a perfect classifier would signal an unrealistically clean sim).
FRESH = {
    "n_lo": 16, "n_hi": 40,
    "session_min_lo": 2.0, "session_min_hi": 75.0,
    "base_rt_lo": 2.5, "base_rt_hi": 4.5,
    "rt_drift_mu": 0.05, "rt_drift_sd": 0.06,      # ~flat RT over the session
    "rt_noise_frac": 0.06,                          # low RT variability
    "acc0_mu": 0.90, "acc0_sd": 0.04,               # high, stable accuracy
    "acc_drop_mu": 0.03, "acc_drop_sd": 0.03,
}
DRAINED = {
    "n_lo": 16, "n_hi": 40,
    "session_min_lo": 25.0, "session_min_hi": 130.0,
    "base_rt_lo": 2.5, "base_rt_hi": 4.5,
    "rt_drift_mu": 0.55, "rt_drift_sd": 0.18,      # strong progressive slowing
    "rt_noise_frac": 0.34,                          # rising RT variability
    "acc0_mu": 0.88, "acc0_sd": 0.05,
    "acc_drop_mu": 0.34, "acc_drop_sd": 0.10,       # accuracy decrement w/ fatigue
}


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def simulate_session(
    rng: random.Random, drained: bool
) -> tuple[list[float], float, int]:
    """Simulate one session -> (feature_vector, heuristic_drain, label).

    ``feature_vector`` is the learned model's 5-feature input; ``heuristic_drain``
    is the OLD deterministic ``smoothed_drain`` for the SAME session (used by the
    eval's baseline comparison); ``label`` is 1 iff the session is drained."""
    p = DRAINED if drained else FRESH
    n = rng.randint(p["n_lo"], p["n_hi"])
    session_minutes = rng.uniform(p["session_min_lo"], p["session_min_hi"])
    base_rt = rng.uniform(p["base_rt_lo"], p["base_rt_hi"])
    rt_drift = max(0.0, rng.gauss(p["rt_drift_mu"], p["rt_drift_sd"]))
    acc0 = _clip(rng.gauss(p["acc0_mu"], p["acc0_sd"]), 0.4, 0.99)
    acc_drop = max(0.0, rng.gauss(p["acc_drop_mu"], p["acc_drop_sd"]))

    state = fx.new_session(now=0)
    for i in range(n):
        progress = i / (n - 1) if n > 1 else 0.0
        rt_mult = 1.0 + rt_drift * progress
        noise_sd = base_rt * p["rt_noise_frac"] * (1.0 + progress)
        rt = _clip(base_rt * rt_mult + rng.gauss(0.0, noise_sd), 0.3, 60.0)
        p_correct = _clip(acc0 - acc_drop * progress, 0.05, 0.99)
        correct = rng.random() < p_correct
        state = fx.update_state(state, rt, correct, topic_key="UnivariateRV")

    # read out the SAME feature vector the engines use at inference time
    now = int(session_minutes * 60)
    features = fx.model_feature_vector(state, now=now)
    heuristic_drain = float(state.get("smoothed_drain", 0.0))
    return features, heuristic_drain, (1 if drained else 0)


def make_dataset(
    n_sessions: int, seed: int, drained_fraction: float = 0.5
) -> tuple[list[list[float]], list[int]]:
    """Generate a labeled dataset (features, labels) from a seeded RNG."""
    X, y, _ = make_dataset_full(n_sessions, seed, drained_fraction)
    return X, y


def make_dataset_full(
    n_sessions: int, seed: int, drained_fraction: float = 0.5
) -> tuple[list[list[float]], list[int], list[float]]:
    """Like `make_dataset` but also returns the per-session deterministic
    `smoothed_drain` (for the baseline comparison in the eval)."""
    rng = random.Random(seed)
    X: list[list[float]] = []
    y: list[int] = []
    drains: list[float] = []
    for _ in range(n_sessions):
        drained = rng.random() < drained_fraction
        feats, hd, label = simulate_session(rng, drained)
        X.append(feats)
        y.append(label)
        drains.append(hd)
    return X, y, drains


# Distinct seeds => disjoint simulated sessions for train vs held-out test.
TRAIN_SEED = 12345
TEST_SEED = 98765
TRAIN_N = 1600
TEST_N = 600
