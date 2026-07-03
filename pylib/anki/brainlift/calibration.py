# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 1 — Metacognitive calibration ("confidence authority").

The student self-rates confidence on ``CALIBRATION_TEST_SIZE`` Exam P cards
(before seeing the answer), then answers ``CALIBRATION_TEST_SIZE`` AI-generated
analog MCQs. We measure how well their confidence predicts their performance:

* headline **accuracy** = ``1 - mean(|confidence - performance|)`` (MAD-based),
* secondary **gamma** = Goodman-Kruskal resolution between JOLs and accuracy,
* a **confidence-authority multiplier** that scales how much the user's
  self-ratings are allowed to suppress future reviews.

All formulas + constants mirror ``BRAINLIFT_AI_SPEC.md`` and the Kotlin engine.
Nothing here calls the network directly — analog generation goes through
:mod:`anki.brainlift.ai`, which degrades gracefully when AI is off/unavailable.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from anki.brainlift import ai as blai

if TYPE_CHECKING:
    from anki.collection import Collection

CONFIG_KEY = "brainlift_calibration"
CONFIG_MULTIPLIER_KEY = "brainlift_calibration_multiplier"

# --- shared constants (see BRAINLIFT_AI_SPEC.md §1, §2, §4) ------------------
CONFIDENCE_SCALE: dict[str, float] = {
    "Highly confident": 1.0,
    "Confident": 0.85,
    "Kind of confident": 0.6,
    "Unsure": 0.3,
    "Guessing": 0.0,
}
CONFIDENCE_ORDER: list[str] = [
    "Highly confident",
    "Confident",
    "Kind of confident",
    "Unsure",
    "Guessing",
]

CALIBRATION_TEST_SIZE = 15
CALIBRATION_PRODUCTION_SIZE = 50

CALIB_AUTHORITY_FLOOR_ACCURACY = 0.5
MIN_AUTHORITY = 0.25

SEED_DECK_NAME = "Exam P — Sample Questions"


def confidence_value(label: str) -> float:
    """Map a confidence label to its [0,1] value (default 0.6 if unknown)."""
    return CONFIDENCE_SCALE.get(label, 0.6)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# --- core scoring (pure, parity-critical) -----------------------------------


def mean_absolute_deviation(confidences: list[float], performances: list[int]) -> float:
    if not confidences:
        return 0.0
    total = sum(abs(c - p) for c, p in zip(confidences, performances))
    return total / len(confidences)


def calibration_accuracy(confidences: list[float], performances: list[int]) -> float:
    """Headline accuracy = 1 - MAD, clamped to [0,1]."""
    return _clamp(1.0 - mean_absolute_deviation(confidences, performances))


def goodman_kruskal_gamma(
    confidences: list[float], performances: list[int]
) -> float | None:
    """Resolution between JOLs and accuracy. None if undefined (no ranked pairs)."""
    concordant = 0
    discordant = 0
    n = len(confidences)
    for i in range(n):
        for j in range(i + 1, n):
            cs = _sign(confidences[i] - confidences[j])
            ps = _sign(performances[i] - performances[j])
            if cs == 0 or ps == 0:
                continue
            if cs == ps:
                concordant += 1
            else:
                discordant += 1
    denom = concordant + discordant
    if denom == 0:
        return None
    return (concordant - discordant) / denom


def authority_multiplier(accuracy: float) -> float:
    """Map calibration accuracy -> [MIN_AUTHORITY, 1] authority weight."""
    norm = _clamp((accuracy - CALIB_AUTHORITY_FLOOR_ACCURACY) / (1.0 - CALIB_AUTHORITY_FLOOR_ACCURACY))
    return MIN_AUTHORITY + (1.0 - MIN_AUTHORITY) * norm


def calibrated_suppression(raw_suppression: float, multiplier: float) -> float:
    """Scale how strongly a high self-rating suppresses reviews, by authority."""
    return _clamp(raw_suppression) * _clamp(multiplier)


def effective_mastery_gap(mastered_fraction: float, multiplier: float) -> float:
    """How much a topic still needs review, after applying self-rating authority.

    A topic that looks "known" (high ``mastered_fraction``) normally suppresses
    its own review priority. We only allow that suppression in proportion to the
    learner's calibration authority (``multiplier``): well-calibrated learners
    fully suppress mastered topics (trust their demonstrated knownness), while
    poorly-calibrated learners keep more review coverage.

        effective_gap = 1 - mastered_fraction * multiplier
    """
    return _clamp(1.0 - _clamp(mastered_fraction) * _clamp(multiplier))


