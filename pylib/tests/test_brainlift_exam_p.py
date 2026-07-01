# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.brainlift import exam_p
from tests.shared import getEmptyCol


def _add(col, tag):
    note = col.newNote()
    note["Front"] = tag
    note.tags = [tag]
    col.addNote(note)
    return note


def test_syllabus_shape():
    # The three official SOA Exam P main topics, weights summing to ~100.
    assert [t.key for t in exam_p.SYLLABUS] == [
        "GeneralProbability",
        "UnivariateRV",
        "MultivariateRV",
    ]
    assert abs(sum(t.weight for t in exam_p.SYLLABUS) - 100.5) < 0.001
    # Topic search matches the topic tag OR any descendant tag.
    gp = exam_p.SYLLABUS[0]
    assert gp.search == '("tag:ExamP::GeneralProbability" OR "tag:ExamP::GeneralProbability::*")'


def test_empty_collection_has_zero_coverage():
    col = getEmptyCol()
    report = exam_p.coverage_report(col)
    assert len(report.topics) == 3
    assert report.coverage_percent == 0.0
    assert all(t.status == exam_p.NOT_STARTED for t in report.topics)


def test_coverage_and_status_mapping():
    col = getEmptyCol()
    # A card tagged at a subtopic should count toward its main topic (via ::*),
    # and a card tagged at the topic level should count too.
    _add(col, "ExamP::GeneralProbability::BayesTheorem")
    _add(col, "ExamP::GeneralProbability")  # topic-level tag
    _add(col, "ExamP::UnivariateRV::DiscreteDistributions")

    report = exam_p.coverage_report(col)

    gp = report.topic("GeneralProbability")
    assert gp.total_cards == 2
    assert gp.covered is True
    assert gp.status == exam_p.NOT_STARTED  # cards exist but none reviewed

    uni = report.topic("UnivariateRV")
    assert uni.total_cards == 1

    multi = report.topic("MultivariateRV")
    assert multi.total_cards == 0
    assert multi.covered is False

    # Weighted coverage = (13.5 + 43.5) / 100.5 * 100; Multivariate missing.
    expected = (13.5 + 43.5) / 100.5 * 100.0
    assert abs(report.coverage_percent - expected) < 0.01

    # Studying a card moves its topic to In Progress (deterministic, no FSRS
    # needed: status uses review counts).
    c = col.sched.getCard()
    col.sched.answerCard(c, 3)
    report = exam_p.coverage_report(col)
    statuses = {t.status for t in report.topics if t.total_cards > 0}
    assert exam_p.IN_PROGRESS in statuses


def test_weak_topics_orders_by_mastery_then_weight():
    col = getEmptyCol()
    _add(col, "ExamP::GeneralProbability::Combinatorics")
    _add(col, "ExamP::UnivariateRV::ExpectationVariance")
    report = exam_p.coverage_report(col)
    weak = report.weak_topics()
    # Only topics with cards are returned; both unmastered so heavier weight
    # (Univariate, 43.5) ranks ahead of lighter (General, 13.5).
    assert [t.key for t in weak] == ["UnivariateRV", "GeneralProbability"]
