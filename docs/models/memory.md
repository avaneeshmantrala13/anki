# Memory model

**What it predicts.** The chance the student will correctly recall a fact they
have *already studied*, right now. It is a memory-retention estimate, not an exam
prediction.

**Inputs.**
- Per-topic **FSRS retrievability** for every reviewed card (from Anki's shipped
  FSRS memory state), aggregated by the Rust `topic_mastery` engine.
- Per-topic **SOA Exam P syllabus weight** (the official weight midpoints).
- The number of **reviewed cards** and the **studied coverage %** of the
  syllabus.

**Method / formula.** A syllabus-weighted mean of FSRS retrievability across
topics that have at least one reviewed card:

```
point = clamp( Σ_topic ( weight · avg_retrievability ) / Σ_topic weight )
```

The underlying FSRS-5 recall curve (used by the Rust engine and validated by the
calibration eval) is:

```
R(t) = (1 + FACTOR · t / S) ^ DECAY,   DECAY = -0.5,  FACTOR = 19/81
```

**Range.** A likely band `point ± margin`, clamped to `[0, 1]`, where
`margin = min(0.25, 0.5 / sqrt(reviewed_cards + 1))` — the band shrinks as more
reviews accumulate. Reported as a percentage (e.g. "78%, likely 70–86%").

**How-sure indicator (confidence).** Reported as `low` / `medium` / `high`:
- `high` — reviewed_cards ≥ 200 **and** studied coverage ≥ 80%
- `medium` — reviewed_cards ≥ 50 **and** studied coverage ≥ 50%
- `low` — otherwise

The score also exposes: the coverage % it is based on, a last-updated timestamp,
and plain-language reasons (e.g. "FSRS recall over 250 reviewed cards", "85% of
the syllabus studied"). These thresholds are identical on desktop
(`pylib/anki/brainlift/measurements.py`) and Android (`BrainLiftEngine.kt`), and
are locked by parity tests.

**Give-up / abstention rule.** If **no** cards have been reviewed (or the total
topic weight is zero), Memory is marked **unavailable** and the UI shows
"Not enough data — study some cards so FSRS can estimate recall" instead of a
fabricated number.

**Calibration.** `brainlift_eval/memory_calibration_eval.py` checks that the
FSRS predicted recall is actually calibrated against outcomes, reporting a Brier
score, log-loss, and a 10-bin reliability diagram (PASS cutoff: Brier ≤ 0.25).
The review outcomes there are **simulated** (FSRS-grounded) and clearly labelled
as such, because no large real review log ships with the app.
