# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The official SOA Exam P syllabus model and card->topic mapping.

Everything here is deterministic and contains no AI. Cards are mapped to Exam P
topics by **tags** using the hierarchy ``ExamP::<Topic>::<Subtopic>`` (Anki's
native ``::`` tag nesting). The actual per-topic aggregation is performed by the
shared Rust engine via ``Collection.topic_mastery`` (see the
``StatsService.TopicMastery`` backend RPC); this module only defines the
syllabus and interprets the results.

Topic weights are the midpoints of the official SOA Exam P weight ranges:

* General Probability            10-17%  -> 13.5
* Univariate Random Variables    40-47%  -> 43.5
* Multivariate Random Variables  40-47%  -> 43.5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki.collection import Collection

# Root tag namespace for all Exam P topic tags.
TAG_ROOT = "ExamP"

# Topic-status thresholds (fractions of a topic's cards). Deterministic and
# intentionally explicit so the give-up / readiness logic can cite them.
COVERED_FRACTION = 0.8  # >= this fraction of cards reviewed -> "Covered"
MASTERED_FRACTION = 0.8  # >= this fraction of cards mastered -> "Mastered"

# Topic status values.
NOT_STARTED = "Not Started"
IN_PROGRESS = "In Progress"
COVERED = "Covered"
MASTERED = "Mastered"


@dataclass(frozen=True)
class Subtopic:
    """A leaf learning outcome within a main Exam P topic."""

    key: str
    name: str

    def tag(self, parent_key: str) -> str:
        return f"{TAG_ROOT}::{parent_key}::{self.key}"


@dataclass(frozen=True)
class Topic:
    """A main Exam P topic with its official syllabus weight."""

    key: str
    name: str
    weight: float
    subtopics: tuple[Subtopic, ...] = field(default_factory=tuple)

    @property
    def tag(self) -> str:
        return f"{TAG_ROOT}::{self.key}"

    @property
    def search(self) -> str:
        """Anki search matching cards tagged at this topic OR any descendant."""
        return f'("tag:{self.tag}" OR "tag:{self.tag}::*")'


# --- The official Exam P syllabus -------------------------------------------

SYLLABUS: tuple[Topic, ...] = (
    Topic(
        key="GeneralProbability",
        name="General Probability",
        weight=13.5,
        subtopics=(
            Subtopic("SampleSpacesEvents", "Sample spaces and events"),
            Subtopic("Combinatorics", "Combinatorial probability"),
            Subtopic("Independence", "Independence and mutually exclusive events"),
            Subtopic("ConditionalProbability", "Conditional probability"),
            Subtopic("BayesTheorem", "Bayes' Theorem and the Law of Total Probability"),
            Subtopic("RandomVariablesIntro", "Random variables (introduction)"),
        ),
    ),
    Topic(
        key="UnivariateRV",
        name="Univariate Random Variables",
        weight=43.5,
        subtopics=(
            Subtopic("DiscreteDistributions", "Discrete distributions (binomial, Poisson, geometric, ...)"),
            Subtopic("ContinuousDistributions", "Continuous distributions (uniform, exponential, gamma, normal)"),
            Subtopic("ExpectationVariance", "Expectation, variance, and moments"),
            Subtopic("MomentGeneratingFunctions", "Moment generating functions"),
            Subtopic("Transformations", "Transformations of a random variable"),
            Subtopic("PercentilesMeasures", "Percentiles, median, and mode"),
        ),
    ),
    Topic(
        key="MultivariateRV",
        name="Multivariate Random Variables",
        weight=43.5,
        subtopics=(
            Subtopic("JointDistributions", "Joint distributions"),
            Subtopic("MarginalConditional", "Marginal and conditional distributions"),
            Subtopic("CovarianceCorrelation", "Covariance and correlation"),
            Subtopic("ConditionalExpectation", "Conditional expectation and variance"),
            Subtopic("SumsAndCLT", "Sums of random variables and the Central Limit Theorem"),
            Subtopic("MultivariateTransformations", "Transformations of multiple random variables"),
            Subtopic("BivariateNormal", "Bivariate normal distribution"),
        ),
    ),
)


# --- Result types ------------------------------------------------------------


