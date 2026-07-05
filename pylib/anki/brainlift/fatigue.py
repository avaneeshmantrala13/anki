# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 2 — Cognitive-load / fatigue offload (learned model + heuristic).

Detects cognitive drain during a study session from per-answer signals — answer
time vs the user's own rolling baseline, accuracy vs baseline, response-time
variability, post-error slowing, and session-time position — then decides
whether to *very gradually* intervene:

* ``ease_difficulty`` — serve easier cards (lower FSRS difficulty), or
* ``interleave`` — add variety across the three Exam P sub-topics when the user
  has spent too long on one.

The *decision of WHEN drain is happening* is made by a small **learned logistic
regression classifier** (§5.5 of ``BRAINLIFT_AI_SPEC.md``) trained OFFLINE on a
research-grounded SIMULATED dataset (see ``brainlift_eval/train_fatigue_model.py``).
Its weights ship as shared constants so desktop (Python) and mobile (Kotlin) run
byte-identical inference: ``p = sigmoid(bias + w·features)``. The learned
probability replaces the old fixed ``drain >= 0.60`` trigger when the master AI
toggle (``brainlift_ai_enabled``) is ON. With the toggle OFF (or on any model
issue) the engine falls back cleanly to the original deterministic weighted-signal
drain heuristic — both paths always produce a decision, never crash, never block
scoring.

The features are EWMA-smoothed so the detector does not thrash, there is an
anti-thrash cooldown between interventions, and a timing gate: in TEST MODE it
fires immediately; in PROD it waits ~1-2 hours unless the user is clearly
struggling severely.

All constants + the update/decision rules mirror ``BRAINLIFT_AI_SPEC.md`` §5-§6
and the Kotlin engine. Every intervention returns a visible banner string.
"""

from __future__ import annotations

import math
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

# --- learned fatigue model (see BRAINLIFT_AI_SPEC.md §5.5) -------------------
# A small, interpretable logistic-regression classifier that predicts the
# probability the user is in a cognitively-drained / struggling state. It is
# trained OFFLINE in Python on a research-grounded SIMULATED dataset (calibrated
# to Fortenbaugh et al. 2015, Hanzal et al. 2024, Hassanzadeh-Behbaha et al.
# 2018 — see brainlift_eval/fatigue_sim.py) and its weights ship here as shared
# constants so desktop and mobile run byte-identical inference.
#
# Inference (identical in Kotlin BrainLiftFatigue):
#     z = FATIGUE_MODEL_BIAS + sum(FATIGUE_MODEL_WEIGHTS[i] * features[i])
#     p = 1 / (1 + exp(-z))
# features (order matters, all in [0,1]): the EWMA-smoothed normalized
# slowdown, accuracy-drop, RT-variability and post-error signals, plus the
# session-time position. Do NOT reorder without retraining + updating Kotlin.
FATIGUE_MODEL_VERSION = "logreg-sim-v1"
FATIGUE_MODEL_FEATURES = (
    "slowdown",
    "accdrop",
    "rt_var",
    "post_error",
    "session_pos",
)
# NOTE: these numbers are produced by brainlift_eval/train_fatigue_model.py and
# copied here verbatim (they are the SHIPPED model, verified by the offline
# eval). Regenerate with `python3 brainlift_eval/train_fatigue_model.py`.
FATIGUE_MODEL_BIAS = -4.125162
FATIGUE_MODEL_WEIGHTS = (
    4.943704,   # slowdown     (RT slowing — Fortenbaugh 2015, Hassanzadeh 2018)
    3.092085,   # accdrop      (accuracy decrement — Hanzal 2024)
    0.795880,   # rt_var       (rising RT variability — Fortenbaugh 2015)
    1.538849,   # post_error   (post-error slowing)
    3.579352,   # session_pos  (time-on-task vigilance decrement — all three)
)

# Pre-declared decision thresholds on the learned probability (chosen on the
# TRAINING split before looking at held-out results; see the eval).
MODEL_INTERVENE = 0.50   # replaces the fixed DRAIN_INTERVENE when AI is ON
MODEL_SEVERE = 0.80      # replaces SEVERE_DRAIN for the PROD timing-gate override

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
    # Learned-model fields (0.0 / False on the deterministic fallback path).
    probability: float = 0.0
    used_model: bool = False


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
        # EWMA-smoothed normalized model features (parallel to smoothed_drain;
        # consumed by the learned classifier). Same DRAIN_ALPHA smoothing.
        "sf_slowdown": 0.0,
        "sf_accdrop": 0.0,
        "sf_var": 0.0,
        "sf_posterr": 0.0,
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

    # instantaneous normalized signals -> deterministic drain + smoothing, and
    # the EWMA-smoothed feature vector consumed by the learned model.
    nf = _instant_norm_features(s)
    drain = _clamp(
        W_SLOWDOWN * nf[0] + W_ACC * nf[1] + W_VAR * nf[2] + W_POSTERR * nf[3]
    )
    s["smoothed_drain"] = (1 - DRAIN_ALPHA) * s.get("smoothed_drain", 0.0) + DRAIN_ALPHA * drain
    s["sf_slowdown"] = (1 - DRAIN_ALPHA) * s.get("sf_slowdown", 0.0) + DRAIN_ALPHA * nf[0]
    s["sf_accdrop"] = (1 - DRAIN_ALPHA) * s.get("sf_accdrop", 0.0) + DRAIN_ALPHA * nf[1]
    s["sf_var"] = (1 - DRAIN_ALPHA) * s.get("sf_var", 0.0) + DRAIN_ALPHA * nf[2]
    s["sf_posterr"] = (1 - DRAIN_ALPHA) * s.get("sf_posterr", 0.0) + DRAIN_ALPHA * nf[3]
    return s


def _instant_norm_features(s: dict[str, Any]) -> tuple[float, float, float, float]:
    """The four normalized [0,1] drain signals for the current state (pure).

    Shared by the deterministic drain score AND the learned model so both read
    identical inputs (slowdown, accuracy-drop, RT-variability, post-error)."""
    recent_rt = s.get("recent_rt", [])
    recent_acc = s.get("recent_acc", [])
    baseline_rt = max(float(s.get("baseline_rt", 0.0)), RT_MIN)
    baseline_var = max(float(s.get("rt_var", 0.0)), RT_MIN)

    slowdown = _mean(recent_rt) / baseline_rt if recent_rt else 1.0
    accdrop = float(s.get("baseline_acc", 1.0)) - _mean(recent_acc) if recent_acc else 0.0
    var_ratio = _pop_std(recent_rt) / baseline_var if recent_rt else 1.0
    posterr = float(s.get("post_error_rt", 0.0)) / baseline_rt

    return (
        _norm(slowdown, SLOWDOWN_LO, SLOWDOWN_HI),
        _norm(accdrop, ACCDROP_LO, ACCDROP_HI),
        _norm(var_ratio, VAR_LO, VAR_HI),
        _norm(posterr, POSTERR_LO, POSTERR_HI),
    )


def compute_drain(s: dict[str, Any]) -> float:
    """Instantaneous drain 0..1 from the current state (pure)."""
    nf = _instant_norm_features(s)
    return _clamp(W_SLOWDOWN * nf[0] + W_ACC * nf[1] + W_VAR * nf[2] + W_POSTERR * nf[3])


# --- learned model inference (parity-critical; mirror in Kotlin) ------------


def sigmoid(z: float) -> float:
    """Numerically-stable logistic sigmoid (identical to Kotlin)."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def predict_drain_probability(features: list[float]) -> float:
    """p(drained) = sigmoid(bias + w·features) for the shipped logistic model.

    ``features`` MUST be in FATIGUE_MODEL_FEATURES order. Returns a probability
    in [0,1]. Pure + deterministic; used identically on desktop and mobile."""
    z = FATIGUE_MODEL_BIAS
    for w, x in zip(FATIGUE_MODEL_WEIGHTS, features):
        z += w * float(x)
    return sigmoid(z)


