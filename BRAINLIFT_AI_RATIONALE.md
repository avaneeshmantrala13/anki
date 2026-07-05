# BrainLift — AI Rationale (standalone reviewer note)

This is a self-contained explanation of **where AI is used in BrainLift, why, and
what was deliberately left out**. It is written to be read on its own; the
authoritative formulas/constants live in `BRAINLIFT_AI_SPEC.md`, the wider
project write-up in `BRAINLIFT_MVP_SUMMARY.md`, the one modified-behaviour note in
`removed_features.md`, and the reproducible numbers in
`brainlift_eval/RESULTS.txt` + `brainlift_eval/BASELINE_COMPARISON.md`.

## Ground rules (true for both AI features)

- **The product works with zero AI.** The core of BrainLift — the three separate
  scores (Memory / Performance / Readiness), coverage, the plan, and the bundled
  Exam P cards — is 100% deterministic. Both AI features sit behind one master
  toggle `brainlift_ai_enabled` (default **OFF**) and each has a deterministic
  fallback, so nothing ever crashes or blocks scoring when AI is off, offline,
  rate-limited, or returns garbage.
- **AI is only introduced where a deterministic rule genuinely falls short**, and
  each use is measured against a simpler baseline (see
  `brainlift_eval/BASELINE_COMPARISON.md`).
- **Parity:** every AI formula/constant is specified once and mirrored in Python
  (`pylib/anki/brainlift/`, desktop) and Kotlin
  (`Anki-Android/.../brainlift/`, mobile). No hand-editing one side.
- **Secrets:** the OpenAI key is read **only** from `OPENAI_API_KEY`
  (env on desktop, runtime on mobile). It is never stored in config or committed.

---

## Feature 1 — Metacognitive calibration ("confidence authority")

Files: `pylib/anki/brainlift/ai.py`, `pylib/anki/brainlift/calibration.py`,
`qt/aqt/brainlift/calibration_dialog.py`; mobile `BrainLiftAi.kt`,
`BrainLiftCalibration.kt`.

### WHAT was built
- The user rates their confidence (5-point scale → `[0,1]`) on 15 cards drawn
  deterministically from the shared 437-card SOA Exam P seed bank, then answers
  **one AI-generated analog MCQ per card** that tests the *same concept*, but is
  **reworded and re-parameterized** (different numbers ⇒ different correct
  answer).
- **AI's job (the only place a model is called):** turn a source flashcard into a
  fresh, checkable analog MCQ. `RealOpenAIClient` calls OpenAI chat-completions
  (`gpt-4o-mini` default) asking for strict JSON `{question, choices,
  correct_index}`. Every generated item records `source_card_id` + `source_text`
  — **named-source traceability**.
- The score is `deviation_i = |confidence_i − performance_i|`;
  `accuracy = 1 − mean(deviation)` (headline), with Goodman–Kruskal `gamma` as a
  secondary resolution figure. That accuracy feeds a **confidence-authority
  multiplier** `authority = 0.25 + 0.75·clamp((accuracy−0.5)/0.5, 0, 1)` (range
  0.25–1.0) that damps how strongly a high self-rating suppresses future review.
- **Safety net — the leakage gate.** A raw model can cheat by copying the source
  (near-verbatim question + same answer), which would hand a free answer to a
  student who already saw the source. `generate_gated_analog` detects this
  (Jaccard question overlap ≥ 0.9 **and** same resolved answer), **regenerates**
  up to `MAX_REGEN = 3` times with an escalating "change the numbers" instruction,
  and **blocks/withholds** the item if it still leaks — so the served set is
  provably clean. Mirrored in Kotlin `generateGatedAnalog`.
- **Prompt-injection defense (see `ai.py` `validate_analog` / Gap 3).** Because
  source card text is interpolated into the prompt, source content is strongly
  delimited and marked as untrusted DATA (never instructions), and a
  post-generation validator rejects-and-regenerates any output that fails the MCQ
  schema, echoes injection/system-prompt markers, or leaks the correct-answer
  letter into the stem. Evidence: `brainlift_eval/prompt_injection_check.py` +
  `pylib/tests/test_brainlift_prompt_injection.py`.

### WHY (where AI earns its keep)
- **Deterministic templates can't scale to arbitrary content.** The offline
  `DeterministicAnalogClient` only re-parameterizes a handful of Exam P concept
  templates; on the gold set it produces a *valid re-parameterized* analog for
  **33/50** cards, and the rest fall back to a "correct-but-bad-teaching"
  concept-variety question that isn't tied to the source. A real model can write a
  faithful analog for the long tail of cards no template covers. (Numbers:
  `BASELINE_COMPARISON.md`.)
- **The metacognitive signal itself requires a *novel* question.** Re-showing the
  original card measures memory, not understanding. The measured **paraphrase gap**
  — original-card recall 84.9% vs analog accuracy 57.9% (**26.9%** gap in the
  simulator) — is exactly the effect that motivates down-weighting over-confident
  self-ratings. You cannot get that gap without generating a genuinely new item.

### WHAT was SKIPPED / de-scoped (and why)
- **Applying the authority multiplier inside the Rust scheduler.** The multiplier
  is computed, persisted to synced config, and applied in the BrainLift
  Python/Kotlin scheduling layer. Wiring it directly into Anki's Rust
  `scheduling`/`answer` weighting is documented as a **candidate second Rust
  engine change** but was left out of the MVP to avoid forking core scheduling.
