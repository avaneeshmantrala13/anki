# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Progress persistence / resume-after-restart for BrainLift state.

All BrainLift state lives in the collection config, so it is written to the
SQLite collection and travels through Anki's existing sync. These tests prove
the state survives a full close/reopen of the collection (i.e. an app restart),
with no network and no AI involved.
"""

from datetime import date

from anki.brainlift import diagnostic as dx
from anki.brainlift import onboarding as ob
from anki.collection import Collection
from tests.shared import getEmptyCol

TODAY = date(2026, 1, 1)


def _reopen(col) -> Collection:
    path = col.path
    col.close(downgrade=False)
    return Collection(path)


def test_onboarding_and_diagnostic_survive_restart():
    col = getEmptyCol()
    profile = ob.OnboardingInput(
        exam_date="2026-06-01",
        goal_score=7,
        weekly_study_hours=12,
        previous_attempts=1,
        prior_experience=ob.EXPERIENCE_SOME,
    )
    ob.save_onboarding(col, profile)
    dx.run_diagnostic(
        col,
        [dx.DiagnosticResponse("gp1", 2), dx.DiagnosticResponse("uni1", 1)],
    )

    col = _reopen(col)
    try:
        loaded = ob.load_onboarding(col)
        assert loaded is not None
        assert loaded.exam_date == "2026-06-01"
        assert loaded.goal_score == 7
        assert loaded.weekly_study_hours == 12
        assert loaded.previous_attempts == 1
        assert loaded.prior_experience == ob.EXPERIENCE_SOME

        diag = dx.load_diagnostic(col)
        assert diag is not None
        assert diag.answered == 2
        assert len(diag.topics) == 2
    finally:
        col.close(downgrade=False)


def test_dashboard_rebuilds_identically_after_restart():
    from anki.brainlift import dashboard

    col = getEmptyCol()
    ob.save_onboarding(
        col,
        ob.OnboardingInput(
            exam_date="2026-06-01", goal_score=6, weekly_study_hours=10
        ),
    )
    before = dashboard.build_dashboard(col, today=TODAY)

    col = _reopen(col)
    try:
        after = dashboard.build_dashboard(col, today=TODAY)
        # Deterministic: same inputs -> same plan and same study mode.
        assert after.plan.mode == before.plan.mode
        assert [p.topic_key for p in after.plan.priorities] == [
            p.topic_key for p in before.plan.priorities
        ]
        assert after.readiness.available == before.readiness.available
    finally:
        col.close(downgrade=False)
