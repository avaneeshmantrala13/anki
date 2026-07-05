# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 2: the fatigue intervention actually reorders the live review queue.

Verifies the offload is APPLIED to scheduling (not merely surfaced as a banner):
``interleave`` pulls a different-topic card to the front and ``ease_difficulty``
pulls the lowest-difficulty card to the front, so the next card the scheduler
serves reflects the cognitive offload.
"""

from __future__ import annotations

from anki.brainlift import fatigue as fx
from anki.collection import Collection
from tests.shared import getEmptyCol


def _add(col: Collection, topic_sub_tag: str) -> int:
    note = col.new_note(col.models.by_name("Basic"))
    note["Front"] = f"q {topic_sub_tag}"
    note["Back"] = "a"
    note.tags = [topic_sub_tag]
    col.add_note(note, col.decks.id("Exam P — Sample Questions"))
    return note.cards()[0].id


def test_interleave_brings_a_different_topic_card_to_front() -> None:
    col = getEmptyCol()
    # Queue is ordered by insertion: many UnivariateRV, then one MultivariateRV.
    for _ in range(5):
        _add(col, "ExamP::UnivariateRV::DiscreteDistributions")
    other = _add(col, "ExamP::MultivariateRV::JointDistributions")

    # Sanity: without intervention the first served card is a UnivariateRV one.
    col.decks.set_current(col.decks.id("Exam P — Sample Questions"))
    first = col.sched.getCard()
    assert fx._card_topic_key(col, first.id) == "UnivariateRV"

    decision = fx.FatigueDecision(
        intervene=True, type=fx.TYPE_INTERLEAVE, banner=fx.BANNER_INTERLEAVE,
        drain=0.9, session_minutes=95.0, reason="test",
    )
    served = fx.apply_offload(col, decision, current_topic_key="UnivariateRV")
    assert served == other
    # The next card the scheduler serves is now the different-topic card.
    nxt = col.sched.getCard()
    assert nxt.id == other
    assert fx._card_topic_key(col, nxt.id) == "MultivariateRV"


def test_ease_selects_lowest_difficulty_card(monkeypatch) -> None:
    col = getEmptyCol()
    a = _add(col, "ExamP::UnivariateRV::DiscreteDistributions")
    b = _add(col, "ExamP::UnivariateRV::ExpectationVariance")
    c = _add(col, "ExamP::UnivariateRV::Transformations")

    # Deterministically assign difficulty: b is the easiest available card.
    difficulty = {a: 0.8, b: 0.2, c: 0.5}
    monkeypatch.setattr(fx, "_card_difficulty", lambda col, cid: difficulty[int(cid)])

    picked = fx.select_offload_card(col, fx.TYPE_EASE)
    assert picked == b  # lowest-difficulty (least cognitive load) card wins


def test_no_intervention_is_a_noop() -> None:
    col = getEmptyCol()
    _add(col, "ExamP::UnivariateRV::DiscreteDistributions")
    decision = fx.FatigueDecision(
        intervene=False, type=None, banner=None, drain=0.1,
        session_minutes=1.0, reason="warming up",
    )
    assert fx.apply_offload(col, decision, "UnivariateRV") is None
