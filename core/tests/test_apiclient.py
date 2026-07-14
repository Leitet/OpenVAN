"""OpenVanClient (the MCP server's bridge) against the real API in-process."""

from __future__ import annotations

import contextlib

import httpx
import pytest

from openvan_core.api import build_app
from openvan_core.apiclient import OpenVanClient
from openvan_core.config import Config


@contextlib.asynccontextmanager
async def _client(tmp_path):
    app = build_app(Config(
        ai_enabled=False, weather_enabled=False, memory_enabled=False,
        telemetry_enabled=False, data_dir=tmp_path,
    ))
    # Drive the app lifespan so Core.start() registers plugins/entities.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield OpenVanClient(base_url="http://test", client=http)


async def test_state_and_devices(tmp_path):
    async with _client(tmp_path) as client:
        state = await client.get_state()
        ids = {e["entity_id"] for e in state["entities"]}
        assert "light.cabin" in ids

        devices = await client.list_devices()
        assert any(d["entity_id"] == "light.cabin" for d in devices)


async def test_control_and_safety(tmp_path):
    async with _client(tmp_path) as client:
        ok = await client.execute_intent("light.cabin", "turn_on")
        assert ok["ok"] is True

        await client.inject_signal("house_battery.soc", 5)
        blocked = await client.execute_intent("light.cabin", "turn_on")
        assert blocked["blocked_by_safety"] is True


async def test_settings_and_personalities(tmp_path):
    async with _client(tmp_path) as client:
        settings = await client.get_settings()
        assert "default_connectivity" in settings

        updated = await client.update_settings(default_connectivity="online")
        assert updated["default_connectivity"] == "online"

        result = await client.set_personality("ranger")
        assert result["active"] == "ranger"