@dataclass
class TopicReport:
    key: str
    name: str
    weight: float
    total_cards: int
    reviewed_cards: int
    mastered_cards: int
    total_reviews: int
    average_retrievability: float
    covered: bool
    status: str

    @property
    def mastered_fraction(self) -> float:
        return self.mastered_cards / self.total_cards if self.total_cards else 0.0

    @property
    def reviewed_fraction(self) -> float:
        return self.reviewed_cards / self.total_cards if self.total_cards else 0.0


@dataclass
class CoverageReport:
    topics: list[TopicReport]
    # Weighted % of the syllabus that has at least one card in the deck.
    coverage_percent: float
    # Weighted % of the syllabus that has actually been studied.
    studied_coverage_percent: float
    # Weighted % of the syllabus considered mastered.
    mastered_percent: float

    def topic(self, key: str) -> TopicReport | None:
        return next((t for t in self.topics if t.key == key), None)

    def weak_topics(self, limit: int | None = None) -> list[TopicReport]:
        """Topics that have cards, ordered weakest-first.

        Weakness ranks not-started/in-progress topics above mastered ones, then
        by mastered fraction, then by syllabus weight (heavier = more urgent).
        """
        ranked = sorted(
            (t for t in self.topics if t.total_cards > 0),
            key=lambda t: (t.mastered_fraction, -t.weight),
        )
        return ranked[:limit] if limit is not None else ranked


# --- Mapping helpers ---------------------------------------------------------


def main_topic_searches() -> list[tuple[str, str]]:
    """(name, search) pairs for the main syllabus topics."""
    return [(t.name, t.search) for t in SYLLABUS]


def subtopic_searches() -> list[tuple[str, str]]:
    """(name, search) pairs for every subtopic across the syllabus."""
    pairs: list[tuple[str, str]] = []
    for topic in SYLLABUS:
        for sub in topic.subtopics:
            tag = sub.tag(topic.key)
            pairs.append((f"{topic.name} / {sub.name}", f'"tag:{tag}"'))
    return pairs


def classify_status(total_cards: int, reviewed_cards: int, mastered_cards: int) -> str:
    """Deterministically classify a topic's progress."""
    if total_cards == 0 or reviewed_cards == 0:
        return NOT_STARTED
    if mastered_cards / total_cards >= MASTERED_FRACTION:
        return MASTERED
    if reviewed_cards / total_cards >= COVERED_FRACTION:
        return COVERED
    return IN_PROGRESS


# --- Public entry point ------------------------------------------------------


def coverage_report(col: Collection, mastered_threshold: float = 0.0) -> CoverageReport:
    """Compute the Exam P coverage/mastery report for the given collection.

    Calls the shared Rust ``topic_mastery`` engine once for all main topics,
    classifies each topic's status, and aggregates weighted coverage. No AI.
    """
    response = col.topic_mastery(main_topic_searches(), mastered_threshold)
    by_name = {t.name: t for t in response.topics}

    reports: list[TopicReport] = []
    for topic in SYLLABUS:
        stats = by_name.get(topic.name)
        total = stats.total_cards if stats else 0
        reviewed = stats.reviewed_cards if stats else 0
        mastered = stats.mastered_cards if stats else 0
        reports.append(
            TopicReport(
                key=topic.key,
                name=topic.name,
                weight=topic.weight,
                total_cards=total,
                reviewed_cards=reviewed,
                mastered_cards=mastered,
                total_reviews=stats.total_reviews if stats else 0,
                average_retrievability=stats.average_retrievability if stats else 0.0,
                covered=total > 0,
                status=classify_status(total, reviewed, mastered),
            )
        )

    total_weight = sum(t.weight for t in SYLLABUS) or 1.0
    coverage = sum(r.weight for r in reports if r.total_cards > 0)
    studied = sum(r.weight * r.reviewed_fraction for r in reports)
    mastered = sum(r.weight * r.mastered_fraction for r in reports)

    return CoverageReport(
        topics=reports,
        coverage_percent=coverage / total_weight * 100.0,
        studied_coverage_percent=studied / total_weight * 100.0,
        mastered_percent=mastered / total_weight * 100.0,
    )
