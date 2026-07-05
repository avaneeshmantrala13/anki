# BrainLift — Evidence & Feature Writeup (editions)

Everything below is organized so you can drop sections straight into your Brainlift.
All numbers are pulled from the committed `RESULTS.txt`, `DATA_PROVENANCE.md`,
`BENCHMARKS.md`, and `BRAINLIFT_AI_RATIONALE.md`, plus the freshly generated
demo-profile data (`brainlift_eval/demo_seed.py`).

---

## 1. Features included & why

**Deterministic core (works with zero AI — master toggle `brainlift_ai_enabled` defaults OFF):**
- **Three separate scores** — Memory, Performance, Readiness — each with a range, confidence label, coverage %, last-updated, reasons, and a give-up rule.
- **Two `TopicMastery` Rust engine changes** — (1) per-topic covered/mastered/avg-recall aggregation (new proto RPC), powering coverage + dashboards; and (2) a confidence-authority-adjusted `effective_mastery_gap` computed *inside* the Rust engine (see §2), consumed directly by the study planner.
- **Syllabus coverage map**, guided onboarding, a diagnostic quiz, a study planner, and 437 bundled real SOA Exam P cards.

**AI Feature 1 — Metacognitive "Confidence Authority" calibration** (OpenAI `gpt-4o-mini`)
- *What:* user rates confidence on 15 SOA cards, then answers **one AI-generated analog MCQ per card** (same concept, reworded + re-parameterized so the answer differs). Score = `1 − mean(|confidence − performance|)`, which sets a **confidence-authority multiplier** (0.25–1.0) that down-weights over-confident self-ratings in scheduling.
- *Why AI Feature is included:* Many users think that they are good at certain topics when in reality, this confidence is misjudged. The reason for this gap between user confidence and performance is due to the fact that a large portion of users in Anki are attempting to cram for exams rather than prepare for the long term. In order to take care of all users (users that don't cram and can accurately evaluate themselves shouldn't be hindered), I am implementing this ai feature which determines how accurate a user's evaluation of themself is. If it is shown to be very innacurate, then the weightage of their own opinion in flashcards is reduced compared to Anki's original model.

**AI Feature 2 — Cognitive-Load / Fatigue Offload** (learned logistic regression)
- *What:* a small interpretable classifier detects cognitive drain from 5 features (slowdown, accuracy-drop, RT-variability, post-error slowing, session-time), then triggers **interleave** or **ease-difficulty** interventions with a visible banner and actually reorders the live review queue.
- *Why this feature:* Again, students that cram are the ones with a specific need for this feature. When most students cram, they want to learn for like 8 hours a day, but that is largely suboptimal for their cognitive load. Hence, I am implementing this feature where if a student is studying for a lot of time in a session but it is clear that they are not able to maintain the level of performance that they started off with (they are taking longer per question and they are getting more questions wrong), then the questions will automatically get a little bit easier and the topics will vary more to reduce the rate at which their cognitive resources are used up and allow them to still benefit towards the end of their session. Users who do not cram are still helped by this feature because when they don't need it, they won't perform badly and the feature will not turn on, but if they are struggling one day and are not able to perform, then the feature can turn on and help them.

---

## 2. Models — what each does

| Model | Type | Does what |
|---|---|---|
| **Memory** | Deterministic (FSRS-derived) | recall of studied material |
| **Performance** | Deterministic measurement + held-out logistic predictor | transfer to new questions |
| **Readiness** | Deterministic blend (0.6·Perf + 0.4·Mem, ×10) | projected Exam P 0–10 + pass prob + range |
| **Analog generator (F1)** | OpenAI `gpt-4o-mini` → strict-JSON MCQ | turns a source card into a checkable analog |
| **Fatigue detector (F2)** | Logistic regression `logreg-sim-v1` | predicts "drained" per answer |
| **Confidence-authority gap (F1→scheduling)** | Deterministic, computed **in the Rust engine** | scales a topic's review gap by the learner's calibration authority: `clamp(1 − mastered_fraction × confidence_authority, 0, 1)` |

