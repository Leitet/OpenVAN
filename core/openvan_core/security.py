"""Security — a simple 'away mode' for peace of mind.

Feeling unsafe and break-ins are real van-life stressors. This is a deliberately
small local alarm: arm it when you leave, and if a door opens or motion is seen
while armed, the `Intrusion` advisor raises a warning (which the companion speaks
and, once a push channel exists, could notify remotely — see backlog).

State is in memory and defaults to *disarmed* on boot — a restart should never
leave you unknowingly unarmed. Offline and model-free; arming is an explicit user
action, never something the AI decides.
"""

from __future__ import annotations

from typing import Any


class SecuritySystem:
    def __init__(self) -> None:
        self._armed = False

    def arm(self) -> None:
        self._armed = True

    def disarm(self) -> None:
        self._armed = False

    def set_armed(self, armed: bool) -> None:
        self._armed = bool(armed)

    def is_armed(self) -> bool:
        return self._armed

    def status(self) -> dict[str, Any]:
        return {"armed": self._armed}
