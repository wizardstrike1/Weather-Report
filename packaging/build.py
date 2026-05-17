"""PyInstaller build helper for CTF Copilot.

    python packaging/build.py

Produces a one-folder bundle in dist/. One-folder (not one-file) is chosen
because Playwright ships browser binaries that must remain on disk.

TODO (post-MVP):
  - bundle/ship the Chromium build, or run `playwright install` on first
    launch from the packaged app and cache under the user data dir.
  - per-OS specs (codesign on macOS, .ico on Windows), Briefcase alternative.
  - exclude PySide6 translations/qml to shrink the bundle.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not installed. Run: pip install pyinstaller")
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--windowed",
        "--name", "CTF-Copilot",
        "--collect-all", "playwright",
        "--collect-submodules", "ctf_copilot",
        str(ROOT / "ctf_copilot" / "app.py"),
    ]
    print("running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
