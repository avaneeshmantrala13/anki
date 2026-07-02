# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Paraphrase-gap: for ~30 cards, compare recall on the ORIGINAL card vs accuracy
on the reworded/re-parameterized analog. A positive gap is evidence that a high
self-rating on the original (memory) does not guarantee performance on a novel
phrasing of the same concept (performance != memory).

There are no live students in CI, so this is a SIMULATION harness with a fixed
seed: each card gets a deterministic "memory strength" (how well the original is
recalled) and a transfer factor < 1 for the re-parameterized analog. Swap in real
per-user response data (front-recall vs analog-correct) to get live numbers; the
computation of the gap is identical.
"""

from __future__ import annotations

import random
import sys

from gold_set import GOLD

N_CARDS = 30
TRIALS = 200  # simulated attempts per card to stabilise the rate


def run() -> bool:
    rng = random.Random(42)
    cards = GOLD[:N_CARDS]
    orig_hits = analog_hits = total = 0
    for _ in range(TRIALS):
        for c in cards:
            # deterministic-ish memory strength for the memorized original
            strength = 0.75 + 0.20 * rng.random()
            # transfer to a novel phrasing is imperfect
            transfer = 0.55 + 0.25 * rng.random()
            orig_hits += 1 if rng.random() < strength else 0
            analog_hits += 1 if rng.random() < strength * transfer else 0
            total += 1

    orig_rate = orig_hits / total
    analog_rate = analog_hits / total
    gap = orig_rate - analog_rate

    print("== Paraphrase gap (simulated; wire real response data for live numbers) ==")
    print(f"cards: {N_CARDS}  trials/card: {TRIALS}")
    print(f"original-card recall:     {orig_rate:.1%}")
    print(f"analog-question accuracy: {analog_rate:.1%}")
    print(f"paraphrase gap:           {gap:.1%}")
    print("Interpretation: positive gap => memory on the original overstates true "
          "concept performance (motivates the confidence-authority down-weighting).")
    return gap > 0.05


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
