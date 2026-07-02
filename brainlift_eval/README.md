# BrainLift AI eval / proof harness

This directory proves the BrainLift AI analog generator is safe to put in front of
students **before** they see anything. Everything runs **offline with deterministic
fixtures** (no key, no network) so it is reproducible in CI, and the same scripts
call the real OpenAI model with `--live` when `OPENAI_API_KEY` is set.

## Run it

```bash
cd anki/brainlift_eval
python3 run_all.py            # offline, deterministic fixtures (default)
python3 run_all.py --live     # exercises the real OpenAI model (needs OPENAI_API_KEY)
```

Individual checks:

```bash
python3 run_eval.py        # held-out eval with pre-declared pass/fail cutoff
python3 gold_eval.py       # 50-card gold-set bucket counts
python3 baseline.py        # structured/AI generator vs keyword baseline
python3 leakage_check.py   # near-duplicate / leakage scan vs the gold set
python3 paraphrase_gap.py  # original-recall vs analog-accuracy gap
```

Latest committed run output is in [`RESULTS.txt`](./RESULTS.txt).

## What each script proves (maps to SpeedRunner AI requirements)

| Script | Requirement | Method |
|---|---|---|
| `run_eval.py` | Held-out eval **before** students, with a cutoff decided **before** looking | 20 held-out gold items generated + graded; **pre-declared** cutoffs `wrong-rate <= 10%` and `useful-rate >= 50%`; failing items are **blocked** (withheld). |
| `gold_eval.py` | Gold set of 50 Q/A run through the checker | Buckets all 50 into correct-and-useful / wrong / correct-but-bad-teaching. |
| `baseline.py` | AI beats a simpler baseline at valid analogs | Structured generator vs a keyword-retrieval baseline; metric = valid re-parameterized analogs. |
| `leakage_check.py` | Leakage scan is clean | Flags an analog only when it is near-verbatim **and** resolves to the same answer as a gold item (true free-answer leakage). |
| `paraphrase_gap.py` | Performance != memory | Compares original-card recall vs reworded-analog accuracy over 30 cards. |
| every script | Named-source traceability | Each generated item carries `source_card_id` + `source_text`; scripts assert it is present. |

## Key design points

- **Named sources:** every generated analog records the source card id and source
  text (`GeneratedAnalog.source_card_id` / `source_text`). The eval asserts this.
- **Cutoffs are pre-declared** at the top of `run_eval.py` (and `gold_eval.py`),
  decided before results were inspected. Items failing the checker are excluded.
- **Checker buckets** (`checker.py`):
  - `wrong` — not a usable/unambiguous MCQ (empty, <2 choices, bad index, or the
    correct choice is duplicated so it is not uniquely checkable).
  - `correct_but_bad_teaching` — a valid, checkable MCQ that is **not** conceptually
    tied to the source (tests a different concept / concept-variety fallback).
  - `correct_and_useful` — a valid, checkable MCQ that re-parameterizes the same
    concept as the source.
- **Leakage** is defined as true free-answer leakage (near-verbatim wording **and**
  identical answer), not mere phrasing similarity — a genuine analog is expected to
  share concept phrasing with the source while changing the numbers/answer.
- **Offline == live shape:** offline uses `DeterministicAnalogClient`; `--live` uses
  `RealOpenAIClient`. Both return the same `GeneratedAnalog` structure, so the eval
  and the checker are identical across modes. This is exactly the mockable-client +
  recorded-fixtures path that lets tests pass without a live key.
- **Paraphrase gap** is a simulation harness (no live students in CI); swap in real
  per-user response data (original-recall vs analog-correct) for live numbers — the
  gap computation is unchanged.

## Latest offline results (see RESULTS.txt)

- Held-out (20): useful 85%, wrong 0% -> **PASS** (cutoffs: wrong <=10%, useful >=50%)
- Gold set (50): 38 correct-and-useful / 12 correct-but-bad-teaching / 0 wrong
- Baseline: structured 33/50 valid analogs vs keyword baseline 0/50 -> **structured BEATS**
- Leakage: 0 true duplicates -> **CLEAN**
- Paraphrase gap: original 84.9% vs analog 57.9% -> **26.9% gap**
