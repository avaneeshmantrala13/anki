# BrainLift — Testing & Validation Notes

Chosen exam: **SOA Exam P**. All logic and bundled content are deterministic — **no AI**.
Bundled study content is the official **SOA Exam P Sample Questions & Solutions**
(Society of Actuaries, freely published for candidates; © Society of Actuaries).

This note captures what was validated today and the exact commands to reproduce it.

---

## 1. Desktop: default-content seeder tests

New feature: a fresh, empty collection is auto-seeded with the SOA Exam P sample
questions (`pylib/anki/brainlift/examp_seed.py` → 660 cards) via
`pylib/anki/brainlift/default_content.py::maybe_seed_default_deck`.

Tests: `pylib/tests/test_brainlift_default_content.py`
- seeds > 0 cards on an empty `getEmptyCol()`
- seeded tags cover all three Exam P main topics (GeneralProbability, UnivariateRV, MultivariateRV)
- a second run adds **0** cards (idempotent via `brainlift_seeded_default` flag)
- a collection that already has a card is left untouched (adds 0)

**Result (today):** all BrainLift pylib tests pass — `36 passed`
(3 new default-content tests + the existing exam_p / onboarding / diagnostic /
planner / measurements / dashboard / persistence suites).

### Reproduce the desktop tests
```bash
cd SpeedRun/anki
source "$HOME/.cargo/env"

# Regenerate the build graph so ninja picks up the new test file:
cargo run -p configure

# Preferred: run pylib pytest through the repo tooling (may rebuild):
./ninja check:pytest:pylib

# Direct run (shows per-test output). The pyenv has an editable install of pylib,
# and out/pylib provides the generated protobuf + compiled Rust bridge:
PYTHONPATH="$(pwd)/out/pylib" ANKI_TEST_MODE=1 out/pyenv/bin/pytest \
  -p no:cacheprovider -v \
  pylib/tests/test_brainlift_default_content.py \
  pylib/tests/test_brainlift_exam_p.py

# Full BrainLift suite:
PYTHONPATH="$(pwd)/out/pylib" ANKI_TEST_MODE=1 out/pyenv/bin/pytest \
  -p no:cacheprovider -q pylib/tests/test_brainlift_*.py
```

### Regenerate the seed module (from the validated .apkg / SOA source)
```bash
python anki-analysis/build_examp_deck.py --emit-seed
# writes anki/pylib/anki/brainlift/examp_seed.py  (660 cards)
```

---

## 2. Desktop: wheel build + bundled-content confirmation

The seed content is a pure-Python module, so it is guaranteed to ship in the wheel.

```bash
cd SpeedRun/anki
source "$HOME/.cargo/env"
./ninja wheels

# Confirm the data module is inside the built anki wheel:
unzip -l out/wheels/anki-*.whl | grep 'brainlift/examp_seed.py'
```

**Result (today):** `./ninja wheels` succeeded. The built
`anki-26.5-cp310-abi3-macosx_12_0_arm64.whl` contains
`anki/brainlift/examp_seed.py` (≈810 KB), `default_content.py`, and `exam_p.py`.
Loading `SEED_CARDS` directly from the wheel returns **660** cards:

| Exam P main topic | Cards |
|---|---|
| General Probability | 310 |
| Univariate Random Variables | 304 |
| Multivariate Random Variables | 46 |

> The full signed `.dmg` installer is built at packaging time with
> `./tools/build-installer` (`RELEASE=2 ./ninja installer`); it was **not**
> rebuilt here (slow). Confirming the wheel content is sufficient because the
> installer packages the same wheel.

---

## 3. Mobile: AnkiDroid build + emulator

```bash
# In the AnkiDroid fork:
./gradlew assembleDebug
adb install -r AnkiDroid/build/outputs/apk/debug/AnkiDroid-debug.apk
```

**Result (today):** the AnkiDroid fork built and installed on the Android
emulator; the BrainLift Exam P coverage view renders on device. Mobile receives
the seeded deck, cards, and coverage through Anki sync (no Android code change is
needed for the default-content feature).

---

## 4. Desktop ↔ mobile sync validation (today)

Validated that onboarding profile, cards, and per-topic coverage created on one
client appear on the other after sync.

**Sync-direction rule used during testing:** change on one side → **sync up** →
switch to the other client → **sync down** → then compare. Do not edit both sides
before syncing (avoids one-way merge conflicts). All BrainLift state lives in the
collection config + standard notes/cards, so it uses Anki's existing sync with no
new transport.

---

## Attribution

Study content: **SOA Exam P Sample Questions & Solutions**, Society of Actuaries
(freely published for candidates), reproduced for personal study; © Society of
Actuaries. Classification into Exam P topics is deterministic (keyword rules in
`anki-analysis/build_examp_deck.py`); no language model generated or graded any
content.
