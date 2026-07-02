# BrainLift AI Features — Shared Algorithm & Data Spec (v2)

This is the **single source of truth** for the two new AI features. Desktop
(Python, `pylib/anki/brainlift/`) and mobile (Kotlin,
`AnkiDroid/.../brainlift/`) implement the **identical** formulas, constants,
and config JSON shapes described here. Parity is verified by
`pylib/tests/test_brainlift_calibration.py`,
`pylib/tests/test_brainlift_fatigue.py`, and the Kotlin `BrainLiftEngineTest`.

If you change a number here, change it in **both** engines and update the parity
tests. Do not hand-edit one platform.

---

## 0. Master toggles & config keys (all in collection config → synced)

Every value below lives in Anki's collection config (SQLite), so it rides
Anki's built-in collection sync (last-writer-wins on conflict).

| Config key | Type | Default | Meaning |
|---|---|---|---|
| `brainlift_ai_enabled` | bool | `false` | Master AI toggle. OFF ⇒ no OpenAI calls; the three scores + both features still function via deterministic fallback. |
| `brainlift_ai_model` | string | `gpt-4o-mini` | Chat-completions model (configurable). |
| `brainlift_calibration` | object | absent | Feature 1 result record (see §3). |
| `brainlift_calibration_multiplier` | float [0,1] | `1.0` | Confidence-authority multiplier read by the scheduling layer (§4). Mirrors `authority_multiplier` inside `brainlift_calibration`. |
| `brainlift_fatigue_test_mode` | bool | `true` | Feature 2 TEST MODE. ON ⇒ interventions fire immediately (for grading/testing). OFF ⇒ PROD timing gate (§6). |
| `brainlift_fatigue_session` | object | absent | Persisted rolling session state for fatigue detection (§5). |
| `brainlift_fatigue_last_intervention` | object | absent | Last intervention `{type, at, banner, drain}`. |

The AI API key is **never** stored in config. It is read only from the
environment variable `OPENAI_API_KEY` (desktop) / passed at runtime (mobile).

---

## 1. Confidence scale (shared constant table)

Ordered worst→best for UI is the reverse of this list.

```
CONFIDENCE_SCALE = {
  "Highly confident":   1.0,
  "Confident":          0.85,
  "Kind of confident":  0.6,
  "Unsure":             0.3,
  "Guessing":           0.0,
}
CONFIDENCE_ORDER = ["Highly confident", "Confident", "Kind of confident", "Unsure", "Guessing"]
```

## 2. Test-size constants

```
CALIBRATION_TEST_SIZE       = 15   # flashcards to self-rate + 15 analog questions
CALIBRATION_PRODUCTION_SIZE = 50   # clear path to production size
```

---

## 3. Feature 1 — Metacognitive calibration ("confidence authority")

### 3.1 Flow
1. Pick `CALIBRATION_TEST_SIZE` cards deterministically from the seeded Exam P
   deck (stable ordering: sort candidate cards by id, take the first N — same on
   both platforms so a re-run is reproducible).
2. For each card the user picks a **confidence label** (§1) *before* seeing the
   answer → `confidence_value ∈ [0,1]`.
3. For each card, generate **one analog MCQ** (reworded / re-parameterized) via
   the AI provider (§7). Every generated item records
   `source_card_id` + `source_text` (front+back) — **named-source
   traceability**. Grade the analog `performance ∈ {0,1}` by comparing the
   chosen index to the generated `correct_index`.

### 3.2 Deviation & accuracy (headline number)
For each pair *i*:
```
conf_i = confidence_value(label_i)        # 0..1
perf_i = 1 if analog answered correctly else 0
dev_i  = |conf_i - perf_i|
```
```
MAD      = mean(dev_i)                     # mean absolute deviation, 0..1
accuracy = 1 - MAD                         # 0..1, reported as %  (headline)
```

