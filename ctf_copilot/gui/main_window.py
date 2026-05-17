"""Main window: project sidebar, tabbed panels, solver controls, event wiring."""
from __future__ import annotations

import shutil
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QFileDialog,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QCheckBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.config import AppConfig
from ..core.events import Event, EventBus, EventType
from ..core.project import STATUS_LABELS, Project, read_status
from ..core.solver import Solver
from ..tools import file_analyzer
from ..tools.registry import ToolRegistry
from ..writeup import generator
from .browser_panel import BrowserPanel
from .challenge_panel import ChallengePanel
from .chat_panel import ChatPanel
from .qt_bridge import QtEventBridge
from .settings_dialog import SettingsDialog
from .tools_panel import ToolsPanel
from .worker import SolverWorker
from .writeup_panel import WriteupPanel


def apply_dark(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(37, 37, 38))
    pal.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    pal.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
    pal.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    pal.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    pal.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    pal.setColor(QPalette.ColorRole.Highlight, QColor(38, 110, 183))
    app.setPalette(pal)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, bus: EventBus) -> None:
        super().__init__()
        self.config = config
        self.bus = bus
        self.registry = ToolRegistry(config.tool_paths)
        self.project: Project | None = None
        self.solver: Solver | None = None
        self.worker: SolverWorker | None = None

        self.setWindowTitle("CTF Copilot")
        self.resize(1280, 860)

        # --- sidebar dock ---
        self.sidebar = QListWidget()
        self.sidebar.itemDoubleClicked.connect(self._open_selected_project)
        dock = QDockWidget("Projects", self)
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.addWidget(QLabel("Projects"))
        sl.addWidget(self.sidebar)
        new_btn = QPushButton("New challenge")
        new_btn.clicked.connect(self._new_project)
        sl.addWidget(new_btn)
        dock.setWidget(sw)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._refresh_projects()

        # --- panels ---
        self.challenge = ChallengePanel()
        self.browser = BrowserPanel()
        self.tools = ToolsPanel(self.registry)
        self.chat = ChatPanel()
        self.writeup = WriteupPanel()
        self.browser.import_requested.connect(self._import_files)
        # connect panel signals ONCE (reconnecting per project load would
        # multiply every action by the number of times a project was opened)
        self.challenge.add_hint_btn.clicked.connect(self._add_hint)
        self.writeup.generate_requested.connect(self._generate_writeup)
        self.chat.answer_submitted.connect(
            lambda t: self.solver and self.solver.provide_answer(t)
        )
        self.chat.approval_submitted.connect(
            lambda ok: self.solver and self.solver.provide_approval(ok)
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self.challenge, "Challenge")
        self.tabs.addTab(self.browser, "Browser")
        self.tabs.addTab(self.chat, "Agent")
        self.tabs.addTab(self.tools, "Tools")
        self.tabs.addTab(self.writeup, "Writeup")

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.addLayout(self._control_bar())
        cl.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self._status("Ready")

        self._build_menu()
        self._wire_events()
        self._first_run_check()

    # ---- UI scaffolding --------------------------------------------------
    def _control_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self.step_btn = QPushButton("Step once")
        self.auto_btn = QPushButton("Auto-solve")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")
        self.solve_state = QLabel("idle")
        for b, fn in (
            (self.step_btn, lambda: self._start(auto=False)),
            (self.auto_btn, lambda: self._start(auto=True)),
            (self.pause_btn, self._toggle_pause),
            (self.stop_btn, self._stop),
        ):
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addWidget(QLabel("State:"))
        bar.addWidget(self.solve_state)
        self.token_lbl = QLabel("Tokens: 0")
        self.token_lbl.setToolTip(
            "LLM tokens — this solver session / per-session budget; "
            "and this project's lifetime total."
        )
        bar.addWidget(self.token_lbl)
        bar.addStretch()
        self.afk_chk = QCheckBox("AFK mode (no prompts — auto-resolve)")
        self.afk_chk.setToolTip(
            "Run fully unattended: any user prompt is auto-resolved "
            "(approvals approved, questions answered 'proceed autonomously')."
        )
        self.afk_chk.setChecked(self.config.afk_mode)
        self.afk_chk.toggled.connect(self._toggle_afk)
        bar.addWidget(self.afk_chk)
        return bar

    def _toggle_afk(self, on: bool) -> None:
        self.config.afk_mode = on
        self.config.save()
        if self.solver:
            self.solver.controls.afk = on
        self._status(f"AFK mode {'ON' if on else 'OFF'}")

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("&File")
        a_new = QAction("New challenge", self, shortcut=QKeySequence.StandardKey.New)
        a_new.triggered.connect(self._new_project)
        a_save = QAction("Save project", self,
                         shortcut=QKeySequence.StandardKey.Save)
        a_save.triggered.connect(lambda: self._persist_challenge_inputs(notify=True))
        a_set = QAction("Settings…", self, shortcut="Ctrl+,")
        a_set.triggered.connect(self._open_settings)
        a_quit = QAction("Quit", self, shortcut=QKeySequence.StandardKey.Quit)
        a_quit.triggered.connect(self.close)
        m.addActions([a_new, a_save, a_set])
        m.addSeparator()
        m.addAction(a_quit)

        h = self.menuBar().addMenu("&Help")
        a_about = QAction("Authorized-use notice", self)
        a_about.triggered.connect(
            lambda: QMessageBox.information(
                self, "Authorized use only",
                "CTF Copilot is for challenges you are authorized to attempt. "
                "Network actions are restricted to the allowed-domains list. "
                "See SECURITY.md.",
            )
        )
        h.addAction(a_about)

    # ---- project lifecycle ----------------------------------------------
    def _refresh_projects(self) -> None:
        selected = None
        cur = self.sidebar.currentItem()
        if cur:
            selected = cur.data(Qt.ItemDataRole.UserRole)
        self.sidebar.clear()
        root = Path(self.config.projects_dir)
        for p in sorted(root.glob("*/project.json")):
            folder = p.parent.name
            status = read_status(p.parent)
            label = STATUS_LABELS.get(status, status)
            item = QListWidgetItem(f"{folder}   —   [{label}]")
            item.setData(Qt.ItemDataRole.UserRole, folder)
            self.sidebar.addItem(item)
            if folder == selected:
                self.sidebar.setCurrentItem(item)

    def _new_project(self) -> None:
        name, ok = QInputDialog.getText(self, "New challenge", "Challenge name:")
        if not ok or not name.strip():
            return
        self._persist_challenge_inputs()  # save current before switching
        proj = Project.create(Path(self.config.projects_dir), name.strip())
        self._load_project(proj)
        self._refresh_projects()

    def _open_selected_project(self) -> None:
        item = self.sidebar.currentItem()
        if not item:
            return
        self._persist_challenge_inputs()  # save current before switching
        folder = item.data(Qt.ItemDataRole.UserRole) or item.text()
        root = Path(self.config.projects_dir) / folder
        self._load_project(Project.open(root))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._persist_challenge_inputs()
        if self.solver:
            self.solver.controls.stop = True
            self.solver.shutdown()
        if self.project:
            self.project.close()
        event.accept()

    def _load_project(self, proj: Project) -> None:
        if self.project:
            self.project.close()
        self.project = proj
        self.solver = Solver(proj, self.config, self.bus)
        self.challenge.name.setText(proj.name)
        self.challenge.category.setText(proj.category)
        self.challenge.url.setText(proj.url)
        self.challenge.flag_format.setText(proj.flag_format)
        self.setWindowTitle(f"CTF Copilot — {proj.name}")
        self.challenge.context.setPlainText(proj.state.get_meta("user_context"))
        self._repopulate_panels()
        self._status(f"Loaded project: {proj.name}")

    def _repopulate_panels(self) -> None:
        """Restore the panels from persisted project state on (re)open.

        The data was always saved in state.sqlite; previously nothing read it
        back, so downloads / notes / flags / log looked empty after reopening.
        """
        if not self.project:
            return
        st = self.project.state

        self.browser.reset()
        self.challenge.notes.clear()
        self.challenge.flags.clear()
        self.tools.output.clear()
        self.token_lbl.setText(
            f"Tokens: proj total {st.get_meta('tokens_spent', '0')}"
        )

        for r in st.downloads():
            self.browser.add_download(r["path"], r["sha256"] or "")
        for n in st.notes():
            self.challenge.add_note(n["content"], n["kind"])
        for f in st.flag_candidates():
            self.challenge.add_flag(
                f["value"], f["source"] or "", f["confidence"]
            )
        for o in reversed(st.tool_outputs(limit=40)):
            self.tools.add_result(o["tool"], o["summary"])

        # rebuild a readable browser/action log from recorded history
        self.browser.append("— restored session history —")
        for a in reversed(st.recent_actions(limit=80)):
            flag = "" if a["success"] else "  [failed]"
            self.browser.append(
                f"{a['created_at']} {a['kind']}: {a['summary']}{flag}"
            )
        for r in st.downloads():
            sha = (r["sha256"] or "")[:16]
            self.browser.append(
                f"{r['created_at']} file: {r['path']} "
                f"(sha256 {sha}…) src={r['source_url']}"
            )
        self.browser.append("— end restored history —")

    # ---- solver controls -------------------------------------------------
    def _persist_challenge_inputs(self, *, notify: bool = False) -> None:
        if not self.project:
            return
        self.project.update_metadata(
            self.challenge.name.text().strip(),
            self.challenge.category.text().strip(),
            self.challenge.url.text().strip(),
            self.challenge.flag_format.text().strip(),
        )
        # store context as overwriteable meta (not a new fact every save)
        ctx = self.challenge.context.toPlainText().strip()
        self.project.state.set_meta("user_context", ctx)
        if ctx and ctx != self.project.state.get_meta("user_context_seen"):
            self.project.state.add_fact(f"User context: {ctx}")
            self.project.state.set_meta("user_context_seen", ctx)
        self._refresh_projects()
        if notify:
            self._status(f"Saved project: {self.project.name}")

    def _start(self, auto: bool) -> None:
        if not self.solver:
            QMessageBox.warning(self, "No project", "Create/open a challenge first.")
            return
        if self.worker and self.worker.isRunning():
            return
        self._persist_challenge_inputs()
        self.solver.controls.stop = False
        self.solver.controls.paused = False
        self.solver.controls.afk = self.afk_chk.isChecked()
        self.worker = SolverWorker(self.solver, auto=auto)
        self.worker.finished_run.connect(lambda: self._status("Solver run finished"))
        self.worker.start()

    def _toggle_pause(self) -> None:
        if self.solver:
            self.solver.controls.paused = not self.solver.controls.paused
            self.pause_btn.setText(
                "Resume" if self.solver.controls.paused else "Pause"
            )

    def _stop(self) -> None:
        if self.solver:
            self.solver.controls.stop = True
            self.solver.shutdown()
            self._status("Stopped")

    def _add_hint(self) -> None:
        if not self.project:
            return
        text = self.challenge.hint_edit.text().strip()
        if text:
            self.project.state.add_note(text, "hint")
            self.challenge.add_note(text, "hint")
            self.challenge.hint_edit.clear()

    def _generate_writeup(self) -> None:
        if not self.project:
            return
        paths = generator.generate(self.project)
        self.writeup.show_markdown(paths["markdown"])
        self.writeup.open_btn.clicked.connect(
            lambda: webbrowser.open(paths["html"].as_uri())
        )
        self._status(f"Writeup written to {paths['markdown']}")

    def _import_files(self) -> None:
        if not self.project:
            QMessageBox.warning(self, "No project", "Create/open a challenge first.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import challenge files into the project workspace"
        )
        if not paths:
            return
        from ..browser.download_manager import sha256_of

        flag_re = self.solver._flag_re if self.solver else None
        for src in paths:
            src_p = Path(src)
            dest = self.project.downloads_dir / src_p.name
            n = 1
            while dest.exists():
                dest = self.project.downloads_dir / f"{dest.stem}_{n}{dest.suffix}"
                n += 1
            shutil.copy2(src_p, dest)
            digest = sha256_of(dest)
            self.project.state.add_download(str(dest), f"import:{src}", digest)
            self.browser.add_download(str(dest), digest)
            try:
                res = file_analyzer.analyze(dest, flag_pattern=flag_re)
                self.project.state.add_tool_output(
                    "file_analyzer", str(dest), res.summary(), ""
                )
                self.tools.add_result("file_analyzer (import)", res.summary())
                for fl in res.flag_candidates:
                    self.project.state.add_flag_candidate(fl, f"import:{dest.name}", 0.7)
                    self.challenge.add_flag(fl, f"import:{dest.name}", 0.7)
            except OSError as e:
                self.bus.log(f"analyze failed for {dest}: {e}", "error")
        self.bus.log(f"Imported {len(paths)} file(s) into the workspace")
        self._status(f"Imported {len(paths)} file(s)")

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        dlg.exec()

    # ---- events ----------------------------------------------------------
    def _wire_events(self) -> None:
        self._bridge = QtEventBridge(self.bus)
        self._bridge.event.connect(self._on_event)

    def _on_event(self, ev: Event) -> None:
        p = ev.payload
        if ev.type == EventType.LOG:
            self.browser.append(f"[{p.get('level','info')}] {p.get('message','')}")
        elif ev.type == EventType.ERROR:
            self.browser.append(f"[error] {p.get('message','')}")
            self.chat.system(f"error: {p.get('message','')}")
            self._status(f"Error: {p.get('message','')}")
        elif ev.type == EventType.BROWSER_ACTION:
            self.browser.append(f"browser: {p}")
        elif ev.type == EventType.PAGE_OBSERVED:
            obs = p.get("observation", {})
            self.browser.append(
                f"observed {obs.get('url','')} — {obs.get('title','')}"
            )
        elif ev.type == EventType.DOWNLOAD:
            self.browser.add_download(p.get("path", ""), p.get("sha256", ""))
        elif ev.type == EventType.TOOL_RESULT:
            self.tools.add_result(
                p.get("tool", "?"), p.get("summary", ""), p.get("returncode")
            )
        elif ev.type == EventType.LLM_ACTION:
            self.chat.set_action(
                p.get("hypothesis", ""), p.get("thought", ""), p.get("action", {})
            )
        elif ev.type == EventType.ASK_USER:
            self.chat.ask(p.get("question", ""), approval=p.get("approval", False))
            self.tabs.setCurrentWidget(self.chat)
            self.activateWindow()
            self.raise_()
        elif ev.type == EventType.FLAG_CANDIDATE:
            self.challenge.add_flag(
                p.get("value", ""), p.get("source", ""), p.get("confidence", 0.0)
            )
        elif ev.type == EventType.NOTE:
            self.challenge.add_note(p.get("content", ""), p.get("kind", "note"))
        elif ev.type == EventType.TOKENS:
            self.token_lbl.setText(
                f"Tokens: {p.get('session', 0):,}/"
                f"{p.get('session_limit', 0):,}  "
                f"(proj {p.get('project_total', 0):,}, {p.get('backend','?')})"
            )
        elif ev.type == EventType.SOLVER_STATE:
            state = p.get("state", "?")
            self.solve_state.setText(state)
            step = p.get("step")
            self.chat.system(
                f"solver: {state}" + (f" (step {step})" if step else "")
            )
            if state == "solved":
                self._status(f"SOLVED — flag {p.get('flag','')}")
            # persisted-status transitions should update the sidebar badge
            if state in STATUS_LABELS:
                self._refresh_projects()

    # ---- first run -------------------------------------------------------
    def _status(self, msg: str) -> None:
        self.statusBar().showMessage(msg)

    def _first_run_check(self) -> None:
        from ..llm.claude_client import ClaudeClient

        backend = ClaudeClient(
            self.config.anthropic_api_key, self.config.model,
            self.config.max_tokens_per_step,
            cli_command=self.config.claude_cli_command,
        ).backend
        if backend == "api":
            pass
        elif backend == "cli":
            QMessageBox.information(
                self, "Using the Claude CLI",
                f"No ANTHROPIC_API_KEY, but the '{self.config.claude_cli_command}'"
                " CLI was found on PATH — autonomous solving will shell out to "
                "`claude -p`. Make sure you're logged into the CLI.",
            )
        else:
            QMessageBox.information(
                self, "Manual mode",
                "No ANTHROPIC_API_KEY and no `claude` CLI found. The app runs "
                "in manual mode: the agent asks you for each step. Set the key "
                "in your environment / .env, or install the Claude Code CLI, "
                "to enable autonomous solving.",
            )
        if not self.config.allowed_domains:
            QMessageBox.warning(
                self, "No allowed domains",
                "No allowed domains configured. Browser navigation and network "
                "tools are blocked until you add the CTF host in Settings.",
            )
