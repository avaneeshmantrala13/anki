# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Leakage check: scan every generated analog against the gold/test set and flag
TRUE near-duplicates. A genuine analog re-parameterizes the source: same concept
and phrasing is expected, so phrasing similarity alone is NOT leakage. Leakage is
when a student who saw a gold/test item gets the analog for free — i.e. the
generated question is near-verbatim AND resolves to the SAME correct answer.

We report the worst phrasing overlap for transparency, but flag an item only when
question overlap >= QUESTION_SIM AND the generated correct answer equals the gold
answer. Flagged items would be blocked/regenerated before students see them.
"""

from __future__ import annotations

import sys

from _common import generate_for_gold, get_generator, jaccard
from gold_set import GOLD

QUESTION_SIM = 0.90  # near-verbatim question wording


def _generated_answer(a) -> str:
    return a.choices[a.correct_index]


def run(live: bool = False) -> bool:
    client, label = get_generator(live)
    analogs = generate_for_gold(GOLD, client)

    flagged = []
    worst_phrasing = 0.0
    for a, src in zip(analogs, GOLD):
        gen_ans = _generated_answer(a).strip().lower()
        for g in GOLD:
            sim = jaccard(a.question, g["front"])
            worst_phrasing = max(worst_phrasing, sim)
            # true leak: near-verbatim wording AND identical answer
            if sim >= QUESTION_SIM and gen_ans == g["back"].strip().lower():
                flagged.append((src["id"], g["id"], round(sim, 3)))
                break

    print("== Leakage check ==")
    print(f"generator: {label}")
    print(f"generated items scanned: {len(analogs)}")
    print(f"question-similarity threshold: {QUESTION_SIM} (plus identical answer)")
    print(f"worst phrasing overlap (expected high; same concept): {worst_phrasing:.3f}")
    print(f"flagged true duplicates (near-verbatim + same answer): {len(flagged)} {flagged}")
    clean = len(flagged) == 0
    print(f"RESULT: {'CLEAN' if clean else 'LEAKAGE DETECTED (would be blocked/regenerated)'}")
    return clean


if __name__ == "__main__":
    ok = run(live="--live" in sys.argv)
    sys.exit(0 if ok else 1)
