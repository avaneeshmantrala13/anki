# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Crash / durability test: kill the app mid-review, reopen, assert no corruption.

Repeatedly (default 20x):

  1. a CHILD process opens the on-disk collection, begins a review, answers cards
     and folds BrainLift fatigue state + config writes, then is **hard-killed**
     with ``os._exit`` — no ``col.close()``, no clean backend shutdown, no chance
     to flush (this is the software equivalent of the OS killing the app / the
     phone being force-stopped / battery-pulled mid-review), and
  2. the PARENT reopens the same collection and runs SQLite ``pragma quick_check``
     + ``pragma integrity_check`` AND Anki's own ``check_database`` (via
     ``Collection.fix_integrity``).

We assert ZERO corruption across all iterations. This works because every write
goes through SQLite's atomic-commit journal (the shared Anki storage core used by
both desktop and Android), so an abrupt kill can lose the last uncommitted
transaction but can never leave a torn/corrupt database.

Run:  ``out/pyenv/bin/python brainlift_eval/crash_test.py``
Options:  --iterations N (default 20)   --cards N (default 300)

Android equivalent (documented in docs/BRAINLIFT_ARCHITECTURE.md): drive a review, then
``adb shell am force-stop com.ichi2.anki`` (or ``adb shell kill -9 <pid>``)
mid-review, relaunch, and run Tools -> Check Database — same zero-corruption
expectation, same SQLite atomic-commit guarantee.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import random
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "out", "pylib"))

from anki.collection import AddNoteRequest, Collection  # noqa: E402
from anki.brainlift import exam_p  # noqa: E402
from anki.brainlift import fatigue as fx  # noqa: E402

DEFAULT_ITERATIONS = 20
DEFAULT_CARDS = 300


def _setup_collection(path: str, n_cards: int) -> None:
    """Create a small tagged Exam P deck and close it CLEANLY (baseline)."""
    col = Collection(path)
    basic = col.models.by_name("Basic")
    deck_id = col.decks.id("Exam P — Crash Test")
    tags = [
        sub.tag(t.key) for t in exam_p.SYLLABUS for sub in t.subtopics
    ]
    reqs = []
    for i in range(n_cards):
        note = col.new_note(basic)
        note["Front"] = f"Crash card {i}"
        note["Back"] = f"Answer {i}"
        note.tags = [tags[i % len(tags)]]
        reqs.append(AddNoteRequest(note=note, deck_id=deck_id))
    col.add_notes(reqs)
    col.decks.set_current(deck_id)
    conf = col.decks.config_dict_for_deck_id(deck_id)
    conf["new"]["perDay"] = n_cards
    conf["rev"]["perDay"] = n_cards
    col.decks.update_config(conf)
    col.close()


def _crash_child(path: str, seed: int) -> None:
    """Open the collection, begin a review, write, then HARD-KILL mid-review.

    Runs in a separate process so ``os._exit`` terminates it without any of the
    normal Python/backend cleanup — simulating an unclean termination.
    """
    rng = random.Random(seed)
    col = Collection(path)
    fx.reset_session(col, now=0)
    # Perform a random number of mid-review writes, then die abruptly.
    n_writes = rng.randint(1, 5)
    for i in range(n_writes):
        card = col.sched.getCard()
        if card is not None:
            col.sched.answerCard(card, rng.choice([2, 3, 4]))
        # BrainLift per-answer state write (config -> DB), the exact hot write
        # path that would be interrupted by a kill mid-review.
        fx.record_answer(col, 2.0 + i, True, "UnivariateRV", now=10 + i)
        col.set_config("brainlift_crash_marker", {"pid": os.getpid(), "i": i})
    # Hard kill: no col.close(), no flush, no clean shutdown.
    os._exit(9)


def _check_integrity(path: str) -> tuple[bool, str]:
    """Reopen and assert integrity. Returns (clean, detail)."""
    col = Collection(path)
    try:
        quick = col.db.scalar("pragma quick_check")
        integrity = col.db.scalar("pragma integrity_check")
        _report, anki_ok = col.fix_integrity()
        clean = (quick == "ok") and (integrity == "ok") and anki_ok
        detail = f"quick_check={quick!r} integrity_check={integrity!r} anki_check_ok={anki_ok}"
        return clean, detail
    finally:
        col.close()


def run(iterations: int = DEFAULT_ITERATIONS, n_cards: int = DEFAULT_CARDS) -> dict:
    ctx = mp.get_context("spawn")
    tmp = tempfile.mkdtemp(prefix="bl_crash_")
    path = os.path.join(tmp, "crash.anki2")

    print("== BrainLift crash / durability test ==")
    print(f"collection: {path}")
    print(f"setting up {n_cards}-card deck ...", flush=True)
    _setup_collection(path, n_cards)

    clean_count = 0
    corruption_count = 0
    print(f"running {iterations} kill-mid-review iterations ...", flush=True)
    for it in range(iterations):
        p = ctx.Process(target=_crash_child, args=(path, 1000 + it))
        p.start()
        p.join(timeout=60)
        if p.is_alive():  # safety: force-terminate a hung child
            p.terminate()
            p.join()
        killed_signal = p.exitcode
        clean, detail = _check_integrity(path)
        if clean:
            clean_count += 1
        else:
            corruption_count += 1
        status = "OK" if clean else "CORRUPT"
        print(f"  iter {it + 1:>2}/{iterations}: child_exit={killed_signal} "
              f"reopen -> {status}  [{detail}]", flush=True)

    passed = corruption_count == 0 and clean_count == iterations
    print("-" * 60)
    print(f"clean reopens: {clean_count}/{iterations}")
    print(f"corruption events: {corruption_count}")
    print(f"RESULT: {'PASS (zero corruption)' if passed else 'FAIL'}")
    return {
        "iterations": iterations,
        "clean": clean_count,
        "corruption": corruption_count,
        "passed": passed,
    }


def _parse_args(argv: list[str]) -> tuple[int, int]:
    iterations, cards = DEFAULT_ITERATIONS, DEFAULT_CARDS
    for i, a in enumerate(argv):
        if a == "--iterations" and i + 1 < len(argv):
            iterations = int(argv[i + 1])
        elif a == "--cards" and i + 1 < len(argv):
            cards = int(argv[i + 1])
    return iterations, cards


if __name__ == "__main__":
    its, cards = _parse_args(sys.argv[1:])
    result = run(its, cards)
    sys.exit(0 if result["passed"] else 1)
