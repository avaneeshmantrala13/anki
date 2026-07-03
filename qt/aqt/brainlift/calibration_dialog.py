# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 1 UI — the metacognitive calibration ("confidence authority") test.

Rendered inside an :class:`~aqt.webview.AnkiWebView` (not plain Qt widgets) so it
can reuse Anki's *own* card rendering + MathJax bundle. That means:

* The real card FRONT is shown (rendered from the note's templates/fields, not
  just the deck/topic name) while the user rates their confidence, and the card
  ANSWER (back) is only revealed *after* they rate.
* Card content, the AI analog questions, their multiple-choice options and the
  shown solution all render as HTML with MathJax — ``\\(...\\)`` / ``\\[...\\]``
  become real equations instead of raw source, and no gibberish/brackets leak.
* Every surface (progress header, prompts, options, buttons, score screen) uses
  an explicit high-contrast BrainLift palette that works in light *and* dark.

Two phases (unchanged scoring):

1. Rate confidence on ``CALIBRATION_TEST_SIZE`` Exam P cards *before* the answer
   is revealed (each rating is followed by an answer-reveal step).
2. Answer ``CALIBRATION_TEST_SIZE`` AI-generated analog MCQs (one per rated
   card; each records its named source), each graded 1/0 and its solution shown.

Scoring/persistence live in :mod:`anki.brainlift.calibration`; works with AI off
(deterministic analogs).
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING

from aqt.qt import QDialog, QVBoxLayout
from aqt.utils import tooltip

if TYPE_CHECKING:
    from aqt.main import AnkiQt


# --- static assets reused from Anki's reviewer ------------------------------
# The exact same MathJax bundle + config the reviewer loads, so math renders
# identically here. reviewer.css carries the `.card` styling for card content.
_CSS = ["css/reviewer.css"]
_JS = [
    "js/mathjax.js",
    "js/vendor/mathjax/tex-chtml-full.js",
]

# High-contrast, theme-aware chrome around the (white) card surface. Explicit
# colors — never palette() — so the header/labels/options are always legible on
# Anki's dark theme (the reported bug) as well as light.
CALIBRATION_CSS = """
:root {
  --cal-bg: #f4f6fb;
  --cal-text: #23283a;
  --cal-strong: #171a24;
  --cal-muted: #4a5165;
  --cal-accent: #3346c4;
  --cal-surface: #ffffff;
  --cal-border: #d7dcea;
  --cal-opt-bg: #ffffff;
  --cal-opt-hover: #eef1fe;
  --cal-opt-border: #cfd6ea;
  --cal-opt-checked-bg: #e7ecff;
  --cal-opt-checked-border: #3346c4;
  --cal-correct-bg: #e3f4ea;
  --cal-correct-border: #178c53;
  --cal-correct-text: #0f6b3e;
  --cal-wrong-bg: #fdecec;
  --cal-wrong-border: #c9463f;
}
html.night-mode, body.nightMode {
  --cal-bg: #14161d;
  --cal-text: #e8eaf3;
  --cal-strong: #f1f3fb;
  --cal-muted: #b3b9cc;
  --cal-accent: #9db0ff;
  --cal-surface: #1d212c;
  --cal-border: #333949;
  --cal-opt-bg: #232836;
  --cal-opt-hover: #2b3143;
  --cal-opt-border: #3a4256;
  --cal-opt-checked-bg: #2e3860;
  --cal-opt-checked-border: #7f92ff;
  --cal-correct-bg: rgba(70,192,136,.16);
  --cal-correct-border: #46c088;
  --cal-correct-text: #7fe0b0;
  --cal-wrong-bg: rgba(201,70,63,.16);
  --cal-wrong-border: #e57373;
}
html, body {
  background: var(--cal-bg) !important;
  color: var(--cal-text);
  margin: 0; padding: 0;
}
.cal-wrap {
  max-width: 760px; margin: 0 auto; padding: 22px 26px 30px;
  font-family: -apple-system, "Segoe UI Variable", "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased; text-align: left;
}
.cal-progress {
  font-size: 12px; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; color: var(--cal-accent); margin: 0 0 6px;
}
.cal-prompt {
  font-size: 16px; font-weight: 600; color: var(--cal-strong);
  margin: 0 0 14px; line-height: 1.45;
}
.cal-answer-label {
  font-size: 12px; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; color: var(--cal-correct-text); margin: 2px 0 8px;
}
/* Card content rendered by Anki's own templates. Force a legible white card
   surface with dark text regardless of theme (matches the reviewer's look). */
.cal-card {
  background: var(--cal-surface); border: 1px solid var(--cal-border);
  border-radius: 12px; padding: 18px 20px; margin: 0 0 16px;
  box-shadow: 0 1px 3px rgba(15,20,45,.08); overflow-x: auto;
}
.cal-card .card {
  color: #12141c !important; background: transparent !important;
  text-align: left !important; font-size: 17px !important; margin: 0 !important;
}
.cal-card img { max-width: 100%; height: auto; }
.cal-groove-title {
  font-size: 13px; font-weight: 700; color: var(--cal-muted);
  margin: 4px 0 10px;
}
.cal-opts { display: flex; flex-direction: column; gap: 9px; margin: 0 0 18px; }
.cal-opt {
  display: flex; align-items: flex-start; gap: 11px; cursor: pointer;
  background: var(--cal-opt-bg); border: 1.5px solid var(--cal-opt-border);
  border-radius: 10px; padding: 12px 15px; transition: background .1s ease,
  border-color .1s ease;
}
.cal-opt:hover { background: var(--cal-opt-hover); border-color: var(--cal-opt-checked-border); }
.cal-opt input { margin: 3px 0 0; accent-color: var(--cal-accent); flex: none; }
.cal-opt-text { color: var(--cal-strong); font-size: 15px; line-height: 1.4; }
.cal-opt.checked { background: var(--cal-opt-checked-bg); border-color: var(--cal-opt-checked-border); }
.cal-opt.correct { background: var(--cal-correct-bg); border-color: var(--cal-correct-border); }
.cal-opt.wrong { background: var(--cal-wrong-bg); border-color: var(--cal-wrong-border); }
.cal-tag {
  margin-left: auto; font-size: 11px; font-weight: 700; padding: 2px 8px;
  border-radius: 20px; text-transform: uppercase; letter-spacing: .04em;
  align-self: center;
}
.cal-tag.correct { background: var(--cal-correct-border); color: #fff; }
.cal-tag.wrong { background: var(--cal-wrong-border); color: #fff; }
.cal-note { font-size: 13.5px; color: var(--cal-muted); margin: 0 0 16px; line-height: 1.5; }
.cal-btn {
  background: var(--cal-accent); color: #fff; border: none; border-radius: 10px;
  padding: 12px 22px; font-size: 14px; font-weight: 700; cursor: pointer;
  font-family: inherit;
}
.cal-btn:hover { filter: brightness(1.06); }
.cal-btn:active { filter: brightness(.94); }
html.night-mode .cal-btn { color: #14161d; }
/* score screen */
.cal-score-head { font-size: 20px; font-weight: 800; color: var(--cal-strong); margin: 0 0 4px; }
.cal-score-big { font-size: 40px; font-weight: 800; color: var(--cal-accent); margin: 6px 0; }
.cal-score-row { font-size: 14px; color: var(--cal-text); margin: 4px 0; line-height: 1.5; }
.cal-score-note { font-size: 12.5px; color: var(--cal-muted); margin: 12px 0 18px; line-height: 1.5; }
"""


