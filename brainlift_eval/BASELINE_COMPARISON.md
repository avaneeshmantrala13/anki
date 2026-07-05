# BrainLift — AI vs Baseline (side-by-side numbers)

Both AI features are compared head-to-head against a **simpler, non-AI baseline**
on the **same** held-out data, with **pre-declared** pass/fail cutoffs. Every
number below is reproducible from the committed eval scripts and matches
`RESULTS.txt` from a fresh run.

**Reproduce everything:**
```bash
cd brainlift_eval
python run_all.py            # offline, deterministic fixtures (no key needed)
# or per-feature:
python baseline.py           # Feature 1: structured generator vs keyword baseline
python fatigue_model_eval.py # Feature 2: learned logreg vs fixed-threshold heuristic
```
Add `--live` (with `OPENAI_API_KEY` set) to route Feature 1 through the real
OpenAI model instead of the deterministic offline fixtures. Numbers below are the
**offline/deterministic** run (the default, reproducible without a key).

---

## Feature 1 — Analog-question generation
**Script:** `brainlift_eval/baseline.py` (also `run_eval.py`, `gold_eval.py`).
**Task:** produce a **valid re-parameterized analog** MCQ per source card —
structurally valid, conceptually tied to the source, and *not* a near-duplicate
of any gold question (`jaccard < LEAK_THRESHOLD = 0.85`).

- **AI / structured generator** — the BrainLift analog client (deterministic
  offline; real OpenAI with `--live`). Re-parameterizes the same concept.
- **Baseline** — a keyword-retrieval baseline: return the gold item whose question
  shares the most keywords, reused verbatim as the "analog", distractors sampled
  from other gold answers. This is what naive keyword similarity produces — it
  echoes the source concept but never creates a new re-parameterized question.

| Method | Valid re-parameterized analogs / 50 | Rate | Result |
|---|---|---|---|
| **AI / structured generator** | **33 / 50** | **66.0%** | ✅ |
| Keyword-retrieval baseline | 0 / 50 | 0.0% | ✗ |
| **Δ (AI − baseline)** | **+33 / 50** | **+66.0 pts** | — |

**Pre-declared cutoff:** structured generator must beat the baseline
(`s_valid > b_valid`). **RESULT: structured BEATS baseline.**

Supporting Feature-1 numbers (same offline run, from `run_all.py`):

| Eval (script) | Metric | Value | Pre-declared cutoff | Result |
|---|---|---|---|---|
| Held-out (`run_eval.py`, 20 items) | useful (accuracy) rate | 85.0% | useful ≥ 50% | ✅ |
| Held-out (`run_eval.py`, 20 items) | wrong-answer rate | 0.0% | wrong ≤ 10% | ✅ |
| Gold set (`gold_eval.py`, 50 items) | correct-and-useful / bad-teaching / wrong | 38 / 12 / 0 | wrong ≤ 10% | ✅ |
| Leakage (`leakage_check.py`, served set) | flagged duplicates | 0 | 0 in served set | ✅ |

> Why the baseline scores 0: a verbatim retrieved question is a near-duplicate of a
> gold item (fails `jaccard < 0.85`), so it is never a valid *re-parameterized*
> analog. This is the point — keyword similarity cannot generate a genuinely new
> question, which is exactly what the metacognitive signal needs.

---

## Feature 2 — Fatigue detection
**Script:** `brainlift_eval/fatigue_model_eval.py` (data: `fatigue_sim.py`,
weights trained by `train_fatigue_model.py`, shipped in `anki.brainlift.fatigue`).
**Task:** decide **WHEN** a student is cognitively drained, evaluated on **600
held-out simulated sessions** (test seed 98765; disjoint from the 1600 training
sessions, seed 12345). The weights under test are the ones **shipped** in the app,
so this measures the real desktop+mobile model.

- **AI / learned model** — interpretable logistic regression
  (`logreg-sim-v1`) over five EWMA-smoothed features (slowdown, accuracy-drop,
  RT-variability, post-error slowing, session-time position); decision at
  `p ≥ MODEL_INTERVENE = 0.50`.
- **Baseline** — the previous **fixed-threshold** heuristic: intervene when
  `smoothed_drain ≥ DRAIN_INTERVENE = 0.60`.

| Method | Accuracy @ cutoff | AUC | Log-loss | Decision cutoff | Result |
|---|---|---|---|---|---|
| **AI / learned logistic regression** | **0.9067** | **0.9706** | **0.2914** | p ≥ 0.50 | ✅ |
| Fixed-threshold heuristic | 0.5283 | 0.9242 | — | drain ≥ 0.60 | ✗ |
| **Δ (AI − baseline)** | **+0.3783** | **+0.0464** | — | — | — |

**Pre-declared cutoffs:** accuracy ≥ 0.80 **AND** AUC ≥ 0.85 (decided before
looking at held-out results). Learned model: **0.9067 / 0.9706 → PASS**, and it
**beats** the fixed-threshold baseline on the same held-out set.

**Integrity checks (also asserted by the script):**
- Train/test separation (no leakage): **True** — 0 overlapping feature vectors.
- Named source documented in `BRAINLIFT_AI_SPEC.md`: **True** (Fortenbaugh 2015,
  Hanzal 2024, Hassanzadeh-Behbaha 2018).

**Honest caveat:** the model is trained on **research-grounded SIMULATED** sessions
(effect sizes calibrated to the three papers above), not live-student data.
Per-user online adaptation is future work. See `../BRAINLIFT_AI_RATIONALE.md`.

---

## Bottom line

| Feature | AI | Baseline | AI beats baseline by |
|---|---|---|---|
| 1 — Analog generation | 33/50 valid (66.0%) | 0/50 (0.0%) | **+66.0 pts** |
| 2 — Fatigue detection | acc 0.9067 / AUC 0.9706 | acc 0.5283 / AUC 0.9242 | **+0.3783 acc / +0.0464 AUC** |

Both AI features clear their pre-declared cutoffs and measurably outperform the
simpler non-AI baseline. `OVERALL: PASS` (`run_all.py`).
