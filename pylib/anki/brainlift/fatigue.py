# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 2 — Cognitive-load / fatigue offload (deterministic detector).

Detects cognitive drain during a study session from per-answer signals — answer
time vs the user's own rolling baseline, accuracy vs baseline, response-time
variability, post-error slowing, and session duration — then decides whether to
*very gradually* intervene:

* ``ease_difficulty`` — serve easier cards (lower FSRS difficulty), or
* ``interleave`` — add variety across the three Exam P sub-topics when the user
  has spent too long on one.

The detector is EWMA-smoothed so it does not thrash, has an anti-thrash cooldown
between interventions, and a timing gate: in TEST MODE it fires immediately; in
PROD it waits ~1-2 hours unless the user is clearly struggling severely.

All constants + the update/decision rules mirror ``BRAINLIFT_AI_SPEC.md`` §5-§6
and the Kotlin engine. Every intervention returns a visible banner string.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anki.collection import Collection

CONFIG_SESSION_KEY = "brainlift_fatigue_session"
CONFIG_LAST_INTERVENTION_KEY = "brainlift_fatigue_last_intervention"
CONFIG_TEST_MODE_KEY = "brainlift_fatigue_test_mode"

# --- constants (see BRAINLIFT_AI_SPEC.md §5.2) ------------------------------
# Baselines adapt SLOWLY (small alpha) so they represent the user's fresh /
# early-session norm; a fast recent window is compared against them. If the
# baseline adapted quickly it would "catch up" to degraded performance and mask
# the very drain we want to detect.
EWMA_ALPHA = 0.05
DRAIN_ALPHA = 0.3
WARMUP = 5
WINDOW = 8
MIN_ANSWERS_BEFORE_DETECT = 6

W_SLOWDOWN = 0.40
W_ACC = 0.30
W_VAR = 0.15
W_POSTERR = 0.15

SLOWDOWN_LO, SLOWDOWN_HI = 1.0, 1.8
ACCDROP_LO, ACCDROP_HI = 0.0, 0.30
VAR_LO, VAR_HI = 1.0, 1.7
POSTERR_LO, POSTERR_HI = 1.0, 1.5

DRAIN_INTERVENE = 0.60
SEVERE_DRAIN = 0.80
SAME_TOPIC_STREAK_LIMIT = 12
INTERVENTION_COOLDOWN = 10
PROD_MIN_MINUTES = 90.0

RT_MIN, RT_MAX = 0.2, 120.0

BANNER_INTERLEAVE = "Cognitive offload deemed necessary — adding variety"
BANNER_EASE = "Cognitive offload — easing difficulty"

