# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""End-to-end proof that BrainLift state syncs two-way through a REAL sync server.

Prior BrainLift tests only proved state survives a local close/reopen
(``test_brainlift_persistence.py``). That shows persistence, not *sync*: the
claim that BrainLift state (diagnostic result, calibration authority, onboarding
profile) and study progress travel between devices was argued, never executed.

This test closes that gap by actually running it:

* It boots Anki's own Rust sync server (``anki.syncserver`` -> the same
  ``SimpleServer`` used by ``docs/syncserver``) on a loopback port with a temp
  data dir, so nothing external / networked is required.
* It creates TWO independent collections pointed at that server.
* Collection 1 sets BrainLift state (onboarding + diagnostic + calibration
  authority multiplier) and does real card reviews, then syncs UP.
* Collection 2 (empty) syncs DOWN and must observe *identical* BrainLift state
  and study progress, with ``sum(reps)`` and the revlog transferred exactly —
  nothing lost, nothing doubled.
* Finally it creates a same-key conflict (both collections edit the same
  BrainLift config key) and asserts Anki's documented last-writer-wins rule:
  the collection that syncs its change last replaces the shared config block, so
  both devices converge on the later writer's value.

All I/O is loopback + temp files and is torn down in fixtures.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

from anki.brainlift import calibration as cal
from anki.brainlift import diagnostic as dx
from anki.brainlift import onboarding as ob
from anki.collection import Collection


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(port: int, timeout: float = 30.0) -> bool:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


@pytest.fixture(scope="module")
def sync_server():
    """Boot Anki's Rust sync server on a loopback port; yield (endpoint, creds)."""
    port = _free_port()
    base = tempfile.mkdtemp(prefix="brainlift_synctest_")
    env = dict(os.environ)
    env.update(
        SYNC_USER1="user:pass",
        SYNC_HOST="127.0.0.1",
        SYNC_PORT=str(port),
        SYNC_BASE=base,
        RUST_LOG="warn",
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", "from anki.syncserver import run_sync_server; run_sync_server()"],
        env=env,
    )
    try:
        if not _wait_health(port):
            proc.terminate()
            pytest.skip("Anki sync server did not start in time")
        yield f"http://127.0.0.1:{port}/"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def _new_collection() -> Collection:
    fd, path = tempfile.mkstemp(suffix=".anki2")
    os.close(fd)
    os.unlink(path)
    return Collection(path)


def _full_sync(col: Collection, endpoint: str, upload: bool) -> None:
    """Perform a full upload or download, mirroring the desktop client flow."""
    auth = col.sync_login("user", "pass", endpoint)
    col.sync_collection(auth, False)  # negotiates; sets required=FULL_*
    col.close_for_full_sync()
    col.full_upload_or_download(auth=auth, server_usn=None, upload=upload)
    col.reopen(after_full_sync=True)


def _normal_sync(col: Collection, endpoint: str) -> int:
    """Perform (and complete) a normal incremental sync; return required code."""
    auth = col.sync_login("user", "pass", endpoint)
    return col.sync_collection(auth, False).required


def _do_reviews(col: Collection, n_notes: int, n_reviews: int) -> None:
    for i in range(n_notes):
        note = col.newNote()
        note["Front"] = f"card {i}"
        note["Back"] = f"answer {i}"
        col.addNote(note)
    done = 0
    while done < n_reviews:
        card = col.sched.getCard()
        if card is None:
            break
        col.sched.answerCard(card, 3)  # "Good"
        done += 1


def test_brainlift_state_syncs_two_way(sync_server):
    """BrainLift state + study progress transfer both directions, none lost/doubled."""
    endpoint = sync_server

    # --- device 1: set BrainLift state + do real reviews, then sync up ---------
    c1 = _new_collection()
    try:
        ob.save_onboarding(
            c1,
            ob.OnboardingInput(
                exam_date="2026-06-01",
                goal_score=7,
                weekly_study_hours=12,
                previous_attempts=1,
                prior_experience=ob.EXPERIENCE_SOME,
            ),
        )
        dx.run_diagnostic(
            c1,
            [dx.DiagnosticResponse("gp1", 2), dx.DiagnosticResponse("uni1", 1)],
        )
        # Calibration authority multiplier is the flat key the scheduler reads.
        c1.set_config(cal.CONFIG_MULTIPLIER_KEY, 0.75)

        _do_reviews(c1, n_notes=4, n_reviews=7)

        reps_1 = c1.db.scalar("select coalesce(sum(reps), 0) from cards")
        revlog_1 = c1.db.scalar("select count() from revlog")
        notes_1 = c1.note_count()
        assert reps_1 == 7 and revlog_1 == 7 and notes_1 == 4

        _full_sync(c1, endpoint, upload=True)
    finally:
        pass

    # --- device 2: empty collection syncs down and must match device 1 ---------
    c2 = _new_collection()
    try:
        _full_sync(c2, endpoint, upload=False)

        # BrainLift state transferred.
        onb = ob.load_onboarding(c2)
        assert onb is not None
        assert onb.goal_score == 7
        assert onb.weekly_study_hours == 12
        assert onb.prior_experience == ob.EXPERIENCE_SOME

        diag = dx.load_diagnostic(c2)
        assert diag is not None
        assert diag.answered == 2

        assert cal.calibration_multiplier(c2) == 0.75

        # Study progress transferred exactly: nothing lost, nothing doubled.
        assert c2.note_count() == notes_1
        assert c2.db.scalar("select coalesce(sum(reps), 0) from cards") == reps_1
        assert c2.db.scalar("select count() from revlog") == revlog_1
    finally:
        c1.close(downgrade=False)
        c2.close(downgrade=False)


def test_brainlift_same_key_conflict_last_writer_wins(sync_server):
    """Same-key edit on two devices resolves last-writer-wins on next sync."""
    endpoint = sync_server

    # Seed the shared server from a fresh device, then bring a second in sync.
    a = _new_collection()
    ob.save_onboarding(
        a, ob.OnboardingInput(exam_date="2026-06-01", goal_score=6, weekly_study_hours=10)
    )
    _do_reviews(a, n_notes=1, n_reviews=1)
    _full_sync(a, endpoint, upload=True)

    b = _new_collection()
    _full_sync(b, endpoint, upload=False)

    try:
        # Device A writes goal_score=5 and syncs first.
        pa = ob.load_onboarding(a)
        pa.goal_score = 5
        ob.save_onboarding(a, pa)
        _normal_sync(a, endpoint)

        # Device B writes goal_score=9 LATER (strictly later mtime) and syncs.
        time.sleep(1.1)
        pb = ob.load_onboarding(b)
        pb.goal_score = 9
        ob.save_onboarding(b, pb)
        _normal_sync(b, endpoint)

        # Device A reconciles by syncing again.
        _normal_sync(a, endpoint)

        # Last writer (device B, goal 9) wins; both devices converge on it.
        assert ob.load_onboarding(a).goal_score == 9
        assert ob.load_onboarding(b).goal_score == 9
    finally:
        a.close(downgrade=False)
        b.close(downgrade=False)