### 3.3 Resolution metric (secondary): Goodman–Kruskal gamma
Over all unordered pairs (i, j), compare confidence ordering vs performance
ordering (ties in either dimension are skipped):
```
concordant C : sign(conf_i-conf_j) == sign(perf_i-perf_j)   (both nonzero)
discordant D : sign(conf_i-conf_j) == -sign(perf_i-perf_j)  (both nonzero)
gamma = (C - D) / (C + D)     if (C+D) > 0 else null
```
`gamma` is reported as a secondary "resolution" figure only; the headline stays
`accuracy` (MAD-based) with a plain-language explanation.

### 3.4 Plain-language bands (on `accuracy`)
```
>= 0.85 : "You're excellent at gauging what you know."
>= 0.70 : "You're good at judging what you know, with a little room to tighten up."
>= 0.55 : "Your self-judgment is roughly right, but not fully reliable yet."
<  0.55 : "Your self-judgment isn't fully reliable yet — treat your confidence with caution."
```

### 3.5 Persisted record (`brainlift_calibration`)
```jsonc
{
  "test_size": 15,
  "ai_used": true,
  "items": [{
    "source_card_id": 123, "source_front": "...", "source_back": "...",
    "confidence_label": "Confident", "confidence_value": 0.85,
    "generated_question": "...", "generated_choices": ["...","..."],
    "generated_correct_index": 2,
    "generated_source_card_id": 123, "generated_source_text": "front :: back",
    "chosen_index": 1, "performance": 0, "deviation": 0.85
  }],
  "mad": 0.34, "accuracy": 0.66, "gamma": 0.5,
  "authority_multiplier": 0.66, "completed_at": 1700000000
}
```

---

## 4. Confidence-authority multiplier (Feature 1 → scheduling)

Anki normally treats a high self-rating as "known" and suppresses future
reviews. We scale that suppression by how well-calibrated the user is.

```
CALIB_AUTHORITY_FLOOR_ACCURACY = 0.5    # coin-flip calibration ⇒ minimum authority
MIN_AUTHORITY                  = 0.25   # poorly-calibrated users keep *some* say

norm      = clamp((accuracy - 0.5) / 0.5, 0, 1)
authority = MIN_AUTHORITY + (1 - MIN_AUTHORITY) * norm      # 0.25 .. 1.0
```
Examples: accuracy 1.0 → 1.0; 0.75 → 0.625; ≤0.5 → 0.25.

Applied in the scheduling/planner layer via:
```
calibrated_suppression(raw_suppression) = raw_suppression * authority
```
where `raw_suppression ∈ [0,1]` is how strongly a topic's high self-rating would
reduce its review priority. Well-calibrated ⇒ full suppression (they really do
know it); poorly-calibrated ⇒ suppression is damped so review coverage remains.

**Rust note:** this is a candidate *second* Rust engine change (a
`scheduling`/`answer` weighting hook). For the MVP it is implemented in the
BrainLift scheduling layer (Python + Kotlin) and reads
`brainlift_calibration_multiplier` from synced config. See report.

---

## 5. Feature 2 — Fatigue / cognitive-load state

Rolling per-session state, EWMA-smoothed. Persisted under
`brainlift_fatigue_session` so it survives app restarts and syncs.

### 5.1 State shape
```jsonc
{
  "answers": 0,               // total answers seen this session
  "session_start": 1700000000,
  "baseline_rt": 0.0,         // EWMA of response time (s)
  "baseline_acc": 1.0,        // EWMA of correctness (0..1)
  "rt_var": 0.0,              // EWMA of |rt - baseline_rt|
  "recent_rt": [ ... ],       // sliding window (max WINDOW) of rt
  "recent_acc": [ ... ],      // sliding window (max WINDOW) of correctness
  "post_error_rt": 0.0,       // EWMA of rt on answers immediately after an error
  "last_correct": true,
  "same_topic_streak": 0,     // consecutive answers in the current sub-topic
  "current_topic": "UnivariateRV",
  "smoothed_drain": 0.0,      // EWMA of instantaneous drain
  "answers_since_intervention": 999
}
```

