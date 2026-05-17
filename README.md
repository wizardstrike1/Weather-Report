# CTF Copilot

A local desktop assistant for solving **authorized** Capture-the-Flag
challenges. It drives a real Chromium browser via Playwright, reasons with
Claude using *compact structured observations* (never raw page/screenshot
dumps by default), runs an allowlisted set of local security tools through a
sandboxed runner, and produces a Markdown/HTML writeup when solved.

> ⚠️ **Authorized use only.** See [SECURITY.md](SECURITY.md). All browser
> navigation and network tools are blocked unless the target host is in your
> allowed-domains list.

## Features

- PySide6 desktop GUI: project sidebar, challenge/context input, browser
  action log, agent chat with an "ask user" workflow, tool matrix + outputs,
  notes/hypotheses, flag candidates, writeup preview/export.
- Playwright persistent Chromium session (headed by default, profile persists
  logins). Downloads are intercepted into the project folder and hashed.
- Token-frugal Claude bridge: structured rolling memory, observation deltas,
  per-step + per-session token budget, prompt caching, strict-JSON action
  protocol validated with pydantic before anything executes.
- Data-driven tool registry (web/forensics/stego/crypto/reverse/pwn/osint)
  with graceful degradation and per-OS install hints.
- Dependency-free built-in analyzers (magic-byte ID, safe recursive archive
  extraction, entropy, strings, hex, flag scan, base/XOR/ROT crypto helpers)
  so the app is useful even with no tools installed.
- Sandboxed tool runner: registered templates only, no `shell=True`,
  workspace path enforcement, allowed-domain checks, approval gate for noisy
  scans, full logs kept locally, summaries sent to the model.
- Autonomous solve loop with Step / Auto / Pause / Stop, plus **AFK mode**
  (auto-resolves every prompt for fully unattended runs) and self-authored
  scripts (`file.write` + `tool.run python` with stdin/argv).
- **Cross-challenge learning:** lessons distilled from solved challenges
  (especially hard ones) are stored in a shared knowledge base and injected
  into prompts for future challenges so it improves over time.
- **Opt-in internet research:** read-only `web.search` / `web.fetch`
  (SSRF-guarded: refuses localhost/private hosts), off by default.
- **Token usage tracker** in the toolbar (session / budget / project total).
- **Multi-instance safe:** per-project browser profiles, WAL-mode SQLite,
  atomic config writes — run several instances/projects at once.
- **Manual mode** when no API key is set — the agent asks you each step.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |  *nix: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

cp .env.example .env        # then put your ANTHROPIC_API_KEY in .env
python -m ctf_copilot.app
```

### One-click launch (Windows, no terminal)

After the one-time install above, create app shortcuts:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1
```

This adds **"CTF Copilot"** to your Desktop and Start Menu. Double-click it
to open the GUI with no console window (it runs `launch.pyw` via
`pythonw.exe`). You can also double-click `launch.pyw` directly, or `run.cmd`
for a console fallback. A true standalone `.exe` is available via
`python packaging/build.py` (PyInstaller).

First run: you'll be prompted about manual mode (no key) and allowed domains.
Open **Settings** (Ctrl+,) and add the CTF host (e.g. `ctf.example`) before
browsing.

## Tests

```bash
pip install pytest
pytest
```

The test suite covers the security-critical core (sandboxing, allowed-domain
validation, registry, file analyzer, flag extraction, token budget, JSON
action validation, project/writeup) and needs no Qt, network, or browser.

## Architecture

`gui/` ⇄ `core/` (config, events, permissions, state, project, **solver**) ⇄
`browser/`, `llm/`, `tools/`, `writeup/`. The core is importable headlessly.
See the in-repo plan and module docstrings. `TODO:` markers flag the
post-MVP work (Docker sandbox backend, GUI tool launchers for Ghidra/Burp/ZAP,
PDF export, multimodal screenshot sending, full per-tool arg schemas).

## Packaging

```bash
python packaging/build.py    # PyInstaller one-folder build (see TODOs inside)
```