# --- pure HTML builders (no Qt / no live collection needed → unit-testable) --


def _progress(text: str) -> str:
    return f"<div class='cal-progress'>{html.escape(text)}</div>"


def _options_html(labels: list[str]) -> str:
    rows = []
    for i, label in enumerate(labels):
        rows.append(
            f"<label class='cal-opt' onclick=\"blPick(this)\">"
            f"<input type='radio' name='bl-opt' value='{i}'>"
            f"<span class='cal-opt-text'>{html.escape(str(label))}</span>"
            f"</label>"
        )
    return "<div class='cal-opts'>" + "".join(rows) + "</div>"


def build_rate_step_html(
    progress: str, question_html: str, confidence_labels: list[str]
) -> str:
    """Rate step: show the *real* rendered card FRONT, then confidence options.

    ``question_html`` is raw rendered card HTML (already sanitized) and is NOT
    escaped, so its formatting/MathJax renders. The answer is never shown here.
    """
    return (
        "<div class='cal-wrap'>"
        + _progress(progress)
        + f"<div class='cal-card'><div class='card'>{question_html}</div></div>"
        + "<div class='cal-groove-title'>Before you see the answer, how "
        "confident are you?</div>"
        + _options_html(confidence_labels)
        + "<button class='cal-btn' onclick='blSubmit()'>See the answer</button>"
        + "</div>"
    )


def build_reveal_step_html(progress: str, answer_html: str) -> str:
    """Reveal step: show the rendered card ANSWER (back) after the rating."""
    return (
        "<div class='cal-wrap'>"
        + _progress(progress)
        + "<div class='cal-answer-label'>Answer</div>"
        + f"<div class='cal-card'><div class='card'>{answer_html}</div></div>"
        + "<button class='cal-btn' onclick=\"pycmd('bl:continue')\">Continue</button>"
        + "</div>"
    )


