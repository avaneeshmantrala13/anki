# Performance model

**What it predicts.** The chance the student answers a *new*, exam-style
(transfer) question correctly — i.e. applied problem-solving, not raw recall of a
studied card.

**Inputs.**
- The student's responses to the deterministic **diagnostic question bank**
  (author-written Exam P multiple-choice questions with known answers).
- Per-topic **accuracy** on the diagnostic.
- Per-topic **SOA Exam P syllabus weight**.
- The number of **questions answered** (out of the bank).

**Method / formula.** A syllabus-weighted mean of per-topic diagnostic accuracy:

```
point = clamp( Σ_topic ( weight · topic_accuracy ) / Σ_topic weight )
```

(If no topic weights match, it falls back to the overall diagnostic accuracy.)

**Held-out evaluation.** `brainlift_eval/performance_holdout_eval.py` goes beyond
this direct measurement: it fits a logistic predictor on a *fit* set of
exam-style questions and reports **held-out accuracy** on a disjoint set, versus
a majority-class **baseline** (PASS: accuracy ≥ 0.65 and beats baseline by
≥ 0.05). The question outcomes are **simulated** and clearly labelled, since no
large corpus of real students answering the bank exists yet.

**Range.** A likely band `point ± margin`, clamped to `[0, 1]`, with
`margin = min(0.25, 0.5 / sqrt(answered + 1))` — tighter as more questions are
answered. Reported as a percentage.

**How-sure indicator (confidence).** Reported as `low` / `medium` / `high`:
- `high` — answered ≥ 12 (the full 12-question bank)
- `medium` — answered ≥ 6
- `low` — otherwise

The score also exposes: coverage % of the question bank answered, a last-updated
timestamp, and reasons (e.g. "Transfer accuracy over 12 diagnostic questions",
"12 of 12 question bank answered (100%)"). These thresholds are identical on
desktop (`measurements.py`) and Android (`BrainLiftEngine.kt`) and are locked by
parity tests.

**Give-up / abstention rule.** If the diagnostic has **not** been taken (zero
questions answered), Performance is marked **unavailable** and the UI shows
"Not enough data — take the diagnostic to measure performance on new questions"
rather than inventing a number.
