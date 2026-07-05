# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""BrainLift skin for Anki's built-in desktop screens.

Injects a cohesive, glassy stylesheet into Anki's *chrome* web views so they
match the BrainLift dashboard (``pylib/anki/brainlift/dashboard.py`` +
``qt/aqt/brainlift/home.py``) instead of the default black-and-white look:
rounded cards, a soft cyan glow behind boxes, subtle indigo gradients on
prominent surfaces, and the distinctive display / body / mono font trio.

How it lands
------------
Full "page" web views (deck browser, deck overview, legacy stats) and the thin
top/bottom bars are all rendered through :meth:`AnkiWebView.stdHtml`, which fires
the public ``gui_hooks.webview_will_set_content`` hook. We subscribe to that
hook and append a ``<style>`` block scoped by the *context* object's class name
(e.g. ``DeckBrowser``, ``Overview``, ``TopToolbar``, ``ReviewerBottomBar``), so
the reviewer's card content and native dialogs are never touched.

The "Congratulations / finished" screen is different: it is a SvelteKit page
loaded by URL (``webview.load_sveltekit_page("congrats")``), so it never goes
through ``stdHtml`` / ``webview_will_set_content``. For that one screen we use
``gui_hooks.webview_did_inject_style_into_page`` (which fires after Anki injects
its own styling into such external pages) and append our stylesheet, scoped to
the congrats URL so no other SvelteKit page (graphs, deck options) is affected.

The design tokens below are copied *by value* from the dashboard's ``:root`` so
the built-in screens match it 1:1, with full dark-mode variants keyed off
Anki's own ``html.night-mode`` / ``body.nightMode`` classes. Purely cosmetic and
deterministic — no AI, no behaviour changes, additive CSS only.
"""

from __future__ import annotations

import json
from typing import Any

from aqt import gui_hooks

# Full "page" web views rendered via stdHtml (context class name -> _PAGE_CSS).
#   * DeckBrowser  -> qt/aqt/deckbrowser.py
#   * Overview     -> qt/aqt/overview.py (the normal, not-finished overview)
#   * DeckStats    -> qt/aqt/stats.py (the *legacy* stats report; the modern
#                     graphs page is SvelteKit and cannot be reached here)
_PAGE_NAMES = {
    "DeckBrowser",
    "Overview",
    "DeckStats",
}
# Thin top bar (qt/aqt/toolbar.py draws with a ``TopToolbar`` context).
_TOP_BAR_NAMES = {
    "TopToolbar",
    "Toolbar",
}
# Thin bottom bars (deck browser + overview draw with these contexts).
_BOTTOM_BAR_NAMES = {
    "DeckBrowserBottomBar",
    "OverviewBottomBar",
    "BottomToolbar",
}
# Reviewer answer-buttons bar (qt/aqt/reviewer.py, ReviewerBottomBar context).
_REVIEWER_BAR_NAMES = {
    "ReviewerBottomBar",
}

# Design tokens — copied by value from dashboard.py's DASHBOARD_CSS :root (plus
# the extra tint/hero/focus tokens the landing uses), so every built-in screen
# shares the exact same palette, fonts, radii, glow and gradients as the
# BrainLift dashboard. Overridden under Anki's night-mode classes.
_TOKENS_CSS = """
  :root {
    --bl-bg: #f6f7fb;
    --bl-surface: #ffffff;
    --bl-surface-2: #eef1f8;
    --bl-hover: #f3f5fb;
    --bl-border: #e4e7f0;
    --bl-row-line: #eef0f6;
    --bl-text: #1b1e28;
    --bl-text-2: #575d70;
    --bl-text-3: #8a90a3;
    --bl-primary: #4f6bed;
    --bl-primary-hover: #4159d6;
    --bl-primary-active: #3a50c4;
    --bl-primary-tint: #edf1fe;
    --bl-primary-tint-border: #dbe2fc;
    --bl-success: #178c53;
    --bl-warn: #b3590a;
    --bl-shadow-card: 0 1px 2px rgba(18,22,45,.05), 0 1px 6px rgba(18,22,45,.04);
    --bl-focus-ring: 0 0 0 3px rgba(79,107,237,.28);
    /* Distinctive type pairing (offline-safe: real system faces first). */
    --bl-font-display: "Avenir Next", "Futura", "Gill Sans",
                       "Segoe UI Variable Display", "Trebuchet MS",
                       -apple-system, sans-serif;
    --bl-font-body: "Avenir Next", "Inter", "Segoe UI", Roboto,
                    "Helvetica Neue", Arial, sans-serif;
    --bl-font-mono: "SF Mono", ui-monospace, "JetBrains Mono", Menlo,
                    Consolas, monospace;
    /* Signature cyan glow that sits behind every box. */
    --bl-cyan: #22d3ee;
    --bl-glow: 0 6px 22px rgba(34,211,238,.13), 0 0 0 1px rgba(34,211,238,.10);
    --bl-glow-strong: 0 10px 30px rgba(34,211,238,.26),
                      0 0 0 1px rgba(34,211,238,.30);
    /* Indigo gradient for prominent/primary surfaces. */
    --bl-hero-a: #5068ea;
    --bl-hero-b: #3d51cd;
    --bl-hero-shadow: 0 12px 32px rgba(61,81,205,.22);
  }
  html.night-mode, body.nightMode {
    --bl-bg: #0f1420;
    --bl-surface: #161c2b;
    --bl-surface-2: #202940;
    --bl-hover: #202940;
    --bl-border: #263149;
    --bl-row-line: #202940;
    --bl-text: #e8eaf3;
    --bl-text-2: #a4aabc;
    --bl-text-3: #737990;
    --bl-primary: #7387f2;
    --bl-primary-hover: #8496f4;
    --bl-primary-active: #6377e8;
    --bl-primary-tint: rgba(115,135,242,.14);
    --bl-primary-tint-border: rgba(115,135,242,.32);
    --bl-success: #46c088;
    --bl-warn: #e09a4e;
    --bl-shadow-card: 0 1px 2px rgba(0,0,0,.4);
    --bl-focus-ring: 0 0 0 3px rgba(115,135,242,.35);
    --bl-glow: 0 6px 24px rgba(34,211,238,.16), 0 0 0 1px rgba(34,211,238,.16);
    --bl-glow-strong: 0 12px 34px rgba(34,211,238,.34),
                      0 0 0 1px rgba(34,211,238,.44);
    --bl-hero-a: #4358cf;
    --bl-hero-b: #333fa8;
    --bl-hero-shadow: 0 12px 32px rgba(0,0,0,.45);
  }
