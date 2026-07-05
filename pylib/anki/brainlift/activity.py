# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""BrainLift AI Activity log — makes the two AI features observable.

A small, capped, synced log of what the AI features actually did, so the user
(and a demo viewer) can *see* the AI working in the backend rather than taking
it on faith:

* Feature 1 (calibration) records each completed run — whether real OpenAI or
  the deterministic fallback produced the analogs, the measured calibration
  accuracy, the resulting confidence-authority multiplier, and the named source
  card behind each generated analog.
* Feature 2 (fatigue) records every intervention the detector fires — the model
  probability, the signals that drove it, the decision, and (via the reviewer
  hook) whether the live queue was reordered.

Stored in collection config (so it syncs desktop <-> mobile) as a capped list,
newest first. Nothing here generates content; it only records events other
modules produce, so it never affects scoring and never raises.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anki.collection import Collection

CONFIG_KEY = "brainlift_ai_activity"
MAX_EVENTS = 30

_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(text: str, limit: int = 90) -> str:
    """Strip HTML tags / collapse whitespace and truncate for a compact log line."""
    plain = _TAG_RE.sub(" ", str(text))
    plain = " ".join(plain.split())
    if len(plain) > limit:
        plain = plain[: limit - 1].rstrip() + "\u2026"
    return plain


def log_event(
    col: Collection,
    feature: str,
    kind: str,
    summary: str,
    detail: list[str] | None = None,
    used_ai: bool = False,
    at: int | None = None,
) -> None:
    """Append one activity event (newest-first), capped at ``MAX_EVENTS``."""
    try:
        events = load_events(col)
        events.insert(
            0,
            {
                "at": int(at if at is not None else time.time()),
                "feature": str(feature),
                "kind": str(kind),
                "summary": str(summary),
                "detail": [str(d) for d in (detail or [])],
                "used_ai": bool(used_ai),
            },
        )
        col.set_config(CONFIG_KEY, events[:MAX_EVENTS])
    except Exception:
        # The activity log is purely observational; never let it disrupt a run.
        pass


def load_events(col: Collection) -> list[dict[str, Any]]:
    data = col.get_config(CONFIG_KEY, None)
    return list(data) if isinstance(data, list) else []


def clear_events(col: Collection) -> None:
    try:
        col.remove_config(CONFIG_KEY)
    except Exception:
        pass
