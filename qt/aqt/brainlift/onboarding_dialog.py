# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Onboarding form for BrainLift (deterministic, no AI).

Collects the student's plan through simple Qt widgets, then persists and
evaluates it with the shared ``anki.brainlift.onboarding`` rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QComboBox,
    QDate,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import showInfo

if TYPE_CHECKING:
    from aqt.main import AnkiQt


class OnboardingDialog(QDialog):
    """Collect exam date, goal score, weekly hours, attempts, experience."""

    def __init__(self, mw: AnkiQt, parent=None) -> None:
        super().__init__(parent or mw)
        self.mw = mw
        self.setWindowTitle("BrainLift — Set up your study plan")
        self.setMinimumWidth(460)
        self._build()

    def _build(self) -> None:
        from anki.brainlift import onboarding as ob

        layout = QVBoxLayout()

        intro = QLabel(
            "Tell BrainLift about your Exam P plan. Everything here is used by "
            "transparent, rule-based logic — no AI — to decide whether you have "
            "time for durable learning or need to focus on the exam."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()

        self.exam_date = QDateEdit()
        self.exam_date.setCalendarPopup(True)
        self.exam_date.setDisplayFormat("yyyy-MM-dd")
        self.exam_date.setDate(QDate.currentDate().addDays(90))
        form.addRow("Exam date", self.exam_date)

        self.goal_score = QDoubleSpinBox()
        self.goal_score.setRange(0.0, 10.0)
        self.goal_score.setSingleStep(0.5)
        self.goal_score.setValue(6.0)
        self.goal_score.setSuffix("  / 10  (6 = pass)")
        form.addRow("Goal score", self.goal_score)

        self.weekly_hours = QSpinBox()
        self.weekly_hours.setRange(1, 80)
        self.weekly_hours.setValue(10)
        self.weekly_hours.setSuffix("  hours / week")
        form.addRow("Weekly study time", self.weekly_hours)

        self.attempts = QSpinBox()
        self.attempts.setRange(0, 20)
        self.attempts.setValue(0)
        form.addRow("Previous Exam P attempts", self.attempts)

        self.experience = QComboBox()
        self.experience.addItem("No prior probability experience", ob.EXPERIENCE_NONE)
        self.experience.addItem("Some probability experience", ob.EXPERIENCE_SOME)
        self.experience.addItem("Strong probability background", ob.EXPERIENCE_STRONG)
        form.addRow("Prior experience", self.experience)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        qconnect(buttons.accepted, self._on_save)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _iso_date(self) -> str:
        d = self.exam_date.date()
        return f"{d.year():04d}-{d.month():02d}-{d.day():02d}"

    def _on_save(self) -> None:
        from anki.brainlift import onboarding as ob

        col = self.mw.col
        if col is None:
            self.reject()
            return

        profile = ob.OnboardingInput(
            exam_date=self._iso_date(),
            goal_score=self.goal_score.value(),
            weekly_study_hours=float(self.weekly_hours.value()),
            previous_attempts=self.attempts.value(),
            prior_experience=self.experience.currentData(),
        )
        result = ob.complete_onboarding(col, profile)

        diag = (
            "A short diagnostic is recommended next so BrainLift can measure your "
            "current ability."
            if result.diagnostic_required
            else "You have enough review history already, so the diagnostic is optional."
        )
        showInfo(
            f"<b>Your plan is saved.</b><br><br>"
            f"Study mode: <b>{result.mode}</b><br>"
            f"Days until exam: {result.days_until_exam}<br>"
            f"Estimated hours available: {result.available_hours:g} "
            f"(durable mastery needs ~{result.estimated_hours_needed:g})<br><br>"
            f"{result.recommendation}<br><br>{diag}",
            parent=self,
            title="BrainLift",
            textFormat="rich",
        )
        self.accept()