TYPE_EASE = "ease_difficulty"
TYPE_INTERLEAVE = "interleave"


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _norm(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return _clamp((x - lo) / (hi - lo))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pop_std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


@dataclass
class FatigueDecision:
    intervene: bool
    type: str | None
    banner: str | None
    drain: float
    session_minutes: float
    reason: str


def new_session(now: int | None = None) -> dict[str, Any]:
    return {
        "answers": 0,
        "session_start": int(now if now is not None else time.time()),
        "baseline_rt": 0.0,
        "baseline_acc": 1.0,
        "rt_var": 0.0,
        "recent_rt": [],
        "recent_acc": [],
        "post_error_rt": 0.0,
        "last_correct": True,
        "same_topic_streak": 0,
        "current_topic": "",
        "smoothed_drain": 0.0,
        "answers_since_intervention": INTERVENTION_COOLDOWN,  # allow first fire
    }


def update_state(
    state: dict[str, Any],
    rt_seconds: float,
    correct: bool,
    topic_key: str = "",
) -> dict[str, Any]:
    """Fold one answered question into the rolling session state (pure)."""
    s = dict(state)
    rt = _clamp(rt_seconds, RT_MIN, RT_MAX)
    c = 1.0 if correct else 0.0
    s["answers"] = int(s.get("answers", 0)) + 1
    n = s["answers"]

    if n == 1:
        s["baseline_rt"] = rt
        s["baseline_acc"] = c
        s["rt_var"] = 0.0
    elif n <= WARMUP:
        # incremental simple mean during warmup
        s["baseline_rt"] = s["baseline_rt"] + (rt - s["baseline_rt"]) / n
        s["baseline_acc"] = s["baseline_acc"] + (c - s["baseline_acc"]) / n
        s["rt_var"] = s["rt_var"] + (abs(rt - s["baseline_rt"]) - s["rt_var"]) / n
    else:
        s["baseline_rt"] = (1 - EWMA_ALPHA) * s["baseline_rt"] + EWMA_ALPHA * rt
        s["baseline_acc"] = (1 - EWMA_ALPHA) * s["baseline_acc"] + EWMA_ALPHA * c
        s["rt_var"] = (1 - EWMA_ALPHA) * s["rt_var"] + EWMA_ALPHA * abs(rt - s["baseline_rt"])

    recent_rt = list(s.get("recent_rt", []))[-(WINDOW - 1):] + [rt]
    recent_acc = list(s.get("recent_acc", []))[-(WINDOW - 1):] + [c]
    s["recent_rt"] = recent_rt
    s["recent_acc"] = recent_acc

    if not s.get("last_correct", True):
        prev = s.get("post_error_rt", 0.0) or rt
        s["post_error_rt"] = (1 - EWMA_ALPHA) * prev + EWMA_ALPHA * rt

    if topic_key and topic_key == s.get("current_topic", ""):
        s["same_topic_streak"] = int(s.get("same_topic_streak", 0)) + 1
    else:
        s["same_topic_streak"] = 1
        s["current_topic"] = topic_key

    s["last_correct"] = bool(correct)
    s["answers_since_intervention"] = int(s.get("answers_since_intervention", 0)) + 1

    # instantaneous drain + smoothing
    drain = compute_drain(s)
    s["smoothed_drain"] = (1 - DRAIN_ALPHA) * s.get("smoothed_drain", 0.0) + DRAIN_ALPHA * drain
    return s


def compute_drain(s: dict[str, Any]) -> float:
    """Instantaneous drain 0..1 from the current state (pure)."""
    recent_rt = s.get("recent_rt", [])
    recent_acc = s.get("recent_acc", [])
    baseline_rt = max(float(s.get("baseline_rt", 0.0)), RT_MIN)
    baseline_var = max(float(s.get("rt_var", 0.0)), RT_MIN)

    slowdown = _mean(recent_rt) / baseline_rt if recent_rt else 1.0
    accdrop = float(s.get("baseline_acc", 1.0)) - _mean(recent_acc) if recent_acc else 0.0
    var_ratio = _pop_std(recent_rt) / baseline_var if recent_rt else 1.0
    posterr = float(s.get("post_error_rt", 0.0)) / baseline_rt

    drain = (
        W_SLOWDOWN * _norm(slowdown, SLOWDOWN_LO, SLOWDOWN_HI)
        + W_ACC * _norm(accdrop, ACCDROP_LO, ACCDROP_HI)
        + W_VAR * _norm(var_ratio, VAR_LO, VAR_HI)
        + W_POSTERR * _norm(posterr, POSTERR_LO, POSTERR_HI)
    )
    return _clamp(drain)


def decide(
    state: dict[str, Any],
    test_mode: bool,
    now: int | None = None,
) -> FatigueDecision:
    """Decide whether to intervene given the current (already-updated) state."""
    now = int(now if now is not None else time.time())
    drain = float(state.get("smoothed_drain", 0.0))
    session_minutes = (now - int(state.get("session_start", now))) / 60.0
    answers = int(state.get("answers", 0))

    if answers < MIN_ANSWERS_BEFORE_DETECT:
        return FatigueDecision(False, None, None, round(drain, 4), round(session_minutes, 2), "warming up")
    if int(state.get("answers_since_intervention", 0)) < INTERVENTION_COOLDOWN:
        return FatigueDecision(False, None, None, round(drain, 4), round(session_minutes, 2), "cooldown")

    timing_ok = test_mode or session_minutes >= PROD_MIN_MINUTES or drain >= SEVERE_DRAIN
    if not (timing_ok and drain >= DRAIN_INTERVENE):
        reason = "below threshold" if drain < DRAIN_INTERVENE else "timing gate not met"
        return FatigueDecision(False, None, None, round(drain, 4), round(session_minutes, 2), reason)

    if int(state.get("same_topic_streak", 0)) >= SAME_TOPIC_STREAK_LIMIT:
        return FatigueDecision(
            True, TYPE_INTERLEAVE, BANNER_INTERLEAVE, round(drain, 4),
            round(session_minutes, 2), "high same-topic streak",
        )
    return FatigueDecision(
        True, TYPE_EASE, BANNER_EASE, round(drain, 4),
        round(session_minutes, 2), "sustained drain",
    )


# --- config-persisted convenience wrapper -----------------------------------


def test_mode(col: Collection) -> bool:
    return bool(col.get_config(CONFIG_TEST_MODE_KEY, True))


def set_test_mode(col: Collection, enabled: bool) -> None:
    col.set_config(CONFIG_TEST_MODE_KEY, bool(enabled))


def load_session(col: Collection) -> dict[str, Any] | None:
    return col.get_config(CONFIG_SESSION_KEY, None)


def save_session(col: Collection, state: dict[str, Any]) -> None:
    col.set_config(CONFIG_SESSION_KEY, state)


def reset_session(col: Collection, now: int | None = None) -> dict[str, Any]:
    state = new_session(now)
    save_session(col, state)
    return state


def record_answer(
    col: Collection,
    rt_seconds: float,
    correct: bool,
    topic_key: str = "",
    now: int | None = None,
) -> FatigueDecision:
    """Fold an answer into the persisted session and decide on intervention.

    Persists updated session state (syncs). On intervention, records the last
    intervention and resets the cooldown counter.
    """
    state = load_session(col) or new_session(now)
    state = update_state(state, rt_seconds, correct, topic_key)
    decision = decide(state, test_mode(col), now)
    if decision.intervene:
        state["answers_since_intervention"] = 0
        col.set_config(
            CONFIG_LAST_INTERVENTION_KEY,
            {
                "type": decision.type,
                "banner": decision.banner,
                "drain": decision.drain,
                "at": int(now if now is not None else time.time()),
            },
        )
    save_session(col, state)
    return decision


def last_intervention(col: Collection) -> dict[str, Any] | None:
    return col.get_config(CONFIG_LAST_INTERVENTION_KEY, None)
