# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Smoke test for the crash / durability harness (brainlift_eval/crash_test.py).

Runs a few kill-mid-review iterations and asserts zero corruption. Kept small so
it stays fast in CI; the full 20x run lives in the script itself.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "brainlift_eval")
)

import crash_test  # noqa: E402


def test_crash_mid_review_never_corrupts():
    res = crash_test.run(iterations=3, n_cards=120)
    assert res["iterations"] == 3
    assert res["corruption"] == 0
    assert res["clean"] == 3
    assert res["passed"] is True
