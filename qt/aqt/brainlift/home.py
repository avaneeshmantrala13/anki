# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""BrainLift landing screen — the guided home rendered inside the main window.

Instead of dropping a new user into Anki's deck browser (which is confusing if
you've never used Anki), BrainLift renders a clean, focused landing page in the
main content area: one obvious "next step", a simple 4-step path, and plain
navigation to the few things a student actually needs (study, add, browse,
stats). The full dashboard sits below.

It renders into ``mw.web`` as a custom main-window state ("brainliftHome") and
drives Anki's real actions through the web bridge (``pycmd``). No AI is used.
"""

from __future__ import annotations

import html
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aqt.main import AnkiQt

# Landing-specific styles. Rendered after DASHBOARD_CSS, which defines the
# shared --bl-* design tokens (light + night-mode); the extra tokens the
# landing needs are defined here.
LANDING_CSS = """
  :root {
    --bl-success: #178c53;
    --bl-success-tint: #e3f4ea;
    --bl-primary-hover: #4159d6;
    --bl-primary-active: #3a50c4;
    --bl-primary-tint: #edf1fe;
    --bl-primary-tint-border: #dbe2fc;
    --bl-hero-a: #5068ea;
    --bl-hero-b: #3d51cd;
    --bl-hero-shadow: 0 12px 32px rgba(61,81,205,.22);
    --bl-focus-ring: 0 0 0 3px rgba(79,107,237,.28);
  }
  html.night-mode, body.nightMode {
    --bl-success: #46c088;
    --bl-success-tint: rgba(70,192,136,.15);
    --bl-primary-hover: #8496f4;
    --bl-primary-active: #6377e8;
    --bl-primary-tint: rgba(115,135,242,.14);
    --bl-primary-tint-border: rgba(115,135,242,.32);
    --bl-hero-a: #4358cf;
    --bl-hero-b: #333fa8;
    --bl-hero-shadow: 0 12px 32px rgba(0,0,0,.45);
    --bl-focus-ring: 0 0 0 3px rgba(115,135,242,.35);
  }
  /* The landing owns its own padding; undo the dashboard body padding. */
  body { padding:0; margin:0; background:var(--bl-bg); }
  .bl-root, .bl-root *, .bl-root *::before, .bl-root *::after { box-sizing:border-box; }
  .bl-root { background:var(--bl-bg); color:var(--bl-text); min-height:100vh;
             margin:0; padding:32px 32px 64px;
             font-family:var(--bl-font-body);
             -webkit-font-smoothing:antialiased; }
  .bl-wrap { max-width:900px; margin:0 auto; }
  .bl-root button { transition:background .12s ease, border-color .12s ease,
                    color .12s ease, box-shadow .12s ease; }
  .bl-root button:focus-visible { outline:none; box-shadow:var(--bl-focus-ring); }

  .hero { background:linear-gradient(160deg,var(--bl-hero-a),var(--bl-hero-b));
          color:#fff; border-radius:16px; padding:28px 30px; margin-bottom:24px;
          box-shadow:var(--bl-hero-shadow); }
  .hero .eyebrow { font-family:var(--bl-font-mono); text-transform:uppercase;
                   letter-spacing:.16em; font-size:11px; font-weight:600;
                   opacity:.85; }
  .hero h1 { font-family:var(--bl-font-display); color:#fff; font-size:26px;
             margin:8px 0 6px; letter-spacing:-.02em; }
  .hero .lead { font-size:14px; line-height:1.55; opacity:.92; margin:0 0 20px;
                max-width:620px; }
  .hero .cta { background:#fff; color:var(--bl-hero-b); border:none;
               border-radius:10px; padding:12px 22px; font-size:14px;
               font-weight:600; cursor:pointer;
               box-shadow:0 1px 3px rgba(16,20,50,.25); }
  .hero .cta:hover { background:#f2f4ff; }
  .hero .cta:active { background:#e7ebfe; }
  .hero .cta:focus-visible { outline:none;
               box-shadow:0 0 0 3px rgba(255,255,255,.45); }

  .section-label { font-family:var(--bl-font-mono); font-size:11px;
                   text-transform:uppercase; letter-spacing:.1em;
                   color:var(--bl-cyan); margin:28px 0 10px; font-weight:600; }

  .steps { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
  .step { background:var(--bl-surface); border-radius:16px; padding:16px;
          position:relative; border:1px solid var(--bl-border);
          box-shadow:var(--bl-glow);
          display:flex; flex-direction:column;
          transition:box-shadow .15s ease, border-color .15s ease,
                     transform .15s ease; }
  .step.next { border-color:rgba(34,211,238,.5); box-shadow:var(--bl-glow-strong); }
  .step.done .num { background:var(--bl-success-tint); color:var(--bl-success); }
  .step .num { font-family:var(--bl-font-mono); width:26px; height:26px;
               border-radius:50%; background:var(--bl-surface-2);
               color:var(--bl-primary); font-weight:600; display:flex;
               align-items:center; justify-content:center; font-size:13px;
               margin-bottom:10px; font-variant-numeric:tabular-nums; }
  .step .title { font-family:var(--bl-font-display); font-weight:600;
                 font-size:14.5px; margin-bottom:4px; letter-spacing:-.01em; }
  .step .desc { font-size:12px; line-height:1.5; color:var(--bl-text-2); flex:1;
                margin-bottom:12px; }
  .pill { display:inline-block; font-family:var(--bl-font-mono); font-size:10px;
          padding:3px 8px; border-radius:20px; font-weight:600;
          text-transform:uppercase; letter-spacing:.06em; margin-bottom:10px;
          width:fit-content; }
  .pill.done { background:var(--bl-success-tint); color:var(--bl-success); }
  .pill.todo { background:var(--bl-primary-tint); color:var(--bl-primary); }
  .pill.optional,.pill.locked { background:var(--bl-surface-2);
          color:var(--bl-text-3); }
  .step .btn { background:var(--bl-primary); color:#fff; border:none;
               border-radius:9px; padding:9px 12px; font-size:13px;
               font-weight:600; cursor:pointer; width:100%; }
  .step .btn:hover { background:var(--bl-primary-hover); }
  .step .btn:active { background:var(--bl-primary-active); }
  .step .btn.secondary { background:var(--bl-surface-2); color:var(--bl-text-2); }
  .step .btn.secondary:hover { background:var(--bl-primary-tint);
               color:var(--bl-primary); }
  .step .btn:disabled { background:var(--bl-surface-2); color:var(--bl-text-3);
               cursor:default; }
  .step .btn:disabled:hover { background:var(--bl-surface-2);
               color:var(--bl-text-3); }

  .quick { display:flex; gap:10px; flex-wrap:wrap; }
  .quick .qbtn { background:var(--bl-surface); border:1px solid var(--bl-border);
                 border-radius:12px; padding:11px 16px; font-size:13px;
                 font-weight:600; color:var(--bl-text-2); cursor:pointer;
                 display:flex; align-items:center; gap:8px;
                 box-shadow:var(--bl-glow); }
  .quick .qbtn:hover { border-color:var(--bl-primary-tint-border);
                 background:var(--bl-primary-tint); color:var(--bl-primary); }
  .quick .qbtn:active { background:var(--bl-surface-2); }
  .quick .qbtn .ico { font-size:14px; color:var(--bl-text-3); }
  .quick .qbtn:hover .ico { color:var(--bl-primary); }

  .dash-wrap { background:transparent; margin-top:6px; }

  /* Feature 1 calibration launcher — deliberately prominent. */
  .cal-card { background:var(--bl-surface); border:1px solid var(--bl-border);
              border-radius:16px;
              padding:18px 20px; box-shadow:var(--bl-glow);
              display:flex; gap:20px; align-items:center;
              justify-content:space-between; flex-wrap:wrap; }
  .cal-head { flex:1; min-width:280px; }
  .cal-title { font-family:var(--bl-font-display); font-weight:700; font-size:16px;
               letter-spacing:-.01em; margin-bottom:4px; }
  .cal-desc { font-size:13px; line-height:1.5; color:var(--bl-text-2);
              margin-bottom:8px; }
  .cal-status { font-size:13px; color:var(--bl-text); margin-bottom:6px; }
  .cal-ai { font-size:11.5px; color:var(--bl-text-3); line-height:1.45; }
  .cal-actions { display:flex; flex-direction:column; gap:8px;
                 align-items:stretch; min-width:200px; }
  .cal-start { background:var(--bl-primary); color:#fff; border:none;
               border-radius:10px; padding:12px 20px; font-size:14px;
               font-weight:700; cursor:pointer; white-space:nowrap; }
  .cal-start:hover { background:var(--bl-primary-hover); }
  .cal-start:active { background:var(--bl-primary-active); }
  .cal-reset { background:var(--bl-surface-2); color:var(--bl-text-2);
               border:1px solid var(--bl-border); border-radius:10px;
               padding:9px 16px; font-size:13px; font-weight:600;
               cursor:pointer; }
  .cal-reset:hover { background:var(--bl-primary-tint); color:var(--bl-primary); }

  /* AI Activity — makes the two AI features observable in the backend. */
  .ai-card { background:var(--bl-surface); border:1px solid var(--bl-border);
             border-radius:16px; padding:18px 20px; box-shadow:var(--bl-glow); }
  .ai-gauge { margin-bottom:14px; }
  .ai-gauge-head { display:flex; justify-content:space-between; align-items:baseline;
                   gap:12px; margin-bottom:6px; }
  .ai-gauge-title { font-family:var(--bl-font-display); font-weight:700;
                    font-size:14px; }
  .ai-p { font-family:var(--bl-font-mono); font-variant-numeric:tabular-nums;
          font-weight:600; font-size:13px; color:var(--bl-text-2); }
  .ai-bar { position:relative; height:8px; border-radius:6px;
            background:var(--bl-surface-2); overflow:hidden; }
  .ai-bar-fill { position:absolute; top:0; left:0; bottom:0;
                 background:linear-gradient(90deg,#38bdf8,var(--bl-cyan));
                 box-shadow:0 0 12px rgba(34,211,238,.7); }
  .ai-bar-thresh { position:absolute; top:-3px; bottom:-3px; width:2px;
                   background:var(--bl-warn); opacity:.8; }
  .ai-status { font-size:12px; color:var(--bl-text-2); margin-top:6px;
               line-height:1.5; }
  .ai-chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .ai-chip { font-family:var(--bl-font-mono); font-size:10.5px; padding:3px 8px;
             border-radius:20px; background:var(--bl-surface-2);
             color:var(--bl-text-2); border:1px solid var(--bl-border);
             font-variant-numeric:tabular-nums; }
  .ai-events { list-style:none; margin:10px 0 0; padding:0;
               border-top:1px solid var(--bl-border); }
  .ai-ev { padding:10px 0; border-bottom:1px solid var(--bl-border); }
  .ai-ev:last-child { border-bottom:none; }
  .ai-ev-head { display:flex; gap:8px; align-items:baseline; flex-wrap:wrap; }
  .ai-badge { font-family:var(--bl-font-mono); font-size:9.5px; font-weight:700;
              text-transform:uppercase; letter-spacing:.06em; padding:2px 7px;
              border-radius:6px; }
  .ai-badge.f1 { background:rgba(34,211,238,.14); color:#0e7490; }
  .ai-badge.f2 { background:var(--bl-primary-tint); color:var(--bl-primary); }
  html.night-mode .ai-badge.f1, body.nightMode .ai-badge.f1 { color:#67e8f9; }
  .ai-ev-sum { font-size:12.5px; font-weight:600; color:var(--bl-text); }
  .ai-ev-time { font-family:var(--bl-font-mono); font-size:10.5px;
                color:var(--bl-text-3); margin-left:auto; }
  .ai-ev-detail { list-style:none; margin:6px 0 0; padding:0 0 0 2px;
                  font-family:var(--bl-font-mono); font-size:11px;
                  color:var(--bl-text-2); line-height:1.55; }
  .ai-ev-detail li { overflow-wrap:anywhere; }
  .ai-empty { font-size:12.5px; color:var(--bl-text-3); font-style:italic;
              padding:6px 0; }
  .ai-actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; }
  .ai-btn { background:var(--bl-surface-2); color:var(--bl-text-2);
            border:1px solid var(--bl-border); border-radius:10px;
            padding:9px 14px; font-size:12.5px; font-weight:600; cursor:pointer; }
  .ai-btn:hover { border-color:rgba(34,211,238,.5); color:var(--bl-text);
                  box-shadow:var(--bl-glow); }
  .ai-btn.accent { background:linear-gradient(160deg,#0891b2,#0e7490);
                   color:#fff; border:none; }
  .ai-btn.accent:hover { filter:brightness(1.08); }

  @media (max-width:760px){ .steps{ grid-template-columns:1fr 1fr; } }
"""


class BrainLiftLanding:
    """Renders the guided landing into the main window's central web view."""

    def __init__(self, mw: AnkiQt) -> None:
        self.mw = mw
        self.web = mw.web

    # --- main-window state entry -------------------------------------------

    def show(self) -> None:
        from aqt.sound import av_player

        av_player.stop_and_clear_queue()
        self.web = self.mw.web
        self.web.set_bridge_command(self._on_cmd, self)
        self.mw.toolbar.redraw()
        # Hide the deck-browser-style bottom bar for a clean, focused landing.
        self.mw.bottomWeb.hide()
        self.render()

    def render(self) -> None:
        from anki.brainlift import dashboard, diagnostic as dx, onboarding as ob

        col = self.mw.col
        if col is None:
            self.web.stdHtml("<h2>Open a collection first.</h2>", context=self)
            return

        d = dashboard.build_dashboard(col)
        onboarded = ob.is_onboarded(col)
        has_diag = dx.has_diagnostic(col)
        diag_required = (
            d.onboarding_result.diagnostic_required if d.onboarding_result else True
        )
        studied = any(t.reviewed_cards > 0 for t in d.coverage.topics)
        has_cards = any(t.total_cards > 0 for t in d.coverage.topics)
        ready = d.readiness.available

        guided = self._guided_html(
            onboarded, has_diag, diag_required, studied, has_cards, ready
        )
        calibration = self._calibration_html(col)
        ai_activity = self._ai_activity_html(col)
        body = (
            f"<style>{dashboard.DASHBOARD_CSS}{LANDING_CSS}</style>"
            "<div class='bl-root'><div class='bl-wrap'>"
            f"{guided}"
            f"{calibration}"
            f"{ai_activity}"
            "<div class='section-label'>Your dashboard</div>"
            f"<div class='dash-wrap'>{dashboard.render_body(d, heading='')}</div>"
            "</div></div>"
        )
        self.web.stdHtml(body, context=self)

    def _calibration_html(self, col) -> str:
        """Feature 1 entry: a prominent, always-visible, re-runnable launcher.

        Renders a dedicated card with a big "Start Calibration Test (15)" button
        (wired through the existing pycmd bridge). If a prior run exists it shows
        the last score plus a "Reset & re-run" affordance — but the test is
        re-runnable regardless, since running it simply overwrites the stored
        result. Also surfaces whether real OpenAI or the deterministic fallback
        will be used, so testing is never silently gated by the AI toggle.
        """
        from anki.brainlift import ai as blai
        from anki.brainlift import calibration as calib

        size = calib.CALIBRATION_TEST_SIZE
        prior = calib.load_calibration(col)

        ai_on = blai.ai_enabled(col)
        key_present = blai.api_key_from_env() is not None
        real_ai = ai_on and key_present
        if real_ai:
            ai_line = (
                "Real OpenAI analog generation is ON "
                f"(model {html.escape(blai.ai_model(col))}, OPENAI_API_KEY detected)."
            )
        elif ai_on and not key_present:
            ai_line = (
                "AI is enabled but no OPENAI_API_KEY was detected — questions use "
                "the deterministic fallback generator."
            )
        else:
            ai_line = (
                "AI is off — questions use the deterministic fallback generator. "
                "Enable it under Tools ▸ BrainLift: AI settings (and set "
                "OPENAI_API_KEY) to use real OpenAI."
            )

        if prior is not None:
            status = (
                "<div class='cal-status'>Last run: "
                f"<b>{prior.accuracy:.0%}</b> calibration accuracy "
                f"· {html.escape(prior.explanation)}</div>"
            )
            primary_label = f"Re-run Calibration Test ({size})"
            reset_btn = (
                "<button class='btn secondary cal-reset' "
                "onclick=\"pycmd('bl:calibrate:reset')\">Reset result</button>"
            )
        else:
            status = (
                "<div class='cal-status'>Not run yet — rate "
                f"{size} cards, answer {size} analog questions, then see your "
                "calibration accuracy score.</div>"
            )
            primary_label = f"Start Calibration Test ({size})"
            reset_btn = ""

        return (
            "<div class='section-label'>Confidence calibration · Feature 1</div>"
            "<div class='cal-card'>"
            "<div class='cal-head'>"
            "<div class='cal-title'>Calibration test</div>"
            f"<div class='cal-desc'>Rate your confidence on {size} Exam P cards, "
            f"answer {size} AI-generated analog questions, and get an accuracy "
            "score for how well you know what you know.</div>"
            f"{status}"
            f"<div class='cal-ai'>{ai_line}</div>"
            "</div>"
            "<div class='cal-actions'>"
            f"<button class='btn cal-start' onclick=\"pycmd('bl:calibrate')\">"
            f"{html.escape(primary_label)}</button>"
            f"{reset_btn}"
            "</div>"
            "</div>"
        )

    def _ai_activity_html(self, col) -> str:
        """A live, always-visible window into what the two AI features are doing.

        Two parts, both reading real state (nothing is faked):
        * a LIVE gauge for Feature 2 — the current fatigue session's learned-model
          probability (or the deterministic drain when AI is off) against the
          intervention threshold, plus the smoothed signals feeding it; and
        * a running EVENT LOG of completed calibration runs (Feature 1) and fired
          fatigue interventions (Feature 2), each with the source/why.
        """
        from anki.brainlift import activity
        from anki.brainlift import ai as blai
        from anki.brainlift import fatigue as fx

        gauge = self._fatigue_gauge_html(col, blai, fx)

        events = activity.load_events(col)
        if events:
            rows = "".join(self._ai_event_html(e) for e in events[:8])
            log = f"<ul class='ai-events'>{rows}</ul>"
        else:
            log = (
                "<div class='ai-empty'>No AI events yet. Run the calibration test "
                "above, or study (or use the demo button) to trigger the fatigue "
                "detector — each one is logged here with its inputs.</div>"
            )

        clear_btn = (
            "<button class='ai-btn' onclick=\"pycmd('bl:ai:clearlog')\">Clear log</button>"
            if events
            else ""
        )
        actions = (
            "<div class='ai-actions'>"
            "<button class='ai-btn accent' onclick=\"pycmd('bl:fatigue:simulate')\">"
            "Simulate a drained session (demo)</button>"
            "<button class='ai-btn' onclick=\"pycmd('bl:refresh')\">Refresh</button>"
            f"{clear_btn}"
            "</div>"
        )

        return (
            "<div class='section-label'>AI activity · behind the scenes</div>"
            "<div class='ai-card'>"
            f"{gauge}"
            f"{log}"
            f"{actions}"
            "</div>"
        )

    def _fatigue_gauge_html(self, col, blai, fx) -> str:
        session = fx.load_session(col)
        answers = int(session.get("answers", 0)) if session else 0
        ai_on = blai.ai_enabled(col)

        if not session or answers == 0:
            return (
                "<div class='ai-gauge'>"
                "<div class='ai-gauge-head'>"
                "<span class='ai-gauge-title'>Feature 2 · live fatigue model</span>"
                "</div>"
                "<div class='ai-status'>No review activity this session yet. Start "
                "reviewing — or run the demo below — and this gauge updates live as "
                "the detector reads your answer speed and accuracy.</div>"
                "</div>"
            )

        fv = fx.model_feature_vector(session)
        prob = fx.predict_drain_probability(fv)
        if ai_on:
            score, thr, engine = prob, fx.MODEL_INTERVENE, "learned logistic model"
        else:
            score = float(session.get("smoothed_drain", 0.0))
            thr, engine = fx.DRAIN_INTERVENE, "deterministic heuristic"

        pct = max(0.0, min(1.0, score)) * 100.0
        thr_pct = max(0.0, min(1.0, thr)) * 100.0

        if answers < fx.MIN_ANSWERS_BEFORE_DETECT:
            status = (
                f"Warming up — {answers}/{fx.MIN_ANSWERS_BEFORE_DETECT} answers "
                "before detection starts."
            )
        elif score >= thr:
            status = (
                "Above the intervention threshold — an offload fires on the next "
                "qualifying answer (easier card / topic switch)."
            )
        else:
            status = (
                f"Below the {thr:.2f} threshold — you're steady, so no intervention "
                "is needed."
            )
        gate = "TEST MODE (fires immediately)" if fx.test_mode(col) else "PROD timing gate"
        status += f" · {engine} · {gate}"

        chips = "".join(
            f"<span class='ai-chip'>{html.escape(name)} {val:.2f}</span>"
            for name, val in zip(fx.FATIGUE_MODEL_FEATURES, fv)
        )

        return (
            "<div class='ai-gauge'>"
            "<div class='ai-gauge-head'>"
            "<span class='ai-gauge-title'>Feature 2 · live fatigue model</span>"
            f"<span class='ai-p'>p(drained) {score:.2f} · fires ≥ {thr:.2f}</span>"
            "</div>"
            "<div class='ai-bar'>"
            f"<div class='ai-bar-fill' style='width:{pct:.1f}%'></div>"
            f"<div class='ai-bar-thresh' style='left:{thr_pct:.1f}%'></div>"
            "</div>"
            f"<div class='ai-status'>{html.escape(status)}</div>"
            f"<div class='ai-chips'>{chips}</div>"
            "</div>"
        )

    def _ai_event_html(self, event: dict) -> str:
        feature = str(event.get("feature", ""))
        badge_cls = "f1" if feature == "calibration" else "f2"
        badge_lbl = "Feature 1" if feature == "calibration" else "Feature 2"
        at = int(event.get("at", 0) or 0)
        when = time.strftime("%b %d, %H:%M", time.localtime(at)) if at else ""
        summary = html.escape(str(event.get("summary", "")))
        details = event.get("detail", []) or []
        detail_html = ""
        if details:
            lis = "".join(f"<li>{html.escape(str(d))}</li>" for d in details[:6])
            detail_html = f"<ul class='ai-ev-detail'>{lis}</ul>"
        return (
            "<li class='ai-ev'>"
            "<div class='ai-ev-head'>"
            f"<span class='ai-badge {badge_cls}'>{badge_lbl}</span>"
            f"<span class='ai-ev-sum'>{summary}</span>"
            f"<span class='ai-ev-time'>{html.escape(when)}</span>"
            "</div>"
            f"{detail_html}"
            "</li>"
        )

    # --- HTML ---------------------------------------------------------------

    def _guided_html(
        self,
        onboarded: bool,
        has_diag: bool,
        diag_required: bool,
        studied: bool,
        has_cards: bool,
        ready: bool,
    ) -> str:
        if not onboarded:
            cta_label, cta_cmd, hero_text, nxt = (
                "Set up my goals",
                "bl:onboard",
                "Welcome to BrainLift for Exam P. Let's start by setting your exam "
                "date and goal — it takes about a minute.",
                "onboard",
            )
        elif diag_required and not has_diag:
            cta_label, cta_cmd, hero_text, nxt = (
                "Take the diagnostic",
                "bl:diagnostic",
                "Great — your goals are set. Next, take a short diagnostic so "
                "BrainLift can measure how you do on real Exam P questions.",
                "diagnostic",
            )
        elif not studied:
            cta_label, cta_cmd, hero_text, nxt = (
                "Start studying",
                "bl:study",
                "You're ready to study. Review your Exam P cards — your scores build "
                "up automatically as you go.",
                "study",
            )
        elif not ready:
            cta_label, cta_cmd, hero_text, nxt = (
                "Keep studying",
                "bl:study",
                "Keep going. Readiness stays hidden until there's enough evidence — "
                "keep reviewing to unlock an honest score.",
                "study",
            )
        else:
            cta_label, cta_cmd, hero_text, nxt = (
                "See my readiness",
                "bl:refresh",
                "You're on track. Review your readiness and weakest topics below, and "
                "keep studying consistently.",
                "done",
            )

        hero = (
            "<div class='hero'>"
            "<div class='eyebrow'>BrainLift · Exam P</div>"
            "<h1>Here's exactly what to do next</h1>"
            f"<p class='lead'>{html.escape(hero_text)}</p>"
            f"<button class='cta' onclick=\"pycmd('{cta_cmd}')\">"
            f"{html.escape(cta_label)}</button>"
            "</div>"
        )

        steps = "".join(
            [
                self._step(
                    1,
                    "Set your goals",
                    "Exam date, goal score, weekly study time.",
                    done=onboarded,
                    is_next=(nxt == "onboard"),
                    btn=("Update" if onboarded else "Start", "bl:onboard"),
                ),
                self._step(
                    2,
                    "Take the diagnostic",
                    "A few real Exam P questions to gauge your starting point.",
                    done=has_diag,
                    is_next=(nxt == "diagnostic"),
                    locked=not onboarded,
                    optional=(onboarded and not diag_required and not has_diag),
                    btn=("Retake" if has_diag else "Start", "bl:diagnostic"),
                ),
                self._step(
                    3,
                    "Study your cards",
                    "Review with Anki's proven engine (FSRS)."
                    if has_cards
                    else "Import an Exam P deck first (button below).",
                    done=studied,
                    is_next=(nxt == "study"),
                    btn=("Study", "bl:study"),
                ),
                self._step(
                    4,
                    "Track readiness",
                    "Memory, Performance & Readiness — shown honestly."
                    if ready
                    else "Unlocks once there's enough evidence (see below).",
                    done=ready,
                    is_next=(nxt == "done"),
                    btn=("View", "bl:refresh"),
                ),
            ]
        )

        quick = (
            "<div class='section-label'>Anki tools</div>"
            "<div class='quick'>"
            "<button class='qbtn' onclick=\"pycmd('bl:study')\">"
            "<span class='ico'>▶</span> Study decks</button>"
            "<button class='qbtn' onclick=\"pycmd('bl:add')\">"
            "<span class='ico'>＋</span> Add cards</button>"
            "<button class='qbtn' onclick=\"pycmd('bl:browse')\">"
            "<span class='ico'>▤</span> Browse</button>"
            "<button class='qbtn' onclick=\"pycmd('bl:stats')\">"
            "<span class='ico'>▦</span> Stats</button>"
            "<button class='qbtn' onclick=\"pycmd('bl:sync')\">"
            "<span class='ico'>⟳</span> Sync</button>"
            "</div>"
        )

        return (
            hero
            + "<div class='section-label'>Your path</div>"
            + f"<div class='steps'>{steps}</div>"
            + quick
        )

    def _step(
        self,
        num: int,
        title: str,
        desc: str,
        done: bool = False,
        is_next: bool = False,
        locked: bool = False,
        optional: bool = False,
        btn: tuple[str, str] | None = None,
    ) -> str:
        if done:
            pill, klass = "<span class='pill done'>Done</span>", "step done"
        elif locked:
            pill, klass = "<span class='pill locked'>Locked</span>", "step"
        elif optional:
            pill = "<span class='pill optional'>Optional</span>"
            klass = "step next" if is_next else "step"
        else:
            pill = "<span class='pill todo'>To do</span>"
            klass = "step next" if is_next else "step"

        button = ""
        if btn is not None:
            label, cmd = btn
            disabled = "disabled" if locked else ""
            btn_class = "btn secondary" if done else "btn"
            button = (
                f"<button class='{btn_class}' {disabled} "
                f"onclick=\"pycmd('{cmd}')\">{html.escape(label)}</button>"
            )

        return (
            f"<div class='{klass}'><div class='num'>{num}</div>"
            f"{pill}"
            f"<div class='title'>{html.escape(title)}</div>"
            f"<div class='desc'>{html.escape(desc)}</div>"
            f"{button}</div>"
        )

    # --- bridge -------------------------------------------------------------

    def _on_cmd(self, cmd: str):
        from aqt.utils import tooltip

        if cmd == "bl:onboard":
            self._open_onboarding()
        elif cmd == "bl:diagnostic":
            self._open_diagnostic()
        elif cmd == "bl:study":
            self.mw.moveToState("deckBrowser")
        elif cmd == "bl:add":
            self.mw.onAddCard()
        elif cmd == "bl:browse":
            self.mw.onBrowse()
        elif cmd == "bl:stats":
            self.mw.onStats()
        elif cmd == "bl:sync":
            self.mw.onSync()
        elif cmd == "bl:calibrate":
            self._open_calibration()
        elif cmd == "bl:calibrate:reset":
            self._reset_calibration()
        elif cmd == "bl:fatigue:simulate":
            self._simulate_fatigue()
        elif cmd == "bl:ai:clearlog":
            self._clear_ai_log()
        elif cmd == "bl:refresh":
            self.render()
        return None

    def _simulate_fatigue(self) -> None:
        """Demo trigger for Feature 2: push a genuinely drained answer burst
        through the REAL detector (nothing is faked) so the offload banner fires
        and the AI Activity log records it. Mirrors what a long, degrading study
        session produces — a fast/accurate baseline followed by slow, error-prone
        answers — so the learned model's probability crosses its threshold."""
        col = self.mw.col
        if col is None:
            return
        from aqt.utils import tooltip

        from anki.brainlift import fatigue as fx

        now = int(time.time())
        fx.reset_session(col, now=now)
        # 5 fast, correct answers establish the user's fresh-session baseline.
        for i in range(5):
            fx.record_answer(col, 2.0, True, "Probability", now=now + i)
        # Then a sustained drained burst: much slower + mostly wrong.
        decision = None
        for i in range(12):
            d = fx.record_answer(
                col, 24.0, (i % 5 == 0), "Probability", now=now + 6 + i
            )
            if d.intervene:
                decision = d
                break
        if decision is not None:
            served = fx.apply_offload(col, decision, "Probability")
            suffix = " — reordering your next card" if served else ""
            tooltip(
                f"🧠 {decision.banner}{suffix} (demo)", period=5000, parent=self.mw
            )
        else:
            tooltip(
                "Ran a simulated drained session — the detector stayed below its "
                "threshold.",
                parent=self.mw,
            )
        self.render()

    def _clear_ai_log(self) -> None:
        from aqt.utils import tooltip

        if self.mw.col is not None:
            from anki.brainlift import activity

            activity.clear_events(self.mw.col)
            tooltip("AI activity log cleared.", parent=self.mw)
        self.render()

    def _open_calibration(self) -> None:
        # Delegate to the single canonical launcher, which defers the dialog off
        # this pycmd bridge callback. Refresh the landing after the dialog closes.
        from aqt.brainlift import open_calibration

        open_calibration(self.mw, on_close=self.render)

    def _reset_calibration(self) -> None:
        from aqt.utils import tooltip

        if self.mw.col is not None:
            from anki.brainlift import calibration as calib

            calib.clear_calibration(self.mw.col)
            tooltip("Calibration result cleared — run the test again.", parent=self.mw)
        self.render()

    def _open_onboarding(self) -> None:
        from aqt.brainlift.onboarding_dialog import OnboardingDialog

        OnboardingDialog(self.mw).exec()
        self.render()

    def _open_diagnostic(self) -> None:
        from aqt.brainlift.diagnostic_dialog import DiagnosticDialog

        DiagnosticDialog(self.mw).exec()
        self.render()
