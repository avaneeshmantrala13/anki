# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 2 (cognitive-load / fatigue offload) detector tests."""

from anki.brainlift import fatigue as fx
from tests.shared import getEmptyCol


def _steady(state, n, rt=3.0, correct=True, topic="UnivariateRV"):
    for _ in range(n):
        state = fx.update_state(state, rt, correct, topic)
    return state


def test_no_intervention_while_warming_up():
    state = fx.new_session(now=0)
    state = _steady(state, 3)
    decision = fx.decide(state, test_mode=True, now=10)
    assert decision.intervene is False
    assert decision.reason == "warming up"


def test_steady_performance_no_intervention():
    state = fx.new_session(now=0)
    state = _steady(state, 15, rt=3.0, correct=True)
    decision = fx.decide(state, test_mode=True, now=60)
    assert decision.intervene is False
    assert decision.drain < fx.DRAIN_INTERVENE


def test_slowdown_and_errors_trigger_intervention_in_test_mode():
    state = fx.new_session(now=0)
    # Establish a fast, accurate baseline.
    state = _steady(state, 8, rt=2.0, correct=True)
    # Then degrade sharply: much slower + wrong answers.
    state = _steady(state, 8, rt=9.0, correct=False)
    decision = fx.decide(state, test_mode=True, now=120)
    assert decision.drain >= fx.DRAIN_INTERVENE
    assert decision.intervene is True
    assert decision.type in (fx.TYPE_EASE, fx.TYPE_INTERLEAVE)
    assert decision.banner


def test_prod_timing_gate_blocks_moderate_early_drain():
    # A moderate drain (>= DRAIN_INTERVENE but < SEVERE) a couple of minutes in
    # must NOT intervene in PROD (timing gate); the same state DOES in TEST MODE.
    state = fx.new_session(now=0)
    state = _steady(state, 8, rt=2.0, correct=True)
    state = _steady(state, 8, rt=4.0, correct=False)
    assert fx.DRAIN_INTERVENE <= state["smoothed_drain"] < fx.SEVERE_DRAIN
    prod = fx.decide(state, test_mode=False, now=120)  # 2 minutes in
    assert prod.intervene is False
    assert prod.reason == "timing gate not met"
    test = fx.decide(state, test_mode=True, now=120)
    assert test.intervene is True


def test_prod_intervenes_after_long_session():
    state = fx.new_session(now=0)
    state = _steady(state, 8, rt=2.0, correct=True)
    state = _steady(state, 8, rt=4.0, correct=False)
    # ~100 minutes into the session -> PROD timing gate satisfied.
    prod = fx.decide(state, test_mode=False, now=100 * 60)
    assert prod.intervene is True


def test_prod_severe_drain_overrides_timing_gate():
    state = fx.new_session(now=0)
    state = _steady(state, 8, rt=1.5, correct=True)
    # Extreme slowdown + all wrong -> severe drain overrides the timing gate.
    state = _steady(state, 10, rt=30.0, correct=False)
    assert state["smoothed_drain"] >= fx.SEVERE_DRAIN
    decision = fx.decide(state, test_mode=False, now=120)
    assert decision.intervene is True


def test_interleave_chosen_on_long_same_topic_streak():
    state = fx.new_session(now=0)
    state = _steady(state, 8, rt=2.0, correct=True, topic="UnivariateRV")
    state = _steady(state, 13, rt=8.0, correct=False, topic="UnivariateRV")
    decision = fx.decide(state, test_mode=True, now=120)
    assert state["same_topic_streak"] >= fx.SAME_TOPIC_STREAK_LIMIT
    assert decision.intervene is True
    assert decision.type == fx.TYPE_INTERLEAVE
    assert decision.banner == fx.BANNER_INTERLEAVE


def test_cooldown_prevents_thrash():
    state = fx.new_session(now=0)
    state = _steady(state, 8, rt=2.0, correct=True)
    state = _steady(state, 8, rt=10.0, correct=False)
    d1 = fx.decide(state, test_mode=True, now=120)
    assert d1.intervene is True
    # Simulate acting on it (reset cooldown) then one more answer.
    state["answers_since_intervention"] = 0
    state = fx.update_state(state, 10.0, False, "UnivariateRV")
    d2 = fx.decide(state, test_mode=True, now=130)
    assert d2.intervene is False
    assert d2.reason == "cooldown"


def test_record_answer_persists_and_syncs_state():
    col = getEmptyCol()
    assert fx.test_mode(col) is True  # default ON
    fx.reset_session(col, now=0)
    for _ in range(6):
        fx.record_answer(col, 3.0, True, "UnivariateRV", now=10)
    state = fx.load_session(col)
    assert state is not None
    assert state["answers"] == 6


