"""Marshal EventBus events (published from worker threads) onto the Qt thread.

A QObject with a single signal carrying ``Event`` objects. Subscribing the
signal's ``emit`` to the bus is thread-safe because Qt queues cross-thread
signal deliveries automatically.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..core.events import Event, EventBus, EventType


class QtEventBridge(QObject):
    event = Signal(object)  # carries core.events.Event

    def __init__(self, bus: EventBus) -> None:
        super().__init__()
        for etype in EventType:
            bus.subscribe(etype, self._forward)

    def _forward(self, ev: Event) -> None:
        # emit is queued onto the GUI thread by Qt when sender != receiver thread
        self.event.emit(ev)
