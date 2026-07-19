"""Device-sensor auto-entities: an integration's arbitrary readings (RuuviTag,
ESPHome, …) become sensor entities with guessed units/names — no per-device code."""

from __future__ import annotations

import pytest

from openvan_core import build_core
from openvan_core.config import Config


@pytest.fixture
async def core(tmp_path):
    c = build_core(
        Config(ai_enabled=False, weather_enabled=False, memory_enabled=False,
               telemetry_enabled=False, simulate=False, data_dir=tmp_path)
    )
    await c.start()
    yield c
    await c.stop()


async def test_helpers(core):
    import device_sensors as ds  # discovered onto sys.path by core.start()

    assert ds.entity_id_for("ruuvitag.outdoor.temperature") == "sensor.ruuvitag_outdoor_temperature"
    assert ds.name_for("esphome.cabin_node.humidity") == "Cabin Node Humidity"
    assert ds.unit_for("ruuvitag.outdoor.battery") == "V"
    assert ds.unit_for("esphome.cabin_node.temperature") == "°C"
    assert ds.unit_for("ruuvitag.outdoor.humidity") == "%"
    assert ds.unit_for("esphome.node.door") is None  # unknown measure → no unit


async def test_no_device_entities_until_an_integration_provides_them(core):
    # Nothing under the device prefixes is seeded, so none appear by default.
    assert not any(
        e.attributes.get("device_sensor") for e in core.hub.entities.values()
    )


async def test_ruuvitag_readings_become_entities(core):
    await core.set_integration_enabled("ruuvitag", True)
    await core.twin.set_signal("outside.temperature", 7.0)
    await core.integrations.simulate_all(1.0)

    temp = core.hub.entities.get("sensor.ruuvitag_outdoor_temperature")
    assert temp is not None
    assert temp.unit == "°C" and temp.name == "Outdoor Temperature"
    assert temp.category == "sensors" and temp.attributes["device_sensor"] is True
    assert temp.state == pytest.approx(7.0)
    assert core.hub.entities["sensor.ruuvitag_outdoor_battery"].unit == "V"
    assert core.hub.entities["sensor.ruuvitag_outdoor_humidity"].unit == "%"


async def test_entities_update_on_later_changes(core):
    await core.set_integration_enabled("ruuvitag", True)
    await core.twin.set_signal("outside.temperature", 7.0)
    await core.integrations.simulate_all(1.0)
    await core.twin.set_signal("outside.temperature", 2.0)
    await core.integrations.simulate_all(1.0)
    assert core.hub.entities["sensor.ruuvitag_outdoor_temperature"].state == pytest.approx(2.0)