def model_feature_vector(state: dict[str, Any], now: int | None = None) -> list[float]:
    """Build the 5-feature model input from a session state (pure).

    Four EWMA-smoothed physiological signals + the normalized session-time
    position (vigilance decrement grows with time-on-task)."""
    now = int(now if now is not None else time.time())
    session_minutes = (now - int(state.get("session_start", now))) / 60.0
    session_pos = _norm(session_minutes, 0.0, PROD_MIN_MINUTES)
    return [
        float(state.get("sf_slowdown", 0.0)),
        float(state.get("sf_accdrop", 0.0)),
        float(state.get("sf_var", 0.0)),
        float(state.get("sf_posterr", 0.0)),
        session_pos,
    ]


def model_probability(state: dict[str, Any], now: int | None = None) -> float | None:
    """The learned drain probability for a state, or None if the model can't run
    (malformed weights) so the caller falls back to the deterministic heuristic."""
    try:
        if len(FATIGUE_MODEL_WEIGHTS) != len(FATIGUE_MODEL_FEATURES):
            return None
        return predict_drain_probability(model_feature_vector(state, now))
    except Exception:
        return None


def decide(
    state: dict[str, Any],
    test_mode: bool,
    now: int | None = None,
    use_model: bool = False,
) -> FatigueDecision:
    """Decide whether to intervene given the current (already-updated) state.

    When ``use_model`` is True the learned logistic classifier decides *when*
    drain is happening (its probability replaces the fixed drain threshold);
    otherwise — or if the model can't run — the deterministic drain heuristic is
    used. The rest of the intervention machinery (cooldown, min-answers, timing
    gate, interleave-vs-ease selection, banner) is unchanged either way."""
    now = int(now if now is not None else time.time())
    drain = float(state.get("smoothed_drain", 0.0))
    session_minutes = (now - int(state.get("session_start", now))) / 60.0
    answers = int(state.get("answers", 0))

    # Learned score + thresholds, with a clean fallback to the heuristic.
    prob = model_probability(state, now) if use_model else None
    used_model = use_model and prob is not None
    if used_model:
        score, intervene_cut, severe_cut = prob, MODEL_INTERVENE, MODEL_SEVERE
    else:
        score, intervene_cut, severe_cut = drain, DRAIN_INTERVENE, SEVERE_DRAIN
    p_report = round(prob, 4) if prob is not None else 0.0

    def _d(intervene: bool, typ: str | None, banner: str | None, reason: str) -> FatigueDecision:
        return FatigueDecision(
            intervene, typ, banner, round(drain, 4), round(session_minutes, 2),
            reason, p_report, used_model,
        )

    if answers < MIN_ANSWERS_BEFORE_DETECT:
        return _d(False, None, None, "warming up")
    if int(state.get("answers_since_intervention", 0)) < INTERVENTION_COOLDOWN:
        return _d(False, None, None, "cooldown")

    timing_ok = test_mode or session_minutes >= PROD_MIN_MINUTES or score >= severe_cut
    if not (timing_ok and score >= intervene_cut):
        reason = "below threshold" if score < intervene_cut else "timing gate not met"
        return _d(False, None, None, reason)

    if int(state.get("same_topic_streak", 0)) >= SAME_TOPIC_STREAK_LIMIT:
        return _d(True, TYPE_INTERLEAVE, BANNER_INTERLEAVE, "high same-topic streak")
    return _d(True, TYPE_EASE, BANNER_EASE, "sustained drain")


