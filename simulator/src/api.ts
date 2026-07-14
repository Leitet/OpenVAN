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
): Promise<IntentResult> {
  const res = await fetch("/api/intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entity_id, command }),
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
