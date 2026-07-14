"""OpenVan Core — an offline-first, AI-first operating system for camper vans.

Home Assistant knows your home. OpenVan understands your journey.
"""

from __future__ import annotations

from .apiclient import OpenVanClient
from .backends import Backend, SimBackend
from .entities import Entity
from .events import Event, EventBus
from .hub import Hub
from .companion import Companion
from .intents import Intent, IntentResolver, IntentResult
from .llm import (
    AnthropicClient,
    LLMIntentResolver,
    ModelRouter,
    OllamaClient,
    OpenAICompatibleClient,
)
from .memory import TravelMemory
from .notices import Advisor, AdvisorEngine, Notice
from .personalities import Personality, PersonalityStore
from .plugins import Plugin, PluginManager
from .predictions import compute_predictions
from .runtime import Core, build_core
from .safety import SafetyDecision, SafetyRule, SafetyValidator
from .simulation import VanSimulation
from .telemetry import TelemetryRecorder, TelemetryStore
from .twin import VanTwin
from .weather import WeatherService

__version__ = "0.1.0"

__all__ = [
    "Backend",
    "SimBackend",
    "OpenVanClient",
    "Entity",
    "Event",
    "EventBus",
    "Hub",
    "Intent",
    "IntentResolver",
    "IntentResult",
    "AnthropicClient",
    "LLMIntentResolver",
    "ModelRouter",
    "OllamaClient",
    "OpenAICompatibleClient",
    "Companion",
    "Advisor",
    "AdvisorEngine",
    "Notice",
    "Personality",
    "PersonalityStore",
    "compute_predictions",
    "Plugin",
    "PluginManager",
    "Core",
    "build_core",
    "SafetyDecision",
    "SafetyRule",
    "SafetyValidator",
    "VanSimulation",
    "TelemetryStore",
    "TelemetryRecorder",
    "WeatherService",
    "TravelMemory",
    "VanTwin",
    "__version__",
]