"""

# Deck browser + overview + legacy stats. Targets Anki's real class names:
#   deckbrowser.py  -> table / tr.deck(.current) / td.decktd / a.deck /
#                      a.collapse / span.new-count|learn-count|review-count /
#                      .zero-count / img.gears / .callout / #studiedToday
#   overview.py     -> h3 (deck name) / .descfont.description / nested count
#                      table / button#study ("Study Now") / .bury-count
_PAGE_CSS = (
    _TOKENS_CSS
    + """
  html, body { background:var(--bl-bg) !important; }
  body { color:var(--bl-text) !important; padding:26px 30px 40px !important;
         margin:0 !important;
         font-family:var(--bl-font-body) !important;
         -webkit-font-smoothing:antialiased; }
  a { color:var(--bl-primary) !important; text-decoration:none !important;
      transition:color .12s ease; }
  a:hover { color:var(--bl-primary-hover) !important; }
  h1, h2, h3, .title { font-family:var(--bl-font-display) !important;
       color:var(--bl-text) !important; letter-spacing:-.01em; }
  h3 { font-size:22px !important; font-weight:700 !important;
       margin:6px 0 10px !important; }

  /* Cards / tables: rounded, glassy, cyan glow. */
  table { border-collapse:separate !important; border-spacing:0 !important;
          background:var(--bl-surface) !important;
          border:1px solid var(--bl-border) !important;
          border-radius:16px !important; overflow:hidden !important;
          box-shadow:var(--bl-glow) !important; margin:8px auto !important; }
  td, th { border:none !important;
           border-bottom:1px solid var(--bl-row-line) !important;
           padding:11px 16px !important; color:var(--bl-text) !important;
           background:transparent !important;
           font-variant-numeric:tabular-nums; }
  tr:last-child td { border-bottom:none !important; }
  /* Small uppercase column headers in mono, with a subtle gradient band. */
  th { color:var(--bl-text-3) !important;
       font-family:var(--bl-font-mono) !important; font-weight:600 !important;
       font-size:11px !important; text-transform:uppercase !important;
       letter-spacing:.07em !important;
       background:linear-gradient(160deg,var(--bl-surface-2),
                  var(--bl-surface)) !important; }
  tr td { transition:background .1s ease; }
  tr:hover td { background:var(--bl-hover) !important; }

  /* Nested tables (overview counts) sit flat inside their parent card. */
  table table { border:none !important; box-shadow:none !important;
        background:transparent !important; border-radius:0 !important;
        margin:0 !important; }
  table table td, table table th { border-bottom:none !important;
        padding:6px 12px !important; background:transparent !important; }

  /* Deck browser rows: deck names in display face, current deck highlighted. */
  a.deck { color:var(--bl-text) !important; font-family:var(--bl-font-display)
           !important; font-weight:600 !important; letter-spacing:-.01em; }
  a.deck:hover { color:var(--bl-primary) !important;
                 text-decoration:none !important; }
  tr.deck.current td { background:var(--bl-primary-tint) !important; }
  a.collapse { color:var(--bl-text-3) !important; }
  img.gears { opacity:.45; transition:opacity .12s ease; }
  tr:hover img.gears { opacity:.9; }

  /* Due/new/learn/review counts as mono pills, matching dashboard chips. */
  .new-count, .learn-count, .review-count, .zero-count {
       display:inline-block; font-family:var(--bl-font-mono) !important;
       font-variant-numeric:tabular-nums; font-weight:600 !important;
       font-size:12px !important; line-height:1.4;
       min-width:18px; text-align:center; padding:2px 9px !important;
       border-radius:12px !important; background:var(--bl-surface-2) !important;
       border:1px solid var(--bl-border) !important; }
  .new-count { color:var(--bl-primary) !important; }
  .learn-count { color:var(--bl-warn) !important; }
  .review-count { color:var(--bl-success) !important; }
  .zero-count { color:var(--bl-text-3) !important;
       background:transparent !important; border-color:transparent !important;
       opacity:.6 !important; }
  .bury-count { color:var(--bl-text-3) !important;
       font-family:var(--bl-font-mono) !important; font-size:11px !important; }

  /* Generic buttons (e.g. v1-upgrade callout). */
  button, .btn, input[type=button] {
       background:var(--bl-primary) !important; color:#fff !important;
       border:none !important; border-radius:12px !important;
       padding:9px 18px !important; font-family:var(--bl-font-body) !important;
       font-weight:600 !important; font-size:13px !important;
       cursor:pointer !important; box-shadow:none !important;
       text-shadow:none !important; transition:background .12s ease,
       box-shadow .12s ease, filter .12s ease; }
  button:hover, .btn:hover { background:var(--bl-primary-hover) !important; }
  button:active, .btn:active { background:var(--bl-primary-active) !important; }
  button:focus-visible, .btn:focus-visible, a:focus-visible {
       outline:none !important; box-shadow:var(--bl-focus-ring) !important; }

  /* Overview "Study Now": the prominent primary action — indigo gradient +
     cyan glow (mirrors the dashboard hero / landing CTA). */
  button#study, button.but {
       background:linear-gradient(160deg,var(--bl-hero-a),var(--bl-hero-b))
            !important; color:#fff !important;
       border:none !important; border-radius:12px !important;
       padding:13px 30px !important; font-size:15px !important;
       font-weight:700 !important; letter-spacing:.01em;
       box-shadow:var(--bl-glow) !important; }
  button#study:hover, button.but:hover {
       filter:brightness(1.05) !important;
       box-shadow:var(--bl-glow-strong) !important;
       background:linear-gradient(160deg,var(--bl-hero-a),var(--bl-hero-b))
            !important; }
  button#study:active, button.but:active { filter:brightness(.97) !important; }

  /* Overview description + share link + deck-browser stats line. */
  .descfont, .description, .smallLink, #studiedToday {
       color:var(--bl-text-2) !important; }
  .description { background:var(--bl-surface) !important;
       border:1px solid var(--bl-border) !important;
       border-radius:16px !important; padding:14px 18px !important;
       box-shadow:var(--bl-glow) !important; margin:10px auto !important;
       max-width:520px; }
  #studiedToday { font-size:13px !important; margin:18px 0 !important;
       font-family:var(--bl-font-mono) !important; }

  /* v1 scheduler upgrade prompt as a rounded, glowing callout card. */
  .callout { background:var(--bl-surface) !important;
       border:1px solid var(--bl-border) !important;
       border-radius:16px !important; box-shadow:var(--bl-glow) !important;
       padding:16px 20px !important; margin:16px auto !important;
       max-width:560px; }
