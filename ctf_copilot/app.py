"""Weather Report entrypoint.

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

    # Under pythonw.exe (the no-console launcher / shortcut) sys.stderr and
    # sys.stdout are None — adding a None sink would raise and the app would
    # never start. Always log to a rotating file; add the stderr sink only
    # when a real console stream exists.
    logger.remove()
    try:
        from .core.config import APP_DIR

        APP_DIR.mkdir(parents=True, exist_ok=True)
        logger.add(APP_DIR / "ctf-copilot.log", level="INFO",
                   rotation="2 MB", retention=3, enqueue=True,
                   format="{time:YYYY-MM-DD HH:mm:ss} {level} {message}")
    except Exception:
        pass
    if sys.stderr is not None:
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

    from PySide6.QtGui import QIcon

    from . import APP_NAME, icon_path

    # Windows: distinct AppUserModelID so the taskbar uses our icon, not
    # python/pythonw's.
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "WeatherReport.CTFCopilot"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    if (ip := icon_path()):
        app.setWindowIcon(QIcon(ip))
    apply_dark(app)
    win = MainWindow(config, bus)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
