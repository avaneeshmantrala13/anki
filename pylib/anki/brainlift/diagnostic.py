# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Deterministic BrainLift diagnostic assessment (no AI).

Presents a small, author-written bank of representative Exam P multiple-choice
questions (with known-correct answers) and scores a student's responses with
transparent rules: overall and per-topic accuracy, time per question, mean
confidence, calibration (confidence minus accuracy), and a weak-topic ranking.

The questions are fixed content authored here — nothing is AI-generated. Results
are persisted to the collection config to seed the study planner (Step 5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from anki.brainlift import exam_p

if TYPE_CHECKING:
    from anki.collection import Collection

CONFIG_KEY = "brainlift_diagnostic"

# Confidence convenience levels (0-1); callers may pass any float in [0, 1].
CONFIDENCE_LOW = 0.25
CONFIDENCE_MEDIUM = 0.5
CONFIDENCE_HIGH = 0.9


@dataclass(frozen=True)
class DiagnosticQuestion:
    id: str
    topic_key: str  # matches an exam_p.SYLLABUS key
    prompt: str
    choices: tuple[str, ...]
    correct_index: int
    difficulty: float  # 0 (easy) .. 1 (hard)


@dataclass
class DiagnosticResponse:
    question_id: str
    chosen_index: int
    time_seconds: float = 0.0
    confidence: float = CONFIDENCE_MEDIUM  # 0..1


@dataclass
class TopicDiagnostic:
    topic_key: str
    topic_name: str
    total: int
    correct: int
    accuracy: float
    avg_time_seconds: float
    avg_confidence: float


@dataclass
class DiagnosticResult:
    total_questions: int
    answered: int
    overall_accuracy: float
    avg_time_seconds: float
    avg_confidence: float
    # confidence minus accuracy: > 0 overconfident, < 0 underconfident.
    calibration_gap: float
    topics: list[TopicDiagnostic] = field(default_factory=list)
    weak_topic_keys: list[str] = field(default_factory=list)


# --- Author-written Exam P question bank -------------------------------------
# Representative, known-correct. NOT AI-generated.

QUESTION_BANK: tuple[DiagnosticQuestion, ...] = (
    # General Probability
    DiagnosticQuestion(
        "gp1", "GeneralProbability",
        "A fair six-sided die is rolled. What is P(the result is even)?",
        ("1/6", "1/3", "1/2", "2/3"), 2, 0.2,
    ),
    DiagnosticQuestion(
        "gp2", "GeneralProbability",
        "Events A and B are independent with P(A)=0.5 and P(B)=0.4. P(A and B)?",
        ("0.20", "0.90", "0.10", "0.45"), 0, 0.4,
    ),
    DiagnosticQuestion(
        "gp3", "GeneralProbability",
        "A disease affects 1% of a population. A test is 99% sensitive and 99% "
        "specific. Given a positive test, P(has disease)?",
        ("0.01", "0.50", "0.99", "0.0099"), 1, 0.7,
    ),
    DiagnosticQuestion(
        "gp4", "GeneralProbability",
        "From a standard 52-card deck, P(drawing an Ace) is:",
        ("1/13", "1/4", "4/13", "1/52"), 0, 0.2,
    ),
    # Univariate Random Variables
    DiagnosticQuestion(
        "uni1", "UnivariateRV",
        "X ~ Binomial(n=10, p=0.5). What is E[X]?",
        ("2.5", "5", "10", "0.5"), 1, 0.3,
    ),
    DiagnosticQuestion(
        "uni2", "UnivariateRV",
        "X ~ Poisson(lambda=3). What is Var(X)?",
        ("3", "1.73", "9", "1.5"), 0, 0.4,
    ),
    DiagnosticQuestion(
        "uni3", "UnivariateRV",
        "X ~ Exponential with rate lambda=2. What is E[X]?",
        ("2", "0.5", "1", "4"), 1, 0.5,
    ),
    DiagnosticQuestion(
        "uni4", "UnivariateRV",
        "X ~ Uniform(0, 10). What is P(X < 3)?",
        ("0.30", "0.70", "3", "0.03"), 0, 0.3,
    ),
    # Multivariate Random Variables
    DiagnosticQuestion(
        "mv1", "MultivariateRV",
        "For any random variable X, Cov(X, X) equals:",
        ("Var(X)", "0", "1", "E[X]"), 0, 0.3,
    ),
    DiagnosticQuestion(
        "mv2", "MultivariateRV",
        "If X and Y are independent, then Cov(X, Y) is:",
        ("0", "1", "Var(X)", "-1"), 0, 0.3,
    ),
    DiagnosticQuestion(
        "mv3", "MultivariateRV",
        "X and Y are independent with Var(X)=2 and Var(Y)=3. Var(X+Y)?",
        ("5", "6", "1", "2.45"), 0, 0.5,
    ),
    DiagnosticQuestion(
        "mv4", "MultivariateRV",
        "By the Central Limit Theorem, the distribution of the sample mean of "
        "many i.i.d. variables is approximately:",
        ("Normal", "Uniform", "Poisson", "Exponential"), 0, 0.4,
    ),
)

_QUESTIONS_BY_ID = {q.id: q for q in QUESTION_BANK}
_TOPIC_NAMES = {t.key: t.name for t in exam_p.SYLLABUS}
_TOPIC_WEIGHTS = {t.key: t.weight for t in exam_p.SYLLABUS}


def get_questions(topic_keys: list[str] | None = None) -> list[DiagnosticQuestion]:
    """Return diagnostic questions, optionally filtered to certain topics."""
    if topic_keys is None:
        return list(QUESTION_BANK)
    keys = set(topic_keys)
    return [q for q in QUESTION_BANK if q.topic_key in keys]


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def score_diagnostic(responses: list[DiagnosticResponse]) -> DiagnosticResult:
    """Deterministically score diagnostic responses."""
    # Aggregate per topic.
    agg: dict[str, dict[str, float]] = {}
    total_correct = 0
    total_time = 0.0
    total_conf = 0.0

    for resp in responses:
        question = _QUESTIONS_BY_ID.get(resp.question_id)
        if question is None:
            continue
        is_correct = resp.chosen_index == question.correct_index
        bucket = agg.setdefault(
            question.topic_key,
            {"total": 0, "correct": 0, "time": 0.0, "conf": 0.0},
        )
        bucket["total"] += 1
        bucket["correct"] += 1 if is_correct else 0
        bucket["time"] += resp.time_seconds
        bucket["conf"] += resp.confidence

        total_correct += 1 if is_correct else 0
        total_time += resp.time_seconds
        total_conf += resp.confidence

    answered = sum(int(b["total"]) for b in agg.values())

    topics: list[TopicDiagnostic] = []
    for key, b in agg.items():
        topics.append(
            TopicDiagnostic(
                topic_key=key,
                topic_name=_TOPIC_NAMES.get(key, key),
                total=int(b["total"]),
                correct=int(b["correct"]),
                accuracy=round(_safe_div(b["correct"], b["total"]), 4),
                avg_time_seconds=round(_safe_div(b["time"], b["total"]), 2),
                avg_confidence=round(_safe_div(b["conf"], b["total"]), 4),
            )
        )

    overall_accuracy = round(_safe_div(total_correct, answered), 4)
    avg_confidence = round(_safe_div(total_conf, answered), 4)

    # Weakest topics first: lowest accuracy, then heaviest syllabus weight.
    weak = sorted(
        topics,
        key=lambda t: (t.accuracy, -_TOPIC_WEIGHTS.get(t.topic_key, 0.0)),
    )

    return DiagnosticResult(
        total_questions=len(QUESTION_BANK),
        answered=answered,
        overall_accuracy=overall_accuracy,
        avg_time_seconds=round(_safe_div(total_time, answered), 2),
        avg_confidence=avg_confidence,
        calibration_gap=round(avg_confidence - overall_accuracy, 4),
        topics=topics,
        weak_topic_keys=[t.topic_key for t in weak],
    )


# --- Persistence -------------------------------------------------------------


def save_diagnostic(col: Collection, result: DiagnosticResult) -> None:
    col.set_config(CONFIG_KEY, asdict(result))


def load_diagnostic(col: Collection) -> DiagnosticResult | None:
    data = col.get_config(CONFIG_KEY, None)
    if not data:
        return None
    topics = [TopicDiagnostic(**t) for t in data.get("topics", [])]
    data = {**data, "topics": topics}
    return DiagnosticResult(**data)


def has_diagnostic(col: Collection) -> bool:
    return load_diagnostic(col) is not None


def run_diagnostic(col: Collection, responses: list[DiagnosticResponse]) -> DiagnosticResult:
    """Score responses and persist the result."""
    result = score_diagnostic(responses)
    save_diagnostic(col, result)
    return result
