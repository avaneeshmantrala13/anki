<!-- BEGIN BrainLift fork additions -->
## BrainLift (Exam P) — fork additions

**BrainLift** is a deterministic (no AI) exam-prep layer added to Anki *from the
inside*. It keeps Anki's FSRS scheduler, collection, review loop, and sync, and
adds an exam readiness model: three **separate** measurements — Memory (FSRS
recall), Performance (a fixed author-written diagnostic), and Readiness (a
transparent blend with an explicit give-up rule) — plus official-syllabus topic
coverage and a rule-based study plan. Every number comes from transparent rules.

- **Chosen exam:** **SOA Exam P** (Probability). Readiness is reported on the
  conventional 0–10 scale (6 = pass).
- **Shared logic, honestly (what runs where):** desktop and mobile share Anki's
  real core — the Rust `rslib` collection, the **FSRS** scheduler, **sync**, and
  SQLite storage. The forked **`TopicMastery` Rust RPC runs on the DESKTOP only.**
  It does **not** ship to the phone: the **AnkiDroid** fork links the *stock,
  published* Anki backend and **reimplements the identical coverage/measurement
  aggregation in Kotlin** (`BrainLiftEngine.kt`; same formulas, thresholds, and
  config shapes), so results match desktop. Equivalence is **verified by a parity
  test** (`BrainLiftParityTest`), not assumed. Compiling the forked backend into
  AnkiDroid so it can call `TopicMastery` directly is documented **future work**.
  See [`docs/BRAINLIFT_ARCHITECTURE.md`](./docs/BRAINLIFT_ARCHITECTURE.md).

### Optional AI features (opt-in; the three scores work with AI OFF)

Two AI features sit *on top of* the deterministic core. They are behind a master
toggle (`brainlift_ai_enabled`, default OFF). **With AI off the app still fully
produces Memory / Performance / Readiness and both features function** via a
deterministic fallback — a hard requirement. Formulas are specified once in
`BRAINLIFT_AI_SPEC.md` and mirrored identically in Python (desktop) and Kotlin
(mobile); parity is enforced by tests on both platforms.

1. **Metacognitive calibration ("confidence authority").** The learner self-rates
   confidence on 15 Exam P cards, then answers 15 AI-generated *analog* questions
   (reworded / re-parameterized versions of each card). What AI does: generate the
   analog MCQ via OpenAI (`gpt-4o-mini` by default, configurable); **every
   generated item records its source card id + source text** (named-source
   traceability). We score deviation = |confidence − performance|, report a
   headline calibration accuracy = 1 − mean deviation (plus a Goodman-Kruskal
   gamma resolution figure), and derive a **confidence-authority multiplier** that
   scales how strongly demonstrated "knownness" suppresses future reviews
   (well-calibrated learners keep authority; poorly-calibrated learners keep more
   review coverage). The multiplier persists in synced config and feeds the
   scheduler on both platforms.
2. **Cognitive-load / fatigue offload (a LEARNED model).** A small **logistic
   regression** decides *when* the learner is cognitively drained, from five
   research-grounded features (EWMA-smoothed normalized response-time slowdown,
   accuracy drop, RT variability, post-error slowing, and session-time position).
   It is trained **offline in Python** and its **weights ship as shared constants**
   so desktop and mobile run **byte-identical** inference (`p = sigmoid(bias +
   w·features)`; see `BRAINLIFT_AI_SPEC.md §5.5`). Honest caveat: with no live
   student data the model is trained on a **research-grounded SIMULATED** dataset
   calibrated to three peer-reviewed papers (Fortenbaugh 2015, Hanzal 2024,
   Hassanzadeh-Behbaha 2018 — the model's *named source*); per-user online
   adaptation on real streams is future work. The learned probability replaces
   the old fixed drain threshold; when drained we *gradually* ease difficulty or
   interleave the three sub-topics and always show a visible banner ("Cognitive
   offload — easing difficulty" / "…adding variety"). The model runs only when the
   AI toggle is ON (local weights, no network); with it **OFF** — or on any model
   issue — the engine falls back to the original deterministic drain heuristic, so
   the three scores always compute. A TEST MODE flag fires interventions
   immediately; in PROD they wait ~1–2 h unless the learner is struggling severely.
   Offline eval (`brainlift_eval/fatigue_model_eval.py`): held-out accuracy 0.9067
   / AUC 0.9706 / log-loss 0.2914 vs a pre-declared cutoff (acc ≥ 0.80, AUC ≥
   0.85), beating the previous fixed-threshold heuristic (0.5283 / 0.9242) with a
   clean train/test separation check.

The key is read **only** from the `OPENAI_API_KEY` environment variable (never
stored or committed). The OpenAI client degrades gracefully (offline /
rate-limited / bad output → deterministic fallback, never crashes, never blocks
scoring). Every generated analog also passes through a **leakage gate**
(regenerate-then-block): if an analog is near-verbatim to its source AND resolves
to the same answer it is regenerated with a stronger re-parameterize instruction
(up to `MAX_REGEN=3`), and blocked/withheld if it still leaks, so the served set
is guaranteed clean. An eval/proof harness lives in `brainlift_eval/` (held-out
accuracy vs a pre-declared cutoff, gold-set counts, baseline comparison, leakage
check on the served/post-gate set, paraphrase gap) and runs offline with no key.

### Attribution

- Built on **Anki** (AGPL-3.0-or-later).
- The mobile companion is built on **AnkiDroid** (GPL-3.0-or-later).
- Default bundled study content: **Society of Actuaries (SOA) Exam P Sample
  Questions & Solutions**, freely published by the SOA for candidates and
  reproduced for personal study (© Society of Actuaries). Classification into
  topics uses deterministic keyword rules only — no content is AI-generated.
  - Questions: https://www.soa.org/globalassets/assets/files/edu/edu-exam-p-sample-quest.pdf
  - Solutions: https://www.soa.org/globalassets/assets/files/edu/edu-exam-p-sample-sol.pdf

### Build & run

- **Desktop (this repo):** `./run`
- **Mobile (AnkiDroid fork):** `./gradlew assemblePlayDebug`

Upstream Anki's original README follows below. License files are unchanged.

<!-- END BrainLift fork additions -->

# Anki

[![Build Status](https://github.com/ankitects/anki/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitects/anki/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-dev--docs.ankiweb.net-blue)](https://dev-docs.ankiweb.net)

This repo contains the source code for the computer version of
[Anki](https://apps.ankiweb.net).

## About

Anki is a spaced repetition program. Please see the [website](https://apps.ankiweb.net) to learn more.

## Getting Started

### Contributing

Want to contribute to Anki? Check out the [Contribution Guidelines](./docs/contributing.md).

For more information on building and developing, please see [Development](./docs/development.md).

#### Contributors

The following people have contributed to Anki: [CONTRIBUTORS](./CONTRIBUTORS)

### Anki Betas

If you'd like to try development builds of Anki but don't feel comfortable
building the code, please see [Anki betas](https://betas.ankiweb.net/).

## License

Anki's license: [LICENSE](./LICENSE)
