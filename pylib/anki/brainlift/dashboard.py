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


def _score_meta(
    confidence: str, coverage_percent: float, last_updated: int, reasons: list[str]
) -> str:
    """Shared metadata block for Memory & Performance (parity with Android)."""
    updated = (
        time.strftime("%Y-%m-%d %H:%M", time.localtime(last_updated))
        if last_updated
        else "—"
    )
    reason_html = "".join(f"<li>{html.escape(r)}</li>" for r in reasons)
    return (
        f"<div class='sub'>Confidence: {html.escape(confidence)} &middot; "
        f"coverage {coverage_percent:.0f}%</div>"
        f"<div class='sub'>Why:</div><ul class='evidence'>{reason_html}</ul>"
        f"<div class='note'>Last updated: {html.escape(updated)}</div>"
    )


def _memory_card(m: measurements.MemoryScore) -> str:
    if not m.available:
        body = "<div class='big muted'>Not enough data</div>"
        sub = "Study some cards so FSRS can estimate recall."
        return _score_card("Memory", body, sub)
    body = (
        f"<div class='big'>{_pct(m.point)}</div>"
        f"<div class='range'>likely {_pct(m.low)}-{_pct(m.high)}</div>"
        + _score_meta(m.confidence_level, m.coverage_percent, m.last_updated, m.reasons)
    )
    return _score_card("Memory", body)


def _performance_card(p: measurements.PerformanceScore) -> str:
    if not p.available:
        body = "<div class='big muted'>Not enough data</div>"
        sub = "Take the diagnostic to measure performance on new questions."
        return _score_card("Performance", body, sub)
    body = (
        f"<div class='big'>{_pct(p.point)}</div>"
        f"<div class='range'>likely {_pct(p.low)}-{_pct(p.high)}</div>"
        + _score_meta(p.confidence_level, p.coverage_percent, p.last_updated, p.reasons)
    )
    return _score_card("Performance", body)


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
# Uses the BrainLift design tokens (same palette as the landing page, the
# skinned Anki chrome, and the Android app) with dark-mode variants keyed off
# Anki's night-mode classes.
DASHBOARD_CSS = """
  :root {
    --bl-bg: #f6f7fb;
    --bl-surface: #ffffff;
    --bl-surface-2: #eef1f8;
    --bl-border: #e4e7f0;
    --bl-row-line: #eef0f6;
    --bl-text: #1b1e28;
    --bl-text-2: #575d70;
    --bl-text-3: #8a90a3;
    --bl-primary: #4f6bed;
    --bl-warn: #b3590a;
    --bl-shadow-card: 0 1px 2px rgba(18,22,45,.05), 0 1px 6px rgba(18,22,45,.04);
  }
  html.night-mode, body.nightMode {
    --bl-bg: #13151c;
    --bl-surface: #1c1f29;
    --bl-surface-2: #262b38;
    --bl-border: #2c3140;
    --bl-row-line: #262b37;
    --bl-text: #e8eaf3;
    --bl-text-2: #a4aabc;
    --bl-text-3: #737990;
    --bl-primary: #7387f2;
    --bl-warn: #e09a4e;
    --bl-shadow-card: 0 1px 2px rgba(0,0,0,.4);
  }
  body { font-family: -apple-system, "Segoe UI Variable", "Segoe UI", Roboto,
          "Helvetica Neue", Arial, sans-serif; margin: 0;
          padding: 20px; background: var(--bl-bg); color: var(--bl-text);
          -webkit-font-smoothing: antialiased; }
  h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: -.01em; }
  .mode { color: var(--bl-text-2); margin-bottom: 16px; font-size: 13px; }
  .cards { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 24px; }
  .card { background: var(--bl-surface); border-radius: 12px; padding: 16px 18px;
           flex: 1; min-width: 220px; border: 1px solid var(--bl-border);
           box-shadow: var(--bl-shadow-card); }
  .card-title { font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
                 color: var(--bl-text-3); font-weight: 600; margin-bottom: 8px; }
  .big { font-size: 32px; font-weight: 700; letter-spacing: -.02em;
         font-variant-numeric: tabular-nums; }
  .big.muted { font-size: 20px; font-weight: 600; color: var(--bl-text-3);
               letter-spacing: 0; }
  .range { color: var(--bl-text-2); font-size: 13px; margin-top: 2px;
           font-variant-numeric: tabular-nums; }
  .sub { color: var(--bl-text-2); font-size: 12px; margin-top: 8px;
         line-height: 1.5; }
  ul.evidence, ul.missing { margin: 4px 0 0; padding-left: 18px; font-size: 12px;
                             color: var(--bl-text-2); line-height: 1.6; }
  ul.missing li { color: var(--bl-warn); }
  h2 { font-size: 15px; margin: 26px 0 8px; letter-spacing: -.01em; }
  table { width: 100%; border-collapse: separate; border-spacing: 0;
           background: var(--bl-surface); border: 1px solid var(--bl-border);
           border-radius: 12px; overflow: hidden;
           box-shadow: var(--bl-shadow-card); }
  th, td { text-align: left; padding: 10px 14px; font-size: 13px;
            border-bottom: 1px solid var(--bl-row-line);
            font-variant-numeric: tabular-nums; }
  tr:last-child td { border-bottom: none; }
  th { background: var(--bl-surface-2); color: var(--bl-text-3);
       font-weight: 600; font-size: 11px; text-transform: uppercase;
       letter-spacing: .06em; }
  td.reasons { color: var(--bl-text-2); font-size: 12px; }
  ul { line-height: 1.6; }
  .timeline { display: flex; gap: 12px; }
  .milestone { background: var(--bl-surface); border-radius: 12px; padding: 14px;
                flex: 1; text-align: center; border: 1px solid var(--bl-border);
                box-shadow: var(--bl-shadow-card); }
  .ms-label { font-size: 11px; color: var(--bl-text-3); font-weight: 600;
              text-transform: uppercase; letter-spacing: .06em; }
  .ms-val { font-size: 26px; font-weight: 700; margin: 4px 0;
            letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
  .ms-cap { font-size: 11px; color: var(--bl-text-3); }
  .note { font-size: 11px; color: var(--bl-text-3); margin-top: 8px; }
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
