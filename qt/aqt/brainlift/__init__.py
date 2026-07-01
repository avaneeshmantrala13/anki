# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Desktop GUI entry point for BrainLift (Exam P).

This registers a clean, guided **landing screen** as a custom main-window state
("brainliftHome") and makes it the first thing users see after their profile
loads — so a newcomer isn't dropped into Anki's deck browser with no direction.
It also adds a "BrainLift" Tools-menu action to return to it, and gates the first
review behind onboarding (skippable). Everything is additive and deterministic;
no AI is used, and no existing Anki behaviour is removed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt import gui_hooks
from aqt.qt import QAction, QMessageBox, qconnect

if TYPE_CHECKING:
    from aqt.main import AnkiQt

STATE = "brainliftHome"

_landed = False
# Session flags for the "complete onboarding before first review" gate.
_skip_gate = False
_gate_active = False


def open_home(mw: AnkiQt) -> None:
    if mw.col is None:
        return
    mw.moveToState(STATE)


def setup_menu(mw: AnkiQt) -> None:
    """Register the landing state + menu action (idempotent)."""
    if getattr(mw, "_brainlift_action", None) is not None:
        return

    from aqt.brainlift import theme
    from aqt.brainlift.home import BrainLiftLanding

    # Skin Anki's built-in screens (deck browser, overview, stats, bars).
    theme.install()

    landing = BrainLiftLanding(mw)
    mw._brainlift_landing = landing
    # Custom main-window state: moveToState("brainliftHome") -> landing.show().
    mw._brainliftHomeState = lambda old_state, *args: landing.show()
    # When leaving the landing, restore the bottom bar we hid.
    mw._brainliftHomeCleanup = lambda new_state: mw.bottomWeb.show()

    action = QAction("BrainLift", mw)
    qconnect(action.triggered, lambda: open_home(mw))
    mw.form.menuTools.addAction(action)
    mw._brainlift_action = action

    gui_hooks.profile_did_open.append(lambda: _land_home(mw))
    gui_hooks.state_did_change.append(
        lambda new_state, old_state: _onboarding_gate(mw, new_state, old_state)
    )


def _land_home(mw: AnkiQt) -> None:
    """Make the BrainLift landing the first screen after the profile loads."""
    global _landed
    if _landed or mw.col is None:
        return
    _landed = True
    # Defer so it runs after Anki's own startup navigation settles.
    mw.progress.single_shot(300, lambda: open_home(mw), False)


# --- "Complete onboarding before first review" gate -------------------------
# The PRD (Feature 1) requires new users to complete onboarding before their
# first review session. This is an additive, skippable, reversible gate: it only
# affects users who have not onboarded, and once onboarded it never fires.


def _onboarding_gate(mw: AnkiQt, new_state: str, old_state: str) -> None:
    global _skip_gate, _gate_active
    if new_state != "review" or _skip_gate or _gate_active:
        return
    if mw.col is None:
        return
    try:
        from anki.brainlift import onboarding as ob

        if ob.is_onboarded(mw.col):
            return
    except Exception:
        return
    mw.progress.single_shot(0, lambda: _do_gate(mw), False)


def _do_gate(mw: AnkiQt) -> None:
    global _skip_gate, _gate_active
    if _gate_active:
        return
    _gate_active = True
    try:
        mw.moveToState(STATE)

        box = QMessageBox(mw)
        box.setWindowTitle("BrainLift")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("Finish your BrainLift setup first")
        box.setInformativeText(
            "BrainLift needs your exam date and goal before your first review so it "
            "can build an honest study plan and readiness estimate. It takes about a "
            "minute — or you can skip for now."
        )
        setup_btn = box.addButton("Set up now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Skip for now", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(setup_btn)
        box.exec()

        if box.clickedButton() is setup_btn:
            from aqt.brainlift.onboarding_dialog import OnboardingDialog

            OnboardingDialog(mw).exec()
            from anki.brainlift import onboarding as ob

            if mw.col is not None and ob.is_onboarded(mw.col):
                mw.moveToState("review")
        else:
            _skip_gate = True
            mw.moveToState("review")
    finally:
        _gate_active = False
