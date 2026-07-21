"""Security cameras plugin.

Van/RV camera setups are a mix of a wired rear/observation camera and a few
wireless (Wi-Fi or 4G-LTE) cams — Reolink, Eufy, Wyze, Ring, Furrion (see
docs/CAMERAS.md). Each camera is a semantic ``camera.*`` entity whose state +
attributes come from three raw twin signals:

    camera.<id>.online     -> entity state "online" / "offline"
    camera.<id>.motion     -> attributes.motion
    camera.<id>.recording  -> attributes.recording

**The camera set is not defined here.** Cameras are *provided* by integrations
("everything is an integration"): any enabled integration exposing
``provided_cameras()`` — the Cameras Simulator card with its configurable
camera list today, a real RTSP/ONVIF/Reolink/Frigate driver tomorrow —
contributes cameras, and this plugin reconciles the entity set whenever an
integration is enabled, disabled or reconfigured. No camera integration →
no camera entities, honestly.

Category: security. Domain: cameras.
"""

from __future__ import annotations

from openvan_core import Entity, Plugin


class Cameras(Plugin):
    domain = "cameras"
    name = "Security Cameras"
    version = "0.1.0"
    categories = ["security"]

    def __init__(self, hub, backend, config=None):
        super().__init__(hub, backend, config)
        self._cams: dict[str, dict[str, str]] = {}
        self._unwatchers: dict[str, list] = {}
        self._unsub = None

    def list(self) -> list[dict[str, str]]:
        return [dict(c) for c in self._cams.values()]

    def _registry(self) -> dict[str, dict[str, str]]:
        """Cameras provided by enabled integrations, first provider wins on id."""
        manager = getattr(self.hub, "integrations", None)
        cams: dict[str, dict[str, str]] = {}
        if manager is None:
            return cams
        for instance in manager.integrations.values():
            provider = getattr(instance, "provided_cameras", None)
            if not instance.enabled or provider is None:
                continue
            for cam in provider():
                cams.setdefault(cam["id"], cam)
        return cams

    async def async_setup(self) -> None:
        # Integrations set up after plugins, so the initial set arrives via the
        # first integration.changed event; reconcile now covers hot reloads.
        await self._reconcile()

        async def _on_integration_changed(_event) -> None:
            await self._reconcile()

        self._unsub = self.hub.bus.subscribe("integration.changed", _on_integration_changed)

    async def _reconcile(self) -> None:
        wanted = self._registry()
        for cam_id in [c for c in self._cams if c not in wanted]:
            await self._remove(cam_id)
        for cam_id, cam in wanted.items():
            if self._cams.get(cam_id) != cam:
                if cam_id in self._cams:  # metadata changed — re-register
                    await self._remove(cam_id)
                await self._register(cam)

    # --- signals ---------------------------------------------------------
    def _sig(self, cam_id: str, field: str) -> str:
        return f"camera.{cam_id}.{field}"

    async def _register(self, cam: dict[str, str]) -> None:
        cam_id = cam["id"]
        online = bool(await self.backend.read(self._sig(cam_id, "online"), True))
        entity = Entity(
            entity_id=f"camera.{cam_id}",
            name=cam["label"],
            domain="camera",
            category="security",
            state="online" if online else "offline",
            unit=None,
            attributes={
                "location": cam["location"],
                "connection": cam["connection"],
                "motion": bool(await self.backend.read(self._sig(cam_id, "motion"), False)),
                "recording": bool(await self.backend.read(self._sig(cam_id, "recording"), False)),
            },
        )
        await self.hub.register_entity(entity)
        self._cams[cam_id] = dict(cam)
        self._unwatchers[cam_id] = [
            self._watch(cam_id, f) for f in ("online", "motion", "recording")
        ]

    async def _remove(self, cam_id: str) -> None:
        for unwatch in self._unwatchers.pop(cam_id, []):
            unwatch()
        self._cams.pop(cam_id, None)
        await self.hub.remove_entity(f"camera.{cam_id}")

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

    async def async_teardown(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        for unwatchers in self._unwatchers.values():
            for unwatch in unwatchers:
                unwatch()
        self._unwatchers.clear()
