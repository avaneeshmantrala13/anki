# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""One-command performance benchmark on a ~50,000-card collection.

Builds (or reuses) a large deck in a throwaway collection, tags cards across the
Exam P syllabus, reviews a subset so the dashboard has real data, then measures
p50 / p95 / worst latency for the hot BrainLift actions and reports each against
its stated budget with PASS / FAIL.

Actions measured (budgets are the shipped BrainLift performance targets):

  button-ack        per-answer fatigue hook (update_state + decide)   p95 < 50 ms
  next-card         scheduler fetches the next due card               p95 < 100 ms
  dashboard-load    build the full dashboard view-model + HTML        p95 < 1000 ms
  dashboard-refresh recompute coverage/measurements (no HTML)         p95 < 500 ms
  aggregate-op      full-collection topic_mastery over all sub/topics p95 < 5000 ms
  cold-start        close + reopen collection + first dashboard       proxy < 2000 ms
  peak-memory       process peak RSS while holding the 50k deck       < 1500 MB

The aggregate op is the "sync-ish" heavy path: it runs the shared Rust
``topic_mastery`` engine across every syllabus main-topic AND subtopic search over
the whole 50k deck in one go (the same aggregation a sync/refresh triggers).

Run (single command):

    out/pyenv/bin/python brainlift_eval/bench.py

Options:  --cards N  (default 50000)   --reviews N (default 500)   --quick

Everything is deterministic-enough for repeatable numbers; exact latencies vary
by machine, so treat these as order-of-magnitude budget checks, not lab figures.
See docs/BRAINLIFT_ARCHITECTURE.md (Benchmarks) and brainlift_eval/BENCHMARKS.md.
"""

from __future__ import annotations

import math
import os
import resource
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
# Use the BUILT pylib (needs the compiled Rust backend to open a Collection).
sys.path.insert(0, os.path.join(_HERE, "..", "out", "pylib"))

from anki.collection import AddNoteRequest, Collection  # noqa: E402
from anki.brainlift import dashboard as dash  # noqa: E402
from anki.brainlift import exam_p  # noqa: E402
from anki.brainlift import fatigue as fx  # noqa: E402

# --- stated budgets (ms unless noted) ---------------------------------------
BUDGETS = {
    "button-ack (p95)": ("button_ack", "p95", 50.0, "ms"),
    "next-card (p95)": ("next_card", "p95", 100.0, "ms"),
    "dashboard-load (p95)": ("dashboard_load", "p95", 1000.0, "ms"),
    "dashboard-refresh (p95)": ("dashboard_refresh", "p95", 500.0, "ms"),
    "aggregate-op (p95)": ("aggregate_op", "p95", 5000.0, "ms"),
    "cold-start (proxy)": ("cold_start", "worst", 2000.0, "ms"),
    "peak-memory (50k)": ("peak_memory", "value", 1500.0, "MB"),
}

DEFAULT_CARDS = 50_000
DEFAULT_REVIEWS = 500
BATCH = 1000


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Nearest-rank percentile (q in [0,1]) over an already-sorted list."""
    if not sorted_vals:
        return 0.0
    rank = max(1, math.ceil(q * len(sorted_vals)))
    return sorted_vals[min(rank, len(sorted_vals)) - 1]


def _summ(times_ms: list[float]) -> dict:
    s = sorted(times_ms)
    return {
        "n": len(s),
        "p50": _percentile(s, 0.50),
        "p95": _percentile(s, 0.95),
        "worst": s[-1] if s else 0.0,
    }


def _peak_rss_mb() -> float:
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kilobytes.
    if sys.platform == "darwin":
        return ru / (1024.0 * 1024.0)
    return ru / 1024.0


