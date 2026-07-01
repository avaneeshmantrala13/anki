# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The three BrainLift measurement models (deterministic, no AI).

These are kept strictly separate, as the PRD requires:

* **Memory**      - chance the student recalls a fact already studied
                    (derived from Anki's FSRS retrievability).
* **Performance** - chance the student answers a *new* exam-style question
                    (derived from the diagnostic's transfer questions).
* **Readiness**   - projected exam outcome, with a range and confidence, and an
                    explicit give-up rule: it refuses to report a number until
                    there is enough evidence.

Every score is a point estimate plus a likely range. No machine learning.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from anki.brainlift import diagnostic as dx
from anki.brainlift import exam_p

if TYPE_CHECKING:
    from anki.collection import Collection

# --- Give-up rule thresholds (the "honesty rule") ----------------------------
# Readiness is withheld until ALL of these are satisfied.
MIN_REVIEWS_FOR_READINESS = 200
MIN_COVERAGE_FOR_READINESS = 50.0  # percent
REQUIRE_DIAGNOSTIC_FOR_READINESS = True

# Exam P is reported on a 0-10 scale (6 is the conventional pass mark).
EXAM_SCALE_MAX = 10.0
EXAM_PASS_MARK = 6.0

# Readiness blend: performance (transfer) weighted above memory (recall).
W_PERFORMANCE = 0.6
W_MEMORY = 0.4


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _margin(sample_size: int) -> float:
    """A simple shrinking uncertainty band: more data -> tighter range."""
    return min(0.25, 0.5 / math.sqrt(sample_size + 1))


@dataclass
class MemoryScore:
    point: float  # 0-1
    low: float
    high: float
    reviewed_cards: int
    available: bool


@dataclass
class PerformanceScore:
    point: float  # 0-1
    low: float
    high: float
    answered: int
    available: bool


@dataclass
class Readiness:
    available: bool
    projected_score: float | None
    score_low: float | None
    score_high: float | None
    pass_probability: float | None
    confidence_level: str  # "low" | "medium" | "high" | "none"
    coverage_percent: float
    evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    last_updated: int = 0


def compute_memory(coverage: exam_p.CoverageReport) -> MemoryScore:
    """Weighted mean FSRS retrievability across reviewed topics."""
    total_weight = 0.0
    weighted = 0.0
    reviewed_cards = 0
    for t in coverage.topics:
        if t.reviewed_cards > 0:
            total_weight += t.weight
            weighted += t.weight * t.average_retrievability
            reviewed_cards += t.reviewed_cards
    if reviewed_cards == 0 or total_weight == 0:
        return MemoryScore(0.0, 0.0, 0.0, 0, available=False)
    point = _clamp(weighted / total_weight)
    margin = _margin(reviewed_cards)
    return MemoryScore(
        point=round(point, 4),
        low=round(_clamp(point - margin), 4),
        high=round(_clamp(point + margin), 4),
        reviewed_cards=reviewed_cards,
        available=True,
    )


def compute_performance(col: Collection) -> PerformanceScore:
    """Weighted mean diagnostic (transfer-question) accuracy."""
    result = dx.load_diagnostic(col)
    if not result or result.answered == 0:
        return PerformanceScore(0.0, 0.0, 0.0, 0, available=False)
    weights = {t.key: t.weight for t in exam_p.SYLLABUS}
    total_weight = 0.0
    weighted = 0.0
    for t in result.topics:
        w = weights.get(t.topic_key, 0.0)
        total_weight += w
        weighted += w * t.accuracy
    point = _clamp(weighted / total_weight) if total_weight else result.overall_accuracy
    margin = _margin(result.answered)
    return PerformanceScore(
        point=round(point, 4),
        low=round(_clamp(point - margin), 4),
        high=round(_clamp(point + margin), 4),
        answered=result.answered,
        available=True,
    )


def _confidence_level(coverage_percent: float, reviews: int, answered: int) -> str:
    if coverage_percent >= 80 and reviews >= 500 and answered >= 10:
        return "high"
    if coverage_percent >= MIN_COVERAGE_FOR_READINESS and reviews >= MIN_REVIEWS_FOR_READINESS:
        return "medium"
    return "low"


def compute_readiness(
    col: Collection,
    coverage: exam_p.CoverageReport,
    memory: MemoryScore,
    performance: PerformanceScore,
    total_reviews: int,
) -> Readiness:
    """Project an exam outcome, or withhold it under the give-up rule."""
    coverage_percent = coverage.coverage_percent
    evidence: list[str] = []
    missing: list[str] = []

    # Evidence inventory.
    evidence.append(f"{total_reviews} graded reviews")
    evidence.append(f"{coverage_percent:.0f}% of the syllabus covered")
    if performance.available:
        evidence.append(f"diagnostic: {performance.answered} questions answered")

    # Give-up checks.
    if total_reviews < MIN_REVIEWS_FOR_READINESS:
        missing.append(
            f"Need >= {MIN_REVIEWS_FOR_READINESS} graded reviews (have {total_reviews})."
        )
    if coverage_percent < MIN_COVERAGE_FOR_READINESS:
        missing.append(
            f"Need >= {MIN_COVERAGE_FOR_READINESS:.0f}% syllabus coverage "
            f"(have {coverage_percent:.0f}%)."
        )
    if REQUIRE_DIAGNOSTIC_FOR_READINESS and not performance.available:
        missing.append("Complete the diagnostic assessment.")

    last_updated = int(time.time())

    if missing:
        return Readiness(
            available=False,
            projected_score=None,
            score_low=None,
            score_high=None,
            pass_probability=None,
            confidence_level="none",
            coverage_percent=round(coverage_percent, 1),
            evidence=evidence,
            missing_evidence=missing,
            last_updated=last_updated,
        )

    blend = W_PERFORMANCE * performance.point + W_MEMORY * memory.point
    blend_low = W_PERFORMANCE * performance.low + W_MEMORY * memory.low
    blend_high = W_PERFORMANCE * performance.high + W_MEMORY * memory.high

    projected = round(blend * EXAM_SCALE_MAX, 1)
    score_low = round(blend_low * EXAM_SCALE_MAX, 1)
    score_high = round(blend_high * EXAM_SCALE_MAX, 1)
    # Monotone pass-probability proxy: 0.4 blend -> 0, 0.8 blend -> 1.
    pass_probability = round(_clamp((blend - 0.4) / 0.4), 2)

    return Readiness(
        available=True,
        projected_score=projected,
        score_low=score_low,
        score_high=score_high,
        pass_probability=pass_probability,
        confidence_level=_confidence_level(
            coverage_percent, total_reviews, performance.answered
        ),
        coverage_percent=round(coverage_percent, 1),
        evidence=evidence,
        missing_evidence=[],
        last_updated=last_updated,
    )
