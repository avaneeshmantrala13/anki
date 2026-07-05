# BrainLift performance benchmarks (50k cards)

A one-command benchmark that builds a ~50,000-card collection and measures the
hot BrainLift actions against their stated budgets, reporting **p50 / p95 /
worst** and **PASS/FAIL** per action.

## Run it (single command)

```bash
cd anki
out/pyenv/bin/python brainlift_eval/bench.py
```

Options:

```bash
out/pyenv/bin/python brainlift_eval/bench.py --cards 50000 --reviews 500
out/pyenv/bin/python brainlift_eval/bench.py --quick          # fewer iterations
```

The script builds a throwaway collection in a temp dir (nothing in the repo is
touched), tags cards across the full Exam P syllabus, reviews a subset to seed
Memory/Readiness, then times each action.

## Actions & budgets

| Action | What it measures | Budget |
|---|---|---|
| `button-ack` | per-answer fatigue hook (`update_state` + `decide`) — runs on every review button press | p95 < 50 ms |
| `next-card` | scheduler fetches the next due card (`sched.getCard`) | p95 < 100 ms |
| `dashboard-load` | build the full dashboard view-model + render HTML | p95 < 1000 ms |
| `dashboard-refresh` | recompute deterministic coverage/measurements | p95 < 500 ms |
| `aggregate-op` | full-collection `topic_mastery` over EVERY syllabus main-topic + subtopic (the sync-ish heavy path) | p95 < 5000 ms |
| `cold-start` | close + reopen collection + first dashboard (proxy) | worst < 2000 ms |
| `peak-memory` | process peak RSS while holding the 50k deck | < 1500 MB |

## Representative result (Apple Silicon, offline)

```
deck size: 50000 cards | deck-gen: ~2s
action                           p50       p95     worst      budget  result
----------------------------------------------------------------------------
button-ack (p95)                0.00      0.00      0.04       <50ms    PASS
next-card (p95)                 0.00      0.00      0.01      <100ms    PASS
dashboard-load (p95)          282.65    284.53    285.10     <1000ms    PASS
dashboard-refresh (p95)       120.86    122.65    124.02      <500ms    PASS
aggregate-op (p95)            420.67    442.62    442.62     <5000ms    PASS
cold-start (proxy)            292.59    292.59    292.59     <2000ms    PASS
peak-memory (50k)                                   140MB      1500MB    PASS

OVERALL: PASS
```

Exact latencies vary by machine; treat these as order-of-magnitude budget checks,
not lab-grade figures. The button-ack / next-card numbers are sub-millisecond
because the per-answer BrainLift work is pure-Python state folding and the
scheduler queue fetch is a single indexed backend call; the dashboard and
aggregate paths dominate because they run the shared Rust `topic_mastery` engine
across all 50k cards.

> Note: the review subset is served through the real V3 scheduler, so the number
> actually reviewed can be smaller than `--reviews` (new-card learning steps).
> This only affects whether Memory/Readiness show a number; every latency path
> still runs over the full 50k-card deck.
