# Writing OpenVan drivers

OpenVan is built to be extended: the core stays small, and everything at the
edges — hardware ecosystems, feature plugins, camp-spot sources — is a **driver**
anyone can write, share and install. This is the guide for driver authors.

```
your-driver/                    <- one directory = one driver
  driver.toml                   <- identity manifest (required for distribution)
  __init__.py                   <- your code (an Integration/Plugin subclass)
  SIGNATURE                     <- added by `openvan-driver sign` (optional)
```

## 1. The manifest (`driver.toml`)

Identity that core can read **without importing your code**:

```toml
[driver]
id = "acme_fridge"          # unique, stable — matches your class's info.id
name = "ACME Fridge"
version = "1.0.0"
kind = "integration"        # integration | plugin | campsource
api = 1                     # the OpenVan driver API level you target
entry = "acme_fridge"       # the package to import (usually the folder name)
```

`api` is checked before anything loads: if a future core drops support for your
level, your driver is listed as *incompatible* with a clear message instead of
crashing at import. Bundled in-repo drivers may omit the manifest; **external
drivers without one are refused**.

## 2. The code

An integration is a subclass of `openvan_core.Integration` with a machine-readable
descriptor and, non-negotiably, a **simulation path** — every driver must be
exercisable against the digital twin with no hardware (CLAUDE.md Rule 1):

```python
from openvan_core import Integration, IntegrationInfo, Status, Transport

class AcmeFridge(Integration):
    info = IntegrationInfo(
        id="acme_fridge",                      # == driver.toml id
        name="ACME Fridge",
        category="sensors",
        transports=[Transport.BLE],
        status=Status.COMMUNITY,               # be honest about robustness
        provides=["acme.fridge.temp"],
        config_fields=[                        # settings shown in the library UI
            {"key": "mode", "label": "Connection", "type": "select",
             "options": ["sim", "ble"], "default": "sim"},
        ],
    )

    async def simulate(self, dt: float) -> None:
        # The dev stand-in: inject the signals a real device would emit.
        await self.twin.set_signal("acme.fridge.temp", 4.5, source=self.info.id)

    async def run_transport(self) -> None:
        # The real thing (mode != "sim"): connect, stream into the twin, set
        # self.live = True. Raise NotImplementedError to stay simulated.
        raise NotImplementedError
```

Key rules (enforced by the architecture — see `CLAUDE.md`):

- **Read** by normalising device data into twin signals; plugins/entities consume
  them. Signals a driver provides are auto-surfaced by `device_sensors`.
- **Actuate** only via `register_control()` — commands then arrive through
  `Hub.execute_intent` → the safety layer → your `send_command()`. Never write to
  hardware outside that path (Rule 2). A safety-refused command must never reach
  the wire.
- **Offline-first** (Rule 3): the sim path must always work; a cloud dependency
  makes your `status` honestly `cloud_dependent`.
- Failures are contained: if your import or setup raises, your driver shows an
  *error* state in the catalog and the van keeps running — but don't rely on it.

### Self-contained by design — what a driver gets for free

A driver is **one directory**; it never touches UI code. When it is enabled
(from either front-end), the platform surfaces it everywhere:

| Surface | How it happens |
| --- | --- |
| Catalog card in the **product UI** (Settings → Integrations) and the **bench** (Integrations card, incl. *Add integration*) | from your `IntegrationInfo` descriptor — name, badges, warning, config form |
| Injectable signal group in the bench's **Signal browser** | automatic: every `twin.set_signal(..., source=self.info.id)` is grouped under your driver id, with an auto-generated control per value type |
| `sensor.*` entities in the product UI | `device_sensors` auto-surfaces readings under known signal prefixes, guessing unit + friendly name from the key |
| History, trends, predictions | the telemetry recorder captures every numeric signal automatically |
| Honest emptiness | if nothing provides a domain, the UI shows "—" and a *no data source* hint — never stale fake values |

For this to work, follow two conventions:

1. **Signal naming**: `"<prefix>.<device>.<measure>"`, where `<prefix>` is a
   short, stable namespace unique to your ecosystem (`ruuvitag.`, `cdh.`,
   `epever.`) and `<measure>` uses the common vocabulary (`temperature`,
   `humidity`, `voltage`, `power`, `battery`, …) so units are guessed right.
   List your keys in the descriptor's `provides`.
2. **Always pass `source=self.info.id`** when writing twin signals — that is
   what groups your signals in the bench and attributes them in tooling.

