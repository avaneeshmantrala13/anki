# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Held-out eval that runs BEFORE students see anything.

Pass/fail cutoffs are declared HERE, at the top, and were decided BEFORE looking
at any results. Items that fail the checker are BLOCKED (excluded from what a
student would see); we report how many were blocked.
"""

from __future__ import annotations

import sys

# --- PRE-DECLARED cutoffs (decided before looking at results) ----------------
WRONG_RATE_CUTOFF = 0.10   # generation must produce <= 10% wrong/malformed analogs
USEFUL_RATE_FLOOR = 0.50   # >= 50% must be correct-and-useful (on-concept, checkable)

from _common import generate_for_gold, get_generator  # noqa: E402
from checker import check_analog, counts  # noqa: E402
from gold_set import held_out  # noqa: E402


def run(live: bool = False) -> bool:
    client, label = get_generator(live)
    gold = held_out(20)
    analogs = generate_for_gold(gold, client)

    # Named-source traceability: every generated item must carry its source.
    missing_source = [a for a in analogs if not a.source_text or a.source_card_id is None]

    results = [check_analog(a, g) for a, g in zip(analogs, gold)]
    labels = [r["label"] for r in results]
    c = counts(labels)
    total = c["total"]
    wrong_rate = c["wrong"] / total if total else 0.0
    useful_rate = c["correct_and_useful"] / total if total else 0.0
    blocked = [g["id"] for g, r in zip(gold, results) if r["label"] == "wrong"]

    print("== Held-out eval ==")
    print(f"generator: {label}")
    print(f"held-out items: {total}")
    print(f"named-source present on every item: {len(missing_source) == 0}")
    print(f"correct_and_useful: {c['correct_and_useful']}  "
          f"correct_but_bad_teaching: {c['correct_but_bad_teaching']}  wrong: {c['wrong']}")
    print(f"useful (accuracy) rate: {useful_rate:.1%}")
    print(f"wrong-answer rate: {wrong_rate:.1%}")
    print(f"blocked (failed checker, withheld from students): {len(blocked)} {blocked}")
    print(f"PRE-DECLARED cutoffs: wrong-rate <= {WRONG_RATE_CUTOFF:.0%} AND useful-rate >= {USEFUL_RATE_FLOOR:.0%}")

    passed = (
        wrong_rate <= WRONG_RATE_CUTOFF
        and useful_rate >= USEFUL_RATE_FLOOR
        and len(missing_source) == 0
    )
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    ok = run(live="--live" in sys.argv)
    sys.exit(0 if ok else 1)
