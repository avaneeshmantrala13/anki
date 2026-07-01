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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aqt.main import AnkiQt

LANDING_CSS = """
  .bl-root, .bl-root *, .bl-root *::before, .bl-root *::after { box-sizing:border-box; }
  .bl-root { background:#f4f5f9; color:#1d1d24; min-height:100vh; margin:0;
             padding:28px 30px 60px;
             font-family:-apple-system,Segoe UI,Roboto,sans-serif; }
  .bl-wrap { max-width:900px; margin:0 auto; }
  .hero { background:linear-gradient(135deg,#4f6bed,#8a4fed); color:#fff;
          border-radius:18px; padding:28px 30px; margin-bottom:22px;
          box-shadow:0 8px 30px rgba(79,107,237,.25); }
  .hero .eyebrow { text-transform:uppercase; letter-spacing:.1em; font-size:11px;
                   opacity:.85; }
  .hero h1 { color:#fff; font-size:26px; margin:6px 0 4px; }
  .hero .lead { font-size:15px; opacity:.95; margin:0 0 18px; max-width:620px; }
  .hero .cta { background:#fff; color:#3b3b7a; border:none; border-radius:10px;
               padding:13px 22px; font-size:15px; font-weight:700; cursor:pointer; }
  .hero .cta:hover { background:#f0f0ff; }
  .section-label { font-size:12px; text-transform:uppercase; letter-spacing:.06em;
                   color:#7a7a86; margin:26px 0 10px; font-weight:700; }
  .steps { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
  .step { background:#fff; border-radius:14px; padding:16px; position:relative;
          box-shadow:0 1px 4px rgba(0,0,0,.07); border-top:4px solid #e3e3ea;
          display:flex; flex-direction:column; }
  .step.next { border-top-color:#4f6bed; box-shadow:0 6px 18px rgba(79,107,237,.18); }
  .step.done { border-top-color:#1a9e5f; }
  .step .num { width:28px; height:28px; border-radius:50%; background:#eef0f6;
               color:#4f6bed; font-weight:700; display:flex; align-items:center;
               justify-content:center; font-size:14px; margin-bottom:10px; }
  .step.done .num { background:#e4f6ec; color:#1a9e5f; }
  .step .title { font-weight:700; font-size:14px; margin-bottom:4px; }
  .step .desc { font-size:12px; color:#6b6b76; flex:1; margin-bottom:12px; }
  .pill { display:inline-block; font-size:10px; padding:2px 8px; border-radius:20px;
          font-weight:700; margin-bottom:10px; width:fit-content; }
  .pill.done { background:#e4f6ec; color:#1a9e5f; }
  .pill.todo { background:#eef0f6; color:#4f6bed; }
  .pill.optional,.pill.locked { background:#f0f0f2; color:#8a8a90; }
  .step .btn { background:#4f6bed; color:#fff; border:none; border-radius:9px;
               padding:9px 12px; font-size:13px; font-weight:600; cursor:pointer;
               width:100%; }
  .step .btn.secondary { background:#eef0f6; color:#3b3b7a; }
  .step .btn:disabled { background:#e6e6ea; color:#a8a8ae; cursor:default; }
  .quick { display:flex; gap:10px; flex-wrap:wrap; }
  .quick .qbtn { background:#fff; border:1px solid #e3e3ea; border-radius:10px;
                 padding:12px 16px; font-size:13px; font-weight:600; color:#3b3b7a;
                 cursor:pointer; display:flex; align-items:center; gap:8px; }
  .quick .qbtn:hover { border-color:#4f6bed; color:#4f6bed; }
  .quick .qbtn .ico { font-size:16px; }
  .dash-wrap { background:transparent; margin-top:6px; }
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
        body = (
            f"<style>{dashboard.DASHBOARD_CSS}{LANDING_CSS}</style>"
            "<div class='bl-root'><div class='bl-wrap'>"
            f"{guided}"
            "<div class='section-label'>Your dashboard</div>"
            f"<div class='dash-wrap'>{dashboard.render_body(d, heading='')}</div>"
            "</div></div>"
        )
        self.web.stdHtml(body, context=self)

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
                "Set up my study plan",
                "bl:onboard",
                "Welcome to BrainLift for Exam P. Let's start by setting up your "
                "study plan — it takes about a minute.",
                "onboard",
            )
        elif diag_required and not has_diag:
            cta_label, cta_cmd, hero_text, nxt = (
                "Take the diagnostic",
                "bl:diagnostic",
                "Great — your plan is set. Next, take a short diagnostic so BrainLift "
                "can measure how you do on real Exam P questions.",
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
                    "Set up your plan",
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
        elif cmd == "bl:refresh":
            self.render()
        return None

    def _open_onboarding(self) -> None:
        from aqt.brainlift.onboarding_dialog import OnboardingDialog

        OnboardingDialog(self.mw).exec()
        self.render()

    def _open_diagnostic(self) -> None:
        from aqt.brainlift.diagnostic_dialog import DiagnosticDialog

        DiagnosticDialog(self.mw).exec()
        self.render()