"""
)

# Shared styling for the thin top/bottom chrome bars: a flat surface with quiet,
# pill-shaped nav items. Targets toolbar.py's .hitem / #sync-spinner and the
# bottom bars' plain <button>s (deckbrowser.py / overview.py).
_BAR_CSS = (
    _TOKENS_CSS
    + """
  html, body { background:var(--bl-surface) !important; }
  body { color:var(--bl-text-2) !important; margin:0 !important;
         font-family:var(--bl-font-body) !important;
         -webkit-font-smoothing:antialiased; }
  .header, .toolbar { font-family:var(--bl-font-body) !important; }
  a, .hitem, .tabbtn, .toolbar-item {
       color:var(--bl-text-2) !important; background:transparent !important;
       text-decoration:none !important; font-weight:600 !important;
       font-size:12.5px !important; border-radius:10px !important;
       padding:6px 12px !important; margin:0 2px !important;
       display:inline-block !important; box-shadow:none !important;
       transition:background .12s ease, color .12s ease; }
  a:hover, .hitem:hover, .tabbtn:hover, .toolbar-item:hover {
       background:var(--bl-primary-tint) !important;
       color:var(--bl-primary) !important; }
  a:active, .hitem:active { color:var(--bl-primary-active) !important; }
  button, .btn { background:var(--bl-surface) !important;
       color:var(--bl-text) !important;
       border:1px solid var(--bl-border) !important;
       border-radius:12px !important; padding:7px 14px !important;
       font-family:var(--bl-font-body) !important;
       font-weight:600 !important; font-size:12.5px !important;
       cursor:pointer !important; box-shadow:none !important;
       transition:background .12s ease, border-color .12s ease,
       color .12s ease, box-shadow .12s ease; }
  button:hover, .btn:hover { background:var(--bl-primary-tint) !important;
       border-color:var(--bl-primary-tint-border) !important;
       color:var(--bl-primary) !important;
       box-shadow:var(--bl-glow) !important; }
  button:active, .btn:active { background:var(--bl-surface-2) !important; }
  a:focus-visible, button:focus-visible, .btn:focus-visible {
       outline:none !important; box-shadow:var(--bl-focus-ring) !important; }