Auto-entity coverage: bundled ecosystems are listed in
`plugins/device_sensors/DEFAULT_PREFIXES`. If your driver is external, either PR
your prefix into that list or tell users to add it to the `device_sensors`
plugin config (`prefixes`). Signals that mirror *core* van state
(`house_battery.soc`, `propane.level_pct`, …) need no prefix work at all — the
dedicated plugins, advisors and safety rules pick them up as-is.

### World-sim providers — simulated data sources as drivers

Everything the UI shows traces to an installed integration — including the
simulated reference van. Its data comes from removable **provider cards**
(`sim_energy`, `sim_water`, …) built on `WorldSimProvider`:

```python
from openvan_core import IntegrationInfo, WorldSimProvider

class SimCompost(WorldSimProvider):
    SEEDS = {"compost.level_pct": 10.0, "compost.temp_c": 35.0}
    info = IntegrationInfo(id="sim_compost", name="Compost Simulator", ...)
```

The base class does the contract for you: installing seeds the keys (without
stomping a value another source already provides — that's what makes per-domain
**mixed mode** work), removing releases them to `None` so the UI honestly reads
unknown. If you introduce a *new simulated domain*, ship a provider card for it
rather than adding keys to `Config.seed_twin` — the seed dict is reserved for
what the platform itself owns (actuator rest-states, the sim clock).

### BLE drivers

Never own a radio — subscribe to the shared scanner with a filter and parse:

```python
    async def async_setup(self) -> None:
        await super().async_setup()
        if self.ble is not None:
            self._unsub = self.ble.subscribe(self._on_adv, manufacturer_id=0x0499)

    async def _on_adv(self, adv) -> None:
        data = my_parser(adv.manufacturer_data.get(0x0499, b""))
        ...  # normalise into twin signals
```

Keep the parser a pure function with test vectors. The bench (or
`POST /api/sim/ble`) injects canned frames into the same dispatch path a real
adapter uses, so your driver is fully testable with no radio.

### Serial-device drivers

Never open ports directly — ask the link layer, so the user chooses how the wire
is reached (TCP bridge with no extras, USB with the `serial` extra, sim):

```python
from openvan_core.transports.links import create_link
from openvan_core.transports.modbus_rtu import AsyncModbusRtuClient

link = create_link(self.config)          # config: link=tcp|serial|sim, host/device…
client = AsyncModbusRtuClient(link, unit_id=1)
```

## 3. Installing

Bundled drivers live in the repo (`integrations/`, `plugins/`, `campsources/`).
User-installed drivers go in the van's data dir:

```
data/drivers/acme_fridge/       <- drop the driver directory here, restart core
```

`GET /api/drivers` lists every discovered driver with its state and provenance.

## 4. Signing & trust

Provenance tiers, shown as badges in the library:

| Tier | Meaning |
| --- | --- |
| `bundled` | ships inside the core repo |
| `official` | signed by an OpenVan store key (`openvan_core/trust/*.pub`) |
| `community` | signed by a key the *user* trusts (`data/trust/*.pub`) |
| `unknown_signer` | valid signature, unrecognised key |
| `unsigned` | no signature — allowed by default, clearly flagged |
| **blocked** | signature present but contents changed (**tampered — never loads**) |

Unsigned drivers run because it's your van — but a signed-then-modified package is
refused outright, and `require_signed = true` (or `OPENVAN_REQUIRE_SIGNED=1`)
locks the van down to official/community signatures only.

Tooling (pure-stdlib Ed25519, RFC 8032):

```bash
openvan-driver keygen acme          # acme.key (keep secret) + acme.pub (publish)
openvan-driver sign path/to/driver --key acme.key
openvan-driver verify path/to/driver
```

Users trust your key by dropping `acme.pub` into their `data/trust/`. The store
signs official releases with the org keys in `openvan_core/trust/` (private keys
held by the org, never in the repo).

**Honesty note:** signatures prove *who published* a driver and that it wasn't
modified — not that it's safe. Loaded drivers run in-process with full access.
The tiers exist so users decide with real information.

## 5. Checklist before you publish

- [ ] `driver.toml` with a stable `id` (== `info.id`) and correct `api`
- [ ] `simulate()` works against the twin; a test in your repo proves it
- [ ] Signals named `<prefix>.<device>.<measure>`, written with
      `source=self.info.id`, listed in `provides`
- [ ] Verified end-to-end with **zero UI code**: enable the driver, see its
      signal group in the bench's Signal browser, inject a value, watch the
      product UI react
- [ ] Honest `status`, `safety_class` and `warning` in the descriptor
- [ ] Controls (if any) go through `register_control` / `send_command`
- [ ] `openvan-driver sign` with your published key
