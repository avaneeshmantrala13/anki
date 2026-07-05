# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from datetime import date, timedelta

from anki.brainlift import diagnostic as dx
from anki.brainlift import onboarding as ob
from anki.brainlift import planner
from tests.shared import getEmptyCol

TODAY = date(2026, 1, 1)


def _add(col, tag):
    note = col.newNote()
    note["Front"] = tag
    note.tags = [tag]
    col.addNote(note)


def test_plan_with_no_profile_defaults_durable():
    col = getEmptyCol()
    plan = planner.build_study_plan(col, today=TODAY)
    assert plan.mode == ob.DURABLE
    assert len(plan.priorities) == 3  # three syllabus topics
    # All topics empty -> coverage gaps drive priorities; next topic set.
    assert plan.next_topic_key is not None


def test_uncovered_and_weak_topics_rank_higher():
    col = getEmptyCol()
    # Give General Probability cards, leave others empty.
    _add(col, "ExamP::GeneralProbability::BayesTheorem")
    # Diagnostic: weak in Multivariate.
    responses = [
        dx.DiagnosticResponse("mv1", 1),  # wrong
        dx.DiagnosticResponse("mv2", 1),  # wrong
    ]
    dx.run_diagnostic(col, responses)

    plan = planner.build_study_plan(col, today=TODAY)
    keys = [p.topic_key for p in plan.priorities]
    # Multivariate (empty + weak diagnostic) should outrank General Probability
    # (which at least has a card).
    assert keys.index("MultivariateRV") < keys.index("GeneralProbability")


def test_cramming_concentrates_hours_on_top_topics():
    col = getEmptyCol()
    profile = ob.OnboardingInput(
        exam_date=(TODAY + timedelta(days=7)).isoformat(),
        goal_score=6,
        weekly_study_hours=20,
        prior_experience=ob.EXPERIENCE_NONE,
    )
    ob.save_onboarding(col, profile)

    plan = planner.build_study_plan(col, today=TODAY)
    assert plan.mode == ob.CRAMMING
    # Cramming concentrates on at most CRAM_FOCUS_TOPICS topics.
    assert 0 < len(plan.weekly_allocation) <= planner.CRAM_FOCUS_TOPICS
    # Hours allocated should not exceed the weekly budget (allowing rounding).
    assert sum(plan.weekly_allocation.values()) <= plan.weekly_hours + 1.0


def test_durable_allocates_across_more_topics():
    col = getEmptyCol()
    profile = ob.OnboardingInput(
        exam_date=(TODAY + timedelta(days=200)).isoformat(),
        goal_score=6,
        weekly_study_hours=15,
        prior_experience=ob.EXPERIENCE_NONE,
    )
    ob.save_onboarding(col, profile)
    plan = planner.build_study_plan(col, today=TODAY)
    assert plan.mode == ob.DURABLE
    # Durable spreads across all three topics.
    assert len(plan.weekly_allocation) == 3


def test_every_priority_has_reasons():
    col = getEmptyCol()
    plan = planner.build_study_plan(col, today=TODAY)
    assert all(p.reasons for p in plan.priorities)
