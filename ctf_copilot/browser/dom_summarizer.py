"""Reduce a raw observation dict further before it reaches the token budget.

The in-page collector (page_observer) already caps sizes; this trims a live
observation to the smallest useful shape and is the single place to tighten
limits if sessions get token-heavy.
"""
from __future__ import annotations

from typing import Any


def compact_observation(obs: dict[str, Any], max_text: int = 600) -> dict[str, Any]:
    out = dict(obs)
    if "visible_text" in out:
        t = out["visible_text"]
        out["visible_text"] = t[:max_text] + ("…" if len(t) > max_text else "")
    for key in ("links", "buttons", "inputs", "forms"):
        if isinstance(out.get(key), list):
            out[key] = out[key][:15]
    return out