**Fatigue model weights (shipped constants):** bias −4.1252; w = [slowdown +4.9437, accdrop +3.0921, rt_var +0.7959, post_error +1.5388, session_pos +3.5794]. Inference `p = sigmoid(bias + w·features)`; intervene at p ≥ 0.50, severe ≥ 0.80.

**Performance predictor weights:** bias −0.2180; w = [mastery +2.4624, difficulty −2.0700, timing −0.9316, coverage +1.1225].

**Confidence-authority in the engine (2nd Rust change):** the multiplier from Feature 1 is now passed into the `TopicMastery` RPC (`confidence_authority` field), and the engine returns `effective_mastery_gap` per topic. A perfectly-calibrated learner (authority 1.0) fully trusts demonstrated mastery (gap → 0); a poorly-calibrated one (e.g. authority 0.5) keeps more review coverage (gap stays ~0.5). Verified by 3 Rust unit tests + a Python integration check.

---

## 3. Evaluation results (all PASS; every check has a pre-declared cutoff)

| Eval | Result | Numbers | Cutoff |
|---|---|---|---|
| **Held-out analog eval** | PASS | 20 items; useful 85.0%, wrong 0.0%; 0 blocked; every item has a named source | wrong ≤10% AND useful ≥50% |
| **Gold-set (50 cards)** | PASS | correct+useful 38, correct-but-bad 12, wrong 0 | wrong ≤10% |
| **Baseline comparison** | PASS | structured generator **33/50 (66%)** vs keyword baseline **0/50 (0%)** | structured beats baseline |
| **Leakage check (served set)** | CLEAN | 50 scanned, 0 leaked, 0 blocked | 0 leaked at sim ≥0.9 + same answer |
| **Prompt-injection resistance** | PASS | 5/5 adversarial sources served clean; 5/5 compromised outputs blocked | all pass |
| **Paraphrase gap** *(sim)* | reported | original recall 84.9% vs analog accuracy 57.9% → **26.9% gap** | (motivates down-weighting) |
| **Fatigue model held-out** *(sim)* | PASS | learned **acc 0.9067 / AUC 0.9706 / log-loss 0.2914** vs baseline **acc 0.5283 / AUC 0.9242** → **+0.3783 acc** | acc ≥0.80 AND AUC ≥0.85 |
| **Memory calibration** *(sim, non-circular)* | PASS | **Brier 0.1646 / log-loss 0.5820 / ECE 0.0794**; 10-bin reliability curve monotone; honestly shows top-bin overconfidence (pred ≈0.98 vs obs ≈0.87) | Brier ≤0.25 |
| **Performance held-out** *(sim)* | PASS | **acc 0.7240 / AUC 0.7963**; majority baseline 0.5173 → **+0.2067 lift** | acc ≥0.65 AND lift ≥0.05 |
| **3-build ablation** *(sim)* | PASS | A full **74.6%** / B ablated **70.2%** / C stock **70.8%**; A−B **+4.4pp** (CI ±0.6), A−C **+3.8pp** (CI ±0.4); isolated calibration-authority effect **+0.8pp** (honest near-null) | A≥B, A≥C, A−C>0 |
| **50k benchmark** *(real latencies)* | PASS | all budgets met (see §6) | per-action budgets |
| **Crash/durability** *(real)* | PASS | **20/20** unclean kills → 0 corruption | zero corruption |

**Suite:** `run_all.py` → **OVERALL: PASS** (all 10). Tests: **118 BrainLift pylib tests passed**, plus **5 Rust `topic_mastery` unit tests** (incl. the new confidence-authority test).

**Memory calibration reliability diagram (predicted → observed by bin):**
0.072→0.184 · 0.147→0.164 · 0.249→0.325 · 0.352→0.374 · 0.450→0.460 · 0.553→0.580 · 0.648→0.590 · 0.750→0.695 · 0.856→0.760 · 0.978→0.871

---

## 4. Synthetic / simulated data — exactly what & how (fully disclosed)

