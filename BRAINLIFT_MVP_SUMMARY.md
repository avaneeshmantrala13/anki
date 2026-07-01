# BrainLift for Anki — MVP Implementation Summary

**Chosen exam:** SOA **Exam P** (Probability) — readiness reported on the conventional **0–10 scale** (6 = pass).
**Built on:** a fork of Anki at `SpeedRun/anki/` (branch `brainlift-mvp`) plus a fork of **AnkiDroid** for mobile.
**AI used:** **None.** Every recommendation, score, plan, and bundled study card is produced (or sourced) by deterministic, transparent rules. The app is fully functional with zero AI services.

**Content source:** the study content bundled with the app is the official **SOA Exam P Sample Questions & Solutions**, freely published by the **Society of Actuaries** for candidates. Questions/solutions are reproduced for personal study; © Society of Actuaries. No content is AI-generated; classification into topics uses deterministic keyword rules only.

---

## What BrainLift adds to Anki

BrainLift extends Anki *from the inside* (no wrapper, no second app, no second scheduler). It keeps Anki's FSRS engine, collection, review loop, and sync, and adds an Exam P measurement + planning layer that answers three **separate** questions:

| Question | Measure | Source |
|---|---|---|
| Can the student **recall** a studied fact? | **Memory** | Anki FSRS retrievability (shared Rust engine) |
| Can they answer a **new** exam-style question? | **Performance** | Deterministic diagnostic (transfer questions) |
| What would they **score today**, and how sure are we? | **Readiness** | Deterministic blend + give-up rule |

The three are never collapsed into one blended number.

---

## Core engine (shared, ships in the `anki` wheel — desktop **and** mobile)

- **Rust core change — Topic Mastery & Coverage API.** New `StatsService.TopicMastery` proto RPC + Rust implementation (`rslib/src/stats/topic_mastery.rs`) that aggregates, per topic search, total/reviewed/mastered cards, total reviews, and average FSRS retrievability. Bound to Python as `Collection.topic_mastery(...)`. Because it lives in the shared engine, desktop and mobile get identical numbers.
- **Exam P topic model** (`pylib/anki/brainlift/exam_p.py`): the official syllabus as a typed hierarchy (3 main topics, 19 subtopics) with SOA weight midpoints (General Probability 13.5%, Univariate RV 43.5%, Multivariate RV 43.5%). Card→topic mapping is by Anki-native nested tags `ExamP::<Topic>::<Subtopic>`. `coverage_report()` classifies each topic **Not Started / In Progress / Covered / Mastered**.
- **Deterministic onboarding / diagnostic / planner / measurements / dashboard** (`pylib/anki/brainlift/*.py`): named thresholds, human-readable reasons, and an explicit **give-up rule** (readiness is withheld unless ≥200 graded reviews AND ≥50% coverage AND a completed diagnostic). All state is persisted in the collection config, so it rides Anki's existing sync and survives restarts.

---

## NEW: Default Exam P content (deterministic, no AI)

New users used to land on an **empty** collection, so coverage/readiness had nothing to measure. BrainLift now ships the official SOA Exam P sample questions inside the app and seeds them automatically for a first-time, empty collection.

- **Bundled data module** `pylib/anki/brainlift/examp_seed.py` — a pure-Python `SEED_CARDS: list[dict]` (each `{"front", "back", "tags"}`) generated from the SAME sourced SOA content used for the validated `.apkg`. A `.py` module is always packaged, so the content is guaranteed to ship in the wheel and installer (no binary-data packaging risk). A short SOA attribution string is in the module docstring **and** on every card back.
- **Seeder** `pylib/anki/brainlift/default_content.py` → `maybe_seed_default_deck(col) -> int`:
  - Returns `0` (does nothing) if the config flag `brainlift_seeded_default` is already set, **or** if the collection already contains any cards (`select count() from cards`) — i.e. it never touches a user's own content.
  - Otherwise creates the deck **"Exam P — Sample Questions"**, ensures a **Basic** notetype, adds all `SEED_CARDS` as notes with their `ExamP::*` tags, sets `brainlift_seeded_default = True`, and returns the number of notes added.
  - Idempotent and wrapped in `try/except` so it can never crash startup.
- **Desktop trigger** (`qt/aqt/brainlift/__init__.py`): on `gui_hooks.profile_did_open`, the deferred landing now calls `maybe_seed_default_deck(mw.col)` (via `_seed_and_land`) once, then `col.reset()` so coverage/landing immediately reflect the seeded cards.
- **Mobile:** no Android code change is needed — the seeded deck, cards, and tags reach mobile through normal Anki sync.

**Seed contents (660 cards total):**

| Exam P main topic | Cards |
|---|---|
| General Probability | 310 |
| Univariate Random Variables | 304 |
| Multivariate Random Variables | 46 |
| **Total** | **660** |

Regenerate the module from the validated deck with:
```bash
python anki-analysis/build_examp_deck.py --emit-seed
```

---

## Mobile: AnkiDroid BrainLift implementation

- The BrainLift logic that matters for numbers lives in the **shared Rust engine** (TopicMastery) and shared Python layer, so AnkiDroid consumes the same coverage/mastery computations rather than reimplementing them.
- The AnkiDroid fork was built and installed on an Android emulator; the BrainLift Exam P coverage view renders on device.
- Study content and BrainLift state (onboarding, diagnostic, coverage) arrive on mobile via Anki sync, so no separate content bundling is required on Android.

## Desktop ↔ mobile sync validation (today)

Validated end-to-end today: onboarding profile, seeded/authored **cards**, and per-topic **coverage** created on one client sync to the other. Sync-direction rule of thumb during testing: make changes on one side, sync **up**, then sync **down** on the other side before comparing, to avoid one-way-merge surprises. Because all BrainLift state is stored in the collection config and standard notes/cards, it uses Anki's existing sync with no new transport.

## Desktop installer (.dmg)

The production macOS installer is produced with the repo's Briefcase-based tooling (`./tools/build-installer` / `RELEASE=2 ./ninja installer`). Because the seed content is a plain `.py` module inside the `anki` wheel, it is included in the installer automatically.

---

## Build & test verification (this change)

- **pylib tests:** `36 passed` — all `pylib/tests/test_brainlift_*.py`, including the new `test_brainlift_default_content.py` (seeds >0 on empty col, tags cover all three Exam P main topics, second run adds 0 / idempotent, and seeds nothing when the collection already has a card).
- **Wheel build:** `./ninja wheels` succeeds; the built `anki-26.5-*.whl` contains `anki/brainlift/examp_seed.py`, `default_content.py`, and `exam_p.py`. Loading `SEED_CARDS` straight from the wheel yields **660** cards (310 / 304 / 46).

See `anki/anki-brainlift-TESTING.md` for exact reproduction commands.

---

## Files added / changed in this batch

**New (ships in the `anki` wheel):**
- `pylib/anki/brainlift/examp_seed.py` — generated SOA Exam P seed data (660 cards).
- `pylib/anki/brainlift/default_content.py` — `maybe_seed_default_deck()` seeder.
- `pylib/tests/test_brainlift_default_content.py` — seeder tests.

**Modified (additive only):**
- `qt/aqt/brainlift/__init__.py` — seed default content once on `profile_did_open` (`_seed_and_land`), then land on the BrainLift home.
- `anki-analysis/build_examp_deck.py` — added `--emit-seed` to emit the pure-Python seed module from the validated `.apkg` (same sourced SOA content).

**Docs:** this summary and `anki/anki-brainlift-TESTING.md`.

No existing Anki behaviour was removed; the feature is strictly additive and deterministic.
