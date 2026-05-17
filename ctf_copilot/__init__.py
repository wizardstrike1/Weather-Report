"""Weather Report - a desktop assistant for solving authorized CTF challenges.

(The Python package stays ``ctf_copilot`` so launchers/shortcuts keep working;
only the user-facing product name is "Weather Report".)
"""
from pathlib import Path

__version__ = "0.1.0"
APP_NAME = "Weather Report"

_ASSETS = Path(__file__).resolve().parent / "assets"
APP_ICON = _ASSETS / "app.ico"
APP_ICON_PNG = _ASSETS / "app.png"


def icon_path() -> str:
    """Best available icon file path ('' if none)."""
    if APP_ICON.exists():
        return str(APP_ICON)
    if APP_ICON_PNG.exists():
        return str(APP_ICON_PNG)
    return ""
