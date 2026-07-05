# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Run the full BrainLift AI eval suite and print an overall PASS/FAIL.

Usage:
    python run_all.py           # offline, deterministic fixtures (no key needed)
    python run_all.py --live    # calls OpenAI if OPENAI_API_KEY is set
"""

from __future__ import annotations

import sys

import ablation
import baseline
import fatigue_model_eval
import gold_eval
import leakage_check
import memory_calibration_eval
import paraphrase_gap
import performance_holdout_eval
import prompt_injection_check
import run_eval


def _ablation_pass() -> bool:
    """Run the 3-build ablation and reduce its dict result to a PASS/FAIL.

    ``ablation.run`` prints its own report and returns a results dict (no single
    PASS line), so aggregate the same directional check the smoke test asserts:
    the full app must be at least as good as both ablated builds AND beat stock
    Anki on the pre-declared primary metric.
    """
    r = ablation.run()
    full = r["builds"]["full"]["mean"]
    passed = (
        full >= r["builds"]["ablation"]["mean"]
        and full >= r["builds"]["stock"]["mean"]
        and r["diff_full_minus_stock"]["mean"] > 0.0
    )
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


def main() -> int:
    live = "--live" in sys.argv
    results = {}
    for name, fn in [
        ("held_out_eval", lambda: run_eval.run(live)),
        ("gold_eval", lambda: gold_eval.run(live)),
        ("baseline_comparison", lambda: baseline.run(live)),
        ("leakage_check", lambda: leakage_check.run(live)),
        ("prompt_injection_check", lambda: prompt_injection_check.run(live)),
        ("paraphrase_gap", paraphrase_gap.run),
        ("fatigue_model_eval", lambda: fatigue_model_eval.run(live)),
        ("memory_calibration_eval", lambda: memory_calibration_eval.run(live)),
        ("performance_holdout_eval", lambda: performance_holdout_eval.run(live)),
        ("ablation_study", _ablation_pass),
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
