# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import tempfile

from anki.collection import CardStats
from tests.shared import getEmptyCol


def test_stats():
    col = getEmptyCol()
    note = col.newNote()
    note["Front"] = "foo"
    col.addNote(note)
    c = note.cards()[0]
    # card stats
    card_stats = col.card_stats_data(c.id)
    assert card_stats.note_id == note.id
    c = col.sched.getCard()
    col.sched.answerCard(c, 3)
    col.sched.answerCard(c, 2)
    card_stats = col.card_stats_data(c.id)
    assert len(card_stats.revlog) == 2


def test_topic_mastery():
    """BrainLift: per-topic mastery & coverage is callable from Python and
    returns deterministic aggregates."""
    col = getEmptyCol()
    # Enable FSRS so reviewing populates a memory state (and thus mastery).
    col.set_config("fsrs", True)

    # Two cards tagged Probability, one tagged Calculus.
    for _ in range(2):
        note = col.newNote()
        note["Front"] = "p"
        note.tags = ["ExamP::Probability"]
        col.addNote(note)
    note = col.newNote()
    note["Front"] = "c"
    note.tags = ["ExamP::Calculus"]
    col.addNote(note)

    resp = col.topic_mastery(
        [
            ("Probability", "tag:ExamP::Probability"),
            ("Calculus", "tag:ExamP::Calculus"),
            ("Missing", "tag:ExamP::DoesNotExist"),
        ]
    )

    by_name = {t.name: t for t in resp.topics}
    assert by_name["Probability"].total_cards == 2
    assert by_name["Probability"].covered is True
    assert by_name["Probability"].reviewed_cards == 0
    assert by_name["Calculus"].total_cards == 1
    # A topic with no matching cards is reported but not covered.
    assert by_name["Missing"].total_cards == 0
    assert by_name["Missing"].covered is False

    # After studying a Probability card it becomes reviewed (and, just-reviewed,
    # mastered under the default threshold).
    c = col.sched.getCard()
    col.sched.answerCard(c, 4)
    resp = col.topic_mastery([("Probability", "tag:ExamP::Probability")])
    topic = resp.topics[0]
    assert topic.reviewed_cards == 1
    assert topic.total_reviews >= 1
    assert topic.mastered_cards == 1


def test_graphs_empty():
    col = getEmptyCol()
    assert col.stats().report()


def test_graphs():
    dir = tempfile.gettempdir()
    col = getEmptyCol()
    g = col.stats()
    rep = g.report()
    with open(os.path.join(dir, "test.html"), "w", encoding="UTF-8") as note:
        note.write(rep)
    return
