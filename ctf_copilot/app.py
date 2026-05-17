"""CTF Copilot entrypoint.

Loads config, builds the event bus, launches the Qt GUI. Designed so the core
(config/state/tools/llm) is importable headlessly for tests without Qt.
"""
from __future__ import annotations

import sys

from loguru import logger

from .core.config import AppConfig
from .core.events import EventBus, EventType


def main() -> int:
    config = AppConfig.load()

    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> <level>{message}</level>")

    bus = EventBus()
    bus.subscribe(EventType.LOG,
                  lambda e: logger.info(e.payload.get("message", "")))
    bus.subscribe(EventType.ERROR,
                  lambda e: logger.error(e.payload.get("message", "")))

    try:
        from PySide6.QtWidgets import QApplication

        from .gui.main_window import MainWindow, apply_dark
    except ImportError as e:
        logger.error(f"GUI unavailable ({e}). Install PySide6: pip install PySide6")
        return 1

    app = QApplication(sys.argv)
    apply_dark(app)
    win = MainWindow(config, bus)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