def _build_deck(col: Collection, n_cards: int) -> float:
    """Add ``n_cards`` Basic notes tagged across the Exam P syllabus. Returns
    wall-clock seconds spent generating the deck."""
    basic = col.models.by_name("Basic")
    assert basic is not None, "Basic notetype missing"
    deck_id = col.decks.id("Exam P — Benchmark")

    # every (topic, subtopic) tag, cycled so all coverage searches have cards
    tags: list[str] = []
    for topic in exam_p.SYLLABUS:
        for sub in topic.subtopics:
            tags.append(sub.tag(topic.key))
    t0 = time.perf_counter()
    made = 0
    while made < n_cards:
        batch = min(BATCH, n_cards - made)
        reqs = []
        for k in range(batch):
            idx = made + k
            note = col.new_note(basic)
            note["Front"] = f"Benchmark card {idx}: P(A|B) for scenario {idx}?"
            note["Back"] = f"Answer {idx} = {(idx * 7) % 97 / 97.0:.4f}"
            note.tags = [tags[idx % len(tags)]]
            reqs.append(AddNoteRequest(note=note, deck_id=deck_id))
        col.add_notes(reqs)
        made += batch
    # select the deck so the scheduler queue serves its (new) cards, and lift the
    # per-day new/review caps so the review subset isn't throttled to ~20 cards.
    col.decks.set_current(deck_id)
    conf = col.decks.config_dict_for_deck_id(deck_id)
    conf["new"]["perDay"] = max(conf["new"]["perDay"], n_cards)
    conf["rev"]["perDay"] = max(conf["rev"]["perDay"], n_cards)
    col.decks.update_config(conf)
    return time.perf_counter() - t0


def _review_subset(col: Collection, n_reviews: int) -> int:
    """Answer up to ``n_reviews`` cards so Memory/Readiness have real data."""
    done = 0
    for _ in range(n_reviews):
        card = col.sched.getCard()
        if card is None:
            break
        col.sched.answerCard(card, 3)  # "Good"
        done += 1
    return done


def _bench_button_ack(iters: int) -> list[float]:
    """Per-answer BrainLift fatigue hook: fold one answer + decide. This is the
    work that runs on every review-button press."""
    times = []
    state = fx.new_session(now=0)
    for i in range(iters):
        rt = 2.0 + (i % 7) * 0.5
        correct = (i % 5) != 0
        t0 = time.perf_counter()
        state = fx.update_state(state, rt, correct, topic_key="UnivariateRV")
        fx.decide(state, test_mode=True, now=i, use_model=True)
        times.append((time.perf_counter() - t0) * 1000.0)
        if state["answers"] > 400:  # keep the rolling window bounded like prod
            state = fx.new_session(now=0)
    return times


def _bench_next_card(col: Collection, iters: int) -> list[float]:
    times = []
    for _ in range(iters):
        t0 = time.perf_counter()
        col.sched.getCard()
        times.append((time.perf_counter() - t0) * 1000.0)
    return times


def _bench_dashboard_load(col: Collection, iters: int) -> list[float]:
    times = []
    for _ in range(iters):
        t0 = time.perf_counter()
        d = dash.build_dashboard(col)
        dash.render_html(d)
        times.append((time.perf_counter() - t0) * 1000.0)
    return times


def _bench_dashboard_refresh(col: Collection, iters: int) -> list[float]:
    """A refresh recomputes the deterministic coverage/measurements (the data
    behind the cards) without re-rendering the full HTML shell."""
    times = []
    for _ in range(iters):
        t0 = time.perf_counter()
        exam_p.coverage_report(col)
        times.append((time.perf_counter() - t0) * 1000.0)
    return times


def _bench_aggregate(col: Collection, iters: int) -> list[float]:
    """Sync-ish heavy path: aggregate the whole 50k deck across EVERY syllabus
    main-topic and subtopic search in one shared-Rust ``topic_mastery`` call."""
    searches = exam_p.main_topic_searches() + exam_p.subtopic_searches()
    times = []
    for _ in range(iters):
        t0 = time.perf_counter()
        col.topic_mastery(searches)
        times.append((time.perf_counter() - t0) * 1000.0)
    return times


def _bench_cold_start(path: str) -> float:
    """Close + reopen the on-disk collection and build the first dashboard."""
    t0 = time.perf_counter()
    col = Collection(path)
    dash.build_dashboard(col)
    elapsed = (time.perf_counter() - t0) * 1000.0
    col.close()
    return elapsed