def build_answer_step_html(
    progress: str, question: str, choices: list[str]
) -> str:
    """Analog step: render the AI question + its MC options (MathJax-enabled).

    The analog question/choices are plain strings that may contain ``\\(...\\)``
    math or ``<``/``>`` from a model; we HTML-escape them (so stray markup can't
    break layout) while MathJax still typesets the math from the text.
    """
    return (
        "<div class='cal-wrap'>"
        + _progress(progress)
        + f"<div class='cal-prompt'>{html.escape(question)}</div>"
        + "<div class='cal-groove-title'>Choose your answer</div>"
        + _options_html(choices)
        + "<button class='cal-btn' onclick='blSubmit()'>Submit answer</button>"
        + "</div>"
    )


def build_answer_reveal_html(
    progress: str,
    question: str,
    choices: list[str],
    correct_index: int,
    chosen_index: int,
) -> str:
    """Reveal the analog solution: mark the correct choice and the user's pick."""
    rows = []
    for i, choice in enumerate(choices):
        cls = "cal-opt"
        tag = ""
        if i == correct_index:
            cls += " correct"
            tag = "<span class='cal-tag correct'>Correct</span>"
        elif i == chosen_index:
            cls += " wrong"
            tag = "<span class='cal-tag wrong'>Your pick</span>"
        rows.append(
            f"<div class='{cls}'>"
            f"<span class='cal-opt-text'>{html.escape(str(choice))}</span>{tag}"
            f"</div>"
        )
    verdict = (
        "You got this one right."
        if chosen_index == correct_index
        else "Not quite — the correct answer is highlighted above."
    )
    return (
        "<div class='cal-wrap'>"
        + _progress(progress)
        + f"<div class='cal-prompt'>{html.escape(question)}</div>"
        + "<div class='cal-opts'>"
        + "".join(rows)
        + "</div>"
        + f"<div class='cal-note'>{html.escape(verdict)}</div>"
        + "<button class='cal-btn' onclick=\"pycmd('bl:continue')\">Continue</button>"
        + "</div>"
    )


def build_score_html(
    accuracy: float,
    explanation: str,
    mad: float,
    gamma_text: str,
    authority_multiplier: float,
    ai_note: str,
) -> str:
    """Final accuracy-score screen (plain-language + AI-vs-fallback note)."""
    return (
        "<div class='cal-wrap'>"
        + "<div class='cal-progress'>Calibration complete</div>"
        + "<div class='cal-score-head'>Your calibration accuracy</div>"
        + f"<div class='cal-score-big'>{accuracy:.0%}</div>"
        + f"<div class='cal-score-row'>{html.escape(explanation)}</div>"
        + f"<div class='cal-score-row'>Mean deviation: {mad:.2f} · "
        f"resolution (gamma): {html.escape(gamma_text)}</div>"
        + "<div class='cal-score-row'>Confidence authority applied to "
        f"scheduling: <b>{authority_multiplier:.0%}</b></div>"
        + f"<div class='cal-score-note'>{html.escape(ai_note)}; every analog "
        "traces to its source card.</div>"
        + "<button class='cal-btn' onclick=\"pycmd('bl:done')\">Done</button>"
        + "</div>"
    )


def shell_html() -> str:
    """The one-time page shell: a content host + JS helpers (defines pycmd flow).

    Loaded once with MathJax; subsequent steps just swap ``#bl-content`` and
    re-typeset, so MathJax isn't reloaded per step.
    """
    return (
        f"<style>{CALIBRATION_CSS}</style>"
        "<div id='bl-content'></div>"
        "<script>"
        "function blTypeset(){try{if(window.MathJax&&MathJax.startup&&"
        "MathJax.typesetPromise){MathJax.startup.promise.then(function(){"
        "try{MathJax.typesetClear([document.getElementById('bl-content')]);}"
        "catch(e){}return MathJax.typesetPromise("
        "[document.getElementById('bl-content')]);}).catch(function(){});}}"
        "catch(e){}}"
        "function blRender(h){var el=document.getElementById('bl-content');"
        "if(el){el.innerHTML=h;blTypeset();window.scrollTo(0,0);}}"
        "function blPick(lbl){var opts=document.querySelectorAll('.cal-opt');"
        "opts.forEach(function(o){o.classList.remove('checked');});"
        "lbl.classList.add('checked');var r=lbl.querySelector('input');"
        "if(r){r.checked=true;}}"
        "function blSubmit(){var r=document.querySelector("
        "'input[name=bl-opt]:checked');if(!r){pycmd('bl:none');return;}"
        "pycmd('bl:choose:'+r.value);}"
        "</script>"
    )


