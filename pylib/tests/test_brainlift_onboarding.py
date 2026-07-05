# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from datetime import date, timedelta

from anki.brainlift import onboarding as ob
from tests.shared import getEmptyCol

TODAY = date(2026, 1, 1)


def _profile(days_ahead, weekly_hours, attempts=0, experience=ob.EXPERIENCE_NONE):
    return ob.OnboardingInput(
        exam_date=(TODAY + timedelta(days=days_ahead)).isoformat(),
        goal_score=6.0,
        weekly_study_hours=weekly_hours,
        previous_attempts=attempts,
        prior_experience=experience,
    )


def test_durable_mode_when_ample_time():
    col = getEmptyCol()
    # 24 weeks * 10h = 240h available vs 100h needed -> durable.
    result = ob.evaluate_onboarding(col, _profile(168, 10), today=TODAY)
    assert result.mode == ob.DURABLE
    assert result.enough_time is True
    assert result.is_cramming is False
    assert result.available_hours == 240.0


def test_cramming_mode_when_exam_close():
    col = getEmptyCol()
    result = ob.evaluate_onboarding(col, _profile(5, 20), today=TODAY)
    assert result.mode == ob.CRAMMING
    assert result.is_cramming is True
    assert "short-term" in result.recommendation


def test_tight_mode_when_low_weekly_hours():
    col = getEmptyCol()
    # 12 weeks * 6h = 72h available: below the 100h needed but above the
    # cramming floor (50h), with plenty of calendar days -> tight.
    result = ob.evaluate_onboarding(col, _profile(84, 6), today=TODAY)
    assert result.mode == ob.TIGHT
    assert result.enough_time is False
    assert result.is_cramming is False


def test_experience_lowers_needed_hours():
    col = getEmptyCol()
    none = ob.evaluate_onboarding(col, _profile(84, 5, experience=ob.EXPERIENCE_NONE), today=TODAY)
    strong = ob.evaluate_onboarding(
        col, _profile(84, 5, experience=ob.EXPERIENCE_STRONG), today=TODAY
    )
    assert none.estimated_hours_needed == 100.0
    assert strong.estimated_hours_needed == 50.0


def test_exam_in_past():
    col = getEmptyCol()
    result = ob.evaluate_onboarding(col, _profile(-1, 10), today=TODAY)
    assert result.mode == ob.EXAM_PASSED


def test_diagnostic_required_logic():
    col = getEmptyCol()
    # Beginner, no exposure, no attempts, no history -> just start, no diagnostic.
    beginner = ob.evaluate_onboarding(col, _profile(84, 10), today=TODAY)
    assert beginner.diagnostic_required is False
    # Experienced student with no history -> measure them first.
    experienced = ob.evaluate_onboarding(
        col, _profile(84, 10, experience=ob.EXPERIENCE_STRONG), today=TODAY
    )
    assert experienced.diagnostic_required is True
    # Previous attempt also triggers a diagnostic.
    retaker = ob.evaluate_onboarding(col, _profile(84, 10, attempts=1), today=TODAY)
    assert retaker.diagnostic_required is True


def test_save_and_load_roundtrip():
    col = getEmptyCol()
    assert ob.is_onboarded(col) is False
    profile = _profile(84, 10, attempts=1, experience=ob.EXPERIENCE_SOME)
    result = ob.complete_onboarding(col, profile, today=TODAY)
    assert result.mode == ob.DURABLE
    assert ob.is_onboarded(col) is True
    loaded = ob.load_onboarding(col)
    assert loaded == profile
