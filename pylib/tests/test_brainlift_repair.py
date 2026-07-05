# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tests for the one-time garbled-seed repair (BrainLift Exam P content).

Older builds seeded/imported a pypdf extraction that scrambled MathType glyph
runs (e.g. ``P[A ∪ B] = 0.7`` stored as ``[ ] 0.7PA B∪=``). ``repair_garbled_seed``
rewrites such cards to the clean bundled content (matched by SOA question
number) and drops SOA cards with no clean counterpart, without touching a user's
own notes.
"""
from __future__ import annotations

import re

from anki.brainlift import default_content as dc
from anki.brainlift.examp_seed import SEED_CARDS
from tests.shared import getEmptyCol

_QNUM_RE = re.compile(r"Sample Questions/Solutions,\s*Q(\d+)\b")


def _a_real_clean_card():
    for c in SEED_CARDS:
        m = _QNUM_RE.search(c["back"])
        if m:
            return int(m.group(1)), c
    raise AssertionError("no SOA-numbered card in seed bank")


def test_repair_rewrites_garbled_removes_unmatched_and_keeps_user_notes():
    col = getEmptyCol()
    qn, clean = _a_real_clean_card()
    basic = col.models.by_name("Basic")

    # (1) Garbled copy of a REAL question number -> rewritten to clean content.
    garbled = col.new_note(basic)
    garbled["Front"] = "You are given<br>[ ] 0.7PA B∪= ."
    garbled["Back"] = (
        "garbled<br><span>SOA Exam P Sample Questions/Solutions, "
        f"Q{qn}. http://x</span>"
    )
    col.add_note(garbled, col.decks.id("Exam P"))

    # (2) SOA card whose number has no clean counterpart -> removed.
    orphan = col.new_note(basic)
    orphan["Front"] = "orphan ∩="
    orphan["Back"] = (
        "x<br><span>SOA Exam P Sample Questions/Solutions, Q999999. http://x</span>"
    )
    col.add_note(orphan, col.decks.id("Exam P"))

    # (3) A user's own note (no SOA attribution) -> must be left untouched.
    mine = col.new_note(basic)
    mine["Front"] = "my own private card"
    mine["Back"] = "do not touch"
    col.add_note(mine, col.decks.id("Default"))

    repaired, removed = dc.repair_garbled_seed(col)
    assert repaired == 1
    assert removed == 1

    assert col.get_note(garbled.id)["Front"] == clean["front"]
    assert col.get_note(garbled.id)["Back"] == clean["back"]
    assert col.get_note(mine.id)["Front"] == "my own private card"
    assert not col.find_notes(f"nid:{orphan.id}")

    # Idempotent + guarded by the synced flag.
    assert dc.repair_garbled_seed(col) == (0, 0)
