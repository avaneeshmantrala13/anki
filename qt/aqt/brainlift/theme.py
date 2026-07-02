# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""BrainLift skin for Anki's built-in screens.

Injects a light, cohesive stylesheet into Anki's *chrome* web views (deck
browser, overview/congrats, stats, and the top/bottom bars) so they match the
BrainLift landing instead of the default black-and-white look. It is applied via
the public ``gui_hooks.webview_will_set_content`` hook and scoped by an
allowlist, so the reviewer's card content and native dialogs are never touched.
Purely cosmetic and deterministic — no AI.

The palette below is the single BrainLift design system, shared (by value) with
the landing page, the dashboard, and the Android app: one indigo accent, a
neutral background scale, a consistent radius/shadow scale, and full dark-mode
variants keyed off Anki's own ``night-mode``/``nightMode`` classes.
"""

from __future__ import annotations

from typing import Any

from aqt import gui_hooks

# Screens rendered as full "pages".
_PAGE_NAMES = {
    "DeckBrowser",
    "Overview",
    "CongratsPage",
    "NewDeckStats",
    "DeckStats",
}
# Thin top/bottom bars.
_TOP_BAR_NAMES = {
    "Toolbar",
    "TopToolbar",
}
_BOTTOM_BAR_NAMES = {
    "DeckBrowserBottomBar",
    "OverviewBottomBar",
}

# Design tokens. Defined on :root for the light theme and overridden under
# Anki's night-mode classes so the skin follows the user's theme setting.
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
    --bl-shadow-card: 0 1px 2px rgba(18,22,45,.05), 0 1px 6px rgba(18,22,45,.04);
    --bl-focus-ring: 0 0 0 3px rgba(79,107,237,.28);
  }
  html.night-mode, body.nightMode {
    --bl-bg: #13151c;
    --bl-surface: #1c1f29;
    --bl-surface-2: #262b38;
    --bl-hover: #232734;
    --bl-border: #2c3140;
    --bl-row-line: #262b37;
    --bl-text: #e8eaf3;
    --bl-text-2: #a4aabc;
    --bl-text-3: #737990;
    --bl-primary: #7387f2;
    --bl-primary-hover: #8496f4;
    --bl-primary-active: #6377e8;
    --bl-primary-tint: rgba(115,135,242,.14);
    --bl-primary-tint-border: rgba(115,135,242,.32);
    --bl-shadow-card: 0 1px 2px rgba(0,0,0,.4);
    --bl-focus-ring: 0 0 0 3px rgba(115,135,242,.35);
  }
"""

