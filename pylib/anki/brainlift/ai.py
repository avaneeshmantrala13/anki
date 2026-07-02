# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""BrainLift AI provider layer (OpenAI + deterministic fallback).

This is the *only* place BrainLift talks to a language model. It exposes a tiny
provider interface (`AiClient`) with two implementations:

* :class:`RealOpenAIClient` — calls the OpenAI chat-completions REST API with
  ``requests`` (mirrors the mobile OkHttp call for parity). The API key is read
  **only** from the ``OPENAI_API_KEY`` environment variable; it is never stored
  in config or committed.
* :class:`DeterministicAnalogClient` — a rule/template-based re-parameterizer
  that always produces a valid, *checkable* analog MCQ and records the named
  source. Used when AI is OFF, no key is present, the service is offline /
  rate-limited / returns broken output, and in tests + the eval harness
  (deterministic fixtures, no live key required).

Design guarantees (SpeedRunner):
* **Named-source traceability** — every :class:`GeneratedAnalog` carries the
  source card id and source text.
* **Graceful degradation** — the real client wraps *all* network + parsing in
  try/except and falls back to the deterministic client with ``ok=False``; it
  never raises, never blocks scoring.
* **AI OFF still works** — :func:`get_client` returns the deterministic client
  whenever AI is disabled or no key is available.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from anki.collection import Collection

# --- config keys (shared with mobile; see BRAINLIFT_AI_SPEC.md) --------------
CONFIG_AI_ENABLED = "brainlift_ai_enabled"
CONFIG_AI_MODEL = "brainlift_ai_model"
DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
ENV_API_KEY = "OPENAI_API_KEY"


# --- shared numeric formatting (kept identical to Kotlin fmtNum) -------------
def fmt_num(x: float) -> str:
    """Format a number: integers without a decimal, else trimmed to 4 dp."""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.4f}".rstrip("0").rstrip(".")


@dataclass
class GeneratedAnalog:
    """One AI-generated analog question with named-source traceability."""

    question: str
    choices: list[str]
    correct_index: int
    source_card_id: int
    source_text: str
    model: str = "deterministic"
    ok: bool = True

    def to_dict(self) -> dict:
        return {
            "generated_question": self.question,
            "generated_choices": self.choices,
            "generated_correct_index": self.correct_index,
            "generated_source_card_id": self.source_card_id,
            "generated_source_text": self.source_text,
            "model": self.model,
            "ok": self.ok,
        }


class AiClient(Protocol):
    def generate_analog(
        self, front: str, back: str, source_card_id: int
    ) -> GeneratedAnalog: ...


# --- deterministic template bank --------------------------------------------
# Each template matches on keywords in the source card and computes a genuinely
# checkable correct answer from parameters derived *deterministically* from the
# source card id (no RNG), so desktop and mobile agree on the correct value.


def _params(card_id: int) -> tuple[int, int, int]:
    """Three small deterministic parameters derived from the card id."""
    a = 2 + (card_id % 5)  # 2..6
    b = 3 + (card_id % 4)  # 3..6
    c = 1 + (card_id % 9)  # 1..9
    return a, b, c


def _dedupe_distractors(correct: str, distractors: list[str], card_id: int) -> list[str]:
    """Drop distractors equal to the correct answer or to each other, then pad
    deterministically so we always have >= 2 distinct wrong choices. Keeps the
    generated MCQ unambiguously checkable (parity-critical: mirror in Kotlin)."""
    out: list[str] = []
    for d in distractors:
        if d != correct and d not in out:
            out.append(d)
    if len(out) >= 2:
        return out[:3]
    # pad with deterministic synthetic wrong answers derived from `correct`
    try:
        base = float(correct)
        is_int = float(base).is_integer() and "." not in correct
        step = 0
        while len(out) < 3:
            step += 1
            for delta in (step, -step):
                cand_val = base + delta
                cand = str(int(cand_val)) if is_int else fmt_num(round(cand_val, 4))
                if cand != correct and cand not in out:
                    out.append(cand)
                if len(out) >= 3:
                    break
    except ValueError:
        suffix = 1
        while len(out) < 3:
            cand = f"{correct} (alt {suffix})"
            if cand not in out:
                out.append(cand)
            suffix += 1
    return out[:3]


