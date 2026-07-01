# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Deterministic BrainLift onboarding (no AI).

Collects a student's plan (exam date, goal score, weekly study hours, previous
attempts, prior probability experience) and deterministically derives:

* how much calendar time and study time is available,
* whether durable long-term learning is realistic or the student is effectively
  cramming,
* whether a diagnostic assessment is needed before planning,
* a plain-language recommendation.

The profile is persisted in the collection's config (so it syncs across devices
and survives restarts via the shared engine). Every decision is a transparent
rule with named thresholds, so the dashboard can explain *why*.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki.collection import Collection

# --- Tunable, transparent thresholds ----------------------------------------

# Rough hours a beginner needs for *durable* Exam P mastery. Scaled by prior
# experience below. Used only to compare planned vs. needed study time.
BASE_HOURS_FOR_DURABLE = 100.0

# Prior-experience multipliers on the hours needed.
EXPERIENCE_FACTORS = {"none": 1.0, "some": 0.7, "strong": 0.5}

# If fewer calendar days than this remain, durable learning is treated as
# unrealistic -> cramming.
CRAM_DAYS = 14
# Below this fraction of the needed hours, the student is cramming even with
# more calendar time.
CRAM_HOURS_FRACTION = 0.5
# Existing graded cards at/above which we already have enough data and can skip
# the diagnostic.
MIN_REVIEWED_FOR_DATA = 50

# Study modes.
DURABLE = "durable"
TIGHT = "tight"
CRAMMING = "cramming"
EXAM_PASSED = "exam_passed"

# Prior-experience levels.
EXPERIENCE_NONE = "none"
EXPERIENCE_SOME = "some"
EXPERIENCE_STRONG = "strong"

# Collection config key the profile is stored under.
CONFIG_KEY = "brainlift_onboarding"


@dataclass
class OnboardingInput:
    """What the student provides during onboarding."""

    exam_date: str  # ISO "YYYY-MM-DD"
    goal_score: float  # on the exam's own scale
    weekly_study_hours: float
    previous_attempts: int = 0
    prior_experience: str = EXPERIENCE_NONE  # none | some | strong

    def parsed_exam_date(self) -> date:
        return date.fromisoformat(self.exam_date)


@dataclass
class OnboardingResult:
    mode: str  # durable | tight | cramming | exam_passed
    days_until_exam: int
    weeks_until_exam: float
    available_hours: float
    estimated_hours_needed: float
    enough_time: bool
    is_cramming: bool
    diagnostic_required: bool
    recommendation: str
    profile: OnboardingInput


def experience_factor(prior_experience: str) -> float:
    return EXPERIENCE_FACTORS.get(prior_experience, 1.0)


def _reviewed_card_count(col: Collection) -> int:
    """How many cards have been studied at least once (via the shared engine)."""
    response = col.topic_mastery([("All", "deck:*")])
    return response.topics[0].reviewed_cards if response.topics else 0


def _recommendation(mode: str) -> str:
    if mode == DURABLE:
        return (
            "You have enough time to study for durable, long-term mastery. "
            "Follow the full study plan and review consistently."
        )
    if mode == TIGHT:
        return (
            "You have enough calendar time, but your planned weekly hours are "
            "low for durable mastery. Increase weekly study time, or expect to "
            "prioritize the highest-weight topics."
        )
    if mode == CRAMMING:
        return (
            "Limited time before your exam. The plan will optimize for "
            "short-term exam performance. After the exam, return to build "
            "durable, lasting understanding."
        )
    return "Your exam date is today or in the past. Update your exam date to continue."


def evaluate_onboarding(
    col: Collection,
    profile: OnboardingInput,
    today: date | None = None,
) -> OnboardingResult:
    """Deterministically derive study mode, time budget, and next steps."""
    today = today or date.today()
    days_until_exam = (profile.parsed_exam_date() - today).days
    weeks_until_exam = max(days_until_exam, 0) / 7.0
    available_hours = weeks_until_exam * profile.weekly_study_hours
    needed = BASE_HOURS_FOR_DURABLE * experience_factor(profile.prior_experience)

    if days_until_exam <= 0:
        mode = EXAM_PASSED
    elif days_until_exam < CRAM_DAYS or available_hours < needed * CRAM_HOURS_FRACTION:
        mode = CRAMMING
    elif available_hours < needed:
        mode = TIGHT
    else:
        mode = DURABLE

    reviewed = _reviewed_card_count(col)
    if reviewed >= MIN_REVIEWED_FOR_DATA:
        diagnostic_required = False
    else:
        diagnostic_required = (
            profile.prior_experience != EXPERIENCE_NONE or profile.previous_attempts > 0
        )

    return OnboardingResult(
        mode=mode,
        days_until_exam=days_until_exam,
        weeks_until_exam=round(weeks_until_exam, 2),
        available_hours=round(available_hours, 1),
        estimated_hours_needed=round(needed, 1),
        enough_time=mode == DURABLE,
        is_cramming=mode == CRAMMING,
        diagnostic_required=diagnostic_required,
        recommendation=_recommendation(mode),
        profile=profile,
    )


# --- Persistence -------------------------------------------------------------


def save_onboarding(col: Collection, profile: OnboardingInput) -> None:
    col.set_config(CONFIG_KEY, asdict(profile))


def load_onboarding(col: Collection) -> OnboardingInput | None:
    data = col.get_config(CONFIG_KEY, None)
    if not data:
        return None
    return OnboardingInput(**data)


def complete_onboarding(
    col: Collection,
    profile: OnboardingInput,
    today: date | None = None,
) -> OnboardingResult:
    """Persist the profile and return its deterministic evaluation."""
    save_onboarding(col, profile)
    return evaluate_onboarding(col, profile, today=today)


def is_onboarded(col: Collection) -> bool:
    return load_onboarding(col) is not None
