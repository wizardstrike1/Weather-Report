"""Synchronous Playwright Chromium controller.

Runs on the solver worker thread (not the Qt UI thread). Headed by default with
a persistent profile so CTF logins survive. All navigation is permission-checked
against allowed domains by the caller (solver) before reaching here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .download_manager import DownloadManager
from .page_observer import observe


class PlaywrightSession:
    def __init__(
        self,
        profile_dir: Path,
        downloads_dir: Path,
        screenshots_dir: Path,
        headless: bool = False,
    ) -> None:
        self.profile_dir = profile_dir
        self.screenshots_dir = screenshots_dir
        self.headless = headless
        self._pw = None
        self._ctx = None
        self._page = None
        self._dl = DownloadManager(downloads_dir)
        self._last_download: dict[str, str] | None = None

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            accept_downloads=True,
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self._page.on("download", self._on_download)

    def stop(self) -> None:
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()
        self._pw = self._ctx = self._page = None

    def _ensure(self) -> Any:
        if self._page is None:
            raise RuntimeError("Browser session not started")
        return self._page

    # ---- download hook ---------------------------------------------------
    def _on_download(self, download: Any) -> None:
        self._last_download = self._dl.save(download)

    def take_pending_download(self) -> dict[str, str] | None:
        d, self._last_download = self._last_download, None
        return d

    # ---- actions ---------------------------------------------------------
    def open_url(self, url: str) -> dict[str, Any]:
        page = self._ensure()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return self.observe()

    def click(self, ref_text: str) -> dict[str, Any]:
        page = self._ensure()
        # ref_text is human text or a CSS selector; try selector then text
        try:
            page.click(ref_text, timeout=8000)
        except Exception:
            page.get_by_text(ref_text, exact=False).first.click(timeout=8000)
        page.wait_for_load_state("domcontentloaded")
        return self.observe()

    def fill(self, selector: str, value: str) -> dict[str, Any]:
        self._ensure().fill(selector, value, timeout=8000)
        return self.observe()

    def upload(self, selector: str, file_paths: list[str]) -> dict[str, Any]:
        """Set files on a file <input>. Caller must have validated the paths
        are inside the workspace sandbox before calling."""
        self._ensure().set_input_files(selector, file_paths, timeout=8000)
        return self.observe()

    def submit(self, form_selector: str = "form") -> dict[str, Any]:
        page = self._ensure()
        page.eval_on_selector(form_selector, "f => f.submit()")
        page.wait_for_load_state("domcontentloaded")
        return self.observe()

    def go_back(self) -> dict[str, Any]:
        self._ensure().go_back()
        return self.observe()

    def reload(self) -> dict[str, Any]:
        self._ensure().reload()
        return self.observe()

    def screenshot(self, name: str = "shot") -> str:
        page = self._ensure()
        out = self.screenshots_dir / f"{name}.png"
        page.screenshot(path=str(out), full_page=False)
        return str(out)

    def observe(self, include_storage_values: bool = False) -> dict[str, Any]:
        return observe(self._ensure(), include_storage_values=include_storage_values)
