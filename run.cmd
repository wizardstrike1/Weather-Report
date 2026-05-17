@echo off
REM Simple double-click launcher (shows a brief console, then the GUI).
REM Prefer the Desktop/Start-Menu shortcut (no console) created by
REM scripts\make_shortcut.ps1.
cd /d "%~dp0"
start "" pythonw -m ctf_copilot.app
