"""Security cameras plugin.

Van/RV camera setups are a mix of a wired rear/observation camera and a few
wireless (Wi-Fi or 4G-LTE) cams — Reolink, Eufy, Wyze, Ring, Furrion and friends
(see docs/CAMERAS.md). They aren't numeric sensors, so each camera is a semantic
``camera.*`` entity whose state + attributes come from three raw twin signals:

    camera.<id>.online     -> entity state "online" / "offline"
    camera.<id>.motion     -> attributes.motion
    camera.<id>.recording  -> attributes.recording

That keeps them driveable from the Hardware Bench and readable by the product UI
(Rule 1), and it's the exact shape a real RTSP/ONVIF/cloud backend fills in later.

Category: security. Domain: cameras.
"""

from __future__ import annotations

from dataclasses import dataclass

from openvan_core import Entity, Plugin


@dataclass
class _Camera:
    id: str
    label: str
    location: str  # rear | cabin | door | awning
    connection: str  # wired | wifi | 4g


# A typical build: wired reversing/observation, Wi-Fi interior + doorbell, and a
# 4G-LTE exterior for off-grid alerts.
CAMERAS = [
    _Camera("rear", "Rear View", "rear", "wired"),
    _Camera("cabin", "Cabin", "cabin", "wifi"),
    _Camera("entry", "Entry / Door", "door", "wifi"),
    _Camera("awning", "Side / Awning", "awning", "4g"),
]


class Cameras(Plugin):
    domain = "cameras"
    name = "Security Cameras"
    version = "0.1.0"
    categories = ["security"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._unwatchers = []

    def _sig(self, cam_id: str, field: str) -> str:
        return f"camera.{cam_id}.{field}"

    async def async_setup(self) -> None:
        for cam in CAMERAS:
            online = bool(await self.backend.read(self._sig(cam.id, "online"), True))
            entity = Entity(
                entity_id=f"camera.{cam.id}",
                name=cam.label,
                domain="camera",
                category="security",
                state="online" if online else "offline",
                unit=None,
                attributes={
                    "location": cam.location,
                    "connection": cam.connection,
                    "motion": bool(await self.backend.read(self._sig(cam.id, "motion"), False)),
                    "recording": bool(
                        await self.backend.read(self._sig(cam.id, "recording"), False)
                    ),
                },
            )
            await self.hub.register_entity(entity)
            for field in ("online", "motion", "recording"):
                self._unwatchers.append(self._watch(cam.id, field))

    def _watch(self, cam_id: str, field: str):
        async def _on_change(_key: str, _value) -> None:
            await self._refresh(cam_id)

        return self.backend.watch(self._sig(cam_id, field), _on_change)

    async def _refresh(self, cam_id: str) -> None:
        entity = self.hub.get_entity(f"camera.{cam_id}")
        if entity is None:
            return
        online = bool(await self.backend.read(self._sig(cam_id, "online"), True))
        await self.hub.set_state(
            f"camera.{cam_id}",
            "online" if online else "offline",
            attributes={
                "motion": bool(await self.backend.read(self._sig(cam_id, "motion"), False)),
                "recording": bool(await self.backend.read(self._sig(cam_id, "recording"), False)),
            },
        )

    async def async_teardown(self) -> None:
        for unwatch in self._unwatchers:
            unwatch()
        self._unwatchers.clear()
