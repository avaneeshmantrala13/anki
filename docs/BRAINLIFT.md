# BrainLift

The "Brainlift" doc: what BrainLift is, why it exists, how it works, and the key
decisions behind it. For the system diagram and the desktop/mobile split, see
[`BRAINLIFT_ARCHITECTURE.md`](./BRAINLIFT_ARCHITECTURE.md); for how every reported
number is generated, see
[`../brainlift_eval/DATA_PROVENANCE.md`](../brainlift_eval/DATA_PROVENANCE.md).

## What it is

BrainLift is an **exam-readiness layer for SOA Exam P (Probability)** built into
Anki (desktop) and AnkiDroid (mobile). On top of Anki's spaced-repetition review
loop it adds:

1. Three **separate, deterministic** measurements — **Memory**, **Performance**,
   and **Readiness** — each a point estimate with a range.
2. Official-syllabus **topic coverage** and a **rule-based study plan**.
3. Two **opt-in AI features** — metacognitive **calibration** and cognitive-load
   **fatigue offload** — that sit on top and degrade gracefully to deterministic
   behavior when AI is off.

## Why it exists (the problem)

A raw flashcard streak tells you that you *reviewed* cards; it does **not** tell
you whether you'll **pass the exam**. Two failure modes motivate BrainLift:

- **Memory ≠ performance.** Recalling a memorized card is not the same as solving
  a novel, re-parameterized exam question. BrainLift measures both separately and
  quantifies the gap (the "paraphrase gap").
- **Miscalibration & fatigue.** Learners over-trust topics they only *feel* they
  know, and their effective learning decays within long sittings. BrainLift's two
  AI features target exactly these: calibration authority and fatigue offload.

The guiding principle is **honest, transparent numbers**: every score is
rule-derived and explainable, Readiness is **withheld** rather than guessed when
evidence is thin, and simulated/fixture data is labeled as such everywhere.

## How it works

### Deterministic core (works with AI OFF)

- **Memory** = weighted mean FSRS retrievability across reviewed topics.
- **Performance** = weighted diagnostic (transfer-question) accuracy.
- **Readiness** = `0.6·Performance + 0.4·Memory` on the 0–10 Exam-P scale, with a
  **give-up rule**: no number until ≥200 reviews, ≥50% coverage, and the
  diagnostic is taken.
- **Coverage / plan** = cards mapped to `ExamP::Topic::Subtopic` tags, aggregated
  by the shared Rust `topic_mastery` engine, ranked into a weekly study plan.

### Optional AI features (opt-in, `brainlift_ai_enabled`)

- **Calibration ("confidence authority").** Self-rate confidence on 15 cards, then
  answer 15 AI-generated *analog* MCQs (each recording its source card id + text).
  We score `accuracy = 1 − mean|confidence − performance|` and derive an
  `authority_multiplier` that scales how strongly demonstrated "knownness"
  suppresses future reviews — well-calibrated learners keep authority; poorly
  calibrated ones keep more review coverage.
- **Fatigue offload (learned model).** A small **logistic-regression** classifier
  predicts `p(drained)` from five EWMA-smoothed features (RT slowdown, accuracy
  drop, RT variability, post-error slowing, session-time position). When drained,
  the app *gradually* eases difficulty or interleaves sub-topics and shows a
  banner. Trained offline; weights ship as shared constants.

### Safety rails on the AI

- Key read **only** from `OPENAI_API_KEY`, never stored or committed.
- **Leakage gate** (regenerate-then-block): analogs that are near-verbatim to
  their source *and* resolve to the same answer are regenerated (up to 3×) and
  withheld if they still leak.
- **Prompt-injection defense**: untrusted card text is delimited and validated;
  outputs that echo the system prompt or leak the answer are rejected.
- **Graceful fallback**: offline / rate-limited / malformed → deterministic path.

## Key decisions

1. **Build inside Anki, reuse its engine.** BrainLift consumes Anki's real FSRS
   scheduler, collection, sync, and SQLite storage instead of reimplementing them.
   This gives correct scheduling and durable, syncable state for free.
2. **State lives in collection config.** All BrainLift state rides Anki's existing,
   well-tested sync path — no bespoke sync code, and it moves between desktop and
   mobile automatically.
3. **Desktop Rust, mobile Kotlin, proven equal.** The forked `TopicMastery` Rust
   RPC runs on **desktop only**; AnkiDroid links the **stock** backend and
   **reimplements the same logic in Kotlin**, with a **parity test**
   (`BrainLiftParityTest`) enforcing identical results. Shipping the forked
   backend to the phone is future work — stated plainly rather than over-claimed.
4. **Three separate measurements, not one blended score.** Memory, Performance and
   Readiness are kept distinct so the app can be honest about *what* it knows and
   refuse to project Readiness without evidence.
5. **AI is additive and optional.** The three scores must fully work with AI OFF;
   the AI toggle only *replaces* deterministic thresholds when explicitly enabled.
6. **Honesty about data.** The learned fatigue model is trained on
   research-grounded **simulated** data (no live students); analog evals default to
   a deterministic **fixture** client; the ablation is a **simulation**. All of
   this is disclosed in `DATA_PROVENANCE.md`, and null/negative results are
   reported, not hidden.

## Where to look in the code

| Area | Path |
|---|---|
| Measurements (Memory/Performance/Readiness) | `pylib/anki/brainlift/measurements.py` |
| Syllabus + topic mapping | `pylib/anki/brainlift/exam_p.py` |
| Dashboard view-model + HTML | `pylib/anki/brainlift/dashboard.py` |
| Calibration | `pylib/anki/brainlift/calibration.py` |
| Fatigue (learned model) | `pylib/anki/brainlift/fatigue.py` |
| AI provider + leakage/injection guards | `pylib/anki/brainlift/ai.py` |
| Eval / ablation / benchmark / crash harness | `brainlift_eval/` |
| AI feature spec (single source of truth) | `BRAINLIFT_AI_SPEC.md` |
| Mobile (Kotlin re-impl) | `Anki-Android/AnkiDroid/src/main/java/com/ichi2/anki/brainlift/` |
