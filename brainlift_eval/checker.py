# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Analog checker: classify a generated analog into one of three buckets.

Rules (documented so the eval is auditable):

* ``wrong`` — the analog is not a usable MCQ:
    - empty question, or fewer than 2 choices, or
    - ``correct_index`` outside the choice range, or
    - the marked-correct choice text is duplicated among the choices (so the
      "correct" answer is ambiguous / not uniquely checkable).
* ``correct_but_bad_teaching`` — a structurally valid, checkable MCQ that is NOT
  conceptually tied to the source card (it tests a different concept). For the
  deterministic generator this is the ``deterministic-variety`` model; for a real
  model it is a valid MCQ that shares no probability concept keyword with the
  source.
* ``correct_and_useful`` — a structurally valid, checkable MCQ that is
  conceptually tied to the source (re-parameterized same concept).
"""

from __future__ import annotations

from _common import tokens

# Probability concept keywords used to judge "conceptually tied to source".
_CONCEPT_WORDS = {
    "coin", "die", "dice", "roll", "flip", "toss", "outcomes", "outcome",
    "independent", "intersection", "binomial", "poisson", "exponential",
    "uniform", "normal", "expected", "mean", "variance", "var", "covariance",
    "cov", "correlation", "corr", "bayes", "conditional", "probability",
    "least", "complement", "joint", "marginal", "clt",
}


def _structurally_valid(analog) -> tuple[bool, str]:
    if not analog.question or not analog.question.strip():
        return False, "empty question"
    if len(analog.choices) < 2:
        return False, "fewer than 2 choices"
    if not (0 <= analog.correct_index < len(analog.choices)):
        return False, "correct_index out of range"
    correct = analog.choices[analog.correct_index]
    if analog.choices.count(correct) != 1:
        return False, "ambiguous correct answer (duplicated choice)"
    return True, "ok"


def _conceptually_tied(analog, gold_item) -> bool:
    model = getattr(analog, "model", "")
    if model == "deterministic":
        return True
    if model == "deterministic-variety":
        return False
    # Real model (or fallback): tie if the analog shares a probability concept
    # keyword with the source card.
    src = tokens(gold_item["front"]) & _CONCEPT_WORDS
    gen = tokens(analog.question) & _CONCEPT_WORDS
    return len(src & gen) > 0


def check_analog(analog, gold_item) -> dict:
    valid, reason = _structurally_valid(analog)
    if not valid:
        return {"label": "wrong", "reason": reason}
    if _conceptually_tied(analog, gold_item):
        return {"label": "correct_and_useful", "reason": "valid + on-concept"}
    return {"label": "correct_but_bad_teaching", "reason": "valid but off-concept"}


def counts(labels: list[str]) -> dict:
    return {
        "correct_and_useful": labels.count("correct_and_useful"),
        "wrong": labels.count("wrong"),
        "correct_but_bad_teaching": labels.count("correct_but_bad_teaching"),
        "total": len(labels),
    }
