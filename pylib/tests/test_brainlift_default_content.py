# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.brainlift import default_content, exam_p
from tests.shared import getEmptyCol


def _card_count(col):
    return col.db.scalar("select count() from cards")


def test_seeds_empty_collection():
    col = getEmptyCol()
    assert _card_count(col) == 0

    added = default_content.maybe_seed_default_deck(col)
    assert added > 0
    assert _card_count(col) == added

    # The bundled deck exists and coverage now reflects the seeded cards for all
    # three official Exam P main topics.
    assert col.decks.id_for_name(default_content.DECK_NAME) is not None
    report = exam_p.coverage_report(col)
    for key in ("GeneralProbability", "UnivariateRV", "MultivariateRV"):
        topic = report.topic(key)
        assert topic is not None and topic.total_cards > 0
    assert report.coverage_percent > 0.0


def test_seeding_is_idempotent():
    col = getEmptyCol()
    first = default_content.maybe_seed_default_deck(col)
    assert first > 0
    assert col.get_config(default_content.CONFIG_KEY) is True

    # A second run must add nothing (flag guards it).
    second = default_content.maybe_seed_default_deck(col)
    assert second == 0
    assert _card_count(col) == first


def test_does_not_seed_when_user_has_cards():
    col = getEmptyCol()
    note = col.newNote()
    note["Front"] = "user's own card"
    col.addNote(note)
    before = _card_count(col)
    assert before == 1

    added = default_content.maybe_seed_default_deck(col)
    assert added == 0
    assert _card_count(col) == before
    # Flag is set so we won't try to auto-seed later either.
    assert col.get_config(default_content.CONFIG_KEY) is True
