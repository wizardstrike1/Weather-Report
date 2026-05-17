"""Pwn tooling is data-driven via :mod:`ctf_copilot.tools.registry` (category
`pwn`). This module adds Python-native helpers that don't shell out.
"""
from __future__ import annotations

import json
import urllib.request

from .registry import Category

CATEGORY = Category.PWN


def libc_lookup(symbols: dict[str, str], timeout: int = 15) -> str:
    """Identify a libc from leaked symbol addresses via libc.rip (the
    libc-database web API). ``symbols`` maps name -> hex/last-nibbles, e.g.
    {"puts":"0x...","system":"0x..."}. Read-only HTTPS, public host."""
    from .web_research import _assert_safe_host

    if not symbols:
        return "libc: provide at least one symbol=address pair"
    url = "https://libc.rip/api/find"
    _assert_safe_host(url)
    body = json.dumps({"symbols": symbols}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "ctf-copilot"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            res = json.loads(r.read(500_000).decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        return f"libc lookup error: {e}"
    if not res:
        return "libc: no match (check the symbol offsets)"
    lines = []
    for entry in res[:8]:
        sset = entry.get("symbols", {})
        lines.append(
            f"- {entry.get('id','?')}  "
            f"buildid={entry.get('buildid','?')[:16]}  "
            f"download={entry.get('download_url','')}  "
            f"symbols={ {k: sset[k] for k in list(sset)[:6]} }"
        )
    return f"{len(res)} libc match(es):\n" + "\n".join(lines)
