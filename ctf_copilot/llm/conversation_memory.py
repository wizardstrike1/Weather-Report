"""Rolling, structured memory. We deliberately do NOT keep a chat transcript.

Each step we feed Claude: the structured state snapshot + only the *new*
observation delta since last turn. Older observations collapse into facts in
the StateStore. This keeps token use roughly flat regardless of step count.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ConversationMemory:
    summarize_after_n: int = 12
    _last_observation: dict | None = None
    _turn: int = 0
    _running_summary: str = ""
    history_digest: list[str] = field(default_factory=list)

    def observation_delta(self, observation: dict) -> dict:
        """Return only keys whose value changed vs. the previous observation."""
        if self._last_observation is None:
            delta = observation
        else:
            delta = {
                k: v
                for k, v in observation.items()
                if self._last_observation.get(k) != v
            }
        self._last_observation = observation
        return delta or {"unchanged": True}

    def record_turn(self, action_summary: str) -> None:
        self._turn += 1
        self.history_digest.append(f"#{self._turn} {action_summary}")
        if len(self.history_digest) > self.summarize_after_n:
            # collapse oldest half into a one-line running summary
            old = self.history_digest[: self.summarize_after_n // 2]
            self._running_summary = (
                f"{self._running_summary} | earlier: " + "; ".join(old)
            ).strip(" |")
            self.history_digest = self.history_digest[self.summarize_after_n // 2 :]

    def digest_text(self) -> str:
        parts = []
        if self._running_summary:
            parts.append("Earlier (summarised): " + self._running_summary)
        if self.history_digest:
            parts.append("Recent: " + " ".join(self.history_digest))
        return "\n".join(parts)

    def to_json(self) -> str:
        return json.dumps(
            {
                "turn": self._turn,
                "running_summary": self._running_summary,
                "recent": self.history_digest,
            }
        )
