"""OpenVan MCP server.

Exposes OpenVan Core as MCP tools so an assistant (e.g. Claude) can read the
van's state and control it — with parity to the REST API. It bridges to a
*running* Core over HTTP (default http://127.0.0.1:8000, override with
OPENVAN_API_URL), so there's a single Core and no duplicated sim loops.

Run:  openvan-mcp        (or: python -m openvan_core.mcp_server)
Needs the optional dependency:  pip install "openvan-core[mcp]"

Configure an MCP client (e.g. Claude Desktop / Code) to launch this command over
stdio, with OpenVan Core already running.
"""

from __future__ import annotations

import os
from typing import Any

from .apiclient import OpenVanClient

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "The OpenVan MCP server needs the 'mcp' package. "
        "Install it with:  pip install 'openvan-core[mcp]'"
    ) from exc

_client = OpenVanClient(os.environ.get("OPENVAN_API_URL", "http://127.0.0.1:8000"))
mcp = FastMCP("OpenVan")


# --- state & control -----------------------------------------------------
@mcp.tool()
async def get_state() -> dict:
    """Full van state: devices, live sensor values, assistant status, active notices."""
    return await _client.get_state()


@mcp.tool()
async def list_devices() -> list:
    """List controllable devices (entities) with their allowed commands and state."""
    return await _client.list_devices()


@mcp.tool()
async def control_device(entity_id: str, command: str, params: dict | None = None) -> dict:
    """Run a command on a device (e.g. entity_id='light.cabin', command='turn_on').
    OpenVan independently safety-checks it and may refuse (see 'blocked_by_safety')."""
    return await _client.execute_intent(entity_id, command, params)


@mcp.tool()
async def command(text: str) -> dict:
    """Control the van with natural language, e.g. "turn on the cabin light" or
    "it's freezing, warm it up". Proposes an intent that OpenVan safety-checks."""
    return await _client.command_text(text)


# --- companion -----------------------------------------------------------
@mcp.tool()
async def briefing() -> str:
    """A short, personality-flavoured status briefing from the companion."""
    result = await _client.briefing()
    return result.get("text", "") if isinstance(result, dict) else str(result)


@mcp.tool()
async def notices() -> list:
    """Active proactive notices (low water, rain approaching, break reminders, …)."""
    result = await _client.get_notices()
    return result.get("notices", [])


# --- telemetry / weather -------------------------------------------------
@mcp.tool()
async def predictions() -> dict:
    """Predictions from history: battery/water/diesel empty ETAs, solar Wh (24h)."""
    return await _client.get_predictions()


@mcp.tool()
async def weather() -> dict:
    """Current weather + hourly forecast for the van's location, with rain ETA."""
    return await _client.get_weather()


@mcp.tool()
async def telemetry(key: str, minutes: float = 60.0, bucket: float | None = None) -> dict:
    """Time-series history for a signal (e.g. key='house_battery.soc')."""
    return await _client.get_series(key, minutes, bucket)


# --- travel memory -------------------------------------------------------
@mcp.tool()
async def journal() -> dict:
    """The travel journal: past stays (place, date, weather, energy, notes)."""
    return await _client.get_stays()


@mcp.tool()
async def bookmark_spot(note: str = "") -> dict:
    """Bookmark the current location as a travel-memory stay, with an optional note."""
    return await _client.bookmark(note)


@mcp.tool()
async def add_journal_note(text: str) -> dict:
    """Add a note to the most recent journal entry."""
    return await _client.add_note(text)


@mcp.tool()
async def name_place(name: str) -> dict:
    """Name the most recent journal entry (e.g. "Lago di Braies")."""
    return await _client.name_place(name)


# --- settings & personalities --------------------------------------------
@mcp.tool()
async def get_settings() -> dict:
    """Current runtime settings (models, connectivity, active personality, plugins)."""
    return await _client.get_settings()


@mcp.tool()
async def update_settings(
    ai_enabled: bool | None = None,
    connectivity: str | None = None,
    language: str | None = None,
    offline_model: str | None = None,
    online_provider: str | None = None,
    online_model: str | None = None,
    simulate: bool | None = None,
) -> dict:
    """Change runtime settings (persisted; the API key is never set over MCP)."""
    return await _client.update_settings(
        ai_enabled=ai_enabled,
        connectivity=connectivity,
        language=language,
        offline_model=offline_model,
        online_provider=online_provider,
        online_model=online_model,
        simulate=simulate,
    )


@mcp.tool()
async def personalities() -> dict:
    """List companion personalities and the active one."""
    return await _client.list_personalities()


@mcp.tool()
async def set_personality(personality_id: str) -> dict:
    """Set the active companion personality (e.g. 'aurora', 'ranger', 'pulse')."""
    return await _client.set_personality(personality_id)


def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
