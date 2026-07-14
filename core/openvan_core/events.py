"""Async publish/subscribe event bus.

The bus is the spine of OpenVan Core. Plugins, the safety layer, the API and
the simulator all communicate through it. Topics are plain strings; subscribing
to ``"*"`` receives every event (used by the WebSocket bridge to the simulator).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[["Event"], Awaitable[None]]


@dataclass(frozen=True)
class Event:
    topic: str
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Minimal asyncio pub/sub. No external dependencies on purpose."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        """Subscribe to a topic (or ``"*"`` for all). Returns an unsubscribe fn."""
        self._subs[topic].append(handler)

        def unsubscribe() -> None:
            handlers = self._subs.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    async def publish(self, topic: str, data: dict[str, Any] | None = None) -> None:
        event = Event(topic=topic, data=data or {})
        handlers = list(self._subs.get(topic, ())) + list(self._subs.get("*", ()))
        if not handlers:
            return
        results = await asyncio.gather(
            *(handler(event) for handler in handlers), return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error("event handler failed for %s: %r", topic, result)
