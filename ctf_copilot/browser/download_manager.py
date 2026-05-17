"""Persist Playwright downloads into the project's downloads/ directory and
hash them, so they can be analysed and referenced in the writeup.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class DownloadManager:
    def __init__(self, downloads_dir: Path) -> None:
        self.downloads_dir = downloads_dir
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def save(self, download: Any) -> dict[str, str]:
        """``download`` is a Playwright Download object."""
        suggested = download.suggested_filename or "download.bin"
        target = self.downloads_dir / Path(suggested).name
        n = 1
        while target.exists():
            target = self.downloads_dir / f"{target.stem}_{n}{target.suffix}"
            n += 1
        download.save_as(str(target))
        return {
            "path": str(target),
            "filename": target.name,
            "sha256": sha256_of(target),
            "source_url": download.url,
        }
