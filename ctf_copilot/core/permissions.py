"""Safety gatekeeper: path sandboxing and allowed-domain validation.

Every filesystem path a tool touches and every network target must pass through
here. Failures raise ``PermissionDenied`` and are surfaced to the user rather
than silently widened.
"""
from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse


class PermissionDenied(Exception):
    """Raised when a sandbox / allowlist check fails."""


class Permissions:
    def __init__(self, workspace: Path, allowed_domains: list[str]) -> None:
        self.workspace = workspace.resolve()
        # store lowercased, strip leading dots
        self.allowed_domains = {d.strip().lower().lstrip(".") for d in allowed_domains if d.strip()}

    # ---- filesystem ------------------------------------------------------
    def resolve_in_workspace(self, candidate: str | Path, *, must_exist: bool = False) -> Path:
        """Resolve ``candidate`` and assert it stays inside the workspace."""
        p = Path(candidate)
        if not p.is_absolute():
            p = self.workspace / p
        p = p.resolve()
        if p != self.workspace and self.workspace not in p.parents:
            raise PermissionDenied(f"Path escapes workspace sandbox: {p}")
        if must_exist and not p.exists():
            raise PermissionDenied(f"Path does not exist: {p}")
        return p

    # ---- network ---------------------------------------------------------
    def _host_allowed(self, host: str) -> bool:
        host = host.lower().strip("[]")  # strip ipv6 brackets
        if not self.allowed_domains:
            return False
        if host in self.allowed_domains:
            return True
        return any(host == d or host.endswith("." + d) for d in self.allowed_domains)

    def check_url(self, url: str) -> str:
        parsed = urlparse(url if "://" in url else "http://" + url)
        host = parsed.hostname or ""
        if not host:
            raise PermissionDenied(f"Cannot parse host from URL: {url!r}")
        if not self._host_allowed(host):
            raise PermissionDenied(
                f"Host {host!r} is not in the allowed-domains list. "
                f"Add it in Settings before targeting it."
            )
        return url

    def check_network_target(self, target: str) -> str:
        """Validate a bare host / host:port target for shell tools."""
        host = target.split("://")[-1].split("/")[0].split(":")[0].strip("[]")
        if self._host_allowed(host):
            return target
        # allow literal IPs only if they resolve from an allowed domain
        try:
            ipaddress.ip_address(host)
            for dom in self.allowed_domains:
                try:
                    if host in {ai[4][0] for ai in socket.getaddrinfo(dom, None)}:
                        return target
                except socket.gaierror:
                    continue
        except ValueError:
            pass
        raise PermissionDenied(f"Network target {target!r} not in allowed domains.")
