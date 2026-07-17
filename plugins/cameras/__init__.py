"""Security cameras plugin.

Van/RV camera setups are a mix of a wired rear/observation camera and a few
wireless (Wi-Fi or 4G-LTE) cams — Reolink, Eufy, Wyze, Ring, Furrion (see
docs/CAMERAS.md). Each camera is a semantic ``camera.*`` entity whose state +
attributes come from three raw twin signals:

    camera.<id>.online     -> entity state "online" / "offline"
    camera.<id>.motion     -> attributes.motion
    camera.<id>.recording  -> attributes.recording

Cameras are **dynamic**: the set is loaded from the config store (or the defaults
on first run) and can be added/removed at runtime (Core persists the list). That
keeps them driveable from the Hardware Bench and readable by the product UI
(Rule 1), and it's the exact shape a real RTSP/ONVIF/cloud backend fills in later.

Category: security. Domain: cameras.
"""

from __future__ import annotations

from typing import Any

from openvan_core import Entity, Plugin

# A typical build, used on first run before anything is customised.
DEFAULT_CAMERAS = [
    {"id": "rear", "label": "Rear View", "location": "rear", "connection": "wired"},
    {"id": "cabin", "label": "Cabin", "location": "cabin", "connection": "wifi"},
    {"id": "entry", "label": "Entry / Door", "location": "door", "connection": "wifi"},
    {"id": "awning", "label": "Side / Awning", "location": "awning", "connection": "4g"},
]


class Cameras(Plugin):
    domain = "cameras"
    name = "Security Cameras"
    version = "0.1.0"
    categories = ["security"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._cams: dict[str, dict[str, str]] = {}
        self._unwatchers: dict[str, list] = {}

    def list(self) -> list[dict[str, str]]:
        return [dict(c) for c in self._cams.values()]

    async def async_setup(self) -> None:
        saved = self.config.get("list")
        cams = saved if isinstance(saved, list) and saved else DEFAULT_CAMERAS
        for c in cams:
            await self._register(c["id"], c.get("label", c["id"]),
                                 c.get("location", "cabin"), c.get("connection", "wifi"))

    # --- signals ---------------------------------------------------------
    def _sig(self, cam_id: str, field: str) -> str:
        return f"camera.{cam_id}.{field}"

    async def _register(self, cam_id: str, label: str, location: str, connection: str) -> None:
        # Seed the raw signals only if they don't exist yet (don't clobber state).
        defaults = {"online": True, "motion": False, "recording": False}
        for field, default in defaults.items():
            if await self.backend.read(self._sig(cam_id, field), None) is None:
                await self.backend.write(self._sig(cam_id, field), default)

        online = bool(await self.backend.read(self._sig(cam_id, "online"), True))
        entity = Entity(
            entity_id=f"camera.{cam_id}",
            name=label,
            domain="camera",
            category="security",
            state="online" if online else "offline",
            unit=None,
            attributes={
                "location": location,
                "connection": connection,
                "motion": bool(await self.backend.read(self._sig(cam_id, "motion"), False)),
                "recording": bool(await self.backend.read(self._sig(cam_id, "recording"), False)),
            },
        )
        await self.hub.register_entity(entity)
        self._cams[cam_id] = {"id": cam_id, "label": label,
                              "location": location, "connection": connection}
        self._unwatchers[cam_id] = [
            self._watch(cam_id, f) for f in ("online", "motion", "recording")
        ]

    def _watch(self, cam_id: str, field: str):
        async def _on_change(_key: str, _value) -> None:
            await self._refresh(cam_id)

        return self.backend.watch(self._sig(cam_id, field), _on_change)

    async def _refresh(self, cam_id: str) -> None:
        if self.hub.get_entity(f"camera.{cam_id}") is None:
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

    # --- dynamic add / remove -------------------------------------------
    async def add_camera(self, cam_id: str, label: str, location: str, connection: str) -> bool:
        if not cam_id or cam_id in self._cams:
            return False
        await self._register(cam_id, label or cam_id, location or "cabin", connection or "wifi")
        return True

    async def remove_camera(self, cam_id: str) -> bool:
        if cam_id not in self._cams:
            return False
        for unwatch in self._unwatchers.pop(cam_id, []):
            unwatch()
        self._cams.pop(cam_id, None)
        await self.hub.remove_entity(f"camera.{cam_id}")
        # Quiet the signals so a removed camera can't trip the intrusion alarm.
        await self.backend.write(self._sig(cam_id, "motion"), False)
        await self.backend.write(self._sig(cam_id, "online"), False)
        return True

    async def async_teardown(self) -> None:
        for unwatchers in self._unwatchers.values():
            for unwatch in unwatchers:
                unwatch()
        self._unwatchers.clear()
