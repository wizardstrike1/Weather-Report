"""Screenshots are NEVER sent to Claude automatically.

Only when the user toggles ``send_screenshots`` (Settings) or explicitly
approves an ``browser.screenshot`` action does the image become an LLM input.
This module centralises that gate and the base64 encoding.

TODO: when sending, downscale to <=1024px and JPEG-encode to cap tokens; wire
the image block into ClaudeClient.complete (multimodal content).
"""
from __future__ import annotations

import base64
from pathlib import Path


def encode_for_llm(path: str | Path) -> dict[str, str]:
    raw = Path(path).read_bytes()
    return {
        "media_type": "image/png",
        "data": base64.standard_b64encode(raw).decode("ascii"),
    }
