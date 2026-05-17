"""Double-click launcher for CTF Copilot (no console window).

A .pyw file is run by pythonw.exe on Windows, so double-clicking this opens
the GUI with no terminal. It works regardless of the current directory.
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from ctf_copilot.app import main

    raise SystemExit(main())
except SystemExit:
    raise
except BaseException:  # surface startup errors instead of failing silently
    msg = traceback.format_exc()
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "CTF Copilot failed to start", msg)
    except BaseException:
        with open(os.path.join(HERE, "launch-error.log"), "w",
                  encoding="utf-8") as f:
            f.write(msg)
    raise SystemExit(1)
