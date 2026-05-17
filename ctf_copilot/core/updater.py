"""Self-update support.

The app is a git checkout, so "an update is available" == the local branch is
behind its remote. We fetch quietly and compare. Applying = ``git pull
--ff-only``; the GUI then relaunches the process so new code is loaded.

If this is not a git checkout (zip download / frozen exe) the feature simply
reports unsupported and the GUI hides the banner.
"""
from __future__ import annotations

import shutil
import subprocess

from .proc import NO_WINDOW
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class UpdateStatus:
    supported: bool = False
    behind: int = 0
    ahead: int = 0
    branch: str = "main"
    error: str = ""
    head: str = ""  # current local HEAD commit (to detect on-disk changes)

    @property
    def available(self) -> bool:
        return self.supported and not self.error and self.behind > 0


def _git(*args: str, timeout: int = 25) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, shell=False, **NO_WINDOW,
    )


def is_git_checkout() -> bool:
    return (REPO_ROOT / ".git").exists() and shutil.which("git") is not None


def head_commit() -> str:
    """Short HEAD hash of the on-disk checkout, or '' if unavailable."""
    if not is_git_checkout():
        return ""
    try:
        return _git("rev-parse", "--short", "HEAD", timeout=10).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def check_for_update() -> UpdateStatus:
    if not is_git_checkout():
        return UpdateStatus(supported=False)
    try:
        br = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
        fetched = _git("fetch", "--quiet", "origin", br)
        if fetched.returncode != 0:
            return UpdateStatus(True, branch=br,
                                error=fetched.stderr.strip()[:200])
        behind = int(
            (_git("rev-list", "--count", f"HEAD..origin/{br}").stdout
             or "0").strip() or 0
        )
        ahead = int(
            (_git("rev-list", "--count", f"origin/{br}..HEAD").stdout
             or "0").strip() or 0
        )
        return UpdateStatus(True, behind=behind, ahead=ahead, branch=br,
                            head=head_commit())
    except (subprocess.SubprocessError, ValueError, OSError) as e:
        return UpdateStatus(True, error=str(e)[:200], head=head_commit())


def apply_update(branch: str = "main") -> tuple[bool, str]:
    """Fast-forward pull. Fails (without restarting) if there are local
    changes or the history diverged — the message tells the user what to do."""
    if not is_git_checkout():
        return False, "Not a git checkout — update manually."
    proc = _git("pull", "--ff-only", "origin", branch, timeout=120)
    if proc.returncode == 0:
        return True, (proc.stdout or "Updated.").strip()
    return False, (
        (proc.stderr or proc.stdout).strip()
        + "\n\nResolve manually with: git -C \"%s\" pull --ff-only"
        % REPO_ROOT
    )