### 5.2 Constants
```
EWMA_ALPHA        = 0.05    # baselines adapt SLOWLY (fresh/early-session norm)
DRAIN_ALPHA       = 0.3     # drain smoothing (anti-thrash)
WARMUP            = 5       # answers used to seed baselines before scoring
WINDOW            = 8       # sliding window for "recent" means
MIN_ANSWERS_BEFORE_DETECT = 6

# drain signal weights (sum = 1.0)
W_SLOWDOWN = 0.40
W_ACC      = 0.30
W_VAR      = 0.15
W_POSTERR  = 0.15

# signal normalization ranges  norm(x, lo, hi) = clamp((x-lo)/(hi-lo), 0, 1)
SLOWDOWN_LO, SLOWDOWN_HI = 1.0, 1.8   # recent_rt / baseline_rt
ACCDROP_LO,  ACCDROP_HI  = 0.0, 0.30  # baseline_acc - recent_acc
VAR_LO,      VAR_HI      = 1.0, 1.7   # recent_rt_var / baseline_rt_var
POSTERR_LO,  POSTERR_HI  = 1.0, 1.5   # post_error_rt / baseline_rt

# thresholds
DRAIN_INTERVENE          = 0.60
SEVERE_DRAIN             = 0.80
SAME_TOPIC_STREAK_LIMIT  = 12
INTERVENTION_COOLDOWN    = 10          # answers between interventions
PROD_MIN_MINUTES         = 90          # ~1-2 hours before PROD interventions
```

### 5.3 Update rule (per answered question)
Inputs: `rt` (seconds, clamped to [0.2, 120]), `correct` (bool), `topic_key`.
```
answers += 1
if answers == 1: baseline_rt = rt; baseline_acc = correct; rt_var = 0
elif answers <= WARMUP:
    baseline_rt  = mean-warmup update
    baseline_acc = mean-warmup update
else:
    baseline_rt  = (1-α)*baseline_rt  + α*rt
    baseline_acc = (1-α)*baseline_acc + α*correct
    rt_var       = (1-α)*rt_var       + α*|rt - baseline_rt|
push rt→recent_rt, correct→recent_acc  (cap WINDOW)
if not last_correct: post_error_rt = (1-α)*post_error_rt + α*rt   (seed with rt if 0)
same_topic_streak = (topic==current_topic) ? streak+1 : 1 ; current_topic = topic
last_correct = correct
```

### 5.4 Drain score
```
recent_rt_mean  = mean(recent_rt)
recent_acc_mean = mean(recent_acc)
slowdown   = recent_rt_mean / max(baseline_rt, 0.2)
accdrop    = baseline_acc - recent_acc_mean
var_ratio  = (recent_rt_var) / max(rt_var, 0.2)         # recent_rt_var = stdev(recent_rt)
posterr    = post_error_rt / max(baseline_rt, 0.2)

drain = clamp(
    W_SLOWDOWN*norm(slowdown, 1.0,1.8) + W_ACC*norm(accdrop,0.0,0.30)
  + W_VAR*norm(var_ratio,1.0,1.7)      + W_POSTERR*norm(posterr,1.0,1.5), 0, 1)
smoothed_drain = (1-DRAIN_ALPHA)*smoothed_drain + DRAIN_ALPHA*drain
```

## 6. Intervention decision (Feature 2)
```
if answers < MIN_ANSWERS_BEFORE_DETECT: no intervention
if answers_since_intervention < INTERVENTION_COOLDOWN: no intervention (anti-thrash)

session_minutes = (now - session_start)/60
timing_ok = test_mode OR session_minutes >= PROD_MIN_MINUTES OR smoothed_drain >= SEVERE_DRAIN

if timing_ok AND smoothed_drain >= DRAIN_INTERVENE:
    if same_topic_streak >= SAME_TOPIC_STREAK_LIMIT:
        type = "interleave";      banner = "Cognitive offload deemed necessary — adding variety"
    else:
        type = "ease_difficulty"; banner = "Cognitive offload — easing difficulty"
    answers_since_intervention = 0
    record brainlift_fatigue_last_intervention = {type, at:now, banner, drain}
else:
    no intervention
```
- `ease_difficulty`: reviewer serves easier cards (lower FSRS difficulty) —
  "very gradually": pick from the easier half of due cards.
- `interleave`: reviewer pulls the next card from a *different* Exam P sub-topic.

Both platforms return the same `FatigueDecision {intervene, type, banner, drain,
session_minutes, reason}`; the platform reviewer acts on it and shows the banner.