def explain_accuracy(accuracy: float) -> str:
    if accuracy >= 0.85:
        return "You're excellent at gauging what you know."
    if accuracy >= 0.70:
        return "You're good at judging what you know, with a little room to tighten up."
    if accuracy >= 0.55:
        return "Your self-judgment is roughly right, but not fully reliable yet."
    return (
        "Your self-judgment isn't fully reliable yet — treat your confidence with "
        "caution."
    )


# --- data types --------------------------------------------------------------


@dataclass
class CalibrationItem:
    source_card_id: int
    source_front: str
    source_back: str
    confidence_label: str
    confidence_value: float
    generated_question: str
    generated_choices: list[str]
    generated_correct_index: int
    generated_source_card_id: int
    generated_source_text: str
    chosen_index: int
    performance: int
    deviation: float


@dataclass
class CalibrationResult:
    test_size: int
    ai_used: bool
    items: list[CalibrationItem]
    mad: float
    accuracy: float
    gamma: float | None
    authority_multiplier: float
    completed_at: int
    explanation: str = ""


# --- card rendering for display (reuses Anki's own card templates) -----------

# The bundled SOA solutions were extracted from a PDF whose big-bracket,
# integral and matrix glyphs land in the Unicode Private Use Area (e.g. U+F8EE).
# Those code points have no portable font glyph and render as tofu boxes /
# "gibberish brackets", so we strip them for DISPLAY ONLY (stored data is never
# mutated). Covers the BMP PUA plus the two supplementary PUA planes.
_PRIVATE_USE_RE = re.compile(
    "[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]"
)


def strip_private_use(text: str) -> str:
    """Remove Unicode Private Use Area glyphs from text (display-only cleanup)."""
    return _PRIVATE_USE_RE.sub("", text)


def render_card_display(col: Collection, card_id: int) -> tuple[str, str]:
    """Return ``(question_html, answer_html)`` for a card, rendered like Anki.

    Uses the collection's *own* card rendering (``Card.question()`` /
    ``Card.answer()``) so templates, fields and cloze resolve exactly as they do
    in the reviewer, escapes media filenames to their served URLs, and strips
    Private Use Area glyphs. The calibration webview loads MathJax, so any
    ``\\(...\\)`` / ``\\[...\\]`` in the rendered HTML becomes real math instead
    of raw source. Returns ``("", "")`` on any failure so the UI never crashes.
    """
    try:
        card = col.get_card(int(card_id))
        question = col.media.escape_media_filenames(card.question())
        answer = col.media.escape_media_filenames(card.answer())
        return strip_private_use(question), strip_private_use(answer)
    except Exception:
        return "", ""


# --- card selection + analog generation -------------------------------------


def select_calibration_cards(
    col: Collection, size: int = CALIBRATION_TEST_SIZE
) -> list[tuple[int, str, str]]:
    """Deterministically pick ``size`` (card_id, front, back) triples.

    Sorted by card id ascending for reproducibility across platforms/re-runs.
    Prefers the seeded Exam P deck, falling back to any ExamP-tagged cards.
    """
    try:
        card_ids = col.find_cards(f'deck:"{SEED_DECK_NAME}"')
        if not card_ids:
            card_ids = col.find_cards("tag:ExamP::*")
    except Exception:
        card_ids = []
    triples: list[tuple[int, str, str]] = []
    for cid in sorted(int(c) for c in card_ids):
        try:
            card = col.get_card(cid)
            note = card.note()
            fields = {name: val for name, val in note.items()}
            front = fields.get("Front") or next(iter(fields.values()), "")
            back = fields.get("Back") or ""
            triples.append((cid, front, back))
        except Exception:
            continue
        if len(triples) >= size:
            break
    return triples


