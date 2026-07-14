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

export async function getBriefing(): Promise<string> {
  const res = await fetch("/api/briefing", { method: "POST" });
  const data = await res.json();
  return data.text as string;
}

import type { Settings } from "./types";

export async function getSettings(): Promise<Settings> {
  return (await fetch("/api/settings")).json();
}

export async function saveSettings(
  patch: Partial<
    Pick<Settings, "ai_enabled" | "llm_model" | "llm_base_url" | "simulate">
  >,
): Promise<Settings> {
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return res.json();
}

export async function getModels(): Promise<string[]> {
  const data = await (await fetch("/api/models")).json();
  return data.models as string[];
}
