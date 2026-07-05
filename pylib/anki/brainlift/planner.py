# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Deterministic BrainLift study planner (no AI).

Combines three deterministic signals into a transparent, rule-based plan:

* onboarding (study mode, weekly hours, exam date),
* Exam P coverage & mastery (from the shared Rust engine), and
* the diagnostic (per-topic accuracy / weakness),

to produce a priority-ordered list of topics, a weekly time allocation, and the
single best next topic to study. Every priority carries human-readable reasons.
No machine learning or LLMs are involved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from anki.brainlift import calibration as calib
from anki.brainlift import diagnostic as dx
from anki.brainlift import exam_p
from anki.brainlift import onboarding as ob

if TYPE_CHECKING:
    from anki.collection import Collection

# Heaviest syllabus weight, used to normalise importance to 0-1.
_MAX_WEIGHT = max(t.weight for t in exam_p.SYLLABUS)

# Priority weighting of the deterministic factors (sum to 1.0).
W_IMPORTANCE = 0.35
W_MASTERY_GAP = 0.30
W_DIAGNOSTIC_GAP = 0.20
W_COVERAGE_GAP = 0.15

# Neutral diagnostic gap when no diagnostic data exists for a topic.
NEUTRAL_DIAGNOSTIC_GAP = 0.5

# In cramming mode, concentrate effort on this many top topics.
CRAM_FOCUS_TOPICS = 3


@dataclass
class TopicPriority:
    topic_key: str
    topic_name: str
    score: float
    recommended_hours: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class StudyPlan:
    mode: str
    weekly_hours: float
    next_topic_key: str | None
    priorities: list[TopicPriority]
    weekly_allocation: dict[str, float]
    summary: str


def _diagnostic_accuracy_by_topic(col: Collection) -> dict[str, float]:
    result = dx.load_diagnostic(col)
    if not result:
        return {}
    return {t.topic_key: t.accuracy for t in result.topics}


def _round_half(value: float) -> float:
    return round(value * 2) / 2


def build_study_plan(col: Collection, today: date | None = None) -> StudyPlan:
    """Build a deterministic study plan from the persisted signals."""
    # Feature 1: confidence-authority multiplier (synced). Scales how strongly a
    # topic's demonstrated "knownness" is allowed to suppress its review
    # priority. Defaults to 1.0 (full authority) when no calibration exists.
    # We pass it INTO the Rust engine so the authority-adjusted mastery gap
    # (``effective_mastery_gap``) is computed in-engine, not in client code.
    authority = calib.calibration_multiplier(col)
    coverage = exam_p.coverage_report(col, confidence_authority=authority)
    diag_acc = _diagnostic_accuracy_by_topic(col)

    profile = ob.load_onboarding(col)
    if profile is not None:
        evaluation = ob.evaluate_onboarding(col, profile, today=today)
        mode = evaluation.mode
        weekly_hours = profile.weekly_study_hours
    else:
        mode = ob.DURABLE
        weekly_hours = 0.0

    priorities: list[TopicPriority] = []
    for topic in coverage.topics:
        importance = topic.weight / _MAX_WEIGHT
        # Rust-computed, confidence-authority-adjusted gap (Feature 1). The
        # ``calib.effective_mastery_gap`` Python formula is retained only as the
        # parity reference the engine mirrors (and the Kotlin fallback).
        mastery_gap = topic.effective_mastery_gap
        coverage_gap = 1.0 if topic.total_cards == 0 else (1.0 - topic.reviewed_fraction)
        if topic.key in diag_acc:
            diagnostic_gap = 1.0 - diag_acc[topic.key]
        else:
            diagnostic_gap = NEUTRAL_DIAGNOSTIC_GAP

        score = (
            W_IMPORTANCE * importance
            + W_MASTERY_GAP * mastery_gap
            + W_DIAGNOSTIC_GAP * diagnostic_gap
            + W_COVERAGE_GAP * coverage_gap
        )

        reasons: list[str] = []
        if topic.total_cards == 0:
            reasons.append("No cards yet for this topic (gap in coverage).")
        elif topic.reviewed_fraction < 0.5:
            reasons.append("Most cards in this topic have not been studied.")
        if topic.key in diag_acc and diag_acc[topic.key] < 0.5:
            reasons.append(f"Low diagnostic accuracy ({diag_acc[topic.key]:.0%}).")
        if importance >= 0.9:
            reasons.append("High-weight topic on the exam.")
        if topic.mastered_fraction < 0.5 and topic.total_cards > 0:
            reasons.append("Few cards mastered so far.")
        if not reasons:
            reasons.append("On track; keep reviewing to maintain mastery.")

        priorities.append(
            TopicPriority(
                topic_key=topic.key,
                topic_name=topic.name,
                score=round(score, 4),
                recommended_hours=0.0,
                reasons=reasons,
            )
        )

    priorities.sort(key=lambda p: p.score, reverse=True)

    # Allocate weekly hours proportional to score. In cramming mode, concentrate
    # on the top topics only.
    allocatable = (
        priorities[:CRAM_FOCUS_TOPICS] if mode == ob.CRAMMING else priorities
    )
    total_score = sum(p.score for p in allocatable) or 1.0
    weekly_allocation: dict[str, float] = {}
    for p in allocatable:
        hours = _round_half(weekly_hours * p.score / total_score)
        p.recommended_hours = hours
        if hours > 0:
            weekly_allocation[p.topic_key] = hours

    next_topic_key = priorities[0].topic_key if priorities else None

    summary = _summary(mode, coverage, priorities, weekly_hours)

    return StudyPlan(
        mode=mode,
        weekly_hours=weekly_hours,
        next_topic_key=next_topic_key,
        priorities=priorities,
        weekly_allocation=weekly_allocation,
        summary=summary,
    )


def _summary(
    mode: str,
    coverage: exam_p.CoverageReport,
    priorities: list[TopicPriority],
    weekly_hours: float,
) -> str:
    top = priorities[0].topic_name if priorities else "your weakest topic"
    cov = f"{coverage.coverage_percent:.0f}% of the syllabus is covered by your deck"
    if mode == ob.CRAMMING:
        return (
            f"Cramming mode: with limited time, focus your {weekly_hours:g} weekly "
            f"hours on the highest-impact topics, starting with {top}. {cov}."
        )
    if mode == ob.TIGHT:
        return (
            f"Tight schedule: prioritize {top} and the other high-weight gaps. "
            f"Consider adding study hours. {cov}."
        )
    if mode == ob.EXAM_PASSED:
        return "Your exam date is today or in the past. Update it to get a fresh plan."
    return (
        f"Durable plan: steady, spaced study across the syllabus, beginning with "
        f"{top}. {cov}."
    )