class CalibrationDialog(QDialog):
    def __init__(self, mw: AnkiQt, parent=None) -> None:
        super().__init__(parent or mw)
        self.mw = mw
        self.setWindowTitle("BrainLift — Confidence calibration")
        self.setMinimumSize(720, 620)

        from anki.brainlift import ai as blai
        from anki.brainlift import calibration as calib

        self._calib = calib
        self._blai = blai

        col = mw.col
        self.cards = calib.select_calibration_cards(col) if col else []
        self.analogs = calib.build_calibration_questions(col) if col else []
        n = min(len(self.cards), len(self.analogs))
        self.cards = self.cards[:n]
        self.analogs = self.analogs[:n]

        self.confidence_labels: list[str] = []
        self.chosen_indices: list[int] = []
        self.index = 0
        self.phase = "rate"  # rate -> reveal -> ... -> answer -> answer_reveal

        self._build()
        if not self.cards:
            from aqt.utils import showInfo

            showInfo(
                "No Exam P cards found to calibrate on. Seed the default deck first.",
                parent=self,
                title="BrainLift",
            )
            self.reject()
            return
        self._render()

    def _build(self) -> None:
        from aqt.webview import AnkiWebView, AnkiWebViewKind

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = AnkiWebView(parent=self, kind=AnkiWebViewKind.DEFAULT)
        self.web.set_bridge_command(self._on_cmd, self)
        layout.addWidget(self.web)
        self.setLayout(layout)
        self.web.stdHtml(shell_html(), css=_CSS, js=_JS, context=self)

    # --- rendering ----------------------------------------------------------

    def _card_html(self, index: int) -> tuple[str, str]:
        cid = self.cards[index][0]
        if self.mw.col is None:
            return "", ""
        return self._calib.render_card_display(self.mw.col, cid)

    def _render(self) -> None:
        total = len(self.cards)
        if self.phase == "rate":
            q_html, _ = self._card_html(self.index)
            if not q_html:
                # fall back to the note's front-field text if rendering failed
                q_html = html.escape(self.cards[self.index][1])
            body = build_rate_step_html(
                f"Step 1 of 2 · Rate your confidence — card {self.index + 1} of {total}",
                q_html,
                self._calib.CONFIDENCE_ORDER,
            )
        elif self.phase == "reveal":
            _, a_html = self._card_html(self.index)
            if not a_html:
                a_html = html.escape(self.cards[self.index][2])
            body = build_reveal_step_html(
                f"Step 1 of 2 · Answer revealed — card {self.index + 1} of {total}",
                a_html,
            )
        elif self.phase == "answer":
            analog = self.analogs[self.index]
            body = build_answer_step_html(
                f"Step 2 of 2 · Answer the analog — question {self.index + 1} of {total}",
                analog.question,
                [str(c) for c in analog.choices],
            )
        else:  # answer_reveal
            analog = self.analogs[self.index]
            body = build_answer_reveal_html(
                f"Step 2 of 2 · Solution — question {self.index + 1} of {total}",
                analog.question,
                [str(c) for c in analog.choices],
                analog.correct_index,
                self.chosen_indices[self.index],
            )
        self.web.eval(f"blRender({json.dumps(body)});")

    # --- bridge -------------------------------------------------------------

    def _on_cmd(self, cmd: str):
        if cmd == "bl:none":
            tooltip("Please choose an option first.", parent=self)
            return None
        if cmd.startswith("bl:choose:"):
            try:
                choice = int(cmd.split(":")[-1])
            except ValueError:
                return None
            self._on_choose(choice)
            return None
        if cmd == "bl:continue":
            self._on_continue()
            return None
        if cmd == "bl:done":
            self.accept()
            return None
        return None

    def _on_choose(self, choice: int) -> None:
        if self.phase == "rate":
            self.confidence_labels.append(self._calib.CONFIDENCE_ORDER[choice])
            self.phase = "reveal"
            self._render()
        elif self.phase == "answer":
            self.chosen_indices.append(choice)
            self.phase = "answer_reveal"
            self._render()

    def _on_continue(self) -> None:
        total = len(self.cards)
        if self.phase == "reveal":
            if self.index < total - 1:
                self.index += 1
                self.phase = "rate"
            else:
                self.index = 0
                self.phase = "answer"
            self._render()
        elif self.phase == "answer_reveal":
            if self.index < total - 1:
                self.index += 1
                self.phase = "answer"
                self._render()
            else:
                self._finish()

    def _finish(self) -> None:
        col = self.mw.col
        if col is None:
            self.reject()
            return
        result = self._calib.run_calibration(
            col, self.cards, self.analogs, self.confidence_labels, self.chosen_indices
        )
        ai_note = (
            "analog questions were AI-generated"
            if result.ai_used
            else "AI was off — analogs were generated deterministically"
        )
        gamma = "n/a" if result.gamma is None else f"{result.gamma:+.2f}"
        body = build_score_html(
            result.accuracy,
            result.explanation,
            result.mad,
            gamma,
            result.authority_multiplier,
            ai_note,
        )
        self.web.eval(f"blRender({json.dumps(body)});")
