# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The BrainLift unified dashboard (deterministic, no AI).

Aggregates every deterministic signal into one view-model and renders it as a
self-contained HTML page for the desktop GUI:

* the three separate measurements (Memory / Performance / Readiness),
* Exam P topic coverage and weakest topics,
* the rule-based study plan, and
* a projected progress timeline (today / 30d / 60d / exam day).

Readiness honours the give-up rule and shows "Not enough data" with the missing
evidence when it cannot honestly produce a number. Nothing here is AI-generated.
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from anki.brainlift import exam_p, measurements, onboarding, planner

if TYPE_CHECKING:
    from anki.collection import Collection

# Deterministic, clearly-labelled motivational projection: estimated extra
# percent of the syllabus mastered per study-hour invested in the plan.
MASTERY_GAIN_PER_HOUR = 0.3


@dataclass
class Milestone:
    label: str
    day_offset: int
    projected_mastered_percent: float


@dataclass
class Dashboard:
    coverage: exam_p.CoverageReport
    memory: measurements.MemoryScore
    performance: measurements.PerformanceScore
    readiness: measurements.Readiness
    weak_topics: list[exam_p.TopicReport]
    plan: planner.StudyPlan
    timeline: list[Milestone]
    onboarding_result: onboarding.OnboardingResult | None
    generated_at: int


def _total_graded_reviews(col: Collection) -> int:
    response = col.topic_mastery([("All", "deck:*")])
    return response.topics[0].total_reviews if response.topics else 0


def _timeline(
    mastered_percent: float,
    weekly_hours: float,
    days_until_exam: int | None,
) -> list[Milestone]:
    offsets: list[tuple[str, int]] = [("Today", 0), ("30 days", 30), ("60 days", 60)]
    if days_until_exam and days_until_exam > 0:
        offsets.append(("Exam day", days_until_exam))

    milestones: list[Milestone] = []
    for label, day in offsets:
        weeks = day / 7.0
        projected = min(
            100.0, mastered_percent + weekly_hours * weeks * MASTERY_GAIN_PER_HOUR
        )
        milestones.append(
            Milestone(
                label=label,
                day_offset=day,
                projected_mastered_percent=round(projected, 1),
            )
        )
    return milestones


def build_dashboard(col: Collection, today: date | None = None) -> Dashboard:
    coverage = exam_p.coverage_report(col)
    memory = measurements.compute_memory(coverage)
    performance = measurements.compute_performance(col)
    total_reviews = _total_graded_reviews(col)
    readiness = measurements.compute_readiness(
        col, coverage, memory, performance, total_reviews
    )
    plan = planner.build_study_plan(col, today=today)

    profile = onboarding.load_onboarding(col)
    onboarding_result = (
        onboarding.evaluate_onboarding(col, profile, today=today) if profile else None
    )
    weekly_hours = profile.weekly_study_hours if profile else 0.0
    days_until_exam = onboarding_result.days_until_exam if onboarding_result else None

    timeline = _timeline(coverage.mastered_percent, weekly_hours, days_until_exam)

    return Dashboard(
        coverage=coverage,
        memory=memory,
        performance=performance,
        readiness=readiness,
        weak_topics=coverage.weak_topics(limit=3),
        plan=plan,
        timeline=timeline,
        onboarding_result=onboarding_result,
        generated_at=int(time.time()),
    )


# --- HTML rendering ----------------------------------------------------------


def _pct(fraction: float) -> str:
    return f"{fraction * 100:.0f}%"


def _score_card(title: str, body: str, subtitle: str = "") -> str:
    sub = f"<div class='sub'>{subtitle}</div>" if subtitle else ""
    return (
        f"<div class='card'><div class='card-title'>{html.escape(title)}</div>"
        f"{body}{sub}</div>"
    )


