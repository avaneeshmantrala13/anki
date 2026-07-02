# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Leakage-gate unit tests (desktop side of the desktop/mobile parity pair).

These mirror the Kotlin `BrainLiftParityTest` gate assertions and prove that the
generation pipeline removes true free-answer leakage (near-verbatim question +
same resolved answer) from the SERVED set by regenerating and, if needed,
blocking — exactly the fix for the live gpt-4o-mini leak on source card 'm06'.
"""

from anki.brainlift import ai as blai


def _analog(question: str, correct: str, source_card_id: int = 1) -> blai.GeneratedAnalog:
    return blai.GeneratedAnalog(
        question=question,
        choices=[correct, "zzz-other", "yyy-other"],
        correct_index=0,
        source_card_id=source_card_id,
        source_text="src",
        model="test",
    )


class _LeakyClient:
    """Test double that echoes the source (near-verbatim + same answer). If
    ``fix_after`` is set, it starts producing a clean re-parameterized analog once
    ``attempt >= fix_after`` (to exercise catch-and-regenerate)."""

    def __init__(self, fix_after: int | None = None):
        self.fix_after = fix_after
        self.calls = 0

    def generate_analog(
        self, front: str, back: str, source_card_id: int, attempt: int = 0
    ) -> blai.GeneratedAnalog:
        self.calls += 1
        if self.fix_after is not None and attempt >= self.fix_after:
            return blai.GeneratedAnalog(
                question="Completely reworded prompt using brand new numbers 999",
                choices=[f"{back}-changed", "aaa", "bbb"],
                correct_index=0,
                source_card_id=source_card_id,
                source_text=f"{front} :: {back}",
                model="test",
            )
        return blai.GeneratedAnalog(
            question=front,  # near-verbatim
            choices=[back, "other1", "other2"],  # same answer
            correct_index=0,
            source_card_id=source_card_id,
            source_text=f"{front} :: {back}",
            model="test",
        )


def test_shared_gate_constants():
    assert blai.LEAKAGE_SIM_THRESHOLD == 0.9
    assert blai.MAX_REGEN == 3
    assert blai.REGEN_PARAM_STRIDE == 101


def test_is_leaked_detects_near_verbatim_same_answer():
    front = "X ~ Poisson(lambda=3). What is Var(X)?"
    assert blai.is_leaked(_analog(front, "3"), front, "3") is True


def test_is_leaked_false_when_answer_differs():
    front = "X ~ Poisson(lambda=3). What is Var(X)?"
    # near-verbatim wording but a DIFFERENT answer is a valid re-parameterization
    assert blai.is_leaked(_analog(front, "7"), front, "3") is False


def test_is_leaked_false_when_wording_differs():
    front = "X ~ Poisson(lambda=3). What is Var(X)?"
    reworded = "A call center gets calls at rate 5 per hour; find the variance"
    assert blai.is_leaked(_analog(reworded, "3"), front, "3") is False


def test_is_leaked_numeric_equivalence():
    front = "P(A and B) for independent A,B?"
    # "0.20" vs "0.2" resolve to the same value -> still leakage
    assert blai.is_leaked(_analog(front, "0.20"), front, "0.2") is True


def test_gate_blocks_persistent_leaker():
    client = _LeakyClient(fix_after=None)  # never stops leaking
    gated = blai.generate_gated_analog(client, "front text", "42", 1)
    assert gated.leaked_initially is True
    assert gated.regen_attempts == blai.MAX_REGEN
    assert gated.blocked is True
    assert gated.served is False


def test_gate_catches_and_regenerates():
    client = _LeakyClient(fix_after=2)  # clean after 2 retries
    gated = blai.generate_gated_analog(client, "front text", "42", 1)
    assert gated.leaked_initially is True
    assert gated.regen_attempts == 2
    assert gated.blocked is False
    assert gated.served is True
    assert blai.is_leaked(gated.analog, "front text", "42") is False


def test_gate_passes_clean_generation_untouched():
    client = _LeakyClient(fix_after=0)  # clean on the very first call
    gated = blai.generate_gated_analog(client, "front text", "42", 1)
    assert gated.leaked_initially is False
    assert gated.regen_attempts == 0
    assert gated.blocked is False
    assert gated.served is True


def test_deterministic_regen_changes_answer():
    client = blai.DeterministicAnalogClient()
    front = "X ~ Poisson(lambda=3). What is Var(X)?"
    a0 = client.generate_analog(front, "3", 7, attempt=0)
    a1 = client.generate_analog(front, "3", 7, attempt=1)
    # perturbing the parameter id must change the generated question/answer
    assert (a0.question, a0.choices[a0.correct_index]) != (
        a1.question,
        a1.choices[a1.correct_index],
    )


def test_deterministic_pipeline_serves_clean_analog_for_m06_like_source():
    # 'm06' style source (joint pdf / marginal density) with the deterministic
    # client must go through the gate and be SERVED (not blocked).
    client = blai.DeterministicAnalogClient()
    front = "The joint pdf f(x,y)=1 on the unit square 0<x<1, 0<y<1. What is the marginal density of X?"
    gated = blai.generate_gated_analog(client, front, "1 on (0,1)", 2006)
    assert gated.served is True
    assert gated.blocked is False
