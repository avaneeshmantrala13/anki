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
- **Shared logic, honestly:** desktop and mobile share Anki's real Rust FSRS
  scheduler and the collection/sync layer. The new `TopicMastery` Rust RPC runs
  on **desktop**; the **AnkiDroid** fork links the stock Anki backend and
  reimplements the same deterministic coverage/measurement aggregation in Kotlin
  (identical formulas, thresholds, and config shapes), so results match.

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