def test_test_mode_toggle_persists():
    col = getEmptyCol()
    fx.set_test_mode(col, False)
    assert fx.test_mode(col) is False
    fx.set_test_mode(col, True)
    assert fx.test_mode(col) is True


# --- learned fatigue model (Feature 2 upgrade) ------------------------------


def test_sigmoid_matches_reference():
    assert abs(fx.sigmoid(0.0) - 0.5) < 1e-12
    # numerically stable at extremes (no overflow)
    assert fx.sigmoid(1000.0) == 1.0
    assert fx.sigmoid(-1000.0) == 0.0


def test_predict_drain_probability_reference_vectors():
    # Locked reference values (parity anchor with Kotlin BrainLiftParityTest).
    cases = [
        ([0.0, 0.0, 0.0, 0.0, 0.0], 0.015903856063),
        ([1.0, 1.0, 1.0, 1.0, 1.0], 0.999945904638),
        ([0.6, 0.4, 0.3, 0.2, 0.5], 0.917896515624),
        ([0.2, 0.1, 0.05, 0.0, 0.1], 0.080951885817),
        ([0.9, 0.8, 0.6, 0.5, 0.9], 0.999301731886),
    ]
    for feats, expected in cases:
        assert abs(fx.predict_drain_probability(feats) - expected) < 1e-9


def test_model_feature_vector_shape_and_session_pos():
    state = fx.new_session(now=0)
    state = _steady(state, 8, rt=3.0, correct=True)
    feats = fx.model_feature_vector(state, now=45 * 60)  # 45 min in
    assert len(feats) == len(fx.FATIGUE_MODEL_FEATURES)
    # session_pos = norm(45, 0, 90) = 0.5
    assert abs(feats[4] - 0.5) < 1e-9
    assert all(0.0 <= f <= 1.0 for f in feats)


def test_model_flags_drained_but_not_fresh_session():
    fresh = fx.new_session(now=0)
    fresh = _steady(fresh, 15, rt=3.0, correct=True)
    d_fresh = fx.decide(fresh, test_mode=True, now=60, use_model=True)
    assert d_fresh.used_model is True
    assert d_fresh.intervene is False
    assert d_fresh.probability < fx.MODEL_INTERVENE

    drained = fx.new_session(now=0)
    drained = _steady(drained, 8, rt=2.0, correct=True)
    drained = _steady(drained, 8, rt=9.0, correct=False)
    d_drain = fx.decide(drained, test_mode=True, now=120, use_model=True)
    assert d_drain.used_model is True
    assert d_drain.intervene is True
    assert d_drain.probability >= fx.MODEL_INTERVENE
    assert d_drain.type in (fx.TYPE_EASE, fx.TYPE_INTERLEAVE)


def test_ai_off_uses_deterministic_heuristic():
    # AI OFF (use_model=False) must behave EXACTLY like the original heuristic.
    state = fx.new_session(now=0)
    state = _steady(state, 15, rt=3.0, correct=True)
    d = fx.decide(state, test_mode=True, now=60, use_model=False)
    assert d.used_model is False
    assert d.probability == 0.0
    assert d.intervene is False


def test_model_falls_back_cleanly_on_bad_weights(monkeypatch):
    # A malformed model must NOT crash — model_probability returns None and the
    # decision falls back to the deterministic heuristic.
    monkeypatch.setattr(fx, "FATIGUE_MODEL_WEIGHTS", (1.0, 2.0))  # wrong length
    state = fx.new_session(now=0)
    state = _steady(state, 8, rt=2.0, correct=True)
    state = _steady(state, 8, rt=9.0, correct=False)
    assert fx.model_probability(state, now=120) is None
    d = fx.decide(state, test_mode=True, now=120, use_model=True)
    assert d.used_model is False           # fell back
    assert d.intervene is True             # heuristic still fires on this state


def test_record_answer_uses_model_when_ai_enabled():
    from anki.brainlift import ai as blai

    col = getEmptyCol()
    blai.set_ai_enabled(col, True)
    assert fx.model_enabled(col) is True
    fx.reset_session(col, now=0)
    d = None
    for _ in range(6):
        d = fx.record_answer(col, 3.0, True, "UnivariateRV", now=10)
    assert d is not None
    assert d.used_model is True            # model path taken with AI ON

    # AI OFF -> deterministic path
    blai.set_ai_enabled(col, False)
    assert fx.model_enabled(col) is False
    fx.reset_session(col, now=0)
    d2 = fx.record_answer(col, 3.0, True, "UnivariateRV", now=10)
    assert d2.used_model is False
