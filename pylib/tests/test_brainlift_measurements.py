# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.brainlift import diagnostic as dx
from anki.brainlift import exam_p, measurements
from tests.shared import getEmptyCol


def _coverage(coverage_percent: float) -> exam_p.CoverageReport:
    return exam_p.CoverageReport(
        topics=[],
        coverage_percent=coverage_percent,
        studied_coverage_percent=coverage_percent,
        mastered_percent=0.0,
    )


def test_memory_unavailable_without_reviews():
    col = getEmptyCol()
    coverage = exam_p.coverage_report(col)
    m = measurements.compute_memory(coverage)
    assert not m.available
    assert m.point == 0.0


def test_performance_unavailable_without_diagnostic():
    col = getEmptyCol()
    p = measurements.compute_performance(col)
    assert not p.available


def test_performance_available_after_diagnostic():
    col = getEmptyCol()
    dx.run_diagnostic(col, [dx.DiagnosticResponse("gp1", 2)])  # correct
    p = measurements.compute_performance(col)
    assert p.available
    assert p.point > 0.0
    assert p.low <= p.point <= p.high


def test_readiness_gives_up_without_enough_evidence():
    col = getEmptyCol()
    coverage = _coverage(10.0)
    memory = measurements.MemoryScore(0.0, 0.0, 0.0, 0, available=False)
    performance = measurements.PerformanceScore(0.0, 0.0, 0.0, 0, available=False)
    r = measurements.compute_readiness(col, coverage, memory, performance, total_reviews=5)
    assert not r.available
    assert r.projected_score is None
    assert r.confidence_level == "none"
    # Should cite all three missing-evidence reasons.
    assert len(r.missing_evidence) == 3


def test_readiness_available_with_sufficient_evidence():
    col = getEmptyCol()
    coverage = _coverage(60.0)
    memory = measurements.MemoryScore(0.8, 0.7, 0.9, 300, available=True)
    performance = measurements.PerformanceScore(0.7, 0.6, 0.8, 12, available=True)
    r = measurements.compute_readiness(
        col, coverage, memory, performance, total_reviews=300
    )
    assert r.available
    # blend = 0.6*0.7 + 0.4*0.8 = 0.74 -> 7.4 on the 0-10 scale.
    assert r.projected_score == 7.4
    assert r.score_low is not None and r.score_high is not None
    assert r.score_low <= r.projected_score <= r.score_high
    assert 0.0 <= r.pass_probability <= 1.0
    assert r.missing_evidence == []
    assert r.confidence_level in ("low", "medium", "high")
