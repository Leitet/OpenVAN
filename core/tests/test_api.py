"""HTTP surface used by the web simulator."""

from __future__ import annotations

from fastapi.testclient import TestClient

from openvan_core.api import build_app
from openvan_core.config import Config


def test_state_intent_and_safety_over_http():
    with TestClient(build_app(Config(ai_enabled=False))) as client:
        state = client.get("/api/state").json()
        entity_ids = {e["entity_id"] for e in state["entities"]}
        assert {"light.cabin", "sensor.house_battery_soc"} <= entity_ids

        ok = client.post(
            "/api/intent", json={"entity_id": "light.cabin", "command": "turn_on"}
        ).json()
        assert ok["ok"] is True

        # Simulator injects a critically low battery, then the same command is refused.
        client.post("/api/sim/signal", json={"key": "house_battery.soc", "value": 5})
        blocked = client.post(
            "/api/intent", json={"entity_id": "light.cabin", "command": "turn_on"}
        ).json()
        assert blocked["blocked_by_safety"] is True