_PAGE_CSS = (
    _TOKENS_CSS
    + """
  html, body { background:var(--bl-bg) !important; }
  body { color:var(--bl-text) !important; padding:24px 28px 36px !important;
         font-family:-apple-system,"Segoe UI Variable","Segoe UI",Roboto,
                     "Helvetica Neue",Arial,sans-serif !important;
         -webkit-font-smoothing:antialiased; }
  a { color:var(--bl-primary) !important; text-decoration:none !important;
      transition:color .12s ease; }
  a:hover { color:var(--bl-primary-hover) !important; }
  h1, h2, h3, .title { color:var(--bl-text) !important; letter-spacing:-.01em; }

  table { border-collapse:separate !important; border-spacing:0 !important;
          width:100% !important; background:var(--bl-surface) !important;
          border:1px solid var(--bl-border) !important;
          border-radius:12px !important; overflow:hidden !important;
          box-shadow:var(--bl-shadow-card) !important; margin-top:8px !important; }
  td, th { border:none !important;
           border-bottom:1px solid var(--bl-row-line) !important;
           padding:11px 16px !important; color:var(--bl-text) !important;
           background:transparent !important;
           font-variant-numeric:tabular-nums; }
  tr:last-child td { border-bottom:none !important; }
  th { color:var(--bl-text-3) !important; font-weight:600 !important;
       font-size:11px !important; text-transform:uppercase !important;
       letter-spacing:.06em !important; }
  tr td { transition:background .1s ease; }
  tr:hover td { background:var(--bl-hover) !important; }

  /* Deck browser rows: quiet deck names, highlighted current deck. */
  a.deck { color:var(--bl-text) !important; font-weight:500 !important; }
  a.deck:hover { color:var(--bl-primary) !important; }
  tr.deck.current td { background:var(--bl-primary-tint) !important; }
  a.collapse { color:var(--bl-text-3) !important; }
  .zero-count { color:var(--bl-text-3) !important; opacity:.55 !important; }
  img.gears { opacity:.45; transition:opacity .12s ease; }
  tr:hover img.gears { opacity:.9; }

  button, .btn, input[type=button] {
       background:var(--bl-primary) !important; color:#fff !important;
       border:none !important; border-radius:9px !important;
       padding:9px 18px !important; font-weight:600 !important;
       font-size:13px !important; cursor:pointer !important;
       box-shadow:none !important; text-shadow:none !important;
       transition:background .12s ease; }
  button:hover, .btn:hover { background:var(--bl-primary-hover) !important; }
  button:active, .btn:active { background:var(--bl-primary-active) !important; }
  button:focus-visible, .btn:focus-visible, a:focus-visible {
       outline:none !important; box-shadow:var(--bl-focus-ring) !important; }

  #studiedToday, .descfont, .dconf, .subtitle { color:var(--bl-text-2) !important; }
  #studiedToday { font-size:13px !important; margin-top:14px !important; }
"""
)

# Shared styling for the thin top/bottom chrome bars: a flat surface with quiet,
# pill-shaped nav items instead of heavy filled chips.
_BAR_CSS = (
    _TOKENS_CSS
    + """
  html, body { background:var(--bl-surface) !important; }
  body { color:var(--bl-text-2) !important;
         font-family:-apple-system,"Segoe UI Variable","Segoe UI",Roboto,
                     "Helvetica Neue",Arial,sans-serif !important;
         -webkit-font-smoothing:antialiased; }
  a, .hitem, .tabbtn, .toolbar-item {
       color:var(--bl-text-2) !important; background:transparent !important;
       text-decoration:none !important; font-weight:600 !important;
       font-size:12.5px !important; border-radius:8px !important;
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
       border-radius:8px !important; padding:7px 14px !important;
       font-weight:600 !important; font-size:12.5px !important;
       cursor:pointer !important; box-shadow:none !important;
       transition:background .12s ease, border-color .12s ease, color .12s ease; }
  button:hover, .btn:hover { background:var(--bl-primary-tint) !important;
       border-color:var(--bl-primary-tint-border) !important;
       color:var(--bl-primary) !important; }
  button:active, .btn:active { background:var(--bl-surface-2) !important; }
  a:focus-visible, button:focus-visible, .btn:focus-visible {
       outline:none !important; box-shadow:var(--bl-focus-ring) !important; }
"""
)

# Hairline separators so the flat bars read as distinct from the page below.
_TOP_BAR_EDGE_CSS = "body { box-shadow:inset 0 -1px 0 var(--bl-border) !important; }"
_BOTTOM_BAR_EDGE_CSS = "body { box-shadow:inset 0 1px 0 var(--bl-border) !important; }"


_installed = False


def _on_will_set_content(web_content: Any, context: Any) -> None:
    name = type(context).__name__ if context is not None else ""
    if name in _PAGE_NAMES:
        web_content.head += f"<style>{_PAGE_CSS}</style>"
    elif name in _TOP_BAR_NAMES:
        web_content.head += f"<style>{_BAR_CSS}{_TOP_BAR_EDGE_CSS}</style>"
    elif name in _BOTTOM_BAR_NAMES:
        web_content.head += f"<style>{_BAR_CSS}{_BOTTOM_BAR_EDGE_CSS}</style>"


def install() -> None:
    """Register the skin (idempotent)."""
    global _installed
    if _installed:
        return
    _installed = True
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