---

## 7. AI provider interface (both platforms)

```
GeneratedAnalog {
  question: str, choices: list[str], correct_index: int,
  source_card_id, source_text: str, model: str, ok: bool
}
```
- `AiClient.generate_analog(front, back, source_card_id) -> GeneratedAnalog`
- **RealOpenAIClient** — POST `https://api.openai.com/v1/chat/completions`
  (desktop: `requests`; mobile: OkHttp). Reads key from env/runtime. Asks for a
  JSON MCQ analog. On any error / bad JSON ⇒ falls back to the deterministic
  generator with `ok=false` (never crashes, never blocks scoring).
- **DeterministicAnalogClient** (a.k.a. Mock) — rule-based re-parameterizer
  (coin→die, swaps numbers, rewords) that always yields a valid checkable MCQ
  and records the named source. Used when AI is OFF, no key, offline, or in
  tests/eval fixtures.
- `get_client(enabled, model, api_key)` returns Real if `enabled AND key` else
  Deterministic. **AI OFF ⇒ Deterministic**, so all scores still compute.

### 7.0 Leakage gate (regenerate-then-block) — shared constants

Every generated analog is passed through a **leakage gate** before it is served
to a student. This is the safety net that guarantees the shipped/served set is
CLEAN even if the raw model copies the source instead of re-parameterizing it.

```
LEAKAGE_SIM_THRESHOLD = 0.9    # jaccard word overlap of question vs source front
MAX_REGEN             = 3       # regeneration attempts before an item is blocked
REGEN_PARAM_STRIDE    = 101     # deterministic regen perturbs the param id by this
```

**Leakage definition (identical to the eval's `leakage_check`):** an analog is
*leaked* when its question is near-verbatim to the source AND its correct answer
resolves to the SAME value as the source answer:

```
is_leaked(analog, src_front, src_back) =
    question_similarity(analog.question, src_front) >= LEAKAGE_SIM_THRESHOLD
    AND same_answer(analog.correct_choice, src_back)
```
- `question_similarity` = Jaccard over `[a-z0-9]+` word tokens (same as the eval).
- `same_answer` = normalized string equality OR numeric equality (e.g. `0.20`==`0.2`).

**Gate algorithm (`generate_gated_analog` / `generateGatedAnalog`):**
```
analog = client.generate_analog(front, back, id, attempt=0)
leaked_initially = is_leaked(analog, front, back)
attempts = 0
while is_leaked(analog, front, back) and attempts < MAX_REGEN:
    attempts += 1
    analog = client.generate_analog(front, back, id, attempt=attempts)
served  = not is_leaked(analog, front, back)
blocked = not served          # still leaked after MAX_REGEN -> withheld from students
```
- **RealOpenAIClient**: on `attempt>0` the prompt gets an escalating "your
  previous analog leaked — substantially change the numbers/phrasing" instruction.
- **DeterministicAnalogClient**: on `attempt>0` the parameter id is perturbed by
  `attempt * REGEN_PARAM_STRIDE`, so the numbers (and the answer) change while the
  concept is unchanged.
- Blocked items use the **same withhold path as `wrong` items**: they are never
  served. The eval reports how many raw items leaked, how many were
  caught-and-regenerated, and how many were blocked (honest transparency).

### 7.1 SpeedRunner eval requirements (see `brainlift_eval/`)
- Named source on every generated item (`source_card_id`, `source_text`).
- Held-out eval with a **pre-declared** pass/fail cutoff; failing items blocked.
- Gold set of 50 Exam P Q/A; counts of correct-and-useful / wrong /
  correct-but-bad-teaching.
- Baseline comparison: AI-style structured generator vs keyword/embedding
  baseline at producing valid analog questions.
- Leakage check: scans the **served (post-gate) set**; the generation pipeline
  regenerates-then-blocks true near-duplicates so the served set is CLEAN, while
  the eval honestly reports caught-and-regenerated / blocked counts (§7.0).
- Paraphrase gap: recall on original vs accuracy on reworded analog.
- Graceful degradation when AI offline/rate-limited/broken.
