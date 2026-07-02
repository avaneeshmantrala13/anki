# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Run the full BrainLift AI eval suite and print an overall PASS/FAIL.

Usage:
    python run_all.py           # offline, deterministic fixtures (no key needed)
    python run_all.py --live    # calls OpenAI if OPENAI_API_KEY is set
"""

from __future__ import annotations

import sys

import baseline
import gold_eval
import leakage_check
import paraphrase_gap
import run_eval


def main() -> int:
    live = "--live" in sys.argv
    results = {}
    for name, fn in [
        ("held_out_eval", lambda: run_eval.run(live)),
        ("gold_eval", lambda: gold_eval.run(live)),
        ("baseline_comparison", lambda: baseline.run(live)),
        ("leakage_check", lambda: leakage_check.run(live)),
        ("paraphrase_gap", paraphrase_gap.run),
    ]:
        print("\n" + "=" * 68)
        results[name] = bool(fn())

    print("\n" + "=" * 68)
    print("SUMMARY")
    for name, ok in results.items():
        print(f"  {name:22s}: {'PASS' if ok else 'FAIL'}")
    overall = all(results.values())
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
