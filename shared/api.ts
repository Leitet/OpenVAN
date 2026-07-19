// Thin REST client for OpenVan Core. Same-origin via the Vite dev proxy.

export async function injectSignal(
  key: string,
  value: number | boolean | string,
): Promise<void> {
  await fetch("/api/sim/signal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
}

export interface IntentResult {
  ok: boolean;
  reason: string;
  blocked_by_safety: boolean;
}

export async function sendIntent(
  entity_id: string,
  command: string,
  params: Record<string, unknown> = {},
): Promise<IntentResult> {
  const res = await fetch("/api/intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entity_id, command, params }),
  });
  return res.json();
}

export async function sendText(text: string): Promise<IntentResult> {
  const res = await fetch("/api/intent/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return res.json();
}

import type { CampSourceInfo, CampSpot } from "./types";

export interface ChatReply {
  reply: string;
  action: boolean; // true if a device command ran (vs a conversational answer)
  ok: boolean;
  blocked_by_safety: boolean;
  spots?: CampSpot[]; // present when the reply is a camp recommendation
}

// Conversational assistant: runs a command (safety-checked) or answers from state.
export async function sendChat(text: string): Promise<ChatReply> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return res.json();
}

export interface CampSearchResult {
  location: { lat: number; lon: number } | null;
  radius_km?: number;
  sources?: string[];
  spots: CampSpot[];
}

export async function campSearch(radius?: number): Promise<CampSearchResult> {
  const q = radius ? `?radius=${radius}` : "";
  return (await fetch(`/api/camp/search${q}`)).json();
}

export async function getCampSources(): Promise<CampSourceInfo[]> {
  const data = await (await fetch("/api/camp/sources")).json();
  return data.sources as CampSourceInfo[];
}

export async function setCampSource(
  id: string,
  enabled: boolean,
): Promise<CampSourceInfo[]> {
  const res = await fetch("/api/camp/sources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, enabled }),
  });
  return (await res.json()).sources as CampSourceInfo[];
}

export async function setCampSourceConfig(
  id: string,
  config: Record<string, string>,
): Promise<CampSourceInfo[]> {
  const res = await fetch("/api/camp/sources/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, config }),
  });
  return (await res.json()).sources as CampSourceInfo[];
}

import type { TelemetryPoint } from "./types";

export async function getSeries(
  key: string,
  minutes = 60,
  bucket?: number,
): Promise<TelemetryPoint[]> {
  const q = new URLSearchParams({ key, minutes: String(minutes) });
  if (bucket) q.set("bucket", String(bucket));
  const data = await (await fetch(`/api/telemetry/series?${q}`)).json();
  return data.points as TelemetryPoint[];
}

export async function getPredictions(): Promise<Record<string, number>> {
  return (await fetch("/api/telemetry/predictions")).json();
}

import type { Weather } from "./types";

export async function getWeather(): Promise<Weather> {
  return (await fetch("/api/weather")).json();
}

export async function refreshWeather(): Promise<Weather> {
  return (await fetch("/api/weather/refresh", { method: "POST" })).json();
}

export async function simulateWeather(scenario: "rain" | "clear"): Promise<Weather> {
  return (
    await fetch("/api/weather/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario }),
    })
  ).json();
}

import type { Stay } from "./types";

export async function getStays(): Promise<{ stays: Stay[]; current: Stay | null }> {
  return (await fetch("/api/memory/stays")).json();
}

async function postJson(url: string, body: unknown) {
  return (
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  ).json();
}

export const bookmarkHere = (note: string) =>
  postJson("/api/memory/bookmark", { note });
export const addStayNote = (text: string) => postJson("/api/memory/note", { text });
export const nameStay = (name: string) => postJson("/api/memory/place", { name });
export const deleteStay = (id: number) =>
  fetch(`/api/memory/stays/${id}`, { method: "DELETE" });

export async function getBriefing(): Promise<string> {
  const res = await fetch("/api/briefing", { method: "POST" });
  const data = await res.json();
  return data.text as string;
}

import type { Settings } from "./types";

export interface SettingsPatch {
  ai_enabled?: boolean;
  connectivity?: "online" | "offline";
  language?: "en" | "sv" | "de";
  offline_model?: string;
  offline_base_url?: string;
  online_provider?: "openai" | "openai_compatible" | "anthropic";
  online_model?: string;
  online_base_url?: string;
  online_api_key?: string;
  simulate?: boolean;
  tuning?: Record<string, number>;
  maintenance_intervals?: Record<string, number>;
}

