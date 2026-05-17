"""Tool execution panel: availability matrix + run results + 'Explain' button."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..tools.registry import ToolRegistry


class ToolsPanel(QWidget):
    def __init__(self, registry: ToolRegistry) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Tool availability (missing tools degrade gracefully)"))

        rows = registry.availability()
        self.table = QTableWidget(len(rows), 4)
        self.table.setHorizontalHeaderLabels(
            ["Tool", "Category", "Available", "Install hint"]
        )
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(str(r["name"])))
            self.table.setItem(i, 1, QTableWidgetItem(str(r["category"])))
            self.table.setItem(
                i, 2, QTableWidgetItem("yes" if r["available"] else "—")
            )
            self.table.setItem(
                i, 3, QTableWidgetItem("; ".join(f"{k}: {v}" for k, v in
                                                  dict(r["install"]).items()))
            )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        lay.addWidget(self.table)

        lay.addWidget(QLabel("Tool output"))
        self.output = QPlainTextEdit(readOnly=True)
        lay.addWidget(self.output)

        row = QHBoxLayout()
        self.explain_btn = QPushButton("Explain this result")
        self.copy_btn = QPushButton("Copy output")
        row.addWidget(self.explain_btn)
        row.addWidget(self.copy_btn)
        lay.addLayout(row)
        self.copy_btn.clicked.connect(
            lambda: self.output.selectAll() or self.output.copy()
        )

    def add_result(self, tool: str, summary: str, rc: int | None = None) -> None:
        head = f"\n=== {tool}" + (f" (rc={rc})" if rc is not None else "") + " ==="
        self.output.appendPlainText(head + "\n" + summary)
