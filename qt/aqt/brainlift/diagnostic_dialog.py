# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Diagnostic assessment UI for BrainLift (deterministic, no AI).

Presents the author-written Exam P question bank one question at a time, timing
each answer and capturing a confidence rating, then scores the responses with
the shared ``anki.brainlift.diagnostic`` rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aqt.qt import (
    QButtonGroup,
    QDialog,
    QElapsedTimer,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import showInfo, tooltip

if TYPE_CHECKING:
    from aqt.main import AnkiQt


class DiagnosticDialog(QDialog):
    def __init__(self, mw: AnkiQt, parent=None) -> None:
        super().__init__(parent or mw)
        self.mw = mw
        self.setWindowTitle("BrainLift — Diagnostic assessment")
        self.setMinimumWidth(560)

        from anki.brainlift import diagnostic as dx

        self._dx = dx
        self.questions = dx.get_questions()
        self.responses: list = []
        self.index = 0
        self._timer = QElapsedTimer()

        self._build()
        self._load_question()

    def _build(self) -> None:
        layout = QVBoxLayout()

        self.progress = QLabel()
        self.progress.setStyleSheet("color:#6b6b70;")
        layout.addWidget(self.progress)

        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        self.prompt.setStyleSheet("font-size:15px; margin:8px 0;")
        layout.addWidget(self.prompt)

        self.choice_box = QGroupBox("Your answer")
        self.choice_layout = QVBoxLayout()
        self.choice_box.setLayout(self.choice_layout)
        self.choice_group = QButtonGroup(self)
        layout.addWidget(self.choice_box)

        conf_box = QGroupBox("How confident are you?")
        conf_layout = QHBoxLayout()
        self.conf_group = QButtonGroup(self)
        for i, (label, value) in enumerate(
            [
                ("Low", self._dx.CONFIDENCE_LOW),
                ("Medium", self._dx.CONFIDENCE_MEDIUM),
                ("High", self._dx.CONFIDENCE_HIGH),
            ]
        ):
            rb = QRadioButton(label)
            rb.setProperty("conf_value", value)
            if label == "Medium":
                rb.setChecked(True)
            self.conf_group.addButton(rb, i)
            conf_layout.addWidget(rb)
        conf_box.setLayout(conf_layout)
        layout.addWidget(conf_box)

        self.next_btn = QPushButton("Next")
        qconnect(self.next_btn.clicked, self._on_next)
        layout.addWidget(self.next_btn)

        self.setLayout(layout)

    def _clear_choices(self) -> None:
        for btn in list(self.choice_group.buttons()):
            self.choice_group.removeButton(btn)
            btn.setParent(None)
            btn.deleteLater()
        while self.choice_layout.count():
            item = self.choice_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _load_question(self) -> None:
        q = self.questions[self.index]
        total = len(self.questions)
        self.progress.setText(f"Question {self.index + 1} of {total}")
        self.prompt.setText(q.prompt)

        self._clear_choices()
        for i, choice in enumerate(q.choices):
            rb = QRadioButton(choice)
            self.choice_group.addButton(rb, i)
            self.choice_layout.addWidget(rb)

        # Reset confidence to Medium each question.
        for btn in self.conf_group.buttons():
            btn.setChecked(btn.text() == "Medium")

        self.next_btn.setText(
            "Finish" if self.index == total - 1 else "Next"
        )
        self._timer.restart()

    def _on_next(self) -> None:
        chosen = self.choice_group.checkedId()
        if chosen < 0:
            tooltip("Please pick an answer first.", parent=self)
            return

        conf_btn = self.conf_group.checkedButton()
        confidence = (
            conf_btn.property("conf_value")
            if conf_btn is not None
            else self._dx.CONFIDENCE_MEDIUM
        )
        elapsed_s = max(0.0, self._timer.elapsed() / 1000.0)

        q = self.questions[self.index]
        self.responses.append(
            self._dx.DiagnosticResponse(
                question_id=q.id,
                chosen_index=chosen,
                time_seconds=round(elapsed_s, 1),
                confidence=float(confidence),
            )
        )

        if self.index < len(self.questions) - 1:
            self.index += 1
            self._load_question()
        else:
            self._finish()

    def _finish(self) -> None:
        col = self.mw.col
        if col is None:
            self.reject()
            return
        result = self._dx.run_diagnostic(col, self.responses)

        from anki.brainlift import exam_p

        names = {t.key: t.name for t in exam_p.SYLLABUS}
        weak = ", ".join(names.get(k, k) for k in result.weak_topic_keys[:2]) or "none"
        calib = (
            "You were somewhat over-confident."
            if result.calibration_gap > 0.15
            else "Your confidence was reasonably calibrated."
        )
        showInfo(
            f"<b>Diagnostic complete.</b><br><br>"
            f"Overall accuracy: <b>{result.overall_accuracy:.0%}</b> "
            f"({result.answered} questions)<br>"
            f"Average time: {result.avg_time_seconds:g}s per question<br>"
            f"Weakest topics: {weak}<br>"
            f"{calib}<br><br>"
            f"Your study plan now reflects these results.",
            parent=self,
            title="BrainLift",
            textFormat="rich",
        )
        self.accept()
