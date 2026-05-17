"""Runs the Solver on a background QThread so the UI stays responsive.

Playwright's sync API requires being created and used on the same thread, so
the session is created lazily inside the worker thread by the Solver.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.solver import Solver


class SolverWorker(QThread):
    finished_run = Signal()

    def __init__(self, solver: Solver, auto: bool) -> None:
        super().__init__()
        self.solver = solver
        self.auto = auto

    def run(self) -> None:  # executes on the worker thread
        try:
            self.solver.run(auto=self.auto)
        finally:
            self.finished_run.emit()