def build_calibration_questions(
    col: Collection,
    size: int = CALIBRATION_TEST_SIZE,
    on_result=None,
) -> list[blai.GeneratedAnalog]:
    """Generate one analog per selected card (named-source recorded).

    Generation is fanned out across a thread pool (see
    :func:`anki.brainlift.ai.generate_analogs_batch`) so the real OpenAI client
    overlaps its network round-trips instead of doing ``size`` sequential
    blocking calls. Order matches :func:`select_calibration_cards`. ``on_result``
    (if given) fires per completed item for live progress reporting.

    NOTE: This does DB reads (card selection) and, with the real client,
    blocking network calls — callers on the Qt UI thread must run it off-thread
    (the desktop dialog dispatches it via ``mw.taskman``).
    """
    cards = select_calibration_cards(col, size)
    client = blai.client_for_collection(col)
    items = [(front, back, cid) for cid, front, back in cards]
    return blai.generate_analogs_batch(client, items, on_result=on_result)


# --- scoring an answered test ------------------------------------------------


def score_calibration(
    cards: list[tuple[int, str, str]],
    analogs: list[blai.GeneratedAnalog],
    confidence_labels: list[str],
    chosen_indices: list[int],
) -> CalibrationResult:
    """Score a completed calibration test into a persisted result."""
    items: list[CalibrationItem] = []
    confidences: list[float] = []
    performances: list[int] = []
    ai_used = False

    for (cid, front, back), analog, label, chosen in zip(
        cards, analogs, confidence_labels, chosen_indices
    ):
        conf = confidence_value(label)
        perf = 1 if chosen == analog.correct_index else 0
        if analog.ok and analog.model not in ("deterministic", "deterministic-variety"):
            ai_used = True
        items.append(
            CalibrationItem(
                source_card_id=cid,
                source_front=front,
                source_back=back,
                confidence_label=label,
                confidence_value=conf,
                generated_question=analog.question,
                generated_choices=analog.choices,
                generated_correct_index=analog.correct_index,
                generated_source_card_id=analog.source_card_id,
                generated_source_text=analog.source_text,
                chosen_index=chosen,
                performance=perf,
                deviation=round(abs(conf - perf), 4),
            )
        )
        confidences.append(conf)
        performances.append(perf)

    mad = round(mean_absolute_deviation(confidences, performances), 4)
    accuracy = round(calibration_accuracy(confidences, performances), 4)
    gamma = goodman_kruskal_gamma(confidences, performances)
    mult = round(authority_multiplier(accuracy), 4)

    return CalibrationResult(
        test_size=len(items),
        ai_used=ai_used,
        items=items,
        mad=mad,
        accuracy=accuracy,
        gamma=round(gamma, 4) if gamma is not None else None,
        authority_multiplier=mult,
        completed_at=int(time.time()),
        explanation=explain_accuracy(accuracy),
    )


# --- persistence (collection config -> syncs) -------------------------------


def save_calibration(col: Collection, result: CalibrationResult) -> None:
    col.set_config(CONFIG_KEY, asdict(result))
    # Mirror the multiplier to a flat key the scheduling layer reads.
    col.set_config(CONFIG_MULTIPLIER_KEY, result.authority_multiplier)


def load_calibration(col: Collection) -> CalibrationResult | None:
    data = col.get_config(CONFIG_KEY, None)
    if not data:
        return None
    items = [CalibrationItem(**it) for it in data.get("items", [])]
    data = {**data, "items": items}
    return CalibrationResult(**data)


def has_calibration(col: Collection) -> bool:
    return load_calibration(col) is not None


def clear_calibration(col: Collection) -> None:
    """Wipe any stored calibration so the test can be cleanly re-run.

    Removes both the full result and the flat scheduling multiplier, resetting
    scheduling authority to neutral (1.0 via :func:`calibration_multiplier`).
    Re-running the test simply overwrites these keys, so an explicit reset is
    optional — it exists mainly so testers can start from a known-empty state.
    """
    col.remove_config(CONFIG_KEY)
    col.remove_config(CONFIG_MULTIPLIER_KEY)


def calibration_multiplier(col: Collection) -> float:
    """The synced authority multiplier used by the scheduling layer (default 1)."""
    return float(col.get_config(CONFIG_MULTIPLIER_KEY, 1.0))


def run_calibration(
    col: Collection,
    cards: list[tuple[int, str, str]],
    analogs: list[blai.GeneratedAnalog],
    confidence_labels: list[str],
    chosen_indices: list[int],
) -> CalibrationResult:
    result = score_calibration(cards, analogs, confidence_labels, chosen_indices)
    save_calibration(col, result)
    return result
