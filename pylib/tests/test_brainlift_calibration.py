# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 1 (metacognitive calibration) unit tests + AI-off fallback."""

import math

from anki.brainlift import ai as blai
from anki.brainlift import calibration as calib
from tests.shared import getEmptyCol


def test_confidence_scale_mapping():
    assert calib.confidence_value("Highly confident") == 1.0
    assert calib.confidence_value("Confident") == 0.85
    assert calib.confidence_value("Kind of confident") == 0.6
    assert calib.confidence_value("Unsure") == 0.3
    assert calib.confidence_value("Guessing") == 0.0
    assert calib.CALIBRATION_TEST_SIZE == 15
    assert calib.CALIBRATION_PRODUCTION_SIZE == 50


def test_deviation_and_accuracy_perfect_calibration():
    # Confident+correct and guessing+wrong -> zero deviation -> accuracy 1.0.
    conf = [1.0, 0.0, 1.0, 0.0]
    perf = [1, 0, 1, 0]
    assert calib.mean_absolute_deviation(conf, perf) == 0.0
    assert calib.calibration_accuracy(conf, perf) == 1.0


def test_deviation_and_accuracy_worst_calibration():
    # Fully confident but always wrong -> deviation 1.0 -> accuracy 0.0.
    conf = [1.0, 1.0, 1.0]
    perf = [0, 0, 0]
    assert calib.mean_absolute_deviation(conf, perf) == 1.0
    assert calib.calibration_accuracy(conf, perf) == 0.0


def test_deviation_mixed():
    conf = [1.0, 0.6, 0.3]
    perf = [1, 0, 0]  # devs: 0.0, 0.6, 0.3 -> mad 0.3
    assert math.isclose(calib.mean_absolute_deviation(conf, perf), 0.3, abs_tol=1e-9)
    assert math.isclose(calib.calibration_accuracy(conf, perf), 0.7, abs_tol=1e-9)


def test_goodman_kruskal_gamma():
    # Perfectly ordered: higher confidence -> more likely correct.
    conf = [1.0, 0.85, 0.3, 0.0]
    perf = [1, 1, 0, 0]
    assert calib.goodman_kruskal_gamma(conf, perf) == 1.0
    # Reversed ordering -> -1.0
    perf_rev = [0, 0, 1, 1]
    assert calib.goodman_kruskal_gamma(conf, perf_rev) == -1.0
    # All ties in performance -> undefined -> None
    assert calib.goodman_kruskal_gamma([1.0, 0.5], [1, 1]) is None


def test_authority_multiplier_bounds_and_monotonic():
    assert calib.authority_multiplier(1.0) == 1.0
    assert calib.authority_multiplier(0.5) == calib.MIN_AUTHORITY
    assert calib.authority_multiplier(0.0) == calib.MIN_AUTHORITY
    assert math.isclose(calib.authority_multiplier(0.75), 0.625, abs_tol=1e-9)
    # monotonic non-decreasing
    vals = [calib.authority_multiplier(a / 10) for a in range(0, 11)]
    assert vals == sorted(vals)


def test_effective_mastery_gap_authority_scaling():
    # Well-calibrated (mult=1): mastered topic fully suppressed.
    assert math.isclose(calib.effective_mastery_gap(1.0, 1.0), 0.0, abs_tol=1e-9)
    # Poorly-calibrated (mult=0.25): mastered topic keeps review coverage.
    assert math.isclose(calib.effective_mastery_gap(1.0, 0.25), 0.75, abs_tol=1e-9)
    # Un-mastered topic always has full gap regardless of authority.
    assert calib.effective_mastery_gap(0.0, 1.0) == 1.0


def test_calibrated_suppression():
    assert calib.calibrated_suppression(1.0, 1.0) == 1.0
    assert calib.calibrated_suppression(1.0, 0.25) == 0.25
    assert calib.calibrated_suppression(0.5, 0.5) == 0.25