- **Embedding-based analog retrieval/quality scoring.** The baseline stays a
  transparent keyword-retrieval baseline; no embedding model is used. Enough to
  demonstrate the structured generator beats naive retrieval without adding a
  second model dependency.
- **Live paraphrase-gap numbers.** The 26.9% gap is from a simulator; wiring real
  per-student response streams into it is future work (noted in the eval output).
- **Production test size.** Calibration ships at 15 items (`CALIBRATION_TEST_SIZE`)
  with a declared path to 50 (`CALIBRATION_PRODUCTION_SIZE`); 50 was not enabled
  by default to keep the flow short for the MVP.

---

## Feature 2 — Cognitive-load / fatigue offload (a LEARNED model)

Files: `pylib/anki/brainlift/fatigue.py`, `qt/aqt/brainlift/fatigue_hooks.py`;
mobile `BrainLiftFatigue.kt`. Offline trainer + eval:
`brainlift_eval/{fatigue_sim,train_fatigue_model,fatigue_model_eval}.py`.

### WHAT was built
- A small, **interpretable logistic-regression classifier** decides **WHEN** a
  student is cognitively drained, from five research-grounded, EWMA-smoothed
  features (all in `[0,1]`): **slowdown, accuracy-drop, RT-variability,
  post-error slowing, and session-time position**.
- It is trained **offline in Python**; its weights ship as **shared constants**
  (`FATIGUE_MODEL_VERSION = "logreg-sim-v1"`, bias −4.1252, weights
  [4.9437, 3.0921, 0.7959, 1.5388, 3.5794]) so desktop and mobile run
  **byte-identical** inference `p = sigmoid(bias + w·features)`. All weights are
  positive and interpretable (RT slowdown dominates, then time-on-task, then
  accuracy drop).
- The learned probability replaces the old fixed `drain ≥ 0.60` trigger with
  `MODEL_INTERVENE = 0.50` (severe `0.80`). The rest of the machinery is
  unchanged: 10-answer cooldown, ≥6-answer minimum, timing gate (TEST MODE / ~90
  min / severe), and the two interventions — **interleave** (pull a different
  sub-topic) or **ease difficulty** (easier-by-FSRS card) — plus a visible banner.
- **AI-OFF fallback:** with the master toggle off (or any model issue) the engine
  falls back to the original deterministic weighted-signal drain heuristic
  (slowdown 0.40 / accuracy-drop 0.30 / RT-var 0.15 / post-error 0.15,
  `smoothed_drain ≥ 0.60`). Both paths always return a `FatigueDecision`.

### WHY (where AI earns its keep)
- **A single fixed threshold is a poor detector.** On 600 held-out simulated
  sessions the learned model scores **accuracy 0.9067 / AUC 0.9706 /
  log-loss 0.2914**, versus the previous fixed-threshold heuristic at **accuracy
  0.5283 / AUC 0.9242** on the *same* set — a **+0.3783 accuracy** improvement.
  A learned weighting of several weak physiological signals is measurably better
  than hand-picking one cutoff. (Numbers: `BASELINE_COMPARISON.md`.)
- Keeping it a **logistic regression** (not a black box) means the decision stays
  auditable and the weights map cleanly onto the cited literature.

### WHAT was SKIPPED / de-scoped (and honest caveats)
- **Trained on SIMULATED data, not live students.** There is no real student
  dataset. The simulator (`fatigue_sim.py`) draws "fresh" vs "drained" sessions
  whose per-answer effect sizes are calibrated to three peer-reviewed papers (the
  model's **named source**): Fortenbaugh et al. 2015 (*Psych Science*; vigilance
  decrement, RT slowing/variability), Hanzal et al. 2024 (*PLOS ONE*, SART; state
  fatigue ↔ accuracy drop), and Hassanzadeh-Behbaha et al. 2018 (*Frontiers*;
  progressive RT slowing). This is a genuine limitation, not a hidden one.
- **Per-user online adaptation is future work.** The shipped weights are global;
  the model does not yet adapt to an individual's response stream.
- **The intervention is surfaced but not yet applied to the scheduler queue.** The
  decision (interleave vs ease-difficulty) is computed, logged to
  `brainlift_fatigue_last_intervention`, and shown as a **banner** to the student.
  Actually re-ordering the FSRS due queue (serving the easier card / the
  different-sub-topic card) is wired at the decision layer but **not yet enforced
  in the review queue** for the MVP — the banner communicates the recommendation
  while the queue mutation is left as follow-up.

---

## One-glance summary

| | Feature 1 — Calibration | Feature 2 — Fatigue |
|---|---|---|
| AI type | OpenAI generation (analog MCQ) | Learned logistic regression |
| Runs when | toggle ON + key present | toggle ON (local weights, no network) |
| Fallback | deterministic template generator | deterministic drain heuristic |
| Beats baseline | 33/50 vs 0/50 valid analogs | acc 0.9067 vs 0.5283 |
| Biggest caveat | analog quality is template-limited offline | trained on simulated (not live) data |
| Not yet done | authority hook not in Rust scheduler | intervention shown as banner, not applied to queue |