| Number/artifact | Data source | Type |
|---|---|---|
| Fatigue acc/AUC/log-loss + weights | `fatigue_sim.py` seeded sessions | **SIMULATED** (train + test) |
| Analog evals (held-out, gold, baseline, leakage, injection) | `DeterministicAnalogClient` fixtures (unless `--live`) | **FIXTURE** (not live model) |
| Paraphrase gap | seeded memory-strength + transfer sim | **SIMULATED** |
| Memory calibration (Brier/log-loss/ECE) | seeded FSRS review sim + **independent MLE** estimator | **SIMULATED, non-circular** |
| 3-build ablation | seeded synthetic learner cohort | **SIMULATED** |
| Demo-profile scores (Memory/Performance/Readiness) | `demo_seed.py` seeded reviews + diagnostic per profile | **SIMULATED history, REAL engine numbers** |
| 50k benchmark & crash test | programmatically generated deck | **SYNTHETIC deck, REAL measurements** |
| Bundled Exam P cards + FSRS | SOA published PDFs / Anki's algorithm | **REAL** |

**How each simulator works (for the reviewer):**
- **Fatigue:** two profiles (`FRESH`/`DRAINED`) with per-answer effect sizes calibrated to 3 peer-reviewed papers; ranges deliberately overlap so the task is non-trivial. Train seed 12345 (n=1600), test seed 98765 (n=600) — **disjoint session-id namespaces, 0 shared ids** (identity-based leakage guard).
- **Memory calibration (non-circular):** each card has a hidden true stability `S_true`; an independent MLE estimator fits `S_hat` from **past outcomes only** (96-pt grid), predicts a **held-out future** review; the observed outcome is an independent draw from `S_true`. Prediction and truth travel separate paths → the diagram genuinely tests the estimator (train seed 20260705, test seed 71072026; 4000/4000 reviews).
- **Performance:** logistic DGP, disjoint fit seed 424242 (n=3000) / held-out seed 909090 (n=3000).
- **Ablation:** master seed 20240501, held-out test seeds in disjoint `900000+` namespace; full app imports the **shipped** `authority_multiplier`/`effective_mastery_gap` formulas; calibration benefit intentionally heterogeneous so the result isn't rigged.
- **Demo profiles:** `demo_seed.py` builds a throwaway collection per profile, tags cards across the whole syllabus (100% coverage), drives real FSRS reviews at the profile's target accuracy, ages the reviews so recall decays realistically, and saves a matching diagnostic — so the dashboard computes genuine numbers over a *simulated* learner (see §7 for the numbers).

These are results on synthetic data generated by deterministic models we wrote — evidence the system behaves as designed under the modeled assumptions, not field evidence from real students.

---

## 5. Named sources (traceability) — with DOK 1 (facts) & DOK 2 (summaries)

- **Every AI analog** records `source_card_id` + `source_text` → traces to a specific SOA Exam P card.
- **Study content:** Society of Actuaries Exam P Sample Questions & Solutions (public PDFs).

### Feature 1 (metacognitive calibration) — self-assessment / JOL literature

**Source 1 — Rhodes (2015), "Judgments of Learning: Methods, Data, and Theory" (Oxford Handbook of Metamemory).** Free PDF: https://pdf.retrievalpractice.org/metacognition/8_Rhodes_2015.pdf
- *DOK 1 – Facts:* Review of judgments of learning (JOLs). Distinguishes **absolute accuracy** (calibration — magnitude of judgment vs actual performance) from **relative accuracy** (resolution — item-by-item discrimination). Relative accuracy is quantified with the **Goodman-Kruskal gamma** correlation between JOLs and test accuracy, −1.0 to +1.0 (Nelson, 1984). The "ideal learner" assigns higher JOLs to items that will be remembered; learners reliably show this. Testing/retrieval substantially raises relative accuracy (King et al., 1980). Judgment accuracy depends on whether the cues learners use are actually predictive (Koriat, 1997).
- *DOK 2 – Summary:* Students can reliably rank-order which items they know well vs poorly (relative accuracy) even when absolute confidence is off. Self-assessment improves markedly when based on diagnostic cues — especially a real retrieval attempt — rather than restudy fluency. A learner can be poorly calibrated overall yet still discriminate strong from weak knowledge.

