"""Execute a built command with timeout, rate limiting, capture & summarise.

Full stdout/stderr is always persisted to ``tool_outputs/``. Only a truncated,
summarised view is returned for the LLM.
"""
from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..core.permissions import PermissionDenied, Permissions
from .registry import ToolRegistry, ToolSpec
from .sandbox import build_command

MAX_SUMMARY_CHARS = 4000


@dataclass
class ToolResult:
    tool: str
    argv: list[str]
    returncode: int
    summary: str          # truncated, safe to send to the LLM
    log_path: Path
    timed_out: bool
    duration_s: float


def _summarise(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n...[{len(text) - limit} chars truncated; full log saved]...\n{tail}"


class ToolRunner:
    def __init__(
        self,
        registry: ToolRegistry,
        perms: Permissions,
        out_dir: Path,
        min_interval_s: float = 1.0,
    ) -> None:
        self._registry = registry
        self._perms = perms
        self._out_dir = out_dir
        self._min_interval = min_interval_s
        self._last_run = 0.0

    def run(
        self,
        name: str,
        args: dict[str, str],
        *,
        timeout_s: int = 120,
        approved: bool = False,
    ) -> ToolResult:
        spec: ToolSpec | None = self._registry.get(name)
        if spec is None:
            raise PermissionDenied(f"Unknown tool {name!r} (not in registry)")
        binary = self._registry.resolve_binary(spec)
        if binary is None:
            raise PermissionDenied(
                f"Tool {name!r} not installed. Install hint: {spec.install}"
            )
        if spec.noisy and not approved:
            raise PermissionDenied(
                f"Tool {name!r} is noisy and needs explicit user approval."
            )

        built = build_command(spec, binary, args, self._perms)

        # Optional: extra argv for script runners (python/python3). Parsed as
        # a JSON list or shell-style split, but each item is still passed as a
        # separate argv element (shell=False) — never interpreted by a shell.
        extra = args.get("script_args", "").strip()
        if extra:
            try:
                parsed = json.loads(extra)
                items = (
                    [str(x) for x in parsed]
                    if isinstance(parsed, list)
                    else shlex.split(extra)
                )
            except (json.JSONDecodeError, ValueError):
                items = shlex.split(extra)
            built.argv.extend(items)

        stdin_data = args.get("stdin")

        # rate limit
        wait = self._min_interval - (time.monotonic() - self._last_run)
        if wait > 0:
            time.sleep(wait)

        started = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                built.argv,
                cwd=built.cwd,
                input=stdin_data,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",  # tool output is rarely the Windows locale
                timeout=timeout_s,
                shell=False,
            )
            rc = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            rc = -1
            stdout = e.stdout or ""
            stderr = (e.stderr or "") + f"\n[timed out after {timeout_s}s]"
        self._last_run = time.monotonic()
        duration = self._last_run - started

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        log_path = self._out_dir / f"{name}-{ts}.log"
        log_path.write_text(
            f"$ {' '.join(built.argv)}\n\n=== STDOUT ===\n{stdout}\n"
            f"=== STDERR ===\n{stderr}\n",
            "utf-8",
        )

        combined = stdout if stdout.strip() else stderr
        return ToolResult(
            tool=name,
            argv=built.argv,
            returncode=rc,
            summary=_summarise(combined),
            log_path=log_path,
            timed_out=timed_out,
            duration_s=round(duration, 2),
        )
