# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""BrainLift skin for Anki's built-in screens.

Injects a light, cohesive stylesheet into Anki's *chrome* web views (deck
browser, overview/congrats, stats, and the top/bottom bars) so they match the
BrainLift landing instead of the default black-and-white look. It is applied via
the public ``gui_hooks.webview_will_set_content`` hook and scoped by an
allowlist, so the reviewer's card content and native dialogs are never touched.
Purely cosmetic and deterministic — no AI.
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
_BAR_NAMES = {
    "Toolbar",
    "TopToolbar",
    "DeckBrowserBottomBar",
    "OverviewBottomBar",
}

_PAGE_CSS = """
  html, body { background:#f4f5f9 !important; }
  body { color:#1d1d24 !important; padding:20px 24px !important;
         font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; }
  a { color:#4f6bed !important; text-decoration:none !important; }
  a:hover { color:#3f59d6 !important; }
  h1, h2, h3, .title { color:#1d1d24 !important; }
  table { border-collapse:separate !important; border-spacing:0 !important;
          width:100% !important; background:#fff !important;
          border-radius:14px !important; overflow:hidden !important;
          box-shadow:0 1px 5px rgba(0,0,0,.07) !important; margin-top:8px !important; }
  td, th { border:none !important; border-bottom:1px solid #eef0f4 !important;
           padding:12px 14px !important; color:#1d1d24 !important;
           background:transparent !important; }
  th { color:#7a7a86 !important; font-weight:700 !important; font-size:12px !important;
       text-transform:uppercase !important; letter-spacing:.04em !important; }
  tr:hover td { background:#f5f7ff !important; }
  button, .btn, input[type=button] {
       background:#4f6bed !important; color:#fff !important; border:none !important;
       border-radius:10px !important; padding:10px 18px !important;
       font-weight:600 !important; font-size:13px !important; cursor:pointer !important;
       box-shadow:none !important; text-shadow:none !important; }
  button:hover, .btn:hover { background:#3f59d6 !important; }
  #studiedToday, .descfont, .dconf, .subtitle { color:#6b6b76 !important; }
"""

_BAR_CSS = """
  html, body { background:#ffffff !important; }
  body { color:#3b3b7a !important;
         font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; }
  /* Make each top-bar item a clearly visible chip. */
  a, .hitem, .tabbtn, .toolbar-item {
       color:#ffffff !important; background:#4f6bed !important;
       text-decoration:none !important; font-weight:700 !important;
       border-radius:9px !important; padding:7px 14px !important;
       margin:0 4px !important; display:inline-block !important;
       box-shadow:0 1px 3px rgba(79,107,237,.35) !important; }
  a:hover, .hitem:hover, .tabbtn:hover {
       background:#3f59d6 !important; color:#ffffff !important; }
  button, .btn { background:#4f6bed !important; color:#fff !important;
       border:none !important; border-radius:9px !important; padding:8px 16px !important;
       font-weight:700 !important; }
  button:hover, .btn:hover { background:#3f59d6 !important; }
"""


_installed = False


def _on_will_set_content(web_content: Any, context: Any) -> None:
    name = type(context).__name__ if context is not None else ""
    if name in _PAGE_NAMES:
        web_content.head += f"<style>{_PAGE_CSS}</style>"
    elif name in _BAR_NAMES:
        web_content.head += f"<style>{_BAR_CSS}</style>"


def install() -> None:
    """Register the skin (idempotent)."""
    global _installed
    if _installed:
        return
    _installed = True
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
