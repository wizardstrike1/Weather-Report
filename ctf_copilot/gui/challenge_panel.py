"""Challenge / context input + notes, hypotheses and flag-candidate views."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ChallengePanel(QWidget):
    reset_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)

        self.name = QLineEdit(placeholderText="Challenge name")
        self.category = QLineEdit(placeholderText="Category (web, pwn, crypto…)")
        self.url = QLineEdit(placeholderText="https://ctf.example/challenge")
        self.flag_format = QLineEdit("flag{...}")
        self.context = QPlainTextEdit()
        self.context.setPlaceholderText(
            "Context, given hints, credentials, constraints, known flags…"
        )
        for w, label in (
            (self.name, "Name"),
            (self.category, "Category"),
            (self.url, "URL"),
            (self.flag_format, "Flag format"),
        ):
            lay.addWidget(QLabel(label))
            lay.addWidget(w)
        lay.addWidget(QLabel("Context / hints"))
        lay.addWidget(self.context)

        hint_row = QHBoxLayout()
        self.hint_edit = QLineEdit(placeholderText="Add a hint from the CTF")
        self.add_hint_btn = QPushButton("Add hint")
        hint_row.addWidget(self.hint_edit)
        hint_row.addWidget(self.add_hint_btn)
        lay.addLayout(hint_row)

        self.reset_btn = QPushButton("Reset challenge (clear agent progress)")
        self.reset_btn.setToolTip(
            "Wipe facts, tool runs, flags, notes/hypotheses and generated "
            "artifacts/logs/screenshots. Keeps name/category/URL/context, "
            "your hints, downloaded files and the browser login."
        )
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        lay.addWidget(self.reset_btn)

        lay.addWidget(QLabel("Notes / hypotheses"))
        self.notes = QListWidget()
        lay.addWidget(self.notes)

        lay.addWidget(QLabel("Flag candidates"))
        self.flags = QListWidget()
        lay.addWidget(self.flags)

    def add_note(self, text: str, kind: str = "note") -> None:
        self.notes.addItem(f"[{kind}] {text}")

    def add_flag(self, value: str, source: str, conf: float) -> None:
        self.flags.addItem(f"{value}  ({source}, conf={conf:.2f})")
