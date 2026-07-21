"""Conversation memory — short-term turns, a long-term summary, and learned
preferences, so the van "learns how you want it".

Three layers, smallest to largest horizon:

- **turns**    — the last few messages verbatim, for immediate follow-ups
  ("turn it on" → the heater we just talked about). In memory only.
- **summary**  — a compact running gist of older conversation, folded in by the
  model when the window overflows so context isn't lost as it scrolls off.
- **preferences** — durable facts about how the traveller likes things ("cabin
  around 21°C", "prefers quiet spots away from roads", "wakes early"). These shape
  future chat, camp picks and briefings.

Offline-first (Rule 3): the turn window always works with no model. Summary and
preference *learning* are model-enhanced — when a model is available it consolidates
them, and both persist to the local config store so they survive restarts. Like the
rest of the assistant, this only shapes phrasing and suggestions; it never controls
hardware on its own (Rule 2).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# --- learned-setpoint extraction (en/sv/de, deterministic) -------------------
# A temperature with an explicit unit ("21°C", "17 degrees", "19 grader"), or —
# only in a sentence that talks about temperature at all — an anchored bare
# number ("around 21", "runt 19", "um 18").
_UNIT_TEMP_RE = re.compile(
    r"(\d{1,2}(?:[.,]\d)?)\s*(?:°\s*c?|degrees?\b|deg\b|grader\b|grad\b|c\b)", re.I
)
_ANCHOR_TEMP_RE = re.compile(
    r"(?:around|about|at|near|runt|cirka|ca|um|auf)\s+(\d{1,2}(?:[.,]\d)?)\b", re.I
)
_SLEEP_WORDS = ("sleep", "night", "bed", "sova", "sömn", "natt", "schlaf", "schläf", "nacht")
_TEMP_CONTEXT = (
    "temp", "°", "warm", "cosy", "cozy", "heat", "cabin",
    "kupé", "grader", "varm", "värme", "kabine", "heiz",
)

_NS = "assistant"  # config-store namespace for persisted memory

# Internal maintenance prompt (not persona-voiced — it returns JSON, not speech).
MEMORY_SYSTEM = """\
Your task: maintain the van's long-term memory of this traveller from the recent
conversation. You are given the running `summary`, the known `preferences` (durable
facts about how they like things), and the latest `messages` (oldest first).

Return JSON ONLY:
  {"summary": "<=70 words, third person, the durable gist>",
   "preferences": ["short phrase", ...]}

Rules for `preferences`: keep only DURABLE likings and habits that should shape
future behaviour — comfort ("likes the cabin around 21°C"), camping ("prefers quiet
spots away from roads", "wants morning sun"), routine ("wakes early", "drives short
days"). Merge with the ones given, don't duplicate, drop anything contradicted. Max
12, each a short phrase. Do NOT store one-off requests, current sensor values, or
transient state. `summary` folds older context so it isn't lost — brief and factual.
Never invent anything not supported by the conversation. No markdown.
"""


class ChatMemory:
    def __init__(
        self,
        store: Any,
        router: Any,
        *,
        keep_turns: int = 8,
        consolidate_every: int = 4,
        max_preferences: int = 12,
    ) -> None:
        self.store = store
        self.router = router
        self.keep_turns = keep_turns
        self.consolidate_every = consolidate_every
        self.max_preferences = max_preferences
        self.turns: list[dict[str, str]] = []
        self.summary: str = ""
        self.preferences: list[str] = []
        self._since_consolidation = 0

    # --- persistence -----------------------------------------------------
    def load(self) -> None:
        data = self.store.get_all(_NS) if self.store is not None else {}
        self.summary = data.get("summary", "") or ""
        prefs = data.get("preferences", []) or []
        self.preferences = [str(p) for p in prefs if str(p).strip()]

    def _persist(self) -> None:
        if self.store is not None:
            self.store.set_many(_NS, {"summary": self.summary, "preferences": self.preferences})

    # --- turns -----------------------------------------------------------
    def record(self, role: str, content: str) -> None:
        if not content:
            return
        self.turns.append({"role": role, "content": content})
        # Keep more than we send so consolidation has material to fold.
        keep = self.keep_turns * 3
        if len(self.turns) > keep:
            del self.turns[: len(self.turns) - keep]
        if role == "user":
            self._since_consolidation += 1

    def recent(self) -> list[dict[str, str]]:
        return self.turns[-self.keep_turns :]

    def context(self) -> dict[str, Any]:
        """What the model gets to personalise a reply: the gist + what we've learned."""
        out: dict[str, Any] = {}
        if self.summary:
            out["summary"] = self.summary
        if self.preferences:
            out["preferences"] = self.preferences
        return out

    def snapshot(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "preferences": list(self.preferences),
            # Structured view of the free-text preferences (deterministic).
            "setpoints": self.learned_setpoints(),
        }

    def learned_setpoints(self) -> dict[str, float | None]:
        """The **learned setpoints seam**: deterministically parse the free-text
        preferences ("likes the cabin around 21°C", "sleeps best at 17 degrees")
        into structured temperatures. Offline-first — the *writing* of
        preferences is model-enhanced, but this extraction is a pure parser, so
        binding a learned temperature into a routine never depends on a model.
        Later preferences win; values outside a sane cabin range are ignored."""
        out: dict[str, float | None] = {"comfort_c": None, "sleep_c": None}
        for pref in self.preferences:
            text = pref.lower()
            match = _UNIT_TEMP_RE.search(text)
            if match is None and any(w in text for w in _TEMP_CONTEXT):
                match = _ANCHOR_TEMP_RE.search(text)
            if match is None:
                continue
            try:
                value = float(match.group(1).replace(",", "."))
            except ValueError:
                continue
            if not 5.0 <= value <= 30.0:
                continue
            key = "sleep_c" if any(w in text for w in _SLEEP_WORDS) else "comfort_c"
            out[key] = value
        return out

    def clear(self) -> None:
        self.turns.clear()
        self.summary = ""
        self.preferences = []
        self._since_consolidation = 0
        self._persist()

    # --- learning --------------------------------------------------------
    async def maybe_consolidate(self, persona: str | None = None, language: str = "en") -> None:
        """Every few turns, when a model is available, fold older conversation into
        the summary and update learned preferences. Best-effort and silent on
        failure — memory is an enhancement, never required for the chat to work."""
        if self._since_consolidation < self.consolidate_every:
            return
        if not getattr(self.router, "active", False):
            return
        self._since_consolidation = 0
        payload = json.dumps(
            {
                "summary": self.summary,
                "preferences": self.preferences,
                "messages": self.turns[-self.keep_turns * 2 :],
            }
        )
        try:
            raw = await self.router.build_client().chat_json(MEMORY_SYSTEM, payload)
        except Exception as exc:  # a memory hiccup must never break chatting
            logger.warning("memory consolidation failed: %r", exc)
            return
        self.apply(raw)

    def apply(self, raw: str | None) -> bool:
        """Merge a consolidation result (JSON) into summary/preferences. Returns
        whether anything changed. Separated out so it's trivially testable."""
        if not raw:
            return False
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return False
        if not isinstance(data, dict):
            return False
        changed = False
        summ = data.get("summary")
        if isinstance(summ, str) and summ.strip():
            self.summary = summ.strip()
            changed = True
        prefs = data.get("preferences")
        if isinstance(prefs, list):
            cleaned = []
            for p in prefs:
                s = str(p).strip()
                if s and s not in cleaned:
                    cleaned.append(s)
            self.preferences = cleaned[: self.max_preferences]
            changed = True
        if changed:
            self._persist()
        return changed
