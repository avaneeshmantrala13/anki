# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Gold-set eval: run all 50 generated cards through the checker and report
counts of correct-and-useful / wrong / correct-but-bad-teaching.
"""

from __future__ import annotations

import sys

from _common import generate_for_gold, get_generator
from checker import check_analog, counts
from gold_set import GOLD


def run(live: bool = False) -> bool:
    client, label = get_generator(live)
    analogs = generate_for_gold(GOLD, client)
    results = [check_analog(a, g) for a, g in zip(analogs, GOLD)]
    c = counts([r["label"] for r in results])

    wrong_rate = c["wrong"] / c["total"] if c["total"] else 0.0
    print("== Gold-set eval (50 generated cards) ==")
    print(f"generator: {label}")
    print(f"correct_and_useful:        {c['correct_and_useful']}")
    print(f"correct_but_bad_teaching:  {c['correct_but_bad_teaching']}")
    print(f"wrong (blocked, withheld):  {c['wrong']}")
    print(f"total:                     {c['total']}")
    print(f"wrong-answer rate: {wrong_rate:.1%} (pre-declared cutoff <= 10%)")

    # Sanity: every item traces to a named source.
    traced = all(a.source_text and a.source_card_id is not None for a in analogs)
    print(f"every item traces to a named source: {traced}")
    return wrong_rate <= 0.10 and traced


if __name__ == "__main__":
    ok = run(live="--live" in sys.argv)
    sys.exit(0 if ok else 1)