def _memory_card(m: measurements.MemoryScore) -> str:
    if not m.available:
        body = "<div class='big muted'>Not enough data</div>"
        sub = "Study some cards so FSRS can estimate recall."
    else:
        body = (
            f"<div class='big'>{_pct(m.point)}</div>"
            f"<div class='range'>likely {_pct(m.low)}-{_pct(m.high)}</div>"
        )
        sub = f"FSRS recall over {m.reviewed_cards} reviewed cards"
    return _score_card("Memory", body, sub)


def _performance_card(p: measurements.PerformanceScore) -> str:
    if not p.available:
        body = "<div class='big muted'>Not enough data</div>"
        sub = "Take the diagnostic to measure performance on new questions."
    else:
        body = (
            f"<div class='big'>{_pct(p.point)}</div>"
            f"<div class='range'>likely {_pct(p.low)}-{_pct(p.high)}</div>"
        )
        sub = f"Transfer accuracy over {p.answered} diagnostic questions"
    return _score_card("Performance", body, sub)


def _readiness_card(r: measurements.Readiness) -> str:
    if not r.available:
        missing = "".join(f"<li>{html.escape(x)}</li>" for x in r.missing_evidence)
        body = (
            "<div class='big muted'>Not enough data</div>"
            "<div class='sub'>Readiness is withheld until there is enough "
            "evidence:</div>"
            f"<ul class='missing'>{missing}</ul>"
        )
        return _score_card("Readiness (Exam P, 0-10)", body)
    evidence = "".join(f"<li>{html.escape(x)}</li>" for x in r.evidence)
    body = (
        f"<div class='big'>{r.projected_score}</div>"
        f"<div class='range'>likely {r.score_low}-{r.score_high} &middot; "
        f"pass chance {_pct(r.pass_probability)}</div>"
        f"<div class='sub'>Confidence: {html.escape(r.confidence_level)} &middot; "
        f"coverage {r.coverage_percent:.0f}%</div>"
        f"<div class='sub'>Evidence:</div><ul class='evidence'>{evidence}</ul>"
    )
    return _score_card("Readiness (Exam P, 0-10)", body)


def _coverage_rows(coverage: exam_p.CoverageReport) -> str:
    rows = ""
    for t in coverage.topics:
        rows += (
            "<tr>"
            f"<td>{html.escape(t.name)}</td>"
            f"<td>{t.weight:g}%</td>"
            f"<td>{t.total_cards}</td>"
            f"<td>{t.reviewed_cards}</td>"
            f"<td>{_pct(t.mastered_fraction)}</td>"
            f"<td>{html.escape(t.status)}</td>"
            "</tr>"
        )
    return rows


def _plan_rows(plan: planner.StudyPlan) -> str:
    rows = ""
    for p in plan.priorities:
        reasons = "; ".join(html.escape(r) for r in p.reasons)
        rows += (
            "<tr>"
            f"<td>{html.escape(p.topic_name)}</td>"
            f"<td>{p.score:.2f}</td>"
            f"<td>{p.recommended_hours:g}h/wk</td>"
            f"<td class='reasons'>{reasons}</td>"
            "</tr>"
        )
    return rows


def _timeline_rows(timeline: list[Milestone]) -> str:
    cells = ""
    for m in timeline:
        cells += (
            "<div class='milestone'>"
            f"<div class='ms-label'>{html.escape(m.label)}</div>"
            f"<div class='ms-val'>{m.projected_mastered_percent:.0f}%</div>"
            "<div class='ms-cap'>mastered</div>"
            "</div>"
        )
    return cells