"""
)

# Hairline separators so the flat bars read as distinct from the page below.
_TOP_BAR_EDGE_CSS = "body { box-shadow:inset 0 -1px 0 var(--bl-border) !important; }"
_BOTTOM_BAR_EDGE_CSS = "body { box-shadow:inset 0 1px 0 var(--bl-border) !important; }"

# Reviewer answer-buttons bar. Deliberately conservative: we only restyle the
# button chrome (palette, font, rounded corners, hover glow) and the little
# count/time labels. We DO NOT touch layout, position or overflow — the timing
# labels (.nobold / .stattxt) are absolutely positioned *above* each button, so
# clipping them (overflow:hidden) or changing positioning would break them.
_REVIEWER_BAR_CSS = (
    _TOKENS_CSS
    + """
  html, body { background:var(--bl-surface) !important; }
  body { color:var(--bl-text-2) !important;
         font-family:var(--bl-font-body) !important;
         -webkit-font-smoothing:antialiased; }
  #outer { border-top:1px solid var(--bl-border) !important; }
  button { background:var(--bl-surface) !important; color:var(--bl-text)
       !important; border:1px solid var(--bl-border) !important;
       border-radius:12px !important; font-family:var(--bl-font-body)
       !important; font-weight:600 !important; box-shadow:none !important;
       text-shadow:none !important; transition:background .12s ease,
       border-color .12s ease, color .12s ease, box-shadow .12s ease; }
  button:hover { background:var(--bl-primary-tint) !important;
       border-color:var(--bl-primary-tint-border) !important;
       box-shadow:var(--bl-glow) !important; }
  button:active { background:var(--bl-surface-2) !important; }
  button:focus-visible { outline:none !important;
       box-shadow:var(--bl-focus-ring) !important; }
  /* Default ease / show-answer button gets a subtle primary tint. */
  #defease, #ansbut { border-color:var(--bl-primary-tint-border) !important;
       color:var(--bl-primary) !important; }
  #defease:hover, #ansbut:hover { box-shadow:var(--bl-glow-strong) !important; }
  .nobold, .stattxt, #time { color:var(--bl-text-3) !important;
       font-family:var(--bl-font-mono) !important;
       font-variant-numeric:tabular-nums; }
  .new-count { color:var(--bl-primary) !important;
       font-family:var(--bl-font-mono) !important; }
  .learn-count { color:var(--bl-warn) !important;
       font-family:var(--bl-font-mono) !important; }
  .review-count { color:var(--bl-success) !important;
       font-family:var(--bl-font-mono) !important; }
