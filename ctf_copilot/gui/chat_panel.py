"""Chat / agent panel: shows hypothesis + next action, and the 'ask user'
workflow (free-text answer or Approve/Deny for noisy actions & flag submits).
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ChatPanel(QWidget):
    answer_submitted = Signal(str)
    approval_submitted = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)

        self.hypothesis = QLabel("Hypothesis: —")
        self.hypothesis.setWordWrap(True)
        self.next_action = QLabel("Next action: —")
        self.next_action.setWordWrap(True)
        lay.addWidget(self.hypothesis)
        lay.addWidget(self.next_action)

        self.transcript = QPlainTextEdit(readOnly=True)
        lay.addWidget(self.transcript)

        self.prompt_label = QLabel("")
        self.prompt_label.setWordWrap(True)
        lay.addWidget(self.prompt_label)

        row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="Reply to the agent…")
        self.send_btn = QPushButton("Send")
        self.approve_btn = QPushButton("Approve")
        self.deny_btn = QPushButton("Deny")
        for w in (self.input, self.send_btn, self.approve_btn, self.deny_btn):
            row.addWidget(w)
        lay.addLayout(row)

        self.send_btn.clicked.connect(self._send)
        self.input.returnPressed.connect(self._send)
        self.approve_btn.clicked.connect(lambda: self._on_approval(True))
        self.deny_btn.clicked.connect(lambda: self._on_approval(False))

    def _send(self) -> None:
        text = self.input.text().strip()
        if text:
            self.transcript.appendPlainText(f"you> {text}")
            self.answer_submitted.emit(text)
            self.input.clear()
            self._clear_prompt("answer sent")

    def _on_approval(self, ok: bool) -> None:
        self.transcript.appendPlainText(f"you> {'APPROVE' if ok else 'DENY'}")
        self.approval_submitted.emit(ok)
        self._clear_prompt("approved" if ok else "denied")

    def _clear_prompt(self, what: str) -> None:
        self.prompt_label.setText(f"(waiting for the agent — last: {what})")

    def set_action(self, hypothesis: str, thought: str, action: dict) -> None:
        self.hypothesis.setText(f"Hypothesis: {hypothesis}")
        self.next_action.setText(f"Next action: {action}")
        self.transcript.appendPlainText(f"agent> {thought}")

    def system(self, msg: str) -> None:
        """Surface solver state / errors here so the Agent tab is never blank."""
        self.transcript.appendPlainText(f"· {msg}")

    def set_transcript(self, lines: list[str]) -> None:
        """Replace the visible conversation when switching challenges (each
        challenge has its own)."""
        self.hypothesis.setText("Hypothesis: —")
        self.next_action.setText("Next action: —")
        self.prompt_label.setText("")
        self.transcript.setPlainText("\n".join(lines))
        sb = self.transcript.verticalScrollBar()
        sb.setValue(sb.maximum())

    def ask(self, question: str, approval: bool = False) -> None:
        self.prompt_label.setText(f"❓ INPUT NEEDED:\n{question}")
        self.transcript.appendPlainText(f"agent asks> {question}")
        self.approve_btn.setEnabled(approval)
        self.deny_btn.setEnabled(approval)
        self.input.setEnabled(not approval)
        self.send_btn.setEnabled(not approval)
        if approval:
            self.input.setPlaceholderText("Use the Approve / Deny buttons →")
        else:
            self.input.setPlaceholderText(
                "Type your answer here and press Enter / Send"
            )
            self.input.setFocus()
