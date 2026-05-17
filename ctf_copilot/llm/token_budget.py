"""Crude-but-useful token accounting and truncation.

We avoid a tokenizer dependency: ~4 chars/token is close enough for budgeting.
The point is to *bound* what we send, not to bill precisely.
"""
from __future__ import annotations

from dataclasses import dataclass

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    keep = max_chars // 2
    return (
        text[:keep]
        + f"\n…[{len(text) - max_chars} chars elided to fit token budget]…\n"
        + text[-keep:]
    )


@dataclass
class TokenBudget:
    session_limit: int
    per_step_limit: int          # caps the *completion*, not the prompt
    spent: int = 0
    prompt_token_cap: int = 12000  # hard ceiling on the prompt we send

    def remaining(self) -> int:
        return max(0, self.session_limit - self.spent)

    def can_spend(self, tokens: int) -> bool:
        return self.spent + tokens <= self.session_limit

    def exhausted(self) -> bool:
        """True when there isn't enough left for another meaningful step
        (a prompt + a full completion). This is what terminates an
        unattended run when no step cap is set."""
        return self.remaining() < (self.per_step_limit + 1000)

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.spent += prompt_tokens + completion_tokens

    def fit_prompt(self, text: str) -> str:
        # Bound by the dedicated prompt cap (NOT the completion size) and by
        # whatever session budget is left. Compaction upstream keeps us well
        # under this so the crude head/tail truncation rarely triggers.
        budget = min(self.prompt_token_cap, self.remaining())
        return truncate_to_tokens(text, max(256, budget))