"""
)

# "Congratulations / finished" SvelteKit page (ts/routes/congrats). Targets its
# real markup: .congrats (wrapper) / h1 / p / .description. Injected via the
# did-inject hook (see _on_did_inject_style) since it bypasses stdHtml.
_CONGRATS_CSS = (
    _TOKENS_CSS
    + """
  body { background:var(--bl-bg) !important;
         font-family:var(--bl-font-body) !important;
         -webkit-font-smoothing:antialiased; }
  .congrats { background:var(--bl-surface) !important;
       border:1px solid var(--bl-border) !important;
       border-radius:16px !important; box-shadow:var(--bl-glow) !important;
       padding:26px 30px !important; margin-top:2.5em !important;
       color:var(--bl-text) !important; }
  .congrats h1 { font-family:var(--bl-font-display) !important;
       color:var(--bl-text) !important; font-size:24px !important;
       font-weight:700 !important; letter-spacing:-.02em;
       margin:0 0 12px !important; }
  .congrats p { color:var(--bl-text-2) !important; line-height:1.55; }
  .congrats a { color:var(--bl-primary) !important;
       text-decoration:none !important; }
  .congrats .description { background:var(--bl-surface-2) !important;
       border:1px solid var(--bl-border) !important;
       border-radius:12px !important; padding:14px 16px !important;
       margin-top:14px !important; color:var(--bl-text-2) !important; }
"""
)


_installed = False


def _on_will_set_content(web_content: Any, context: Any) -> None:
    name = type(context).__name__ if context is not None else ""
    if name in _PAGE_NAMES:
        web_content.head += f"<style>{_PAGE_CSS}</style>"
    elif name in _TOP_BAR_NAMES:
        web_content.head += f"<style>{_BAR_CSS}{_TOP_BAR_EDGE_CSS}</style>"
    elif name in _BOTTOM_BAR_NAMES:
        web_content.head += f"<style>{_BAR_CSS}{_BOTTOM_BAR_EDGE_CSS}</style>"
    elif name in _REVIEWER_BAR_NAMES:
        web_content.head += f"<style>{_REVIEWER_BAR_CSS}</style>"


def _on_did_inject_style(webview: Any) -> None:
    """Skin the SvelteKit congrats page, which bypasses ``stdHtml``.

    Fired after Anki injects its own styling into externally-loaded pages. We
    scope strictly to the congrats URL so other SvelteKit pages (graphs, deck
    options) are untouched, and guard against double-injection.
    """
    try:
        path = webview.page().url().path()
    except Exception:
        return
    if "congrats" not in path:
        return
    css = json.dumps(_CONGRATS_CSS)
    webview.eval(
        "(function(){"
        "if(document.querySelector('style[data-brainlift]'))return;"
        "var s=document.createElement('style');"
        "s.setAttribute('data-brainlift','1');"
        f"s.innerHTML={css};"
        "document.head.appendChild(s);"
        "})();"
    )


def install() -> None:
    """Register the skin (idempotent)."""
    global _installed
    if _installed:
        return
    _installed = True
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.webview_did_inject_style_into_page.append(_on_did_inject_style)
