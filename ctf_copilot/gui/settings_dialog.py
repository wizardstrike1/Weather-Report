"""Settings dialog. The API key is intentionally NOT stored here — it is read
from the ANTHROPIC_API_KEY environment variable / .env only.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
)

from ..core.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.config = config
        form = QFormLayout(self)

        self.model = QLineEdit(config.model)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(256, 16384)
        self.max_tokens.setValue(config.max_tokens_per_step)
        self.summarize_n = QSpinBox()
        self.summarize_n.setRange(2, 100)
        self.summarize_n.setValue(config.summarize_after_n_messages)
        self.max_steps = QSpinBox()
        self.max_steps.setRange(0, 100_000)
        self.max_steps.setValue(config.max_solver_steps)
        self.max_steps.setToolTip(
            "0 = no step cap (token budget + Stop govern the run). "
            "A positive value adds a hard step ceiling."
        )
        self.upd_min = QSpinBox()
        self.upd_min.setRange(0, 1440)
        self.upd_min.setValue(config.update_check_minutes)
        self.upd_min.setToolTip(
            "Auto update-check throttle in minutes (checked at startup, then "
            "at most this often when you re-focus the app — no background "
            "polling). 0 = startup + manual only."
        )
        self.allowed = QLineEdit(", ".join(config.allowed_domains))
        self.allow_all = QCheckBox(
            "Allow ALL domains (CTF-only — disables target-scope safety)"
        )
        self.allow_all.setChecked(config.allow_all_domains)
        self.flag_re = QLineEdit(" | ".join(config.flag_regexes))
        self.profile = QLineEdit(config.browser_profile_dir)
        self.headless = QCheckBox("Run browser headless")
        self.headless.setChecked(config.headless)
        self.sandbox = QCheckBox("Sandbox mode (recommended)")
        self.sandbox.setChecked(config.sandbox_mode)
        self.afk = QCheckBox("AFK mode (auto-resolve all prompts)")
        self.afk.setChecked(config.afk_mode)
        self.max_tools = QCheckBox(
            "Maximum tools (unlock angr/sage; longer timeouts)"
        )
        self.max_tools.setChecked(config.max_tools_mode)
        self.research = QCheckBox(
            "Allow internet research (read-only web.search / web.fetch)"
        )
        self.research.setChecked(config.allow_internet_research)
        self.learning = QCheckBox(
            "Enable cross-challenge learning (knowledge base)"
        )
        self.learning.setChecked(config.enable_learning)
        self.auto_submit = QCheckBox("Auto-submit flags (dangerous)")
        self.auto_submit.setChecked(config.auto_submit_flags)
        self.send_shots = QCheckBox("Allow sending screenshots to Claude")
        self.send_shots.setChecked(config.send_screenshots)

        import shutil

        key_state = "set" if config.anthropic_api_key else "NOT set"
        form.addRow(QLabel(f"ANTHROPIC_API_KEY: <b>{key_state}</b> (env/.env only)"))
        self.cli_cmd = QLineEdit(config.claude_cli_command)
        cli_found = "found" if shutil.which(config.claude_cli_command) else "not found"
        form.addRow(
            QLabel(
                f"Fallback when no key: Claude CLI (<b>{cli_found}</b> on PATH)"
            )
        )
        form.addRow("Claude CLI command", self.cli_cmd)
        form.addRow("Model", self.model)
        form.addRow("Max tokens / step", self.max_tokens)
        form.addRow("Summarize after N", self.summarize_n)
        form.addRow("Max solver steps (0 = unlimited)", self.max_steps)
        form.addRow("Auto update-check (min, 0 = off)", self.upd_min)
        form.addRow("Allowed domains (comma-sep)", self.allowed)
        form.addRow(self.allow_all)
        form.addRow("Flag regexes ( | -sep)", self.flag_re)
        form.addRow("Browser profile dir", self.profile)
        form.addRow(self.headless)
        form.addRow(self.sandbox)
        form.addRow(self.afk)
        form.addRow(self.max_tools)
        form.addRow(self.research)
        form.addRow(self.learning)
        form.addRow(self.auto_submit)
        form.addRow(self.send_shots)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _save(self) -> None:
        c = self.config
        c.claude_cli_command = self.cli_cmd.text().strip() or "claude"
        c.model = self.model.text().strip()
        c.max_tokens_per_step = self.max_tokens.value()
        c.summarize_after_n_messages = self.summarize_n.value()
        c.max_solver_steps = self.max_steps.value()
        c.update_check_minutes = self.upd_min.value()
        c.allowed_domains = [
            d.strip() for d in self.allowed.text().split(",") if d.strip()
        ]
        c.allow_all_domains = self.allow_all.isChecked()
        c.flag_regexes = [
            r.strip() for r in self.flag_re.text().split("|") if r.strip()
        ]
        c.browser_profile_dir = self.profile.text().strip()
        c.headless = self.headless.isChecked()
        c.sandbox_mode = self.sandbox.isChecked()
        c.afk_mode = self.afk.isChecked()
        c.max_tools_mode = self.max_tools.isChecked()
        c.allow_internet_research = self.research.isChecked()
        c.enable_learning = self.learning.isChecked()
        c.auto_submit_flags = self.auto_submit.isChecked()
        c.send_screenshots = self.send_shots.isChecked()
        c.save()
        self.accept()
