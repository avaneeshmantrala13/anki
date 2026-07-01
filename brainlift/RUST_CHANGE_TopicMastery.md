# BrainLift Rust Engine Change — Topic Mastery & Coverage API

Satisfies the SpeedRunner "real Rust change" requirement and the PRD's recommended
Topic Mastery backend (Implementation Guide, Phase 3).

## What it does

Adds one read-only backend RPC, `StatsService.TopicMastery`, that takes a list of
topics — each identified by an Anki **search string** — and returns deterministic
per-topic aggregates:

| Field | Meaning |
|---|---|
| `total_cards` | cards matching the topic's search |
| `reviewed_cards` | cards studied at least once (`reps > 0`) |
| `mastered_cards` | cards whose current FSRS retrievability ≥ threshold |
| `total_reviews` | sum of reps across the topic's cards |
| `average_retrievability` | mean current retrievability over cards that have an FSRS memory state |
| `covered` | whether the topic has any cards (coverage signal) |

The mastery threshold is a request parameter (defaults to `0.9`). The engine stays
generic: it has **no** hard-coded Exam P syllabus — the topic→search mapping lives
in the client (Step 2). Contains **no AI**; every number comes from existing review
history and FSRS memory state.

## Why this belongs in Rust, not Python

- **Single shared engine.** rslib is the one backend used by desktop *and* AnkiDroid.
  Implementing it here means the same aggregation ships to mobile for free; doing it
  in Python would have to be re-implemented for Android (violates "one engine").
- **Reuses core internals.** It calls the existing `search_cards_into_table` +
  `all_searched_cards` path and the same FSRS `current_retrievability_seconds` used by
  the stats graphs — the canonical, correct implementations, not a reimplementation.
- **Performance.** Per-topic aggregation over large decks (the 50k-card target) is a
  tight loop over card rows; native Rust avoids per-card Python/FFI overhead and powers
  the dashboard within the speed budget.
- **Correctness/consistency.** Retrievability math matches Anki's own stats exactly,
  so BrainLift's "memory" numbers agree with Anki's graphs.

## Safety: undo & corruption

The RPC is **read-only**. It performs searches and reads card rows; it makes **no
writes** to the collection. The only side effect is a temporary search table created
and dropped by `search_cards_into_table`'s guard (the same mechanism the stats graphs
use), which is not part of collection data or the undo history. Therefore undo is
unaffected and there is no corruption risk. (Verified: full pylib suite — 122 tests —
passes unchanged.)

## Files touched

New files (BrainLift-owned, low merge risk):
- `rslib/src/stats/topic_mastery.rs` — implementation + 3 Rust unit tests.

Edited upstream files (small, additive, append-only — low merge risk):
- `proto/anki/stats.proto` — appended `TopicMastery` rpc to `StatsService` (kept at end
  so method indices of existing RPCs are unchanged) + 4 new messages.
- `rslib/src/stats/mod.rs` — `mod topic_mastery;`.
- `rslib/src/stats/service.rs` — added the `topic_mastery` trait method (delegates to
  `compute_topic_mastery`).
- `pylib/anki/collection.py` — added `Collection.topic_mastery(...)` wrapper.
- `pylib/tests/test_stats.py` — added `test_topic_mastery` integration test.

Auto-generated (not hand-edited): prost Rust types, `pylib/anki/_backend_generated.py`,
`stats_pb2.py`, TS `backend.ts`, dispatch tables.

## Future merge difficulty: LOW

- All edits are additive and the proto rpc is appended at the end of the service, so we
  never renumber existing methods. Conflicts would only arise if upstream edits the same
  few lines of `StatsService` / `stats/mod.rs` / `service.rs`; both are trivial 1–3 line
  re-applications. The bulk of the logic lives in a standalone new file that upstream
  will never touch.

## How to test

```bash
cd anki && source "$HOME/.cargo/env"
cargo test -p anki topic_mastery        # 3 Rust unit tests
./ninja check:pytest:pylib              # Python integration test (+ full pylib suite)
```

Live, in the running desktop app (`./run`) via the debug console:

```python
mw.col.topic_mastery([("All", "deck:*"), ("Probability", "tag:ExamP::Probability")])
```
