"""A challenge project: directory layout + persisted metadata + state store."""
from __future__ import annotations

import json
import re
import shutil
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


def read_card(root: Path) -> dict:
    """Cheap metadata for the sidebar tree (no StateStore construction)."""
    try:
        m = json.loads((root / "project.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        m = {}
    return {
        "name": m.get("name", root.name),
        "competition": (m.get("competition") or "").strip(),
        "category": (m.get("category") or "").strip(),
        "status": read_status(root),
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


def _comp_slug(competition: str) -> str:
    return slugify(competition) if competition.strip() else "_ungrouped"


def _set_persisted(root: Path, **meta: str) -> None:
    """Write fields to BOTH project.json and the state meta table without
    constructing a StateStore. Caller must ensure the project is not open."""
    mf = root / "project.json"
    try:
        data = json.loads(mf.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.update(meta)
    mf.write_text(json.dumps(data, indent=2), "utf-8")
    try:
        con = sqlite3.connect(root / "state.sqlite")
        for k, v in meta.items():
            con.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, v),
            )
        con.commit()
        con.close()
    except sqlite3.Error:
        pass


def move_project(root: Path, projects_dir: Path, new_competition: str) -> Path:
    """Move a project's folder into another competition group and update its
    persisted competition. The project MUST be closed first (Windows file
    locks). Returns the new root."""
    dest_dir = projects_dir / _comp_slug(new_competition)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / root.name
    n = 1
    while dest.exists():
        dest = dest_dir / f"{root.name}-{n}"
        n += 1
    shutil.move(str(root), str(dest))
    _set_persisted(dest, competition=new_competition)
    return dest


def rename_group(projects_dir: Path, old_competition: str,
                 new_competition: str) -> int:
    """Re-label every project in a competition group. Returns count moved."""
    roots = [
        p.parent for p in projects_dir.rglob("project.json")
        if read_card(p.parent)["competition"] == old_competition.strip()
    ]
    for r in roots:
        move_project(r, projects_dir, new_competition)
    return len(roots)


def delete_project(root: Path) -> None:
    """Remove a project tree. The project MUST be closed first."""
    shutil.rmtree(root, ignore_errors=True)


@dataclass
class Project:
    root: Path
    name: str
    category: str
    url: str
    flag_format: str
    state: StateStore
    competition: str = ""  # grouping label (CTF event); "" = Ungrouped

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
        competition: str = "",
    ) -> "Project":
        # Group projects on disk by competition slug so bulk-imported events
        # stay tidy and folder names don't collide across events.
        comp_slug = slugify(competition) if competition else "_ungrouped"
        root = projects_dir / comp_slug / slugify(name)
        n = 1
        while root.exists():
            root = projects_dir / comp_slug / f"{slugify(name)}-{n}"
            n += 1
        root.mkdir(parents=True, exist_ok=True)
        for sub in SUBDIRS:
            (root / sub).mkdir(exist_ok=True)
        state = StateStore(root / "state.sqlite")
        proj = cls(root, name, category, url, flag_format, state, competition)
        for key, val in (
            ("name", name),
            ("category", category),
            ("url", url),
            ("flag_format", flag_format),
            ("competition", competition),
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
            competition=manifest.get("competition", ""),
        )

    def _write_manifest(self) -> None:
        (self.root / "project.json").write_text(
            json.dumps(
                {
                    "name": self.name,
                    "category": self.category,
                    "url": self.url,
                    "flag_format": self.flag_format,
                    "competition": self.competition,
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