**Source 2 — Bui, Bailey et al. (2017), delayed judgment-of-learning effect.** Free PDF: https://www.k-state.edu/psych/about/people/bailey/Bui%20et%20al%202017%20pdf.pdf
- *DOK 1 – Facts:* Experimental study of the **delayed-JOL effect** — JOLs made after a delay predict later recall more accurately than immediate ones. Both calibration and resolution (gamma) were better for delayed JOLs, which were also lower in magnitude (Exp 1). A sufficiently demanding intervening task produced equally accurate JOLs without a long delay (Exp 2–4). Interpreted via a retrieval-based account: JOLs are diagnostic when the target must be retrieved from long-term (not short-term) memory.
- *DOK 2 – Summary:* When students judge knowledge after a delay or after retrieving from long-term memory, their predictions become highly accurate. The key condition for trustworthy self-assessment is basing the judgment on a genuine retrieval attempt, not the ease of freshly-studied material.

**Source 3 — Metcalfe & Kornell (2003/2005), "Region of Proximal Learning" model of study-time allocation.** Free PDF: https://www.columbia.edu/cu/psychology/metcalfe/PDFs/Metcalfe%20Kornell%202003.pdf
- *DOK 1 – Facts:* Proposes the **region of proximal learning** account across eight experiments. Two components: **choice** (whether/what order to study) and **perseverance** (when to stop). Under time constraints, learners first select items judged almost-but-not-yet-learned, then progressively harder items. They don't pour the most time into the hardest items. They decide when to stop using judgments of their **rate** of learning (jROLs). Extra time on the hardest items did not reliably help; time in the proximal region did.
- *DOK 2 – Summary:* Students systematically regulate study time, sequencing by difficulty relative to what they already know, concentrating effort at the edge of mastery, and using a sense of their own learning rate to decide when to move on — adaptive self-assessment of what still needs work.

### Feature 2 (cognitive-load / fatigue) — the three papers the model is calibrated to

**Source 1 — Fortenbaugh et al. (2015), *Sustained Attention Across the Lifespan…*, Psychological Science 26(9), 1497–1510.** https://pmc.ncbi.nlm.nih.gov/articles/PMC4567490/
- *DOK 1 – Facts:* 10,430 participants (aged 10–70, M=26.07) on a 4-minute gradual-onset CPT (gradCPT). Separates **"ability"** (d′, RT variability) from **"strategy"** (mean RT, criterion). d′ peaks ~43; breakpoints at 16.5 and 42.9 years.
- *DOK 2 – Summary:* After ~15, ability and strategy diverge: strategy grows monotonically more conservative (slower, more cautious) with age; ability keeps improving modestly, peaks ~43, then declines at less than 1/5 the childhood rate. Post-error slowing increases with age.

**Source 2 — Hanzal et al. (2024), *Probing sustained attention and fatigue across the lifespan*, PLOS ONE 19(1), e0292695.** https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0292695
- *DOK 1 – Facts:* 115 participants (mean age 48.4, range 18–81) on an online SART (502 trials). Mean accuracy change first→last block −3.34%. State fatigue (VAS-F) vs trait fatigue (MFI). Age was the strongest accuracy predictor (β=.372); RTs sped up over the task (learning effect).
- *DOK 2 – Summary:* **State-fatigue change** was the only significant predictor of accuracy change (β=−.359) — bigger fatigue increase → bigger accuracy drop ("tight coupling"), outperforming trait fatigue. Older = more accurate (motivational + accuracy-based strategy). Subjective state-fatigue tracked the objective accuracy drop.

**Source 3 — Hassanzadeh-Behbaha et al. (2018), *…Task Requirements in the Magnitude of the Vigilance Decrement*, Frontiers in Psychology 9, 1504.** https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2018.01504/full
- *DOK 1 – Facts:* Vigilance decrement = decreased probability of detecting critical trials as time-on-task increases. 40 minutes, 1,200 trials, four unsignaled blocks. Successive (hold comparison in memory) vs simultaneous task. RT to critical signals increased significantly across blocks (F(1,55)=41.36, η²=0.75); eye-tracking at 250 Hz.
- *DOK 2 – Summary:* Every processing stage slowed as blocks progressed (most in the final encoding→response stage). A single attentional/executive-control resource explains the decrement across both tasks (consistent with Resource-Control Theory); task-type differences come from how degraded processing interacts with each task's requirements.

