"""LLM backend with graceful fallback.

Backend selection (first available wins):
  1. ``api``    — Anthropic SDK, if ANTHROPIC_API_KEY is set and the package
                   imports. System prompt is sent as a cacheable block.
  2. ``cli``    — shell out to the Claude Code CLI (``claude -p``) if the
                   binary is on PATH. Lets users with no API key but an
                   authenticated CLI still get autonomous reasoning.
  3. ``manual`` — no backend: return an ``ask_user`` action so the app stays
                   fully usable and user-driven.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from .prompt_builder import SYSTEM_PROMPT
from .token_budget import TokenBudget, estimate_tokens

_MANUAL_JSON = (
    '{{"thought_summary":"{msg}",'
    '"hypothesis":"User-driven solving.",'
    '"action":{{"type":"ask_user","name":"",'
    '"args":{{"question":"{msg}"}}}},'
    '"risk":"low","needs_user_approval":false,"notes_to_save":[]}}'
)


def _manual_payload(msg: str) -> str:
    return _MANUAL_JSON.format(msg=msg.replace('"', "'").replace("\n", " "))


@dataclass
class LLMCallResult:
    raw_text: str
    prompt_tokens: int
    completion_tokens: int
    manual_mode: bool = False
    backend: str = "manual"


class ClaudeClient:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        max_tokens: int,
        cli_command: str = "claude",
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.cli_command = cli_command
        self._client = None
        self.backend = "manual"

        if api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=api_key)
                self.backend = "api"
            except Exception:  # missing pkg / bad key -> try next backend
                self._client = None

        if self.backend == "manual":
            self._cli_path = shutil.which(cli_command)
            if self._cli_path:
                self.backend = "cli"

    @property
    def manual_mode(self) -> bool:
        return self.backend == "manual"

    # ---- public ----------------------------------------------------------
    def complete(self, user_message: str, budget: TokenBudget) -> LLMCallResult:
        user_message = budget.fit_prompt(user_message)
        if self.backend == "api":
            return self._complete_api(user_message, budget)
        if self.backend == "cli":
            return self._complete_cli(user_message, budget)
        return LLMCallResult(
            raw_text=_manual_payload(
                "Manual mode: no API key and no `claude` CLI found. "
                "Tell me the next step, or set a key / install the CLI."
            ),
            prompt_tokens=0,
            completion_tokens=0,
            manual_mode=True,
            backend="manual",
        )

    def vision(self, image_path: str, prompt: str,
               budget: TokenBudget) -> str:
        """Send ONE image to Claude and return its textual reading.

        API backend only — Claude has no audio modality and the CLI/manual
        backends have no image input, so they return a clear note. The image
        is Pillow-downscaled to <=1024px JPEG to bound tokens; gated upstream
        by the send_screenshots toggle.
        """
        if self.backend != "api" or self._client is None:
            return ("vision unavailable on this backend (need an "
                    "ANTHROPIC_API_KEY / API mode). Use OCR/zbarimg/strings "
                    "or describe via other tools instead.")
        try:
            import base64
            import io

            from PIL import Image

            im = Image.open(image_path)
            im.thumbnail((1024, 1024))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=80)
            b64 = base64.standard_b64encode(buf.getvalue()).decode()
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=600,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg",
                        "data": b64}},
                    {"type": "text", "text": prompt},
                ]}],
            )
            text = "".join(
                b.text for b in resp.content
                if getattr(b, "type", "") == "text"
            )
            usage = getattr(resp, "usage", None)
            budget.record(getattr(usage, "input_tokens", 1200),
                          getattr(usage, "output_tokens",
                                  estimate_tokens(text)))
            return text.strip() or "(model returned no text)"
        except Exception as e:  # noqa: BLE001
            return f"vision error: {e}"

    # ---- backends --------------------------------------------------------
    def _complete_api(self, user_message: str, budget: TokenBudget) -> LLMCallResult:
        resp = self._client.messages.create(  # type: ignore[union-attr]
            model=self.model,
            max_tokens=self.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
        usage = getattr(resp, "usage", None)
        ptok = getattr(usage, "input_tokens", estimate_tokens(user_message))
        ctok = getattr(usage, "output_tokens", estimate_tokens(text))
        budget.record(ptok, ctok)
        return LLMCallResult(text, ptok, ctok, backend="api")

    def _complete_cli(self, user_message: str, budget: TokenBudget) -> LLMCallResult:
        """Pipe '<system>\\n\\n<user>' to `claude -p` over stdin (no shell).

        Uses ``--output-format json`` so the CLI returns a structured envelope
        ({"type":"result","result":"<assistant text>", "usage":{…}}). We unwrap
        ``result`` before handing it to the strict-JSON parser, so any prose
        Claude Code wraps around the action JSON can't break parsing. Falls
        back to treating stdout as raw text if the envelope is absent.
        """
        prompt = (
            f"{SYSTEM_PROMPT}\n\n{user_message}\n\n"
            "Respond with ONLY the single JSON object specified above. "
            "Do not use any tools. Do not add explanation or markdown."
        )
        try:
            proc = subprocess.run(
                [self._cli_path, "-p", "--output-format", "json"],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",  # Windows locale (e.g. gbk) would crash decode
                timeout=90,
                shell=False,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return LLMCallResult(
                raw_text=_manual_payload(f"claude CLI failed: {e}"),
                prompt_tokens=0,
                completion_tokens=0,
                manual_mode=True,
                backend="cli",
            )
        out = (proc.stdout or "").strip()
        if proc.returncode != 0 or not out:
            return LLMCallResult(
                raw_text=_manual_payload(
                    f"claude CLI returned no usable output "
                    f"(rc={proc.returncode}). {(proc.stderr or '').strip()[:200]}"
                ),
                prompt_tokens=0,
                completion_tokens=0,
                manual_mode=True,
                backend="cli",
            )

        # Unwrap the Claude Code JSON envelope when present.
        import json

        text = out
        ptok = ctok = 0
        try:
            env = json.loads(out)
            if isinstance(env, dict) and "result" in env:
                text = str(env["result"]).strip()
                usage = env.get("usage") or {}
                ptok = int(usage.get("input_tokens", 0) or 0)
                ctok = int(usage.get("output_tokens", 0) or 0)
        except (json.JSONDecodeError, ValueError):
            pass  # not an envelope -> treat stdout as the reply text

        if not text:
            return LLMCallResult(
                raw_text=_manual_payload("claude CLI returned an empty result"),
                prompt_tokens=0, completion_tokens=0,
                manual_mode=True, backend="cli",
            )
        # The CLI envelope reports input_tokens EXCLUDING cached prefix
        # (often ~2), which would make the session budget never trip. Charge
        # the budget the larger of reported vs. our estimate of what we
        # actually sent, so the cap reflects real usage.
        ptok = max(ptok, estimate_tokens(prompt))
        ctok = max(ctok, estimate_tokens(text))
        budget.record(ptok, ctok)
        return LLMCallResult(text, ptok, ctok, backend="cli")
