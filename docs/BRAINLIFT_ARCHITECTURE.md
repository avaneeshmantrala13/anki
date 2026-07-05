# BrainLift architecture

> Naming note: this file is intentionally `BRAINLIFT_ARCHITECTURE.md` rather than
> `ARCHITECTURE.md`, because Anki already ships `docs/architecture.md` and the
> repo lives on case-insensitive filesystems (macOS/Windows) where `ARCHITECTURE`
> and `architecture` collide. This is the BrainLift-specific companion to Anki's
> upstream `docs/architecture.md`.

BrainLift is an Exam-P study layer added to Anki (desktop) and AnkiDroid
(mobile) **from the inside**, reusing Anki's real engine rather than
reimplementing it. This document explains how the pieces fit together and, in
particular, the **honest** split between what runs where.

## 1. High-level layout

```
                         ┌──────────────────────────────────────────┐
                         │            Shared Anki core                │
                         │  rslib (Rust): collection, FSRS scheduler, │
                         │  sync, DB (SQLite atomic-commit storage)   │
                         └───────────────┬───────────────┬───────────┘
                                         │               │
                 desktop (this repo)     │               │   mobile (AnkiDroid fork)
        ┌────────────────────────────────▼──┐        ┌───▼──────────────────────────────┐
        │ pylib/anki/brainlift/ (Python)     │        │ .../com/ichi2/anki/brainlift/     │
        │  measurements, exam_p, dashboard,  │        │  BrainLiftEngine.kt (Kotlin       │
        │  calibration, fatigue, ai, planner │        │  re-impl of the SAME formulas),   │
        │                                    │        │  BrainLiftAi/Calibration/Fatigue  │
        │  + forked Rust TopicMastery RPC    │        │  (links the STOCK Anki backend;   │
        │    (StatsService.TopicMastery)     │        │   no forked Rust on device — yet) │
        └────────────────────────────────────┘        └───────────────────────────────────┘
```

Both platforms sit on top of the **same shared Anki core** — the Rust `rslib`
library that implements the collection model, the **FSRS** scheduler, **sync**,
and the SQLite storage layer. BrainLift does not fork any of that; it consumes it.

## 2. The desktop Rust change vs the phone — the honest split

This is the part most easily over-claimed, so it is stated precisely:

- **Desktop** adds a forked **Rust RPC**, `StatsService.TopicMastery` (called from
  Python via `Collection.topic_mastery`), which aggregates per-topic card counts,
  reviewed/mastered counts, total reviews, and average FSRS retrievability across
  a set of tag searches. `pylib/anki/brainlift/exam_p.py` defines the syllabus and
  interprets this RPC's results.
- **Mobile** does **NOT** run that forked Rust code. The AnkiDroid fork links the
  **stock, published Anki backend** and **reimplements the identical aggregation
  logic in Kotlin** (`BrainLiftEngine.kt`) — same formulas, thresholds, and config
  shapes — so results match the desktop for the same collection.
- Building the forked backend into AnkiDroid so it can call `TopicMastery`
  directly is **documented future work**, not something that ships today.

**Parity is verified by tests**, not asserted: the Kotlin implementation is checked
against the desktop numbers by `BrainLiftParityTest` (including the learned fatigue
model's exact probabilities and decisions), and the Python side is covered by the
`pylib/tests/test_brainlift_*.py` suite. The shared numeric constants (e.g. the
fatigue model weights) are copied verbatim so `sigmoid(bias + w·features)`
evaluates byte-identically on both platforms.

Bottom line: **the forked Rust TopicMastery RPC runs on desktop only. The phone
gets the same behavior through a Kotlin reimplementation over the shared Anki core,
proven equivalent by a parity test.**

## 3. The three deterministic measurements

`pylib/anki/brainlift/measurements.py` computes three **separate** scores, each a
point estimate plus a range, with an explicit give-up rule:

- **Memory** — weighted mean FSRS retrievability over reviewed topics.
- **Performance** — weighted diagnostic (transfer-question) accuracy.
- **Readiness** — a transparent blend (`0.6·performance + 0.4·memory`) on the
  Exam-P 0–10 scale, **withheld** until enough evidence exists (≥200 reviews,
  ≥50% coverage, diagnostic taken). No ML; every number is rule-derived.

`exam_p.py` maps cards → syllabus topics via `ExamP::<Topic>::<Subtopic>` tags and
calls the shared Rust `topic_mastery` engine; `dashboard.py` aggregates everything
into one view-model + self-contained HTML.

## 4. The optional AI provider layer

Two AI features sit on top of the deterministic core behind a master toggle
(`brainlift_ai_enabled`, default OFF). With AI OFF, all three scores and both
features still function via deterministic fallbacks.

- **AI provider (`ai.py`)** — a small client abstraction with two
  implementations: `RealOpenAIClient` (reads the key **only** from
  `OPENAI_API_KEY`, never stored/committed) and `DeterministicAnalogClient`
  (offline fixtures). All generated analogs pass a **leakage gate**
  (regenerate-then-block) and prompt-injection validation before being served.
- **Calibration ("confidence authority", `calibration.py`)** — self-rated
  confidence vs performance on AI analog MCQs → a `authority_multiplier` that
  scales how strongly demonstrated "knownness" suppresses future reviews.
- **Fatigue offload (`fatigue.py`)** — a small **learned logistic-regression**
  classifier predicts `p(drained)` from five EWMA-smoothed features; trained
  offline on research-grounded simulated data, weights ship as shared constants.

The AI layer degrades gracefully (offline / rate-limited / bad output → fixture
fallback), never crashes, and never blocks scoring.

## 5. State, config and sync

BrainLift stores all of its state in the **collection config** (calibration
result + multiplier, fatigue session state, onboarding profile, test-mode flags).
Because config lives in the collection, it **rides Anki's existing sync** — the
same well-tested path used for decks and cards — so state moves between desktop and
mobile with no bespoke sync code. Durability is provided by SQLite's atomic-commit
journal (see the crash test below).

## 6. Verification, benchmarks & durability

- **Correctness / AI evals**: `brainlift_eval/` (held-out analog eval, gold set,
  baseline comparison, leakage + prompt-injection checks, paraphrase gap, learned
  fatigue-model held-out eval). Data provenance for all of these is documented in
  [`brainlift_eval/DATA_PROVENANCE.md`](../brainlift_eval/DATA_PROVENANCE.md).
- **Ablation**: `brainlift_eval/ablation.py` — a pre-registered, seeded 3-build
  simulation (full app vs feature-ablated vs stock Anki) reporting the effect of
  the two AI features with confidence intervals and honest null reporting.
- **Benchmarks (50k cards)**: `brainlift_eval/bench.py` measures p50/p95/worst for
  the hot actions vs their budgets. Run it with:

  ```bash
  cd anki && out/pyenv/bin/python brainlift_eval/bench.py
  ```

  See [`brainlift_eval/BENCHMARKS.md`](../brainlift_eval/BENCHMARKS.md) for the
  action/budget table and a representative result.
- **Crash / durability**: `brainlift_eval/crash_test.py` hard-kills the app
  mid-review ~20x and asserts zero corruption on reopen (SQLite atomic commit).

  ```bash
  cd anki && out/pyenv/bin/python brainlift_eval/crash_test.py
  ```

  **Android equivalent**: drive a review on a device/emulator, then force an
  unclean termination with `adb shell am force-stop com.ichi2.anki` (or
  `adb shell kill -9 <pid>`) mid-review, relaunch, and run
  **Tools → Check Database**. The same SQLite atomic-commit guarantee applies, so
  the expectation is likewise zero corruption.