def _place(correct: str, distractors: list[str], card_id: int) -> tuple[list[str], int]:
    """Deterministically position the correct answer among de-duplicated distractors."""
    clean = _dedupe_distractors(correct, distractors, card_id)
    idx = card_id % (len(clean) + 1)
    choices = list(clean)
    choices.insert(idx, correct)
    return choices, idx


@dataclass
class _Template:
    key: str
    keywords: tuple[str, ...]

    def render(self, card_id: int) -> tuple[str, str, list[str]]:  # pragma: no cover
        raise NotImplementedError


def _tpl_counting(card_id: int) -> tuple[str, str, list[str]]:
    sided, n, _ = _params(card_id)
    n = 2 + (card_id % 3)  # 2..4 rolls
    correct = sided**n
    q = (
        f"A fair {sided}-sided die is rolled {n} times. How many equally likely "
        f"ordered outcomes are there?"
    )
    d = [str(sided * n), str(sided ** (n - 1)), str(sided * (n + 1))]
    return q, str(correct), d


def _tpl_atleastone(card_id: int) -> tuple[str, str, list[str]]:
    _, _, c = _params(card_id)
    n = 2 + (card_id % 4)
    p = round(0.1 * (1 + card_id % 5), 2)  # 0.1..0.5
    correct = round(1 - (1 - p) ** n, 4)
    q = (
        f"An event occurs independently with probability {fmt_num(p)} on each of "
        f"{n} trials. What is P(it occurs at least once)?"
    )
    d = [fmt_num(round(p * n, 4)), fmt_num(round(p**n, 4)), fmt_num(round((1 - p) ** n, 4))]
    return q, fmt_num(correct), d


def _tpl_binomial_mean(card_id: int) -> tuple[str, str, list[str]]:
    n = 5 + (card_id % 8)
    p = round(0.1 * (1 + card_id % 8), 2)
    correct = round(n * p, 4)
    q = f"X ~ Binomial(n={n}, p={fmt_num(p)}). What is E[X]?"
    d = [fmt_num(round(n * p * (1 - p), 4)), fmt_num(n), fmt_num(p)]
    return q, fmt_num(correct), d


def _tpl_poisson_var(card_id: int) -> tuple[str, str, list[str]]:
    lam = 1 + (card_id % 6)
    q = f"X ~ Poisson(lambda={lam}). What is Var(X)?"
    d = [fmt_num(round(lam**0.5, 4)), str(lam * lam), str(lam + 1)]
    return q, str(lam), d


def _tpl_exponential_mean(card_id: int) -> tuple[str, str, list[str]]:
    rate = 2 + (card_id % 5)
    correct = round(1 / rate, 4)
    q = f"X ~ Exponential with rate lambda={rate}. What is E[X]?"
    d = [str(rate), fmt_num(round(1 / (rate * rate), 4)), str(rate * rate)]
    return q, fmt_num(correct), d


def _tpl_independent_and(card_id: int) -> tuple[str, str, list[str]]:
    a = round(0.1 * (2 + card_id % 7), 2)
    b = round(0.1 * (1 + card_id % 6), 2)
    correct = round(a * b, 4)
    q = (
        f"Events A and B are independent with P(A)={fmt_num(a)} and "
        f"P(B)={fmt_num(b)}. What is P(A and B)?"
    )
    d = [fmt_num(round(a + b, 4)), fmt_num(round(a + b - a * b, 4)), fmt_num(round(abs(a - b), 4))]
    return q, fmt_num(correct), d


# (keywords, renderer). Order matters: first match wins.
_TEMPLATES: list[tuple[tuple[str, ...], object]] = [
    (("coin", "flip", "die", "roll", "outcome", "possib", "toss"), _tpl_counting),
    (("at least one", "at least", "complement"), _tpl_atleastone),
    (("binomial", "e[x]", "expected", "mean"), _tpl_binomial_mean),
    (("poisson", "var(", "variance"), _tpl_poisson_var),
    (("exponential",), _tpl_exponential_mean),
    (("independent", "p(a and b)", "intersection"), _tpl_independent_and),
]


def _matched_template(text: str):
    low = text.lower()
    for keywords, renderer in _TEMPLATES:
        if any(k in low for k in keywords):
            return renderer
    return None


