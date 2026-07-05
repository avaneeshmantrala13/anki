# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Smoke test for the 3-build ablation study (brainlift_eval/ablation.py).

Runs a SMALL, fast version of the simulated ablation and asserts it is
deterministic, well-formed, and directionally sane (the full app is not worse
than the two ablated builds under the modeled mechanisms). Kept deliberately
lenient so it verifies the harness works without over-fitting to exact numbers.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "brainlift_eval")
)

import ablation  # noqa: E402

SMALL = dict(n_learners=12, study_slots=60, heldout_questions=40, verbose=False)


def test_ablation_is_deterministic():
    a = ablation.run(**SMALL)
    b = ablation.run(**SMALL)
    assert a == b


def test_ablation_structure_and_ranges():
    r = ablation.run(**SMALL)
    assert r["primary_metric"]  # pre-declared metric is present
    for build in ("full", "ablation", "stock"):
        m = r["builds"][build]["mean"]
        ci = r["builds"][build]["ci95"]
        assert 0.0 <= m <= 1.0
        assert ci >= 0.0
    # both required paired comparisons are reported with a range
    assert "diff_full_minus_ablation" in r
    assert "diff_full_minus_stock" in r
    # calibration subgroups partition the cohort
    sg = r["calibration_subgroups"]
    assert sg["poorly_calibrated"]["n"] + sg["well_calibrated"]["n"] == SMALL[
        "n_learners"
    ]


def test_full_app_not_worse_than_ablated_builds():
    r = ablation.run(**SMALL)
    full = r["builds"]["full"]["mean"]
    ablated = r["builds"]["ablation"]["mean"]
    stock = r["builds"]["stock"]["mean"]
    # Under the modeled mechanisms the full app should be at least as good.
    assert full >= ablated
    assert full >= stock
    # And the A-vs-stock advantage should be a positive point estimate.
    assert r["diff_full_minus_stock"]["mean"] > 0.0