def test_score_and_persist_roundtrip():
    col = getEmptyCol()
    cards = [(1, "front1", "back1"), (2, "front2", "back2")]
    client = blai.DeterministicAnalogClient()
    analogs = [client.generate_analog(f, b, cid) for cid, f, b in cards]
    labels = ["Highly confident", "Guessing"]
    # Answer first correctly, second wrong.
    chosen = [analogs[0].correct_index, (analogs[1].correct_index + 1) % len(analogs[1].choices)]
    result = calib.run_calibration(col, cards, analogs, labels, chosen)
    assert result.test_size == 2
    # conf 1.0 + correct -> dev 0; conf 0.0 + wrong -> dev 0 => accuracy 1.0
    assert result.accuracy == 1.0
    assert result.authority_multiplier == 1.0
    # persisted + synced flat multiplier
    assert calib.calibration_multiplier(col) == 1.0
    loaded = calib.load_calibration(col)
    assert loaded is not None and loaded.test_size == 2
    # named-source traceability recorded on every item
    for it in loaded.items:
        assert it.generated_source_card_id == it.source_card_id
        assert it.generated_source_text


def test_clear_calibration_makes_it_rerunnable():
    col = getEmptyCol()
    cards = [(1, "front1", "back1"), (2, "front2", "back2")]
    client = blai.DeterministicAnalogClient()
    analogs = [client.generate_analog(f, b, cid) for cid, f, b in cards]
    labels = ["Highly confident", "Guessing"]
    chosen = [analogs[0].correct_index, analogs[1].correct_index]
    calib.run_calibration(col, cards, analogs, labels, chosen)
    assert calib.has_calibration(col) is True
    # Reset wipes the stored result and resets scheduling authority to neutral.
    calib.clear_calibration(col)
    assert calib.has_calibration(col) is False
    assert calib.load_calibration(col) is None
    assert calib.calibration_multiplier(col) == 1.0
    # Re-running after a reset persists a fresh result cleanly.
    calib.run_calibration(col, cards, analogs, labels, chosen)
    assert calib.has_calibration(col) is True


def test_ai_off_uses_deterministic_client_and_still_scores():
    col = getEmptyCol()
    # AI disabled by default; client must be the deterministic one.
    assert blai.ai_enabled(col) is False
    client = blai.client_for_collection(col)
    assert isinstance(client, blai.DeterministicAnalogClient)
    analog = client.generate_analog(
        "A fair coin is flipped 3 times. How many outcomes?", "8", 42
    )
    assert analog.ok is True
    assert len(analog.choices) >= 2
    assert 0 <= analog.correct_index < len(analog.choices)
    assert analog.source_card_id == 42


def test_real_client_falls_back_gracefully_without_network():
    # A real client with a bogus key must NOT raise; it returns a fallback
    # analog with ok=False so scoring never blocks.
    client = blai.RealOpenAIClient(api_key="sk-invalid", model="gpt-4o-mini")
    analog = client.generate_analog("X ~ Poisson(lambda=3). Var(X)?", "3", 7)
    assert analog.ok is False
    assert len(analog.choices) >= 2
    assert 0 <= analog.correct_index < len(analog.choices)


def test_explanation_bands():
    assert "excellent" in calib.explain_accuracy(0.9).lower()
    assert calib.explain_accuracy(0.72)
    assert calib.explain_accuracy(0.6)
    assert "caution" in calib.explain_accuracy(0.4).lower()


def test_strip_private_use_removes_pdf_glyphs():
    # U+F8EE / U+F8F9 etc. are the PUA "big bracket" glyphs from the SOA PDF.
    dirty = "P\uf8eeH \u2229 Fc\uf8f9 = 0.173"
    clean = calib.strip_private_use(dirty)
    assert "\uf8ee" not in clean and "\uf8f9" not in clean
    # Real content (intersection sign, text, numbers) is preserved.
    assert "\u2229" in clean and "0.173" in clean


def test_render_card_display_returns_real_rendered_html():
    from anki.brainlift.default_content import maybe_seed_default_deck

    col = getEmptyCol()
    maybe_seed_default_deck(col)
    cards = calib.select_calibration_cards(col)
    assert cards, "expected seeded Exam P cards"
    cid, front, back = cards[0]

    q_html, a_html = calib.render_card_display(col, cid)
    # The rendered FRONT carries the real card question, not just a topic path.
    assert "watched gymnastics" in q_html
    # The rendered ANSWER carries the back/solution content.
    assert "Answer" in a_html
    # No Private Use Area glyphs leak into displayed HTML.
    assert not any("\ue000" <= ch <= "\uf8ff" for ch in q_html + a_html)


def test_render_card_display_bad_id_is_safe():
    col = getEmptyCol()
    assert calib.render_card_display(col, 123456789) == ("", "")
