# Readiness model

**What it predicts.** The student's projected **Exam P outcome on a 0–10 scale**
(6 is the conventional pass mark), together with a likely range, a pass
probability, and an explicit confidence. Readiness is the only score that
combines the others.

**Inputs.**
- The **Memory** score (recall of studied material).
- The **Performance** score (transfer to new questions).
- Total **graded reviews** across the collection (sum of card reps).
- **Syllabus coverage %** (weighted % of the syllabus present in the deck).
- Whether the **diagnostic** has been completed.

**Method / formula.** A weighted blend of Performance and Memory, favouring
transfer over recall, scaled to 0–10:

```
blend      = W_PERFORMANCE · performance + W_MEMORY · memory   (0.6 / 0.4)
projected  = round(blend · 10, 1)
pass_prob  = clamp( (blend - 0.4) / 0.4 )      # 0.4 blend → 0, 0.8 blend → 1
```

The range is the same blend applied to each input's low/high band.

**Range.** `score_low`–`score_high` on the 0–10 scale, derived from the Memory
and Performance ranges, plus a pass-probability in `[0, 1]`.

**How-sure indicator (confidence).** Reported as `low` / `medium` / `high`
(or `none` when withheld):
- `high` — coverage ≥ 80% **and** reviews ≥ 500 **and** diagnostic answered ≥ 10
- `medium` — coverage ≥ 50% **and** reviews ≥ 200
- `low` — otherwise

**Give-up / abstention rule (the honesty rule).** Readiness refuses to report a
number until **all** of the following hold. Otherwise it returns
`available = false`, `confidence = none`, and lists exactly what is missing:
- ≥ **200** graded reviews,
- ≥ **50%** syllabus coverage,
- the **diagnostic** has been completed.

This is the pre-existing, deliberately conservative behaviour: Readiness would
rather say "Not enough data" and enumerate the missing evidence than emit a
confident-looking but unsupported projection. These thresholds are identical on
desktop (`measurements.py`) and Android (`BrainLiftEngine.kt`).
