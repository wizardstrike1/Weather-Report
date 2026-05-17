"""Read-only internet research (opt-in).

Distinct from the target allow-list: research lets the agent look up *general*
help (docs, writeups, algorithms) on the open web. It is GET-only, size- and
time-capped, never sends cookies/credentials, and refuses localhost / private /
link-local hosts so it can't be turned into an SSRF against internal services.
Gated behind config.allow_internet_research.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
import urllib.request

from ..core.permissions import PermissionDenied

_UA = "CTF-Copilot-Research/1.0 (read-only)"
_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_DDG = "https://html.duckduckgo.com/html/?q="
_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I
)


def _assert_safe_host(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise PermissionDenied(f"Research URL must be http(s): {url!r}")
    host = (parsed.hostname or "").lower()
    if not host or host == "localhost" or host.endswith(".local"):
        raise PermissionDenied(f"Refusing research host {host!r}")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise PermissionDenied(f"Cannot resolve {host!r}: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            raise PermissionDenied(
                f"Refusing research host {host!r} -> non-public IP {ip}"
            )
    return url


def _get(url: str, max_bytes: int, timeout: int = 15) -> str:
    _assert_safe_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    return raw.decode("utf-8", "replace")


def html_to_text(html: str, limit: int = 6000) -> str:
    txt = _HTML_RE.sub(" ", _TAG_RE.sub(" ", html))
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:limit]


def search(query: str, max_bytes: int = 200_000, n: int = 6) -> str:
    """DuckDuckGo HTML search -> 'title — url' lines (no JS, no API key)."""
    html = _get(_DDG + urllib.parse.quote(query), max_bytes)
    out: list[str] = []
    for href, title in _RESULT_RE.findall(html)[:n]:
        t = re.sub(r"\s+", " ", _HTML_RE.sub("", title)).strip()
        # DDG wraps links: /l/?uddg=<encoded real url>
        m = re.search(r"uddg=([^&]+)", href)
        real = urllib.parse.unquote(m.group(1)) if m else href
        out.append(f"- {t} — {real}")
    return "\n".join(out) if out else "(no results)"


def fetch(url: str, max_bytes: int = 300_000) -> str:
    return html_to_text(_get(url, max_bytes))