export async function getSettings(): Promise<Settings> {
  return (await fetch("/api/settings")).json();
}

export async function saveSettings(patch: SettingsPatch): Promise<Settings> {
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return res.json();
}

export async function getModels(
  connectivity: "online" | "offline" = "offline",
): Promise<string[]> {
  const data = await (
    await fetch(`/api/models?connectivity=${connectivity}`)
  ).json();
  return data.models as string[];
}

import type { Personality } from "./types";

export async function getPersonalities(): Promise<{
  active: string;
  personalities: Personality[];
}> {
  return (await fetch("/api/personalities")).json();
}

export async function setActivePersonality(id: string): Promise<void> {
  await fetch("/api/personalities/active", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
}

export async function forkPersonality(
  base_id: string,
  name: string,
): Promise<Personality> {
  const res = await fetch("/api/personalities/fork", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_id, name }),
  });
  return res.json();
}

export async function updatePersonality(
  id: string,
  patch: Partial<Personality>,
): Promise<Personality> {
  const res = await fetch(`/api/personalities/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return res.json();
}

export async function deletePersonality(id: string): Promise<void> {
  await fetch(`/api/personalities/${id}`, { method: "DELETE" });
}

import type { AssistantMemory, SceneInfo, MaintenanceItem, VehicleState, VehicleProfile } from "./types";

export async function getVehicle(): Promise<VehicleState> {
  return (await fetch("/api/vehicle")).json();
}

export async function setVehicle(profile: VehicleProfile): Promise<VehicleState> {
  const res = await fetch("/api/vehicle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile }),
  });
  return res.json();
}

export async function getMaintenance(): Promise<MaintenanceItem[]> {
  const data = await (await fetch("/api/maintenance")).json();
  return data.items as MaintenanceItem[];
}

export async function completeMaintenance(id: string): Promise<MaintenanceItem[]> {
  const res = await fetch("/api/maintenance/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  return (await res.json()).items as MaintenanceItem[];
}

import type { CameraDef } from "./types";

export async function getCameras(): Promise<CameraDef[]> {
  return (await (await fetch("/api/cameras")).json()).cameras as CameraDef[];
}

export async function addCamera(cam: CameraDef): Promise<CameraDef[]> {
  const res = await fetch("/api/cameras", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cam),
  });
  return (await res.json()).cameras as CameraDef[];
}

export async function removeCamera(id: string): Promise<CameraDef[]> {
  const res = await fetch(`/api/cameras/${id}`, { method: "DELETE" });
  return (await res.json()).cameras as CameraDef[];
}

import type { IntegrationInfo } from "./types";

export async function getIntegrations(): Promise<IntegrationInfo[]> {
  // Tolerate an older Core without this endpoint (404) — never crash the UI over it.
  const res = await fetch("/api/integrations");
  if (!res.ok) return [];
  return ((await res.json()).integrations ?? []) as IntegrationInfo[];
}

export async function setIntegration(
  id: string,
  enabled: boolean,
): Promise<IntegrationInfo[]> {
  const res = await fetch("/api/integrations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, enabled }),
  });
  if (!res.ok) return [];
  return ((await res.json()).integrations ?? []) as IntegrationInfo[];
}

export async function setIntegrationConfig(
  id: string,
  values: Record<string, string>,
): Promise<IntegrationInfo[]> {
  const res = await fetch("/api/integrations/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, values }),
  });
  if (!res.ok) return [];
  return ((await res.json()).integrations ?? []) as IntegrationInfo[];
}

export async function getSecurity(): Promise<{ armed: boolean }> {
  return (await fetch("/api/security")).json();
}

export async function setSecurity(armed: boolean): Promise<{ armed: boolean }> {
  const res = await fetch("/api/security", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ armed }),
  });
  return res.json();
}

export async function getAssistantMemory(): Promise<AssistantMemory> {
  return (await fetch("/api/assistant/memory")).json();
}

export async function getScenes(): Promise<SceneInfo[]> {
  const data = await (await fetch("/api/scenes")).json();
  return data.scenes as SceneInfo[];
}

export async function runScene(id: string): Promise<{ applied: number; ok: boolean }> {
  const res = await fetch("/api/scenes/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  return res.json();
}

export async function clearAssistantMemory(): Promise<AssistantMemory> {
  return (await fetch("/api/assistant/memory", { method: "DELETE" })).json();
}