---

## 6. Performance benchmark (50k cards, real wall-clock)

| Action | p50 | p95 | worst | budget | result |
|---|---|---|---|---|---|
| button-ack | 0.00 | 0.00 | 0.04 ms | <50 ms | PASS |
| next-card | 0.00 | 0.00 | 0.01 ms | <100 ms | PASS |
| dashboard-load | 282.65 | 284.53 | 285.10 ms | <1000 ms | PASS |
| dashboard-refresh | 120.86 | 122.65 | 124.02 ms | <500 ms | PASS |
| aggregate-op (`topic_mastery` all topics) | 420.67 | 442.62 | 442.62 ms | <5000 ms | PASS |
| cold-start (proxy) | 292.59 | — | — | <2000 ms | PASS |
| peak-memory (50k) | — | — | 140 MB | <1500 MB | PASS |

**Crash test:** 20/20 unclean mid-review kills → 0 corruption (real `os._exit(9)` + SQLite/Anki integrity checks). **Sync:** executed loopback two-way sync round-trip — BrainLift state + `sum(reps)` + revlog transfer with none lost/doubled; same-key conflict resolves last-writer-wins.

**Shared engine on the phone:** the forked Rust backend — **including both `TopicMastery` engine changes (aggregation + confidence-authority `effective_mastery_gap`)** — compiles and links into the Android native library `librsdroid.so` (arm64-v8a, built via `cargo-ndk` against the fork's `rslib`). The `.so` is symbol-verified to contain `anki::stats::service::…topic_mastery` and the `TopicMasteryRequest`/`confidence_authority` protos (artifact in `dist/phone-rust/`), so the exact same Rust engine runs on desktop and phone.

---

## 7. Honest uncertainty / give-up rules & demo-profile data

**Give-up / confidence rules:**
- **Readiness abstains** (shows no number, lists what's missing) until: **≥200 graded reviews AND ≥50% coverage AND diagnostic completed.** Confidence: high = coverage ≥80% & reviews ≥500 & diagnostic ≥10; medium = coverage ≥50% & reviews ≥200; else low.
- **Memory/Performance** show "Not enough data" below thresholds; confidence labels are identical desktop↔Android (parity-tested).

**Synthetic demo data (so the scores show real numbers in the demo video):** because Readiness abstains until the evidence thresholds are met, a fresh collection shows "Not enough data." To demo genuine, *calculated* numbers I generated synthetic collections with `demo_seed.py`. Synthetic data is generated for a **profile of someone with ~90% accuracy so that Readiness can also show a number**, and synthetic **Memory / Performance** data is generated so those scores show numbers too. I generated this for **all three profiles** (strong / medium / weak) so the demo can show a spread of calculated numbers. All three are seeded to 100% syllabus coverage with 260 graded reviews (clearing the give-up gate); the numbers below are computed by the shipped Rust engine + measurement formulas over the simulated review history:

| Profile (target accuracy) | Memory | Performance | Readiness /10 | Pass-prob |
|---|---|---|---|---|
| **Strong (~90%)** | 80% [77–83] | 93% [80–100] | **8.8** [7.9–9.3] | 1.0 |
| **Medium (~70%)** | 78% [75–81] | 74% [60–87] | **7.5** [6.6–8.5] | 0.88 |
| **Weak (~50%)** | 75% [72–78] | 50% [36–64] | **6.0** [5.1–7.0] | 0.5 |

(Import a profile via **File → Import** using `dist/demo-profiles/brainlift-demo-<profile>.colpkg`.) These are simulated learners, not field data — the review history and diagnostic responses are RNG-generated to a target accuracy; only the engine's computation of the scores over that history is "real."
