"""Application configuration.

Settings precedence (low -> high): defaults -> config.json -> environment.
The API key is never written to config.json; it lives only in the environment
or the OS-level keychain-equivalent left to the user.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

APP_DIR = Path(os.environ.get("CTF_COPILOT_HOME", Path.home() / ".ctf-copilot"))
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_PROJECTS_DIR = APP_DIR / "projects"
KNOWLEDGE_DB = APP_DIR / "knowledge.sqlite"  # shared by all projects/instances

DEFAULT_FLAG_REGEXES = [
    r"flag\{[^}]{1,256}\}",
    r"CTF\{[^}]{1,256}\}",
    r"HTB\{[^}]{1,256}\}",
    r"picoCTF\{[^}]{1,256}\}",
]


class AppConfig(BaseModel):
    """Persisted, non-secret application configuration."""

    model: str = Field(default="claude-opus-4-7")
    max_tokens_per_step: int = Field(default=2048, ge=256, le=16384)
    summarize_after_n_messages: int = Field(default=12, ge=2)
    token_budget_per_session: int = Field(default=400_000, ge=10_000)
    prompt_token_cap: int = Field(default=12_000, ge=1_000, le=180_000)

    projects_dir: str = Field(default=str(DEFAULT_PROJECTS_DIR))
    browser_profile_dir: str = Field(default=str(APP_DIR / "browser-profile"))
    headless: bool = Field(default=False)

    allowed_domains: list[str] = Field(default_factory=list)
    # CTF-only convenience: treat every host as in-scope. OFF by default;
    # disables the target-scope safety net (not the research SSRF guard).
    allow_all_domains: bool = Field(default=False)
    flag_regexes: list[str] = Field(default_factory=lambda: list(DEFAULT_FLAG_REGEXES))

    # fallback LLM backend when no ANTHROPIC_API_KEY: the Claude Code CLI
    claude_cli_command: str = Field(default="claude")

    sandbox_mode: bool = Field(default=True)
    docker_image: str = Field(default="")
    tool_paths: dict[str, str] = Field(default_factory=dict)

    # "Maximum tools": unlock expensive/optional power tools (angr symbolic
    # execution, sage) and raise the per-tool timeout/output ceilings. Does
    # NOT relax the noisy-approval gate or the workspace/domain sandbox.
    max_tools_mode: bool = Field(default=False)

    # AFK mode: when the agent would ask the user, auto-resolve (approve /
    # answer "proceed autonomously") so a run completes with zero interaction.
    afk_mode: bool = Field(default=False)

    # Opt-in read-only internet research (web.search / web.fetch). Separate
    # from the target allow-list; refuses localhost/private hosts.
    allow_internet_research: bool = Field(default=False)
    research_max_bytes: int = Field(default=300_000, ge=10_000, le=5_000_000)

    # Cross-challenge learning (lessons distilled from solved challenges).
    enable_learning: bool = Field(default=True)

    auto_submit_flags: bool = Field(default=False)
    send_screenshots: bool = Field(default=False)
    max_solver_steps: int = Field(default=25, ge=1, le=500)

    # --- not persisted ---
    @property
    def anthropic_api_key(self) -> str | None:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        return key or None

    @classmethod
    def load(cls) -> "AppConfig":
        APP_DIR.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        # env overrides
        if env_model := os.environ.get("CTF_COPILOT_MODEL"):
            data["model"] = env_model
        if env_tok := os.environ.get("CTF_COPILOT_MAX_TOKENS_PER_STEP"):
            data["max_tokens_per_step"] = int(env_tok)
        if env_proj := os.environ.get("CTF_COPILOT_PROJECTS_DIR"):
            data["projects_dir"] = env_proj
        if env_cli := os.environ.get("CTF_COPILOT_CLAUDE_CLI"):
            data["claude_cli_command"] = env_cli
        cfg = cls.model_validate(data)
        Path(cfg.projects_dir).mkdir(parents=True, exist_ok=True)
        return cfg

    def save(self) -> None:
        # Atomic write so concurrent instances never read a half-written file.
        APP_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(f".json.tmp.{os.getpid()}")
        tmp.write_text(self.model_dump_json(indent=2), "utf-8")
        os.replace(tmp, CONFIG_PATH)
