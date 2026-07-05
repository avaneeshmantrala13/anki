# 2nd Rust engine change — confidence-authority-adjusted mastery gap

## What changed
`StatsService.TopicMastery` (the shared BrainLift Rust engine) now:
- accepts a `confidence_authority` field on `TopicMasteryRequest` (0–1; ≤0 → 1.0), and
- returns `effective_mastery_gap` on each `TopicMastery` result, computed in-engine as
  `clamp(1 − mastered_fraction × confidence_authority, 0, 1)`.

Files touched:
- `proto/anki/stats.proto` — two new fields (`confidence_authority`, `effective_mastery_gap`).
- `rslib/src/stats/topic_mastery.rs` — reads the authority, computes the gap, + 2 new unit tests.
- `pylib/anki/collection.py`, `pylib/anki/brainlift/exam_p.py` — thread the value through.
- `pylib/anki/brainlift/planner.py` — the study planner now consumes the **Rust-computed** gap
  instead of the Python `calibration.effective_mastery_gap` (kept only as the parity reference /
  Kotlin fallback).

## Why this belongs in Rust, not Python
- **It runs on the shared engine, so it ships to both platforms.** The confidence-authority
  adjustment is now part of the same Rust `topic_mastery` aggregation that the desktop and the
  Android `librsdroid.so` execute — one implementation, no drift.
- **It fuses with data the engine already owns.** `mastered_fraction` comes from per-card FSRS
  retrievability the engine computes anyway; doing the authority scaling in the same pass avoids a
  second Python round-trip over the card set (matters on the 50k-card dashboard path).
- **Additive and safe.** It does not fork FSRS interval math or the core scheduler; it extends the
  existing BrainLift RPC with an optional field that defaults to "no adjustment" (authority 1.0),
  so undo, sync, and stock scheduling are untouched.

## Tests
- Rust: `empty_topic_has_full_effective_gap`, `authority_scales_effective_gap` (authority 1.0 → gap
  0; 0.5 → 0.5; ≤0 → full authority), plus the 3 pre-existing `topic_mastery` tests — all pass
  (`cargo test -p anki topic_mastery` → 5 passed).
- Python: integration check confirms `coverage_report(col, confidence_authority=…)` returns the
  Rust-computed gap (1.0→0.000, 0.5→0.500), and the full 118-test BrainLift pylib suite passes.

## Upstream merge risk
Low. The change is confined to the BrainLift-specific `stats/topic_mastery.rs` module and two new
proto fields (both additive, backward-compatible tags). No upstream scheduler/FSRS files are
modified, so a future rebase onto upstream Anki only needs to re-apply the isolated proto field
additions and the self-contained module.
