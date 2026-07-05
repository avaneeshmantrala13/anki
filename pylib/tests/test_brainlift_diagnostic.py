# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.brainlift import diagnostic as dx
from anki.brainlift import exam_p
from tests.shared import getEmptyCol


def test_question_bank_is_valid():
    qs = dx.get_questions()
    assert len(qs) == 12
    valid_topics = {t.key for t in exam_p.SYLLABUS}
    for q in qs:
        assert q.topic_key in valid_topics
        assert 0 <= q.correct_index < len(q.choices)
        assert q.choices  # non-empty


def test_filter_by_topic():
    qs = dx.get_questions(["GeneralProbability"])
    assert qs and all(q.topic_key == "GeneralProbability" for q in qs)


def _answer_all(correct: bool, confidence=dx.CONFIDENCE_MEDIUM, time=10.0):
    responses = []
    for q in dx.get_questions():
        idx = q.correct_index if correct else (q.correct_index + 1) % len(q.choices)
        responses.append(
            dx.DiagnosticResponse(q.id, idx, time_seconds=time, confidence=confidence)
        )
    return responses


def test_all_correct_perfect_accuracy():
    result = dx.score_diagnostic(_answer_all(correct=True))
    assert result.answered == 12
    assert result.overall_accuracy == 1.0
    assert all(t.accuracy == 1.0 for t in result.topics)


def test_all_wrong_zero_accuracy_and_overconfidence():
    result = dx.score_diagnostic(_answer_all(correct=False, confidence=dx.CONFIDENCE_HIGH))
    assert result.overall_accuracy == 0.0
    # High confidence + zero accuracy => strongly overconfident.
    assert result.calibration_gap == dx.CONFIDENCE_HIGH


def test_weak_topic_ranking():
    # Get General Probability questions wrong, the rest right.
    responses = []
    for q in dx.get_questions():
        wrong = q.topic_key == "GeneralProbability"
        idx = (q.correct_index + 1) % len(q.choices) if wrong else q.correct_index
        responses.append(dx.DiagnosticResponse(q.id, idx))
    result = dx.score_diagnostic(responses)
    # Weakest topic should be the one we missed.
    assert result.weak_topic_keys[0] == "GeneralProbability"
    gp = next(t for t in result.topics if t.topic_key == "GeneralProbability")
    assert gp.accuracy == 0.0


def test_partial_answers_counted():
    responses = [dx.DiagnosticResponse(q.id, q.correct_index) for q in dx.get_questions(["UnivariateRV"])]
    result = dx.score_diagnostic(responses)
    assert result.answered == 4
    assert {t.topic_key for t in result.topics} == {"UnivariateRV"}


def test_save_and_load_roundtrip():
    col = getEmptyCol()
    assert dx.has_diagnostic(col) is False
    result = dx.run_diagnostic(col, _answer_all(correct=True, time=12.5))
    assert dx.has_diagnostic(col) is True
    loaded = dx.load_diagnostic(col)
    assert loaded.overall_accuracy == 1.0
    assert loaded.answered == 12
    assert loaded.avg_time_seconds == 12.5
    assert all(isinstance(t, dx.TopicDiagnostic) for t in loaded.topics)
