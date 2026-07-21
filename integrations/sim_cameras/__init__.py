"""Cameras Simulator — the world-sim provider AND registry for the cameras.

The camera *placement* is configuration of this integration, not code: the
``cameras`` list (id, label, mounting location, connection) lives in this card's
settings page, defaults to a typical four-camera build, and can be edited there
(or via the bench / ``/api/cameras``). Each configured camera gets its
``camera.<id>.online/motion/recording`` signals seeded (online, quiet), and the
cameras *plugin* turns the same list into ``camera.*`` entities — so adding a
row in the settings page is all it takes for a new camera to appear everywhere.

Removable like every provider: remove the card (with no real camera
integration) and the camera grid honestly reads unknown. A real camera driver
(RTSP/ONVIF, Reolink, Frigate…) exposes the same ``provided_cameras()`` shape.
"""

from __future__ import annotations

from typing import Any

from openvan_core import IntegrationInfo, Permissions, Status, Transport, WorldSimProvider

# A typical build, used until the user edits the camera list. Placement is in
# van coordinates seen from above (front left): x 0 (front) … 100 (rear) along
# the length, y 0 … 100 across the width; heading in degrees clockwise from the
# direction of travel (0 = forward, 90 = across, 180 = rearward).
DEFAULT_CAMERAS = [
    {"id": "rear", "label": "Rear View", "location": "rear", "connection": "wired",
     "x": 97.0, "y": 50.0, "heading": 180.0},
    {"id": "cabin", "label": "Cabin", "location": "cabin", "connection": "wifi",
     "x": 55.0, "y": 50.0, "heading": 0.0},
    {"id": "entry", "label": "Entry / Door", "location": "door", "connection": "wifi",
     "x": 40.0, "y": 95.0, "heading": 270.0},
    {"id": "awning", "label": "Side / Awning", "location": "awning", "connection": "4g",
     "x": 12.0, "y": 88.0, "heading": 0.0},
]

LOCATIONS = ["rear", "cabin", "door", "awning"]
CONNECTIONS = ["wired", "wifi", "4g"]


class SimCameras(WorldSimProvider):
    info = IntegrationInfo(
        id="sim_cameras",
        name="Cameras Simulator",
        category="sensors",
        vendor="OpenVan",
        transports=[Transport.NATIVE_API],
        local=True,
        offline_capable=True,
        discovery="builtin",
        permissions=Permissions(read=True, control=False, configure=True),
        safety_class=0,
        status=Status.NATIVE,
        priority="P0",
        provides=["camera.<id>.online", "camera.<id>.motion", "camera.<id>.recording"],
        description=(
            "Provides the simulated security cameras. The camera set — ids, "
            "names, mounting locations, connections — is configured on this "
            "card; each row becomes a camera everywhere (grid, van map, alarm). "
            "Remove the card when a real camera integration provides these."
        ),
        config_fields=[
            {
                "key": "cameras",
                "label": "Cameras",
                "type": "list",
                # Rows are placed and aimed on a top-down van view in the UI.
                "van_placement": True,
                "default": DEFAULT_CAMERAS,
                "item_fields": [
                    {"key": "id", "label": "Id", "type": "text"},
                    {"key": "label", "label": "Name", "type": "text"},
                    {"key": "location", "label": "View", "type": "select",
                     "options": LOCATIONS},
                    {"key": "connection", "label": "Connection", "type": "select",
                     "options": CONNECTIONS},
                    # Managed by the placement editor, not the table.
                    {"key": "x", "label": "X", "type": "number", "hidden": True, "default": 50.0},
                    {"key": "y", "label": "Y", "type": "number", "hidden": True, "default": 50.0},
                    {"key": "heading", "label": "Heading", "type": "number", "hidden": True, "default": 0.0},
                ],
            },
        ],
    )

    def provided_cameras(self) -> list[dict[str, Any]]:
        """The configured camera set — the registry the cameras plugin consumes.
        A real camera driver exposes the same method for its discovered cams."""
        configured = self.config.get("cameras")
        # Unset → the typical default build; an explicitly *emptied* list means
        # "no cameras" and must not resurrect the defaults.
        cams = configured if isinstance(configured, list) else DEFAULT_CAMERAS
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        def _num(value: Any, default: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        for cam in cams:
            cam_id = str(cam.get("id", "")).strip().lower()
            if not cam_id or cam_id in seen:
                continue
            seen.add(cam_id)
            out.append({
                "id": cam_id,
                "label": str(cam.get("label") or cam_id),
                "location": str(cam.get("location") or "cabin"),
                "connection": str(cam.get("connection") or "wifi"),
                "x": _num(cam.get("x"), 50.0),
                "y": _num(cam.get("y"), 50.0),
                "heading": _num(cam.get("heading"), 0.0),
            })
        return out

    def seeds(self) -> dict[str, Any]:
        # Online, no motion, not recording — per configured camera.
        return {
            f"camera.{cam['id']}.{measure}": measure == "online"
            for cam in self.provided_cameras()
            for measure in ("online", "motion", "recording")
        }
