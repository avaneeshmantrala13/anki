# Upstream files touched by BrainLift

This lists every **existing upstream file** the BrainLift fork modifies, in both
the Anki desktop fork and the AnkiDroid mobile fork, so an upstream rebase/merge
can be scoped quickly. It is derived directly from `git diff` against each fork's
upstream merge-base (desktop `b00308e5`, mobile `65577ec1`). The large majority of
BrainLift lives in **new, self-contained files** (`pylib/anki/brainlift/`,
`qt/aqt/brainlift/`, `brainlift_eval/`, `docs/`, and the AnkiDroid `brainlift/`
package) that add no merge risk; those are summarized but not enumerated here.

Merge-difficulty ratings: **Low** = isolated/additive edit unlikely to conflict;
**Medium** = edit sits inside a file/region upstream changes often.

## Desktop fork (ankitects/anki)

### Modified upstream files

| File | What changed | Merge difficulty |
| --- | --- | --- |
| `proto/anki/stats.proto` | Adds a `TopicMastery` RPC to `StatsService` plus the `TopicMasteryRequest`/`TopicSearch`/`TopicMasteryResponse`/`TopicMastery` messages. | Medium |
| `rslib/src/stats/service.rs` | Implements the `topic_mastery` method in the `StatsService` impl, delegating to `compute_topic_mastery`. | Medium |
| `rslib/src/stats/mod.rs` | Adds `mod topic_mastery;` to the stats module. | Low |
| `pylib/anki/collection.py` | Adds a `topic_mastery()` method to `Collection` that wraps the new backend RPC. | Low |
| `pylib/pyproject.toml` | Adds a comment noting BrainLift AI reuses the existing `requests` dependency; no new dependency added. | Low |
| `pylib/tests/test_stats.py` | Adds `test_topic_mastery` covering the new aggregation. | Low |
| `qt/aqt/main.py` | Adds a 3-line call to `brainlift.setup_menu(self)` to register the Tools-menu entry. | Low |
| `README.md` | Prepends a fenced "BrainLift fork additions" block above the original README. | Low |

### New file wired into an upstream module

| File | What changed | Merge difficulty |
| --- | --- | --- |
| `rslib/src/stats/topic_mastery.rs` | New Rust file implementing `compute_topic_mastery` (deterministic per-topic mastery/coverage), referenced by `mod.rs` and `service.rs`. | Low |

All other desktop BrainLift code is new files under `pylib/anki/brainlift/`,
`qt/aqt/brainlift/`, `pylib/tests/`, `brainlift_eval/`, and `docs/`, which do not
modify upstream code.

## AnkiDroid fork (ankidroid/Anki-Android)

### Modified upstream files

| File | What changed | Merge difficulty |
| --- | --- | --- |
| `AnkiDroid/src/main/java/com/ichi2/anki/Reviewer.kt` | Adds fatigue tracking: a `brainLiftQuestionShownAt` field, a `recordBrainLiftFatigue(rating)` call in `answerCardInner`, the response-time stamp in `displayCardQuestion`, and the `recordBrainLiftFatigue` helper. | Medium |
| `AnkiDroid/src/main/java/com/ichi2/anki/DeckPicker.kt` | Adds an `R.id.action_brainlift` branch to the options-menu `when` block that launches `BrainLiftActivity`. | Medium |
| `AnkiDroid/src/main/AndroidManifest.xml` | Registers the `.brainlift.BrainLiftActivity` activity (`exported=false`). | Low |
| `AnkiDroid/src/main/res/menu/deck_picker.xml` | Adds the `action_brainlift` menu item. | Low |
| `README.md` | Prepends a fenced "BrainLift fork additions" block above the original README. | Low |

All other AnkiDroid BrainLift code is new files under
`AnkiDroid/src/main/java/com/ichi2/anki/brainlift/`, the
`AnkiDroid/src/main/assets/brainlift/` seed asset, and the
`BrainLiftParityTest` under `src/test/`, which do not modify upstream code.