# --- config-persisted convenience wrapper -----------------------------------


def test_mode(col: Collection) -> bool:
    return bool(col.get_config(CONFIG_TEST_MODE_KEY, True))


def model_enabled(col: Collection) -> bool:
    """Use the learned classifier iff the master AI toggle is ON. With it OFF we
    fall back to the deterministic heuristic (both still produce a decision)."""
    try:
        from anki.brainlift import ai as blai

        return blai.ai_enabled(col)
    except Exception:
        return bool(col.get_config("brainlift_ai_enabled", False))


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
    decision = decide(state, test_mode(col), now, use_model=model_enabled(col))
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


# --- applying the intervention to the LIVE review queue ---------------------
# The detector doesn't just show a banner: when it fires we actually reorder the
# review queue so the NEXT card served reflects the cognitive offload —
#   * interleave      -> pull a DIFFERENT Exam P topic to the front (variety),
#   * ease_difficulty -> pull the easiest available card (lowest FSRS
#                        difficulty — a well-known, low-load card) to the front.
# New cards are repositioned to the head of the new queue; already-seen cards
# are pulled forward with a due-date change. Everything is best-effort and can
# never crash reviewing. Mirrored in Kotlin (BrainLiftFatigue.applyOffload).


def _card_topic_key(col: Collection, card_id: int) -> str:
    """The Exam P main-topic key for a card, from its ``ExamP::<Topic>::*`` tag."""
    try:
        card = col.get_card(int(card_id))
        for tag in card.note().tags:
            if tag.startswith("ExamP::"):
                parts = tag.split("::")
                if len(parts) >= 2:
                    return parts[1]
    except Exception:
        pass
    return ""


def _card_difficulty(col: Collection, card_id: int) -> float:
    """FSRS difficulty for a card (0..1-ish). Unknown/new -> 1.0 (treated as
    hardest) so 'ease' prefers already-seen, low-difficulty cards."""
    try:
        card = col.get_card(int(card_id))
        ms = getattr(card, "memory_state", None)
        if ms is not None:
            return float(ms.difficulty)
    except Exception:
        pass
    return 1.0


def select_offload_card(
    col: Collection, decision_type: str | None, current_topic_key: str = ""
) -> int | None:
    """Pick the card the offload should serve next, or None if none is suitable.

    Pure selection (no mutation) so it can be unit-tested without touching the
    queue. ``interleave`` returns a due/new card in a different main topic;
    ``ease_difficulty`` returns the lowest-FSRS-difficulty due/new card."""
    try:
        candidates = [int(c) for c in col.find_cards("is:due OR is:new")]
    except Exception:
        candidates = []
    if not candidates:
        return None
    if decision_type == TYPE_INTERLEAVE:
        for cid in candidates:
            tk = _card_topic_key(col, cid)
            if tk and tk != current_topic_key:
                return cid
        return None
    if decision_type == TYPE_EASE:
        ranked = sorted(candidates, key=lambda cid: _card_difficulty(col, cid))
        return ranked[0] if ranked else None
    return None


def apply_offload(
    col: Collection, decision: FatigueDecision, current_topic_key: str = ""
) -> int | None:
    """Reorder the live queue for an active intervention. Returns the card id
    pulled to the front, or None. Best-effort; never raises."""
    if not getattr(decision, "intervene", False) or not decision.type:
        return None
    try:
        target = select_offload_card(col, decision.type, current_topic_key)
        if target is None:
            return None
        card = col.get_card(target)
        # New cards (type 0) are repositioned to the head of the new queue;
        # anything already in scheduling is pulled forward to "due today".
        if int(getattr(card, "type", 0)) == 0:
            col.sched.reposition_new_cards(
                [target], starting_from=0, step_size=1, randomize=False,
                shift_existing=True,
            )
        else:
            col.sched.set_due_date([target], "0")
        return target
    except Exception:
        return None
