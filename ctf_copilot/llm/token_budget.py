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
    per_step_limit: int
    spent: int = 0

    def remaining(self) -> int:
        return max(0, self.session_limit - self.spent)

    def can_spend(self, tokens: int) -> bool:
        return self.spent + tokens <= self.session_limit

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.spent += prompt_tokens + completion_tokens

    def fit_prompt(self, text: str) -> str:
        budget = min(self.per_step_limit, self.remaining())
        return truncate_to_tokens(text, max(256, budget))
