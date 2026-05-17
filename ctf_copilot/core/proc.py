"""Shared subprocess kwargs.

On Windows, a console child process spawned from a windowless app (pythonw —
our launcher/shortcut) pops its own console window and steals focus. The
solver shells out every step (the `claude` CLI) plus tools, so this was very
disruptive. ``CREATE_NO_WINDOW`` suppresses the window while output is still
captured via pipes. No-op on non-Windows.
"""
from __future__ import annotations

import subprocess
import sys

if sys.platform == "win32":
    NO_WINDOW: dict = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    }
else:
    NO_WINDOW = {}
