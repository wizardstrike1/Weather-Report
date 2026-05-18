"""Validate the strict-JSON action Claude returns.

Anything that doesn't parse into one of these models is rejected before it can
touch the browser, filesystem or a subprocess. This is the security boundary
between the model and the machine.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

ActionType = Literal[
    "browser.open_url",
    "browser.click",
    "browser.fill",
    "browser.submit",
    "browser.download",
    "browser.upload",
    "browser.screenshot",
    "browser.storage",
    "browser.fetch",
    "browser.wait",
    "file.inspect",
    "file.extract",
    "file.write",
    "vision.look",
    "web.search",
    "web.fetch",
    "tool.run",
    "session.spawn",
    "session.send",
    "session.recv",
    "session.close",
    "net.connect",
    "net.send",
    "net.recv",
    "net.close",
    "notes.add",
    "ask_user",
    "flag.submit_candidate",
    "writeup.update",
    "done",
]


class Action(BaseModel):
    type: ActionType
    name: str = ""                       # tool name (tool.run) / element id
    args: dict[str, str] = Field(default_factory=dict)

    @field_validator("args", mode="before")
    @classmethod
    def _coerce_args(cls, v: Any) -> dict[str, str]:
        """The model legitimately sends bools/ints (full=true, max_bytes=4096).
        Coerce every value to a string instead of rejecting the whole action
        (downstream sandbox/runner all expect string args)."""
        if not isinstance(v, dict):
            return {}
        out: dict[str, str] = {}
        for k, val in v.items():
            if isinstance(val, bool):
                out[str(k)] = "true" if val else "false"
            elif isinstance(val, (str, int, float)):
                out[str(k)] = str(val)
            elif val is None:
                out[str(k)] = ""
            else:  # list/dict -> compact JSON
                out[str(k)] = json.dumps(val, separators=(",", ":"))
        return out


class LLMResponse(BaseModel):
    thought_summary: str = ""
    hypothesis: str = ""
    # Either a single action OR a short batch the host runs in order
    # (amortises the per-call prompt — big win on the no-cache CLI backend).
    action: Action | None = None
    actions: list[Action] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"] = "low"
    needs_user_approval: bool = False
    notes_to_save: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _need_one(self) -> "LLMResponse":
        if self.action is None and not self.actions:
            raise ValueError("response needs 'action' or 'actions'")
        return self

    def steps(self) -> list[Action]:
        return self.actions if self.actions else [self.action]  # type: ignore


def parse_llm_response(text: str) -> LLMResponse:
    """Extract the first JSON object and validate it. Raises ValueError."""
    text = text.strip()
    # tolerate ```json fences
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response")
    try:
        data = json.loads(text[start : end + 1])
        return LLMResponse.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Invalid action JSON: {e}") from e
