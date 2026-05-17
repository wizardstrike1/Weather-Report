"""Cross-challenge knowledge base.

A single SQLite DB (shared by every project and every running instance) that
records lessons distilled from solved challenges — especially ones the agent
struggled with before getting right. Relevant lessons are injected into the
prompt for new challenges so the agent gets better over time.

Concurrency: WAL + busy_timeout + a small retry make it safe for several app
instances writing at once.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT NOT NULL DEFAULT '',
    title      TEXT NOT NULL DEFAULT '',
    problem    TEXT NOT NULL DEFAULT '',
    solution   TEXT NOT NULL DEFAULT '',
    tags       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@dataclass
class Lesson:
    category: str
    title: str
    problem: str
    solution: str
    tags: str = ""


class KnowledgeBase:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.RLock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _retry(self, fn, *a):
        last: Exception | None = None
        for _ in range(6):
            try:
                with self._lock:
                    return fn(*a)
            except sqlite3.OperationalError as e:  # locked by another instance
                last = e
                time.sleep(0.25)
        if last:
            raise last

    def add_lesson(self, lesson: Lesson) -> None:
        def _ins():
            self._conn.execute(
                "INSERT INTO lessons(category,title,problem,solution,tags) "
                "VALUES(?,?,?,?,?)",
                (lesson.category, lesson.title, lesson.problem,
                 lesson.solution, lesson.tags),
            )
            self._conn.commit()

        self._retry(_ins)

    def count(self) -> int:
        return self._retry(
            lambda: self._conn.execute(
                "SELECT COUNT(*) FROM lessons"
            ).fetchone()[0]
        )

    def relevant(self, category: str, query: str, limit: int = 5) -> list[dict]:
        """Cheap keyword + category scoring (no extra deps / no LLM call)."""
        rows = self._retry(
            lambda: self._conn.execute(
                "SELECT * FROM lessons ORDER BY id DESC LIMIT 500"
            ).fetchall()
        )
        terms = {t for t in _tokens(query) if len(t) > 2}
        cat = (category or "").strip().lower()
        scored: list[tuple[float, dict]] = []
        for r in rows:
            text = f"{r['title']} {r['problem']} {r['solution']} {r['tags']}"
            hay = set(_tokens(text))
            score = len(terms & hay)
            if cat and cat == (r["category"] or "").lower():
                score += 3
            if score > 0:
                scored.append((score, dict(r)))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [d for _, d in scored[:limit]]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _tokens(s: str) -> list[str]:
    return [w for w in "".join(
        c.lower() if (c.isalnum() or c == "_") else " " for c in s
    ).split()]