# Shared CSS for the dashboard body. Exposed so the desktop GUI can reuse it
# when it embeds the dashboard beneath the guided "getting started" header.
DASHBOARD_CSS = """
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
          padding: 20px; background: #f5f6f8; color: #1d1d1f; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .mode { color: #444; margin-bottom: 16px; font-size: 13px; }
  .cards { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 22px; }
  .card { background: #fff; border-radius: 12px; padding: 16px 18px; flex: 1;
           min-width: 220px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .card-title { font-size: 13px; text-transform: uppercase; letter-spacing: .04em;
                 color: #6b6b70; margin-bottom: 8px; }
  .big { font-size: 34px; font-weight: 700; }
  .big.muted { font-size: 22px; color: #b00020; }
  .range { color: #555; font-size: 13px; margin-top: 2px; }
  .sub { color: #6b6b70; font-size: 12px; margin-top: 8px; }
  ul.evidence, ul.missing { margin: 4px 0 0; padding-left: 18px; font-size: 12px;
                             color: #555; }
  ul.missing li { color: #b00020; }
  h2 { font-size: 16px; margin: 24px 0 8px; }
  table { width: 100%; border-collapse: collapse; background: #fff;
           border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  th, td { text-align: left; padding: 9px 12px; font-size: 13px;
            border-bottom: 1px solid #eee; }
  th { background: #fafafa; color: #6b6b70; font-weight: 600; }
  td.reasons { color: #555; font-size: 12px; }
  .timeline { display: flex; gap: 12px; }
  .milestone { background: #fff; border-radius: 10px; padding: 14px; flex: 1;
                text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  .ms-label { font-size: 12px; color: #6b6b70; }
  .ms-val { font-size: 26px; font-weight: 700; margin: 4px 0; }
  .ms-cap { font-size: 11px; color: #999; }
  .note { font-size: 11px; color: #999; margin-top: 6px; }
"""


def render_body(d: Dashboard, heading: str = "BrainLift — Exam P Dashboard") -> str:
    """Render the dashboard sections (no <html> wrapper).

    Used both by ``render_html`` and by the desktop GUI, which prepends a guided
    "getting started" header above these sections.
    """
    updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.generated_at))
    if d.onboarding_result:
        o = d.onboarding_result
        mode_line = (
            f"<div class='mode'>Study mode: <b>{html.escape(o.mode)}</b> &middot; "
            f"{o.days_until_exam} days until exam &middot; "
            f"{html.escape(o.recommendation)}</div>"
        )
    else:
        mode_line = (
            "<div class='mode'>No onboarding profile yet — complete onboarding to "
            "personalize your plan.</div>"
        )

    weak = "".join(
        f"<li>{html.escape(t.name)} — {_pct(t.mastered_fraction)} mastered "
        f"({html.escape(t.status)})</li>"
        for t in d.weak_topics
    ) or "<li>No started topics yet.</li>"

    heading_html = f"<h1>{html.escape(heading)}</h1>" if heading else ""

    return f"""
  {heading_html}
  {mode_line}

  <div class="cards">
    {_memory_card(d.memory)}
    {_performance_card(d.performance)}
    {_readiness_card(d.readiness)}
  </div>

  <h2>Study plan</h2>
  <div class="mode">{html.escape(d.plan.summary)}</div>
  <table>
    <tr><th>Topic</th><th>Priority</th><th>Weekly time</th><th>Why</th></tr>
    {_plan_rows(d.plan)}
  </table>

  <h2>Topic coverage</h2>
  <table>
    <tr><th>Topic</th><th>Weight</th><th>Cards</th><th>Reviewed</th>
        <th>Mastered</th><th>Status</th></tr>
    {_coverage_rows(d.coverage)}
  </table>

  <h2>Weakest topics</h2>
  <ul>{weak}</ul>

  <h2>Projected mastery (if you follow the plan)</h2>
  <div class="timeline">{_timeline_rows(d.timeline)}</div>
  <div class="note">Deterministic estimate based on your weekly study hours — not a guarantee, and not AI-generated.</div>

  <div class="note">Last updated: {updated}</div>
"""


def render_html(d: Dashboard) -> str:
    return (
        '<!doctype html>\n<html><head><meta charset="utf-8">'
        f"<style>{DASHBOARD_CSS}</style></head><body>{render_body(d)}</body></html>"
    )
