# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Smoke test for the performance benchmark harness (brainlift_eval/bench.py).

Runs a tiny, fast version (a few hundred cards, --quick iterations) and asserts
the harness produces the expected metric structure. It does NOT assert wall-clock
budgets (those are machine-dependent); ``bench.py`` itself reports PASS/FAIL.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "brainlift_eval")
)

import bench  # noqa: E402


def test_bench_runs_and_reports_all_actions():
    res = bench.run(n_cards=400, n_reviews=50, quick=True)
    for key in (
        "button_ack",
        "next_card",
        "dashboard_load",
        "dashboard_refresh",
        "aggregate_op",
        "cold_start",
        "peak_memory",
    ):
        assert key in res, f"missing benchmark action: {key}"
    # latency actions report percentiles; memory reports a value
    assert res["button_ack"]["p95"] >= 0.0
    assert res["aggregate_op"]["p95"] >= 0.0
    assert res["peak_memory"]["value"] > 0.0
    assert "_passed" in res
