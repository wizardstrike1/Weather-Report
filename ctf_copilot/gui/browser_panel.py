"""Browser action log + downloads list. The actual Chromium window is the
real Playwright browser (headed); this panel mirrors what the agent did.
"""
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


class BrowserPanel(QWidget):
    import_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Filter log…")
        row.addWidget(QLabel("Browser action log"))
        row.addWidget(self.search)
        lay.addLayout(row)

        self.log = QPlainTextEdit(readOnly=True)
        lay.addWidget(self.log)

        dl_row = QHBoxLayout()
        dl_row.addWidget(QLabel("Downloaded / imported files"))
        self.import_btn = QPushButton("Import files…")
        self.import_btn.setToolTip(
            "Copy local challenge files into the project workspace so the "
            "analyzer and agent can use them (and upload them)."
        )
        self.import_btn.clicked.connect(self.import_requested.emit)
        dl_row.addStretch()
        dl_row.addWidget(self.import_btn)
        lay.addLayout(dl_row)
        self.downloads = QListWidget()
        lay.addWidget(self.downloads)

        self.copy_btn = QPushButton("Copy log")
        lay.addWidget(self.copy_btn)
        self.copy_btn.clicked.connect(
            lambda: self.log.selectAll() or self.log.copy()
        )
        self.search.textChanged.connect(self._filter)
        self._all_lines: list[str] = []

    def reset(self) -> None:
        """Clear the live view (used when switching/loading a project before
        the persisted history is replayed back in)."""
        self._all_lines.clear()
        self.log.clear()
        self.downloads.clear()
        self.search.clear()

    def append(self, line: str) -> None:
        self._all_lines.append(line)
        if not self.search.text() or self.search.text().lower() in line.lower():
            self.log.appendPlainText(line)

    def _filter(self, text: str) -> None:
        self.log.clear()
        for ln in self._all_lines:
            if not text or text.lower() in ln.lower():
                self.log.appendPlainText(ln)

    def add_download(self, path: str, sha256: str) -> None:
        self.downloads.addItem(f"{path}  (sha256 {sha256[:16]}…)")