class DeterministicAnalogClient:
    """Rule/template-based analog generator (no network, fully deterministic).

    * If the source card matches a known Exam P template, produce a genuinely
      re-parameterized, *checkable* analog (this is the "correct-and-useful"
      path).
    * Otherwise fall back to a concept-variety MCQ chosen by card id. It is
      still a valid checkable math question but is not conceptually tied to the
      source (the eval flags these as "correct-but-bad-teaching").
    """

    model = "deterministic"

    def generate_analog(
        self, front: str, back: str, source_card_id: int
    ) -> GeneratedAnalog:
        source_text = f"{front} :: {back}".strip()
        renderer = _matched_template(source_text)
        conceptually_matched = renderer is not None
        if renderer is None:
            # concept-variety fallback: deterministic pick keeps parity.
            renderer = _TEMPLATES[source_card_id % len(_TEMPLATES)][1]
        question, correct, distractors = renderer(source_card_id)
        choices, idx = _place(correct, distractors, source_card_id)
        return GeneratedAnalog(
            question=question,
            choices=choices,
            correct_index=idx,
            source_card_id=source_card_id,
            source_text=source_text,
            model="deterministic" if conceptually_matched else "deterministic-variety",
            ok=True,
        )


class RealOpenAIClient:
    """Calls OpenAI chat-completions via ``requests`` (parity with mobile)."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 30.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._fallback = DeterministicAnalogClient()

    def _prompt(self, front: str, back: str) -> list[dict]:
        system = (
            "You are an actuarial exam tutor. Given a source flashcard, write ONE "
            "multiple-choice analog question that tests the SAME concept but is "
            "reworded and re-parameterized (different numbers/scenario). Return "
            "STRICT JSON: {\"question\": str, \"choices\": [str,...], "
            "\"correct_index\": int}. 3-4 choices, exactly one correct."
        )
        user = f"SOURCE FRONT: {front}\nSOURCE BACK: {back}\nReturn only JSON."
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def generate_analog(
        self, front: str, back: str, source_card_id: int
    ) -> GeneratedAnalog:
        source_text = f"{front} :: {back}".strip()
        try:
            import requests

            resp = requests.post(
                OPENAI_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": self._prompt(front, back),
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"OpenAI HTTP {resp.status_code}")
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            question = str(parsed["question"]).strip()
            choices = [str(c) for c in parsed["choices"]]
            correct_index = int(parsed["correct_index"])
            if not question or len(choices) < 2 or not (0 <= correct_index < len(choices)):
                raise ValueError("malformed analog")
            return GeneratedAnalog(
                question=question,
                choices=choices,
                correct_index=correct_index,
                source_card_id=source_card_id,
                source_text=source_text,
                model=self.model,
                ok=True,
            )
        except Exception:
            # Any failure (offline, rate-limited, bad JSON) -> clean fallback.
            fb = self._fallback.generate_analog(front, back, source_card_id)
            fb.model = f"{self.model}-fallback"
            fb.ok = False
            return fb


# --- config helpers + client factory ----------------------------------------


def ai_enabled(col: Collection) -> bool:
    return bool(col.get_config(CONFIG_AI_ENABLED, False))


def set_ai_enabled(col: Collection, enabled: bool) -> None:
    col.set_config(CONFIG_AI_ENABLED, bool(enabled))


def ai_model(col: Collection) -> str:
    return str(col.get_config(CONFIG_AI_MODEL, DEFAULT_MODEL) or DEFAULT_MODEL)


def set_ai_model(col: Collection, model: str) -> None:
    col.set_config(CONFIG_AI_MODEL, model)


def api_key_from_env() -> str | None:
    key = os.environ.get(ENV_API_KEY)
    return key.strip() if key and key.strip() else None


def get_client(
    enabled: bool, model: str = DEFAULT_MODEL, api_key: str | None = None
) -> AiClient:
    """Return the real client only when AI is enabled AND a key is present."""
    if enabled and api_key:
        return RealOpenAIClient(api_key=api_key, model=model)
    return DeterministicAnalogClient()


def client_for_collection(col: Collection) -> AiClient:
    return get_client(ai_enabled(col), ai_model(col), api_key_from_env())
