"""A challenge project: directory layout + persisted metadata + state store."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .state import StateStore

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")

SUBDIRS = ("downloads", "artifacts", "screenshots", "logs", "tool_outputs")

# Project lifecycle statuses (persisted in state.meta['status']).
STATUS_INCOMPLETE = "incomplete"
STATUS_INPUT_NEEDED = "input_needed"
STATUS_AWAITING = "awaiting_confirmation"
STATUS_SOLVED = "solved"

STATUS_LABELS = {
    STATUS_INCOMPLETE: "incomplete",
    STATUS_INPUT_NEEDED: "input needed",
    STATUS_AWAITING: "awaiting confirmation",
    STATUS_SOLVED: "solved",
}


def read_status(root: Path) -> str:
    """Cheaply read a project's status without constructing a StateStore
    (used by the sidebar to show a badge per project)."""
    try:
        con = sqlite3.connect(root / "state.sqlite")
        row = con.execute(
            "SELECT value FROM meta WHERE key='status'"
        ).fetchone()
        con.close()
        return (row[0] if row else STATUS_INCOMPLETE) or STATUS_INCOMPLETE
    except sqlite3.Error:
        return STATUS_INCOMPLETE


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "challenge"


@dataclass
class Project:
    root: Path
    name: str
    category: str
    url: str
    flag_format: str
    state: StateStore

    @property
    def downloads_dir(self) -> Path:
        return self.root / "downloads"

    @property
    def screenshots_dir(self) -> Path:
        return self.root / "screenshots"

    @property
    def tool_outputs_dir(self) -> Path:
        return self.root / "tool_outputs"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    # ---- lifecycle -------------------------------------------------------
    @classmethod
    def create(
        cls,
        projects_dir: Path,
        name: str,
        category: str = "",
        url: str = "",
        flag_format: str = "flag{...}",
    ) -> "Project":
        root = projects_dir / slugify(name)
        root.mkdir(parents=True, exist_ok=True)
        for sub in SUBDIRS:
            (root / sub).mkdir(exist_ok=True)
        state = StateStore(root / "state.sqlite")
        proj = cls(root, name, category, url, flag_format, state)
        for key, val in (
            ("name", name),
            ("category", category),
            ("url", url),
            ("flag_format", flag_format),
            ("status", STATUS_INCOMPLETE),
        ):
            state.set_meta(key, val)
        proj._write_manifest()
        return proj

    @classmethod
    def open(cls, root: Path) -> "Project":
        manifest = json.loads((root / "project.json").read_text("utf-8"))
        state = StateStore(root / "state.sqlite")
        return cls(
            root=root,
            name=manifest["name"],
            category=manifest.get("category", ""),
            url=manifest.get("url", ""),
            flag_format=manifest.get("flag_format", "flag{...}"),
            state=state,
        )

    def _write_manifest(self) -> None:
        (self.root / "project.json").write_text(
            json.dumps(
                {
                    "name": self.name,
                    "category": self.category,
                    "url": self.url,
                    "flag_format": self.flag_format,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            "utf-8",
        )

    def update_metadata(
        self, name: str, category: str, url: str, flag_format: str
    ) -> None:
        """Persist editable challenge fields to BOTH project.json (read by
        Project.open) and the state meta table. Without the manifest write,
        edits do not survive a reopen."""
        self.name = name or self.name
        self.category = category
        self.url = url
        self.flag_format = flag_format or self.flag_format
        for key, val in (
            ("name", self.name),
            ("category", self.category),
            ("url", self.url),
            ("flag_format", self.flag_format),
        ):
            self.state.set_meta(key, val)
        self._write_manifest()

    def set_status(self, status: str) -> None:
        self.state.set_meta("status", status)

    @property
    def status(self) -> str:
        return self.state.get_meta("status", STATUS_INCOMPLETE)

    def set_solved(self, solved: bool = True) -> None:
        self.set_status(STATUS_SOLVED if solved else STATUS_INCOMPLETE)

    @property
    def solved(self) -> bool:
        return self.status == STATUS_SOLVED

    def close(self) -> None:
        self.state.close()
