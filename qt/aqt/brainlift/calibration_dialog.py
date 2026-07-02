# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Feature 1 UI — the metacognitive calibration ("confidence authority") test.

Two phases:

1. The user self-rates confidence (Highly confident … Guessing) on
   ``CALIBRATION_TEST_SIZE`` Exam P cards *before* seeing the answer.
2. The user answers ``CALIBRATION_TEST_SIZE`` AI-generated analog MCQs (one per
   rated card; each records its named source). Each analog is graded 1/0.

We then compute deviation, a headline calibration accuracy, a Goodman-Kruskal
gamma, and the confidence-authority multiplier (persisted to synced config),
via :mod:`anki.brainlift.calibration`. Works with AI off (deterministic analogs).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QButtonGroup,
    QDialog,
    QGroupBox,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import showInfo, tooltip

if TYPE_CHECKING:
    from aqt.main import AnkiQt


class CalibrationDialog(QDialog):
    def __init__(self, mw: AnkiQt, parent=None) -> None:
        super().__init__(parent or mw)
        self.mw = mw
        self.setWindowTitle("BrainLift — Confidence calibration")
        self.setMinimumWidth(600)

        from anki.brainlift import ai as blai
        from anki.brainlift import calibration as calib

        self._calib = calib
        self._blai = blai

        col = mw.col
        self.cards = calib.select_calibration_cards(col) if col else []
        self.analogs = calib.build_calibration_questions(col) if col else []
        n = min(len(self.cards), len(self.analogs))
        self.cards = self.cards[:n]
        self.analogs = self.analogs[:n]

        self.confidence_labels: list[str] = []
        self.chosen_indices: list[int] = []
        self.index = 0
        self.phase = "confidence"  # then "answer"

        self._build()
        if not self.cards:
            showInfo(
                "No Exam P cards found to calibrate on. Seed the default deck first.",
                parent=self,
                title="BrainLift",
            )
            self.reject()
            return
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        self.progress = QLabel()
        self.progress.setStyleSheet(
            "color: palette(mid); font-size: 12px; font-weight: 600; letter-spacing:.5px;"
        )
        layout.addWidget(self.progress)

        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        self.prompt.setStyleSheet("font-size:15px; font-weight:500; margin:8px 0;")
        layout.addWidget(self.prompt)

        self.box = QGroupBox("")
        self.box_layout = QVBoxLayout()
        self.box_layout.setSpacing(8)
        self.box_layout.setContentsMargins(12, 10, 12, 12)
        self.box.setLayout(self.box_layout)
        self.group = QButtonGroup(self)
        layout.addWidget(self.box)

        self.next_btn = QPushButton("Next")
        self.next_btn.setMinimumHeight(34)
        qconnect(self.next_btn.clicked, self._on_next)
        layout.addWidget(self.next_btn)

        self.setLayout(layout)

    def _clear(self) -> None:
        for btn in list(self.group.buttons()):
            self.group.removeButton(btn)
            btn.setParent(None)
            btn.deleteLater()
        while self.box_layout.count():
            item = self.box_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _load(self) -> None:
        total = len(self.cards)
        self._clear()
        if self.phase == "confidence":
            cid, front, _back = self.cards[self.index]
            self.progress.setText(
                f"Step 1 of 2 · Rate your confidence — card {self.index + 1} of {total}"
            )
            self.prompt.setText(front)
            self.box.setTitle("Before you see the answer, how confident are you?")
            for i, label in enumerate(self._calib.CONFIDENCE_ORDER):
                rb = QRadioButton(label)
                if label == "Kind of confident":
                    rb.setChecked(True)
                self.group.addButton(rb, i)
                self.box_layout.addWidget(rb)
        else:
            analog = self.analogs[self.index]
            self.progress.setText(
                f"Step 2 of 2 · Answer the analog — question {self.index + 1} of {total}"
            )
            self.prompt.setText(analog.question)
            self.box.setTitle("Your answer")
            for i, choice in enumerate(analog.choices):
                rb = QRadioButton(str(choice))
                self.group.addButton(rb, i)
                self.box_layout.addWidget(rb)

        last = self.index == total - 1
        if self.phase == "confidence":
            self.next_btn.setText("Start analog questions" if last else "Next")
        else:
            self.next_btn.setText("Finish" if last else "Next")

    def _on_next(self) -> None:
        checked = self.group.checkedId()
        if checked < 0:
            tooltip("Please choose an option first.", parent=self)
            return
        total = len(self.cards)
        if self.phase == "confidence":
            self.confidence_labels.append(self._calib.CONFIDENCE_ORDER[checked])
            if self.index < total - 1:
                self.index += 1
            else:
                self.phase = "answer"
                self.index = 0
            self._load()
        else:
            self.chosen_indices.append(checked)
            if self.index < total - 1:
                self.index += 1
                self._load()
            else:
                self._finish()

    def _finish(self) -> None:
        col = self.mw.col
        if col is None:
            self.reject()
            return
        result = self._calib.run_calibration(
            col, self.cards, self.analogs, self.confidence_labels, self.chosen_indices
        )
        ai_note = (
            "analog questions were AI-generated"
            if result.ai_used
            else "AI was off — analogs were generated deterministically"
        )
        gamma = "n/a" if result.gamma is None else f"{result.gamma:+.2f}"
        showInfo(
            f"<b>Calibration complete.</b><br><br>"
            f"Calibration accuracy: <b>{result.accuracy:.0%}</b><br>"
            f"{result.explanation}<br><br>"
            f"Mean deviation: {result.mad:.2f} · resolution (gamma): {gamma}<br>"
            f"Confidence authority applied to scheduling: "
            f"<b>{result.authority_multiplier:.0%}</b><br>"
            f"<span style='color:palette(mid)'>({ai_note}; every analog traces to "
            f"its source card.)</span>",
            parent=self,
            title="BrainLift",
            textFormat="rich",
        )
        self.accept()
