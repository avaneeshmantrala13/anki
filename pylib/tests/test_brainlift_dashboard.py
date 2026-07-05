# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from datetime import date

from anki.brainlift import dashboard
from tests.shared import getEmptyCol

TODAY = date(2026, 1, 1)


def test_build_dashboard_on_empty_collection():
    col = getEmptyCol()
    d = dashboard.build_dashboard(col, today=TODAY)
    # Empty collection: no evidence -> measurements withhold.
    assert not d.memory.available
    assert not d.performance.available
    assert not d.readiness.available
    # Plan and timeline are always produced deterministically.
    assert len(d.plan.priorities) == 3
    assert len(d.timeline) == 3  # today / 30 / 60 (no exam date)


def test_render_html_is_self_contained_and_honest():
    col = getEmptyCol()
    d = dashboard.build_dashboard(col, today=TODAY)
    html = dashboard.render_html(d)
    assert html.startswith("<!doctype html>")
    assert "BrainLift" in html
    # Honesty rule visible to the user.
    assert "Not enough data" in html
    # No AI anywhere.
    assert "not AI-generated" in html


def test_timeline_includes_exam_day_when_onboarded():
    from anki.brainlift import onboarding as ob

    col = getEmptyCol()
    ob.save_onboarding(
        col,
        ob.OnboardingInput(
            exam_date="2026-04-01", goal_score=6, weekly_study_hours=10
        ),
    )
    d = dashboard.build_dashboard(col, today=TODAY)
    labels = [m.label for m in d.timeline]
    assert "Exam day" in labels
