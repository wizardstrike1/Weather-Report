"""SQLite-backed structured working memory for a single challenge project.

This is the source of truth the prompt builder summarises for Claude. We keep
it small and structured on purpose so we send deltas, not transcripts.
"""
from __future__ import annotations

import sqlite3
import os
import threading
from pathlib import Path
from typing import Any

MIGRATIONS = Path(__file__).resolve().parent.parent / "data" / "migrations.sql"


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        # WAL + busy_timeout: tolerate several app instances running at once.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(MIGRATIONS.read_text("utf-8"))
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- generic helpers -------------------------------------------------
    def _exec(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    # ---- meta ------------------------------------------------------------
    def set_meta(self, key: str, value: str) -> None:
        self._exec(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def get_meta(self, key: str, default: str = "") -> str:
        rows = self._all("SELECT value FROM meta WHERE key=?", (key,))
        return rows[0]["value"] if rows else default

    # ---- typed adders ----------------------------------------------------
    def add_fact(self, content: str) -> None:
        self._exec("INSERT INTO facts(content) VALUES(?)", (content,))

    def add_action(self, kind: str, summary: str, success: bool = True) -> None:
        self._exec(
            "INSERT INTO actions(kind,summary,success) VALUES(?,?,?)",
            (kind, summary, int(success)),
        )

    def add_download(self, path: str, source_url: str = "", sha256: str = "") -> None:
        self._exec(
            "INSERT INTO downloads(path,source_url,sha256) VALUES(?,?,?)",
            (path, source_url, sha256),
        )

    def add_tool_output(self, tool: str, argv: str, summary: str, log_path: str) -> None:
        self._exec(
            "INSERT INTO tool_outputs(tool,argv,summary,log_path) VALUES(?,?,?,?)",
            (tool, argv, summary, log_path),
        )

    def add_flag_candidate(self, value: str, source: str, confidence: float) -> None:
        self._exec(
            "INSERT INTO flag_candidates(value,source,confidence) VALUES(?,?,?) "
            "ON CONFLICT(value) DO UPDATE SET confidence=MAX(confidence,excluded.confidence)",
            (value, source, confidence),
        )

    def mark_flag_submitted(self, value: str) -> None:
        self._exec("UPDATE flag_candidates SET submitted=1 WHERE value=?", (value,))

    def add_note(self, content: str, kind: str = "note") -> None:
        self._exec("INSERT INTO notes(content,kind) VALUES(?,?)", (content, kind))

    # ---- readers ---------------------------------------------------------
    def facts(self) -> list[str]:
        return [r["content"] for r in self._all("SELECT content FROM facts ORDER BY id")]

    def recent_actions(self, limit: int = 15) -> list[sqlite3.Row]:
        return self._all(
            "SELECT * FROM actions ORDER BY id DESC LIMIT ?", (limit,)
        )

    def downloads(self) -> list[sqlite3.Row]:
        return self._all("SELECT * FROM downloads ORDER BY id")

    def tool_outputs(self, limit: int = 10) -> list[sqlite3.Row]:
        return self._all(
            "SELECT * FROM tool_outputs ORDER BY id DESC LIMIT ?", (limit,)
        )

    def flag_candidates(self) -> list[sqlite3.Row]:
        return self._all(
            "SELECT * FROM flag_candidates ORDER BY confidence DESC, id DESC"
        )

    def notes(self, kind: str | None = None) -> list[sqlite3.Row]:
        if kind:
            return self._all("SELECT * FROM notes WHERE kind=? ORDER BY id", (kind,))
        return self._all("SELECT * FROM notes ORDER BY id")

    # ---- compact snapshot for the LLM ------------------------------------
    def snapshot(self, max_items: int = 8) -> dict[str, Any]:
        """A small, structured view of state. Intentionally lossy.

        Sent to the model EVERY step, so values are length-clipped to keep
        per-step token cost flat regardless of how big logs/facts grow.
        """
        def trunc(rows: list[Any], n: int = max_items) -> list[Any]:
            return rows[:n]

        def clip(s: Any, n: int) -> str:
            s = str(s)
            return s if len(s) <= n else s[:n] + "…"

        return {
            "challenge": {
                "name": self.get_meta("name"),
                "category": self.get_meta("category"),
                "url": self.get_meta("url"),
                "flag_format": self.get_meta("flag_format"),
                "status": self.get_meta("status", "unsolved"),
            },
            "facts": [clip(f, 400) for f in trunc(self.facts())],
            "tried_actions": [
                {"kind": r["kind"], "summary": clip(r["summary"], 180),
                 "ok": bool(r["success"])}
                for r in self.recent_actions(max_items)
            ],
            "downloads": [
                os.path.basename(r["path"]) for r in self.downloads()
            ][:max_items],
            "tool_outputs": [
                {"tool": r["tool"], "summary": clip(r["summary"], 400)}
                for r in trunc(self.tool_outputs(5), 5)
            ],
            "flag_candidates": [
                {"value": clip(r["value"], 120),
                 "confidence": round(r["confidence"], 2)}
                for r in trunc(self.flag_candidates(), 6)
            ],
            "open_questions": [
                clip(r["content"], 200) for r in self.notes("question")
            ][:5],
            "hypotheses": [
                clip(r["content"], 200) for r in self.notes("hypothesis")
            ][:5],
        }
