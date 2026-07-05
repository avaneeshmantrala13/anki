# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Shared helpers for the BrainLift eval harness.

Makes ``anki.brainlift.ai`` importable without a full Anki build, chooses the
client (deterministic offline, or real OpenAI with --live + a key), and provides
small text utilities. No third-party deps.
"""

from __future__ import annotations

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "pylib"))

from anki.brainlift import ai as blai  # noqa: E402


def get_generator(live: bool):
    """Return (client, label). Offline default uses the deterministic client."""
    key = blai.api_key_from_env()
    if live and key:
        return blai.RealOpenAIClient(api_key=key, model=blai.DEFAULT_MODEL), f"OpenAI:{blai.DEFAULT_MODEL}"
    return blai.DeterministicAnalogClient(), "deterministic(no-key fixtures)"


def generate_for_gold(gold: list[dict], client) -> list:
    """Generate one RAW analog per gold item (no leakage gate); the gold id
    becomes the source card id."""
    analogs = []
    for i, item in enumerate(gold):
        # stable integer source id from position (mirrors card ids)
        analogs.append(client.generate_analog(item["front"], item["back"], 1000 + i))
    return analogs


def generate_served_for_gold(gold: list[dict], client):
    """Run the SERVED pipeline: generate each analog THROUGH the leakage gate
    (regenerate-then-block). Returns ``(served, stats)`` where ``served`` is the
    list of gated results and ``stats`` reports how many raw items leaked, were
    caught-and-regenerated, and were blocked/withheld. This mirrors exactly what
    students would actually see, on both desktop and mobile."""
    gated = []
    for i, item in enumerate(gold):
        gated.append(
            blai.generate_gated_analog(client, item["front"], item["back"], 1000 + i)
        )
    stats = {
        "total": len(gated),
        "leaked_raw": sum(1 for g in gated if g.leaked_initially),
        "caught_regenerated": sum(
            1 for g in gated if g.regen_attempts > 0 and not g.blocked
        ),
        "blocked": sum(1 for g in gated if g.blocked),
        "served": sum(1 for g in gated if g.served),
    }
    return gated, stats


_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
