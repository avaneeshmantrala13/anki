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
