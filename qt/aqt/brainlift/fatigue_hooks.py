# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 2 wiring — feed the reviewer's answers into the fatigue detector.

On every graded review we measure the response time and correctness, attribute
it to an Exam P sub-topic (via the card's ``ExamP::*`` tags), and fold it into
the synced fatigue session state (:mod:`anki.brainlift.fatigue`). When the
detector decides to intervene we show a clearly visible banner — the actual
easier-card / interleave selection is a scheduling concern documented in the
spec; here we surface the decision so the user can see cognitive-offload working.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from aqt import gui_hooks

if TYPE_CHECKING:
    from anki.cards import Card
    from aqt.main import AnkiQt
    from aqt.reviewer import Reviewer

_shown_at: float = 0.0


def _topic_key_for_card(card: Card) -> str:
    try:
        note = card.note()
        for tag in note.tags:
            if tag.startswith("ExamP::"):
                parts = tag.split("::")
                if len(parts) >= 2:
                    return parts[1]
    except Exception:
        pass
    return ""


def _on_show_question(card: Card) -> None:
    global _shown_at
    _shown_at = time.time()


def _on_answer(reviewer: Reviewer, card: Card, ease: int) -> None:
    mw = reviewer.mw
    if mw is None or mw.col is None:
        return
    try:
        from anki.brainlift import fatigue as fx

        rt = time.time() - _shown_at if _shown_at else 0.0
        # ease 1 == "Again" -> wrong; 2/3/4 -> recalled.
        correct = ease >= 2
        topic = _topic_key_for_card(card)
        decision = fx.record_answer(mw.col, rt, correct, topic)
        if decision.intervene and decision.banner:
            from aqt.utils import tooltip

            tooltip(f"🧠 {decision.banner}", period=4000, parent=mw)
    except Exception:
        # Never let fatigue tracking disrupt reviewing.
        pass


def install(mw: AnkiQt) -> None:
    if getattr(mw, "_brainlift_fatigue_installed", False):
        return
    mw._brainlift_fatigue_installed = True
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_answer_card.append(_on_answer)
    # Start a fresh fatigue session each time the user enters review.
    def _maybe_reset(new_state: str, old_state: str) -> None:
        if new_state == "review" and old_state != "review" and mw.col is not None:
            try:
                from anki.brainlift import fatigue as fx

                fx.reset_session(mw.col)
            except Exception:
                pass

    gui_hooks.state_did_change.append(_maybe_reset)
