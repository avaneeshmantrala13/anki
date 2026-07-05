# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Side-by-side: the structured/AI analog generator vs a simpler keyword baseline.

Metric = "valid re-parameterized analog": structurally valid MCQ that is
conceptually tied to its source AND is not a near-duplicate of any gold question
(a real analog must reword/re-parameterize, not echo an existing item).

* Structured generator: the BrainLift analog client (deterministic offline, or
  real OpenAI with --live). Re-parameterizes the same concept.
* Keyword baseline: a retrieval baseline. For each source it returns the gold
  item whose question shares the most keywords, reused verbatim as the "analog",
  with distractors sampled from other gold answers. This is what naive keyword
  similarity produces — it leaks the source concept but does not create a new
  re-parameterized question.
"""

from __future__ import annotations

import sys

from _common import generate_for_gold, get_generator, jaccard
from checker import _structurally_valid, check_analog
from gold_set import GOLD

LEAK_THRESHOLD = 0.85


class _BaselineAnalog:
    def __init__(self, question, choices, correct_index, source_card_id, source_text):
        self.question = question
        self.choices = choices
        self.correct_index = correct_index
        self.source_card_id = source_card_id
        self.source_text = source_text
        self.model = "keyword-baseline"
        self.ok = True


class KeywordBaseline:
    """Retrieval baseline driven purely by keyword overlap."""

    def __init__(self, corpus: list[dict]):
        self.corpus = corpus

    def generate_analog(self, front: str, back: str, source_card_id: int):
        source_text = f"{front} :: {back}".strip()
        # nearest neighbor by keyword overlap, excluding the exact source front
        best = None
        best_score = -1.0
        for item in self.corpus:
            if item["front"] == front:
                continue
            s = jaccard(front, item["front"])
            if s > best_score:
                best_score, best = s, item
        # distractors: the next gold answers cyclically (naive, causes collisions)
        backs = [g["back"] for g in self.corpus]
        start = self.corpus.index(best)
        distractors = [backs[(start + k) % len(backs)] for k in (1, 2, 3)]
        choices = [best["back"]] + distractors
        return _BaselineAnalog(best["front"], choices, 0, source_card_id, source_text)


def _valid_analog(analog, gold_item) -> bool:
    ok, _ = _structurally_valid(analog)
    if not ok:
        return False
    if check_analog(analog, gold_item)["label"] != "correct_and_useful":
        return False
    max_leak = max(jaccard(analog.question, g["front"]) for g in GOLD)
    return max_leak < LEAK_THRESHOLD


def run(live: bool = False) -> bool:
    client, label = get_generator(live)
    structured = generate_for_gold(GOLD, client)
    baseline_client = KeywordBaseline(GOLD)
    baseline = [baseline_client.generate_analog(g["front"], g["back"], 1000 + i)
                for i, g in enumerate(GOLD)]

    s_valid = sum(_valid_analog(a, g) for a, g in zip(structured, GOLD))
    b_valid = sum(_valid_analog(a, g) for a, g in zip(baseline, GOLD))
    n = len(GOLD)

    print("== Baseline comparison (valid re-parameterized analogs / 50) ==")
    print(f"structured generator ({label}): {s_valid}/{n}  ({s_valid / n:.1%})")
    print(f"keyword baseline:               {b_valid}/{n}  ({b_valid / n:.1%})")
    beats = s_valid > b_valid
    print(f"RESULT: structured {'BEATS' if beats else 'does NOT beat'} baseline")
    return beats


if __name__ == "__main__":
    ok = run(live="--live" in sys.argv)
    sys.exit(0 if ok else 1)