def run(n_cards: int = DEFAULT_CARDS, n_reviews: int = DEFAULT_REVIEWS,
        quick: bool = False) -> dict:
    iters = {
        "button_ack": 200 if quick else 3000,
        "next_card": 50 if quick else 300,
        "dashboard_load": 5 if quick else 25,
        "dashboard_refresh": 5 if quick else 25,
        "aggregate_op": 3 if quick else 10,
    }
    tmp = tempfile.mkdtemp(prefix="bl_bench_")
    path = os.path.join(tmp, "bench.anki2")
    col = Collection(path)

    print("== BrainLift 50k-card performance benchmark ==")
    print(f"collection: {path}")
    print(f"building deck: {n_cards} cards ...", flush=True)
    gen_s = _build_deck(col, n_cards)
    total_cards = col.card_count()
    print(f"  deck generated in {gen_s:.1f}s ({total_cards} cards)", flush=True)
    reviewed = _review_subset(col, n_reviews)
    print(f"  reviewed {reviewed} cards to seed Memory/Readiness", flush=True)

    results: dict[str, dict] = {}
    print("measuring ...", flush=True)
    results["button_ack"] = _summ(_bench_button_ack(iters["button_ack"]))
    results["next_card"] = _summ(_bench_next_card(col, iters["next_card"]))
    results["dashboard_load"] = _summ(_bench_dashboard_load(col, iters["dashboard_load"]))
    results["dashboard_refresh"] = _summ(
        _bench_dashboard_refresh(col, iters["dashboard_refresh"])
    )
    results["aggregate_op"] = _summ(_bench_aggregate(col, iters["aggregate_op"]))

    col.close()
    cold = _bench_cold_start(path)
    results["cold_start"] = {"worst": cold, "p50": cold, "p95": cold, "n": 1}
    results["peak_memory"] = {"value": _peak_rss_mb()}

    _print_table(results, n_cards, gen_s)
    passed = _evaluate(results)
    print(f"\nOVERALL: {'PASS' if passed else 'FAIL'}")
    results["_passed"] = passed
    return results


def _print_table(results: dict, n_cards: int, gen_s: float) -> None:
    print(f"\ndeck size: {n_cards} cards | deck-gen: {gen_s:.1f}s")
    print(f"{'action':<26}{'p50':>10}{'p95':>10}{'worst':>10}{'budget':>12}{'result':>8}")
    print("-" * 76)
    for label, (key, stat, budget, unit) in BUDGETS.items():
        r = results[key]
        if key == "peak_memory":
            measured = r["value"]
            row_p50 = row_p95 = row_worst = ""
            check = measured
            print(
                f"{label:<26}{'':>10}{'':>10}{measured:>9.0f}{unit}"
                f"{str(int(budget))+unit:>12}"
                f"{('PASS' if check <= budget else 'FAIL'):>8}"
            )
            continue
        check = r[stat]
        p50 = f"{r['p50']:.2f}"
        p95 = f"{r['p95']:.2f}"
        worst = f"{r['worst']:.2f}"
        verdict = "PASS" if check <= budget else "FAIL"
        print(
            f"{label:<26}{p50:>10}{p95:>10}{worst:>10}"
            f"{('<'+format(budget,'.0f')+unit):>12}{verdict:>8}"
        )


def _evaluate(results: dict) -> bool:
    ok = True
    for _label, (key, stat, budget, _unit) in BUDGETS.items():
        r = results[key]
        measured = r["value"] if key == "peak_memory" else r[stat]
        if measured > budget:
            ok = False
    return ok


def _parse_args(argv: list[str]) -> tuple[int, int, bool]:
    cards, reviews, quick = DEFAULT_CARDS, DEFAULT_REVIEWS, False
    for i, a in enumerate(argv):
        if a == "--cards" and i + 1 < len(argv):
            cards = int(argv[i + 1])
        elif a == "--reviews" and i + 1 < len(argv):
            reviews = int(argv[i + 1])
        elif a == "--quick":
            quick = True
    return cards, reviews, quick


if __name__ == "__main__":
    cards, reviews, quick = _parse_args(sys.argv[1:])
    res = run(cards, reviews, quick)
    sys.exit(0 if res.get("_passed") else 1)
