// Thin REST client for OpenVan Core. Same-origin via the Vite dev proxy.

export async function injectSignal(
  key: string,
  value: number | boolean,
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

export async function getBriefing(): Promise<string> {
  const res = await fetch("/api/briefing", { method: "POST" });
  const data = await res.json();
  return data.text as string;
}

import type { Settings } from "./types";

export interface SettingsPatch {
  ai_enabled?: boolean;
  default_connectivity?: "online" | "offline";
  offline_model?: string;
  offline_base_url?: string;
  online_provider?: "openai" | "anthropic";
  online_model?: string;
  online_base_url?: string;
  online_api_key?: string;
  simulate?: boolean;
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
