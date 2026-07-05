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


def open_calibration(mw: AnkiQt, on_close=None) -> None:
    """Canonical calibration launcher used by BOTH the Tools menu and the home
    button. The dialog is deferred onto the next event-loop tick via
    ``mw.progress.single_shot(0, ...)`` so it never runs nested inside a
    QtWebEngine ``pycmd`` bridge callback — creating a modal dialog and spinning
    a nested event loop (``.exec()``) from inside that callback is a known
    failure mode that leaves the dialog blank/non-functional.
    """
    if mw.col is None:
        return

    def _run() -> None:
        from aqt.brainlift.calibration_dialog import CalibrationDialog

        dlg = CalibrationDialog(mw)
        dlg.exec()
        if on_close is not None:
            on_close()

    mw.progress.single_shot(0, _run, False)


def open_ai_settings(mw: AnkiQt) -> None:
    """Master AI toggle + model + fatigue TEST MODE (all synced via config)."""
    if mw.col is None:
        return
    from anki.brainlift import ai as blai
    from anki.brainlift import fatigue as fx
    from aqt.qt import (
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QLabel,
        QLineEdit,
        QVBoxLayout,
        qconnect,
    )

    col = mw.col
    dlg = QDialog(mw)
    dlg.setWindowTitle("BrainLift — AI settings")
    dlg.setMinimumWidth(460)
    lay = QVBoxLayout()
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(10)

    ai_cb = QCheckBox("Enable AI features (OpenAI analog generation)")
    ai_cb.setChecked(blai.ai_enabled(col))
    lay.addWidget(ai_cb)

    key_note = QLabel(
        "Reads the key only from the OPENAI_API_KEY environment variable. "
        + ("A key is set." if blai.api_key_from_env() else "No key detected — analogs fall back to the deterministic generator.")
    )
    key_note.setWordWrap(True)
    key_note.setStyleSheet("color: palette(mid); font-size: 12px;")
    lay.addWidget(key_note)

    model_label = QLabel("Model:")
    lay.addWidget(model_label)
    model_edit = QLineEdit(blai.ai_model(col))
    lay.addWidget(model_edit)

    fatigue_cb = QCheckBox("Fatigue TEST MODE (intervene immediately for testing)")
    fatigue_cb.setChecked(fx.test_mode(col))
    lay.addWidget(fatigue_cb)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    qconnect(buttons.accepted, dlg.accept)
    qconnect(buttons.rejected, dlg.reject)
    lay.addWidget(buttons)
    dlg.setLayout(lay)

    if dlg.exec():
        blai.set_ai_enabled(col, ai_cb.isChecked())
        blai.set_ai_model(col, model_edit.text().strip() or blai.DEFAULT_MODEL)
        fx.set_test_mode(col, fatigue_cb.isChecked())


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

    calib_action = QAction("BrainLift: Confidence calibration…", mw)
    qconnect(calib_action.triggered, lambda: open_calibration(mw))
    mw.form.menuTools.addAction(calib_action)

    settings_action = QAction("BrainLift: AI settings…", mw)
    qconnect(settings_action.triggered, lambda: open_ai_settings(mw))
    mw.form.menuTools.addAction(settings_action)

    # Feature 2: feed reviews into the fatigue detector (+ visible banner).
    from aqt.brainlift import fatigue_hooks

    fatigue_hooks.install(mw)

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
    # Defer so it runs after Anki's own startup navigation settles. We seed the
    # bundled default Exam P content (if the collection is empty) just before
    # landing, so the coverage/landing view reflects the new cards immediately.
    mw.progress.single_shot(300, lambda: _seed_and_land(mw), False)


def _seed_and_land(mw: AnkiQt) -> None:
    """Seed default content (once, only if empty) then show the landing."""
    if mw.col is not None:
        try:
            from anki.brainlift.default_content import (
                maybe_seed_default_deck,
                repair_garbled_seed,
            )

            added = maybe_seed_default_deck(mw.col)
            # Heal any stale/garbled seed cards from an older (pypdf) build so
            # reviews show readable math; the fix syncs to the phone.
            repaired, removed = repair_garbled_seed(mw.col)
            if added or repaired or removed:
                # Reset so the freshly-seeded/repaired cards are visible everywhere.
                mw.col.reset()
            if repaired or removed:
                from aqt.utils import tooltip

                msg = f"BrainLift fixed {repaired} Exam P question cards"
                if removed:
                    msg += f" and removed {removed} unreadable ones"
                tooltip(msg + ". Sync to update your phone.", parent=mw)
        except Exception:
            # Never let seeding/repair block the user from reaching the landing.
            pass
    open_home(mw)


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
            "can build an honest readiness estimate. It takes about a minute — or "
            "you can skip for now."
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
