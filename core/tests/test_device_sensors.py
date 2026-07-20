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


# --- self-contained drivers: prefixes derived from descriptors ---------------

def _fake_driver(core, provides, driver_id="acme_fridge"):
    """An 'external' driver present only in this test — deliberately NOT
    registered globally (info set after class creation), inserted straight into
    the manager as an enabled instance."""
    from openvan_core import Integration, IntegrationInfo

    class Fake(Integration):
        info = None

    Fake.info = IntegrationInfo(id=driver_id, name="ACME", category="sensors",
                                provides=provides)
    inst = Fake(core.twin, core.bus, {})
    inst.enabled = True
    core.integrations.integrations[driver_id] = inst
    core.integrations._prefix_cache = None
    return inst


async def test_declared_prefixes_from_enabled_drivers(core):
    # Default install: only world-sim providers + the master switch → excluded.
    assert core.integrations.declared_prefixes() == ()
    _fake_driver(core, ["acme.fridge.temp", "acme.fridge.door", "solar.power (mirrored)"])
    assert core.integrations.declared_prefixes() == ("acme.", "solar.")


async def test_external_driver_entities_appear_without_prefix_edits(core):
    # "acme." is in nobody's DEFAULT_PREFIXES — it comes from the descriptor.
    _fake_driver(core, ["acme.fridge.temperature"])
    await core.twin.set_signal("acme.fridge.temperature", 4.5, source="acme_fridge")
    entity = core.hub.entities.get("sensor.acme_fridge_temperature")
    assert entity is not None and entity.state == 4.5
    assert entity.attributes["device_sensor"] is True
    assert entity.unit == "°C" and entity.name == "Fridge Temperature"


async def test_core_mirror_in_provides_never_hijacks_existing_entities(core):
    # A driver declaring a core mirror must not duplicate the dedicated entity.
    _fake_driver(core, ["acme.fridge.temp", "house_battery.soc (mirrored)"])
    await core.twin.set_signal("house_battery.soc", 61.0, source="acme_fridge")
    entity = core.hub.entities["sensor.house_battery_soc"]
    assert entity.state == 61.0  # updated by the battery plugin's own watcher
    assert not (entity.attributes or {}).get("device_sensor")  # not ours
