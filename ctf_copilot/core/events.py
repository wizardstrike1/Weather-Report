"""A tiny thread-safe pub/sub event bus.

The browser session, solver loop and tools run off the GUI thread. They publish
events here; the GUI subscribes and marshals updates onto the Qt thread.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class EventType(str, Enum):
    LOG = "log"
    BROWSER_ACTION = "browser_action"
    PAGE_OBSERVED = "page_observed"
    DOWNLOAD = "download"
    TOOL_RESULT = "tool_result"
    LLM_ACTION = "llm_action"
    ASK_USER = "ask_user"
    FLAG_CANDIDATE = "flag_candidate"
    NOTE = "note"
    SOLVER_STATE = "solver_state"
    ERROR = "error"


@dataclass(slots=True)
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[EventType, list[Callable[[Event], None]]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, etype: EventType, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._subs[etype].append(handler)

    def publish(self, etype: EventType, **payload: Any) -> None:
        event = Event(type=etype, payload=payload)
        with self._lock:
            handlers = list(self._subs.get(etype, []))
        for h in handlers:
            try:
                h(event)
            except Exception:  # a bad subscriber must not break publishers
                pass

    def log(self, message: str, level: str = "info") -> None:
        self.publish(EventType.LOG, message=message, level=level)
