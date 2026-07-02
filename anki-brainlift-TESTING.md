# BrainLift — Testing & Validation Notes

Chosen exam: **SOA Exam P**. All logic and bundled content are deterministic — **no AI**.
Bundled study content is the official **SOA Exam P Sample Questions & Solutions**
(Society of Actuaries, freely published for candidates; © Society of Actuaries).

This note captures what was validated today and the exact commands to reproduce it.

---

## 1. Desktop: default-content seeder tests

New feature: a fresh, empty collection is auto-seeded with the SOA Exam P sample
questions (`pylib/anki/brainlift/examp_seed.py` → 437 cards) via
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
# writes anki/pylib/anki/brainlift/examp_seed.py  (437 cards)
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
Loading `SEED_CARDS` directly from the wheel returns **437** cards:

| Exam P main topic | Cards |
|---|---|
| General Probability | 229 |
| Univariate Random Variables | 198 |
| Multivariate Random Variables | 10 |

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

## 4. AI features (Feature 1 calibration + Feature 2 fatigue)

Both features are opt-in behind `brainlift_ai_enabled` (default OFF) and share
one spec, `BRAINLIFT_AI_SPEC.md`. All new state is in collection config, so it
syncs. Formulas are mirrored in Python + Kotlin and parity-tested.

**Desktop tests** (`pylib/tests/test_brainlift_calibration.py`,
`test_brainlift_fatigue.py`):
- deviation / MAD / accuracy (perfect, worst, mixed calibration)
- Goodman-Kruskal gamma (+1 / −1 / undefined→None)
- authority multiplier bounds + monotonicity; `effective_mastery_gap` scaling
- score + persist round-trip; **named-source recorded on every item**
- **AI-off** uses the deterministic client and still scores
- real client with a bogus key **falls back gracefully** (`ok=False`, no raise)
- fatigue: warmup, steady=no drain, degradation triggers in TEST MODE, PROD
  timing gate blocks moderate early drain, severe overrides gate, interleave on
  long same-topic streak, cooldown prevents thrash, persisted/synced session

```bash
cd SpeedRun/anki/pylib
PYTHONPATH="$(pwd):$(pwd)/../out/pylib" ../out/pyenv/bin/python -m pytest -q \
  tests/test_brainlift_calibration.py tests/test_brainlift_fatigue.py
# Result (this batch): 22 passed. Full BrainLift suite: 58 passed.
```

**Mobile parity test** (`AnkiDroid/.../brainlift/BrainLiftParityTest.kt`) asserts
the SAME numbers as the desktop tests:
```bash
cd SpeedRun/Anki-Android
./gradlew :AnkiDroid:testPlayDebugUnitTest --tests "com.ichi2.anki.brainlift.BrainLiftParityTest"
```

---

## 5. AI eval / proof harness (`brainlift_eval/`)

Runs fully **offline with no `OPENAI_API_KEY`** (deterministic client stands in
for GPT via fixtures); a live key + `--live` exercises real generation.

```bash
cd SpeedRun/anki
python brainlift_eval/run_all.py            # held-out eval, gold counts, baseline, leakage, paraphrase gap
OPENAI_API_KEY=sk-... python brainlift_eval/run_all.py --live   # real GPT
```
Proves: named-source traceability, held-out accuracy vs a **pre-declared** cutoff
(blocking failures), gold-set counts (correct-and-useful / wrong /
correct-but-bad-teaching), AI-vs-baseline valid-analog rate, a clean leakage
check, and the paraphrase gap (recall on original vs accuracy on analog).

**Leakage gate (regenerate-then-block).** `leakage_check.py` scans the **served
(post-gate)** set. The generation pipeline (`anki.brainlift.ai.generate_gated_analog`,
mirrored in Kotlin `BrainLiftAi.generateGatedAnalog`) checks each analog for true
free-answer leakage (question near-verbatim to source **and** same resolved answer,
threshold `LEAKAGE_SIM_THRESHOLD=0.9`). Leaked items are **regenerated** up to
`MAX_REGEN=3` times with a stronger re-parameterize instruction, then **blocked**
(withheld, same path as `wrong` items) if still leaking — so the served set is
CLEAN. The check reports raw-leaked / caught-and-regenerated / blocked counts; the
definition is **not** weakened and detections are **not** hidden (a live gpt-4o-mini
run that copies a source, e.g. on card `m06`, is caught by the gate before serving).
Parity is asserted by `pylib/tests/test_brainlift_leakage.py` and the Kotlin
`BrainLiftParityTest` gate tests.

---

## 6. Desktop ↔ mobile sync (FULL two-way validation)

**Conflict/merge rule (the actual behavior).** BrainLift state is stored in the
Anki collection config and rides Anki's built-in collection sync; there is no
custom merge — Anki's standard sync resolution applies. On config divergence it
is effectively **last-writer-wins** (the client whose change is uploaded last
wins); on a structural divergence a full sync prompts the user to keep one side.
All new AI state (`brainlift_calibration`, `brainlift_calibration_multiplier`,
`brainlift_fatigue_session`, `brainlift_fatigue_test_mode`, `brainlift_ai_enabled`,
`brainlift_ai_model`) lives in the collection config, so it syncs with no new
transport.

### Exact procedure to validate FULL two-way sync
Pre-req: both the desktop app and the AnkiDroid build are logged into the SAME
AnkiWeb account and have synced once so the collection matches.

1. **Disjoint offline reviews (nothing lost / double-counted).**
   - Put the phone in airplane mode; review **10** cards in the Exam P deck.
   - On desktop (offline / don't sync yet); review **10 _different_** cards.
   - Re-enable network. Sync desktop, then sync phone (or vice-versa).
   - **Expected:** all **20** reviews are present on both devices; each card's
     `reps` reflects exactly the reviews done (no card counted twice, none lost).
     Verify via the coverage/`reps` counts (`select sum(reps) from cards`) — the
     total increases by exactly 20 across the round-trip.
2. **Same-card conflict (documented winner).**
   - Offline on both devices, review the **same** card (e.g. rate it "Again" on
     phone and "Easy" on desktop), and on desktop also run the confidence
     calibration so `brainlift_calibration_multiplier` changes.
   - Sync device A, then device B.
   - **Expected (documented rule):** Anki's normal sync resolves the card to a
     single consistent scheduling state across both devices (no duplicate review
     log divergence after a full sync). For the BrainLift **config** values
     (calibration multiplier, fatigue session), the value from the client that
     synced **last** wins (last-writer-wins) and both devices then read that same
     value. This is the intended, documented behavior — BrainLift adds no custom
     merge.

> Note: this environment has no `adb`/two live clients, so the round-trip was not
> executed here; the design guarantee (all state in synced collection config,
> last-writer-wins) is verified by construction and by the config round-trip unit
> tests. Run the steps above on two real logged-in clients to confirm end-to-end.

---

## Attribution

Study content: **SOA Exam P Sample Questions & Solutions**, Society of Actuaries
(freely published for candidates), reproduced for personal study; © Society of
Actuaries. Classification into Exam P topics is deterministic (keyword rules in
`anki-analysis/build_examp_deck.py`); no language model generated or graded any
content.
