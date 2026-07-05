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
python3 prompt_injection_check.py  # prompt-injection resistance (Feature 1)
python3 paraphrase_gap.py  # original-recall vs analog-accuracy gap
python3 fatigue_model_eval.py    # Feature 2 LEARNED fatigue model: held-out acc/AUC/log-loss
python3 memory_calibration_eval.py   # Memory model: FSRS predicted-recall calibration (Brier/log-loss/ECE + reliability diagram)
python3 performance_holdout_eval.py  # Performance model: held-out correctness prediction (accuracy vs baseline, AUC, log-loss)
python3 ablation.py                  # 3-build ablation (full app vs feature-ablated vs stock Anki) on a held-out test
python3 train_fatigue_model.py   # (re)train the Feature 2 model offline; prints shipped weights
```

Standalone one-command tools (NOT in the default `run_all.py` — they are slower and
build/kill throwaway collections; see [`BENCHMARKS.md`](./BENCHMARKS.md)):

```bash
out/pyenv/bin/python brainlift_eval/bench.py         # 50k-card performance benchmark (p50/p95/worst vs budgets)
out/pyenv/bin/python brainlift_eval/crash_test.py    # kill-mid-review durability test (asserts zero DB corruption)
```

Latest committed run output is in [`RESULTS.txt`](./RESULTS.txt). How the simulated
datasets are generated and why they are honest is documented in
[`DATA_PROVENANCE.md`](./DATA_PROVENANCE.md); the standalone benchmark tools and
budgets are in [`BENCHMARKS.md`](./BENCHMARKS.md).

## What each script proves (maps to SpeedRunner AI requirements)

| Script | Requirement | Method |
|---|---|---|
| `run_eval.py` | Held-out eval **before** students, with a cutoff decided **before** looking | 20 held-out gold items generated + graded; **pre-declared** cutoffs `wrong-rate <= 10%` and `useful-rate >= 50%`; failing items are **blocked** (withheld). |
| `gold_eval.py` | Gold set of 50 Q/A run through the checker | Buckets all 50 into correct-and-useful / wrong / correct-but-bad-teaching. |
| `baseline.py` | AI beats a simpler baseline at valid analogs | Structured generator vs a keyword-retrieval baseline; metric = valid re-parameterized analogs. |
| `leakage_check.py` | Leakage scan is clean | Scans the **served (post-gate) set**. The generation pipeline runs a leakage gate (regenerate-then-block); this check flags an analog only when it is near-verbatim **and** resolves to the same answer as a gold item, and reports how many raw items leaked / were caught-and-regenerated / were blocked. |
| `prompt_injection_check.py` | **Prompt-injection resistance** (source content is interpolated into the prompt) | Feeds NAMED injection payloads embedded in source-card text through the generator and asserts the served output ignores them (valid MCQ, no system-prompt leak, no instruction-following); also proves a simulated **compromised** model is BLOCKED by the validator (`validate_analog`). |
| `paraphrase_gap.py` | Performance != memory | Compares original-card recall vs reworded-analog accuracy over 30 cards. |
| `fatigue_model_eval.py` | **Feature 2 learned model** meets the AI bar | Held-out **accuracy / AUC / log-loss** of the SHIPPED logistic-regression fatigue model vs a **pre-declared** cutoff (acc ≥ 0.80 AND AUC ≥ 0.85); **baseline beat** vs the previous fixed-threshold heuristic on the same held-out set; **train/test separation (leakage) check**; asserts the three named papers are documented. |
| `memory_calibration_eval.py` | **Memory model is calibrated** (is an "80% recall" claim actually 80%?) | Scores the FSRS-5 predicted-recall probability against simulated-but-FSRS-grounded outcomes on a HELD-OUT pool with **Brier score / log-loss / ECE** + a 10-bin **reliability diagram**; **pre-declared** cutoff Brier ≤ 0.25 and all metrics finite. Writes `memory_calibration_reliability.{csv,txt}`. Data is SIMULATED (see `DATA_PROVENANCE.md`). |
| `performance_holdout_eval.py` | **Performance features PREDICT unseen questions** (not just re-score the diagnostic) | Fits a small logistic regression on a FIT set of exam-style questions (features BrainLift already has: mastery/difficulty/timing/coverage) and reports **held-out accuracy / AUC / log-loss** plus **lift over the majority-class baseline**; **pre-declared** cutoff accuracy ≥ 0.65 AND lift ≥ 0.05. Writes `performance_holdout_results.csv`. Data is SIMULATED (see `DATA_PROVENANCE.md`). |
| `ablation.py` | **The two AI features actually help** | Pre-registered 3-build ablation — A full app (fatigue offload + calibration authority ON) vs B same core with both OFF vs C stock Anki — over a cohort of seeded synthetic learners on an identical fixed study budget; primary metric = **held-out mixed-topic accuracy**, reported with 95% CIs and **paired A−B / A−C** differences (so a null is visible), plus a calibration-subgroup diff-in-diff that isolates the calibration-authority effect. Imports the SHIPPED `anki.brainlift` formulas. Data is SIMULATED (see `DATA_PROVENANCE.md`). |
| `train_fatigue_model.py` | Offline training is reproducible | Trains the logistic regression (pure-Python GD, fixed seed) on research-grounded simulated sessions and prints the shipped bias/weights verbatim. |
| `fatigue_sim.py` | Honest, research-grounded data | Generates the SIMULATED labeled sessions (effect sizes calibrated to Fortenbaugh 2015 / Hanzal 2024 / Hassanzadeh-Behbaha 2018); folds them through the shipped feature pipeline. |
| every script | Named-source traceability | Each generated item carries `source_card_id` + `source_text`; scripts assert it is present. The fatigue model's named source is the three peer-reviewed papers (asserted present in the spec). |

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
- **Prompt-injection defense (shared logic):** source card text is untrusted DATA
  interpolated into the prompt, so (1) the prompt strongly delimits it and forbids
  following instructions inside it, (2) `anki.brainlift.ai.validate_analog`
  (mirrored in Kotlin `BrainLiftAi.validateAnalog`) rejects any output that fails
  the MCQ schema, echoes injection markers / our system prompt, or leaks the
  answer into the stem, and (3) `generate_gated_analog` regenerates-then-blocks a
  still-failing item while `RealOpenAIClient` also rejects an injected output in
  favour of the clean deterministic fallback on every call. Proven by
  `prompt_injection_check.py` and `pylib/tests/test_brainlift_prompt_injection.py`.
- **Leakage gate (regenerate-then-block):** before any analog is served, the
  generation pipeline (`anki.brainlift.ai.generate_gated_analog`, mirrored in
  Kotlin `BrainLiftAi.generateGatedAnalog`) checks each item for leakage. Leaked
  items are **regenerated** up to `MAX_REGEN=3` times with a stronger
  re-parameterize instruction (threshold `LEAKAGE_SIM_THRESHOLD=0.9`); if still
  leaking they are **blocked** (withheld, same path as `wrong` items). So the
  served set has zero leaked items. `leakage_check.py` scans that served set and
  reports the raw-leaked / caught-and-regenerated / blocked counts — we do **not**
  weaken the definition or hide detections; the gate removes them before serving.
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
- Leakage (served/post-gate set): 0 true duplicates -> **CLEAN** (0 raw-leaked, 0 regenerated, 0 blocked offline; the gate catches live-model leaks)
- Prompt-injection: 5/5 adversarial source cards yield a clean served MCQ; 5/5 simulated compromised outputs BLOCKED -> **PASS**
- Paraphrase gap: original 84.9% vs analog 57.9% -> **26.9% gap**
- Fatigue model (Feature 2, learned): held-out **acc 0.9067 / AUC 0.9706 / log-loss 0.2914** -> **PASS** (pre-declared acc >=0.80, AUC >=0.85); **beats** fixed-threshold heuristic (0.5283 / 0.9242); train/test separation clean (0 overlap)
- Memory calibration: held-out **Brier 0.1229 / log-loss 0.4391 / ECE 0.0187**, reliability diagram monotone -> **PASS** (pre-declared Brier <=0.25)
- Performance held-out: **accuracy 0.7240 / AUC 0.7963**, majority baseline 0.5173 -> **lift +0.2067** -> **PASS** (pre-declared acc >=0.65, lift >=0.05)
- Ablation (3-build, 60 learners): A full **74.6%** vs B ablated **70.2%** vs C stock **70.8%**; paired **A−B +4.4 pp** and **A−C +3.8 pp** (both 95% CIs exclude 0) -> **PASS**; diff-in-diff shows fatigue offload drives most of the gain, calibration authority's isolated effect is modest (reported honestly)

## Feature 2 fatigue model — honesty note

The Feature 2 drain decision is a **learned logistic-regression classifier**
(`anki.brainlift.fatigue`), NOT a hand-tuned threshold. Because there is no live
student data, it is trained **offline** on a **research-grounded SIMULATED**
dataset whose per-answer effect sizes are calibrated to three peer-reviewed
papers (Fortenbaugh et al. 2015; Hanzal et al. 2024; Hassanzadeh-Behbaha et al.
2018). The weights ship as shared constants (`BRAINLIFT_AI_SPEC.md §5.5`) so
desktop (Python) and mobile (Kotlin) run byte-identical inference. Per-user
online adaptation on real response streams is explicit future work. With the AI
toggle OFF the engine falls back to the original deterministic drain heuristic.
