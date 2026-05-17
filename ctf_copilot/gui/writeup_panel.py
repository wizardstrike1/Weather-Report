"""Writeup preview + export."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class WriteupPanel(QWidget):
    generate_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        self.preview = QPlainTextEdit(readOnly=True)
        lay.addWidget(self.preview)

        row = QHBoxLayout()
        self.gen_btn = QPushButton("Generate writeup now")
        self.open_btn = QPushButton("Open HTML")
        row.addWidget(self.gen_btn)
        row.addWidget(self.open_btn)
        lay.addLayout(row)
        self.gen_btn.clicked.connect(self.generate_requested.emit)

    def show_markdown(self, md_path: Path) -> None:
        try:
            self.preview.setPlainText(md_path.read_text("utf-8"))
        except OSError as e:
            self.preview.setPlainText(f"(could not read writeup: {e})")
