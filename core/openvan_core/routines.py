"""Routines — user-programmable automations, safety-checked end to end.

The evolution of scenes: a **routine** is triggers + an ordered step list,
fully editable from the Settings UI and persisted to the config store. The four
classic scenes (goodnight, morning, set up camp, leaving) ship as editable
defaults.

Triggers (any of them starts the routine; "signal" and "time" are
edge-triggered so a routine fires once per crossing, never every tick):

    {"type": "manual"}                                   # home button / voice
    {"type": "signal", "signal": "house_battery.soc",
     "op": "below", "value": 20}                         # above|below|equals|on|off
    {"type": "time", "at": "07:30"}                      # local (sim-clock) time
    {"type": "sun", "event": "sunrise", "offset_min": 30}  # sunrise|sunset (+delay,
                                                           # counted in *sim* time)
    {"type": "van", "event": "park"}                     # park | drive_off
                                                         # (ignition off / on edge)

Steps (executed in order):

    {"type": "action", "entity_id": "light.cabin", "command": "turn_on",
     "params": {}}                                       # via Hub.execute_intent
    {"type": "wait", "seconds": 300}                     # clamped to 1 h
    {"type": "condition", "signal": "cabin.temperature",
     "op": "below", "value": 15}                         # continue only if true
    {"type": "notify", "message": "Warming up the cabin"}

Design rules carried over from scenes and the rest of the platform:

* **Rule 2 by construction** — every ``action`` goes through
  ``Hub.execute_intent`` → the safety layer. A routine can never do anything a
  direct command couldn't; a blocked step is reported, not silently retried.
* **Offline-first, model-free** — deterministic triggers and steps only; the
  assistant is used elsewhere to *recognise* a spoken routine, never to run it.
* Time triggers follow the same local-time derivation as the sun model
  (``clock.epoch`` + longitude), so bench time-travel exercises them (Rule 1).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from .intents import Intent
from .twin import SIGNAL_CHANGED

if TYPE_CHECKING:  # pragma: no cover
    from .events import EventBus
    from .hub import Hub
    from .twin import VanTwin

logger = logging.getLogger(__name__)

MAX_WAIT_S = 3600.0
OPS = ("above", "below", "equals", "on", "off")
ICONS = ("moon", "sun", "tent", "door", "zap", "bell", "droplet", "thermometer", "shield", "car")

STORE_NS = "routines"


def default_routines(sleep_c: float = 16.0, comfort_c: float = 20.0) -> list[dict[str, Any]]:
    """The four everyday routines, now as editable defaults. Heater setpoints
    come from tuning (nothing hardcoded)."""

    def action(entity_id: str, command: str, **params: Any) -> dict[str, Any]:
        return {"type": "action", "entity_id": entity_id, "command": command, "params": params}

    return [
        {
            "id": "goodnight", "name": "Goodnight", "icon": "moon",
            "description": "Lights off, heater to a cosy sleeping temperature, pump off.",
            "enabled": True, "show_on_home": True,
            "triggers": [{"type": "manual"}],
            "steps": [
                action("light.cabin", "turn_off"),
                action("climate.diesel_heater", "set_temperature", temperature=sleep_c),
                action("climate.diesel_heater", "turn_on"),
                action("switch.water_pump", "turn_off"),
            ],
        },
        {
            "id": "morning", "name": "Good morning", "icon": "sun",
            "description": "Lights on and warm the cabin back up.",
            "enabled": True, "show_on_home": True,
            "triggers": [{"type": "manual"}],
            "steps": [
                action("light.cabin", "turn_on"),
                action("climate.diesel_heater", "set_temperature", temperature=comfort_c),
                action("climate.diesel_heater", "turn_on"),
            ],
        },
        {
            "id": "setup_camp", "name": "Set up camp", "icon": "tent",
            "description": "Arriving: lights on, comfortable warmth.",
            "enabled": True, "show_on_home": True,
            "triggers": [{"type": "manual"}],
            "steps": [
                action("light.cabin", "turn_on"),
                action("climate.diesel_heater", "set_temperature", temperature=comfort_c),
                action("climate.diesel_heater", "turn_on"),
            ],
        },
        {
            "id": "leaving", "name": "Leaving", "icon": "door",
            "description": "Everything off before you drive away.",
            "enabled": True, "show_on_home": True,
            "triggers": [{"type": "manual"}],
            "steps": [
                action("light.cabin", "turn_off"),
                action("climate.diesel_heater", "turn_off"),
                action("switch.water_pump", "turn_off"),
            ],
        },
    ]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_") or "routine"


def normalize_routine(raw: dict[str, Any], taken: set[str]) -> dict[str, Any] | None:
    """Coerce one user-supplied routine into a valid shape (or drop it).
    Unknown trigger/step types are dropped rather than crashing the engine —
    a saved routine must never take the van down."""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip() or "Routine"
    rid = str(raw.get("id") or "").strip() or _slug(name)
    while rid in taken:
        rid += "_2"
    taken.add(rid)

    triggers: list[dict[str, Any]] = []
    for t in raw.get("triggers") or []:
        kind = t.get("type") if isinstance(t, dict) else None
        if kind == "manual":
            triggers.append({"type": "manual"})
        elif kind == "signal" and t.get("signal") and t.get("op") in OPS:
            triggers.append({
                "type": "signal", "signal": str(t["signal"]), "op": str(t["op"]),
                "value": _num(t.get("value"), 0.0),
            })
        elif kind == "time":
            at = str(t.get("at") or "")
            if re.fullmatch(r"\d{1,2}:\d{2}", at):
                triggers.append({"type": "time", "at": at})
        elif kind == "sun":
            event = t.get("event") if t.get("event") in ("sunrise", "sunset") else "sunrise"
            triggers.append({"type": "sun", "event": event,
                             "offset_min": max(0.0, min(720.0, _num(t.get("offset_min"), 0.0)))})
        elif kind == "van":
            event = t.get("event") if t.get("event") in ("park", "drive_off") else "park"
            triggers.append({"type": "van", "event": event})
    if not triggers:
        triggers = [{"type": "manual"}]

    steps: list[dict[str, Any]] = []
    for s in raw.get("steps") or []:
        kind = s.get("type") if isinstance(s, dict) else None
        if kind == "action" and s.get("entity_id") and s.get("command"):
            params = s.get("params") if isinstance(s.get("params"), dict) else {}
            steps.append({"type": "action", "entity_id": str(s["entity_id"]),
                          "command": str(s["command"]), "params": params})
        elif kind == "wait":
            steps.append({"type": "wait",
                          "seconds": max(0.0, min(MAX_WAIT_S, _num(s.get("seconds"), 0.0)))})
        elif kind == "condition" and s.get("signal") and s.get("op") in OPS:
            steps.append({"type": "condition", "signal": str(s["signal"]),
                          "op": str(s["op"]), "value": _num(s.get("value"), 0.0)})
        elif kind == "notify":
            steps.append({"type": "notify", "message": str(s.get("message") or "")[:300]})

    return {
        "id": rid,
        "name": name[:80],
        "icon": str(raw.get("icon") or "zap"),
        "description": str(raw.get("description") or "")[:300],
        "enabled": bool(raw.get("enabled", True)),
        "show_on_home": bool(raw.get("show_on_home", False)),
        "triggers": triggers,
        "steps": steps,
    }


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _check(op: str, actual: Any, value: float) -> bool:
    if op == "on":
        return bool(actual)
    if op == "off":
        return actual is not None and not bool(actual)
    try:
        current = float(actual)
    except (TypeError, ValueError):
        return False
    if op == "above":
        return current > value
    if op == "below":
        return current < value
    return abs(current - value) < 1e-9


class RoutineEngine:
    """Holds, persists, triggers and runs the routines."""

    def __init__(self, hub: "Hub", bus: "EventBus", twin: "VanTwin", store: Any = None) -> None:
        self.hub = hub
        self.bus = bus
        self.twin = twin
        self.store = store
        self._routines: list[dict[str, Any]] = default_routines()
        self._customized = False  # user-edited → tuning changes stop touching them
        # Edge state per (routine id, trigger index): last boolean outcome.
        self._edges: dict[tuple[str, int], bool] = {}
        self._last_minutes: int | None = None
        self._last_phase: str | None = None
        # Sun triggers with an offset become one-shot local-time targets, so the
        # delay is counted in *sim* time (bench time-travel works).
        self._pending_at: list[tuple[str, int]] = []  # (routine id, minutes-of-day)
        self._running: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._unsubs: list[Any] = []

    # --- persistence ------------------------------------------------------

    def load(self) -> None:
        saved = self.store.get(STORE_NS, "list") if self.store is not None else None
        if isinstance(saved, list):
            self._routines = self._normalize_all(saved)
            self._customized = True

    def refresh_defaults(self, sleep_c: float, comfort_c: float) -> None:
        """Tuning changed: rebuild the *default* set only — a user-edited set is
        theirs and is never overwritten by a setpoint tweak."""
        if not self._customized:
            self._routines = default_routines(sleep_c, comfort_c)

    async def save(self, routines: list[Any]) -> list[dict[str, Any]]:
        self._routines = self._normalize_all(routines)
        self._customized = True
        if self.store is not None:
            self.store.set_many(STORE_NS, {"list": self._routines})
        self._edges.clear()
        await self.bus.publish("routines.changed", {"routines": self.list()})
        return self.list()

    async def reset(self, sleep_c: float = 16.0, comfort_c: float = 20.0) -> list[dict[str, Any]]:
        self._routines = default_routines(sleep_c, comfort_c)
        self._customized = False
        if self.store is not None:
            self.store.set_many(STORE_NS, {"list": None})
        self._edges.clear()
        await self.bus.publish("routines.changed", {"routines": self.list()})
        return self.list()

    def _normalize_all(self, raw: list[Any]) -> list[dict[str, Any]]:
        taken: set[str] = set()
        out = []
        for r in raw:
            normalized = normalize_routine(r, taken)
            if normalized is not None:
                out.append(normalized)
        return out

    # --- views ------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._routines]

    def get(self, routine_id: str) -> dict[str, Any] | None:
        for r in self._routines:
            if r["id"] == routine_id:
                return r
        return None

    def home_list(self) -> list[dict[str, Any]]:
        """The scenes-shaped subset for the home screen and voice matching."""
        return [
            {"id": r["id"], "name": r["name"], "icon": r["icon"], "description": r["description"]}
            for r in self._routines
            if r["enabled"] and r["show_on_home"]
        ]

    # --- triggers ---------------------------------------------------------

    def start(self) -> None:
        # Baselines from the current world, so the first *change* is a real edge
        # (the seeded phase/time must not be mistaken for a transition).
        self._last_phase = str(self.twin.get("environment.phase") or "") or None
        self._last_minutes = self._local_minutes()
        self._unsubs.append(self.bus.subscribe(SIGNAL_CHANGED, self._on_signal))

    async def stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown
                pass
        self._tasks.clear()

    async def _on_signal(self, event: Any) -> None:
        key = event.data.get("key")
        if key == "clock.epoch":
            await self._check_time_triggers()
        elif key == "environment.phase":
            await self._check_sun_triggers()
        await self._check_signal_triggers(key)

    async def _check_signal_triggers(self, key: str | None) -> None:
        for routine in self._routines:
            if not routine["enabled"]:
                continue
            for idx, trigger in enumerate(routine["triggers"]):
                if trigger["type"] == "signal" and trigger["signal"] == key:
                    now = _check(trigger["op"], self.twin.get(trigger["signal"]),
                                 trigger.get("value", 0.0))
                    cause = f"signal:{key}"
                elif trigger["type"] == "van" and key == "vehicle.ignition":
                    # park = ignition switched off; drive_off = switched on.
                    ignition = self.twin.get("vehicle.ignition")
                    if ignition is None:
                        continue
                    now = bool(ignition) if trigger["event"] == "drive_off" else not bool(ignition)
                    cause = f"van:{trigger['event']}"
                else:
                    continue
                edge = (routine["id"], idx)
                fired_before = self._edges.get(edge, False)
                self._edges[edge] = now
                if now and not fired_before:
                    self._spawn(routine["id"], cause)

    async def _check_sun_triggers(self) -> None:
        """Sunrise = the phase turning "day"; sunset = the light starting to
        fade (phase "dusk", or a jump straight day→night). An offset delays the
        run by sim-time minutes via a one-shot local-time target."""
        phase = str(self.twin.get("environment.phase") or "")
        previous, self._last_phase = self._last_phase, phase
        if previous is None or previous == phase:
            return
        sunrise = phase == "day" and previous in ("dawn", "dusk", "night")
        sunset = (phase == "dusk" and previous in ("day", "dawn")) or (
            phase == "night" and previous == "day"
        )
        for routine in self._routines:
            if not routine["enabled"]:
                continue
            for trigger in routine["triggers"]:
                if trigger["type"] != "sun":
                    continue
                if (trigger["event"] == "sunrise" and sunrise) or (
                    trigger["event"] == "sunset" and sunset
                ):
                    offset = int(trigger.get("offset_min") or 0)
                    if offset <= 0:
                        self._spawn(routine["id"], f"sun:{trigger['event']}")
                    else:
                        minutes = self._local_minutes()
                        if minutes is not None:
                            self._pending_at.append(
                                (routine["id"], (minutes + offset) % (24 * 60))
                            )

    async def _check_time_triggers(self) -> None:
        minutes = self._local_minutes()
        if minutes is None:
            return
        previous, self._last_minutes = self._last_minutes, minutes
        if previous is None or previous == minutes:
            return
        # One-shot sun-offset targets first (consumed on fire).
        still_pending: list[tuple[str, int]] = []
        for routine_id, target in self._pending_at:
            if _minute_crossed(previous, minutes, target):
                self._spawn(routine_id, "sun:offset")
            else:
                still_pending.append((routine_id, target))
        self._pending_at = still_pending
        for routine in self._routines:
            if not routine["enabled"]:
                continue
            for trigger in routine["triggers"]:
                if trigger["type"] != "time":
                    continue
                try:
                    hh, mm = trigger["at"].split(":")
                    target = int(hh) * 60 + int(mm)
                except ValueError:
                    continue
                if _minute_crossed(previous, minutes, target):
                    self._spawn(routine["id"], f"time:{trigger['at']}")

    def _local_minutes(self) -> int | None:
        """Local time-of-day in minutes from the sim clock + longitude — the
        same solar-time approximation the sun model uses."""
        epoch = self.twin.get("clock.epoch")
        try:
            epoch = float(epoch)
        except (TypeError, ValueError):
            return None
        lon = _num(self.twin.get("gps.lon"), 0.0)
        local = epoch + lon / 15.0 * 3600.0
        return int(local // 60) % (24 * 60)

    def _spawn(self, routine_id: str, cause: str) -> None:
        if routine_id in self._running:
            return  # never stack runs of the same routine
        logger.info("routine %s triggered by %s", routine_id, cause)
        task = asyncio.create_task(self.run(routine_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- execution --------------------------------------------------------

    async def run(self, routine_id: str) -> dict[str, Any] | None:
        routine = self.get(routine_id)
        if routine is None:
            return None
        if routine_id in self._running:
            return {"routine": _summary(routine), "steps": [], "applied": 0,
                    "ok": False, "reason": "already running"}
        self._running.add(routine_id)
        try:
            return await self._run_steps(routine)
        finally:
            self._running.discard(routine_id)

    async def _run_steps(self, routine: dict[str, Any]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        stopped = False
        for step in routine["steps"]:
            kind = step["type"]
            if kind == "action":
                if step["entity_id"] not in self.hub.entities:
                    results.append({**step, "ok": False, "skipped": True, "reason": "not present"})
                    continue
                res = await self.hub.execute_intent(
                    Intent(step["entity_id"], step["command"], dict(step["params"]),
                           source="routine")
                )
                results.append({**step, "ok": res.ok, "reason": res.reason,
                                "blocked_by_safety": res.blocked_by_safety})
            elif kind == "wait":
                await asyncio.sleep(step["seconds"])
                results.append({**step, "ok": True})
            elif kind == "condition":
                passed = _check(step["op"], self.twin.get(step["signal"]), step["value"])
                results.append({**step, "ok": passed})
                if not passed:
                    stopped = True
                    break
            elif kind == "notify":
                await self.bus.publish(
                    "routine.notify",
                    {"routine": routine["id"], "name": routine["name"],
                     "message": step["message"]},
                )
                results.append({**step, "ok": True})
        applied = sum(1 for r in results if r.get("ok") and r.get("type") == "action")
        return {
            "routine": _summary(routine),
            # Scenes-compat alias so voice replies / older consumers keep working.
            "scene": _summary(routine),
            "steps": results,
            "applied": applied,
            "stopped": stopped,
            "ok": applied > 0 or (not stopped and bool(results)),
        }


def _summary(routine: dict[str, Any]) -> dict[str, Any]:
    return {"id": routine["id"], "name": routine["name"],
            "icon": routine["icon"], "description": routine["description"]}


def _minute_crossed(previous: int, current: int, target: int) -> bool:
    """True when the clock moved past `target` between two ticks (wrap-safe)."""
    if previous == current:
        return False
    if previous < current:  # normal advance
        return previous < target <= current
    # wrapped past midnight
    return target > previous or target <= current
