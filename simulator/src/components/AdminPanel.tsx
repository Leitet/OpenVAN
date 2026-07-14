import { useEffect, useState } from "react";
import { getModels, getSettings, saveSettings } from "../api";
import type { Settings } from "../types";
import { Personalities } from "./Personalities";

// Curated fallbacks so the dropdowns are useful before (or without) a live
// /models fetch. Merged with fetched models + the current value.
const KNOWN_ONLINE_MODELS: Record<"openai" | "anthropic", string[]> = {
  openai: [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4-turbo",
    "o3",
    "o4-mini",
    "gpt-3.5-turbo",
  ],
  anthropic: [
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-fable-5",
    "claude-opus-4-7",
    "claude-opus-4-6",
  ],
};

export function AdminPanel() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offlineModels, setOfflineModels] = useState<string[]>([]);
  const [onlineModels, setOnlineModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = async () => {
    const [s, off, on] = await Promise.all([
      getSettings(),
      getModels("offline"),
      getModels("online"),
    ]);
    setSettings(s);
    setOfflineModels(off);
    setOnlineModels(on);
  };

  useEffect(() => {
    load();
  }, []);

  const patch = async (p: Parameters<typeof saveSettings>[0]) => {
    setSaving(true);
    setSaved(false);
    try {
      const updated = await saveSettings(p);
      setSettings(updated);
      // Provider / URL / key changes affect which models are reachable.
      const [off, on] = await Promise.all([
        getModels("offline"),
        getModels("online"),
      ]);
      setOfflineModels(off);
      setOnlineModels(on);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (!settings) return <div className="panel span2">Loading settings…</div>;

  // Always keep the currently-configured model selectable, even if the server
  // reports it under a different tag ("llama3.2" vs "llama3.2:latest").
  const offlineOptions = Array.from(
    new Set([...offlineModels, settings.offline.model].filter(Boolean)),
  );
  const onlineOptions = Array.from(
    new Set(
      [
        ...(KNOWN_ONLINE_MODELS[settings.online.provider] ?? []),
        ...onlineModels,
        settings.online.model,
      ].filter(Boolean),
    ),
  );
  const a = settings.assistant;

  return (
    <div className="admin">
      <section className="panel span2">
        <h2>Assistant</h2>
        <div className="setting-row">
          <label>Enable AI assistant</label>
          <input
            type="checkbox"
            checked={settings.ai_enabled}
            onChange={(e) => patch({ ai_enabled: e.target.checked })}
          />
        </div>
        <div className="setting-row">
          <label>Default connectivity (for profiles set to “inherit”)</label>
          <select
            value={settings.default_connectivity}
            onChange={(e) =>
              patch({
                default_connectivity: e.target.value as "online" | "offline",
              })
            }
          >
            <option value="offline">offline</option>
            <option value="online">online</option>
          </select>
        </div>
        <p className="hint">
          Effective now: <strong>{a.connectivity}</strong> / {a.model}{" "}
          <span className={"pill" + (a.llm ? " on" : "")}>
            {a.llm ? "active" : "offline / rules"}
          </span>{" "}
          — voice: {a.personality}
        </p>

        <h3 className="sub">Offline model (local Ollama)</h3>
        <div className="setting-row">
          <label>Model</label>
          <select
            value={settings.offline.model}
            onChange={(e) => patch({ offline_model: e.target.value })}
          >
            {offlineOptions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div className="setting-row">
          <label>Server URL</label>
          <input
            className="text-setting"
            defaultValue={settings.offline.base_url}
            onBlur={(e) =>
              e.target.value !== settings.offline.base_url &&
              patch({ offline_base_url: e.target.value })
            }
          />
        </div>

        <h3 className="sub">Online model</h3>
        <div className="setting-row">
          <label>Provider</label>
          <select
            value={settings.online.provider}
            onChange={(e) =>
              patch({ online_provider: e.target.value as "openai" | "anthropic" })
            }
          >
            <option value="openai">OpenAI-compatible</option>
            <option value="anthropic">Anthropic (Claude)</option>
          </select>
        </div>
        {settings.online.provider === "openai" && (
          <div className="setting-row">
            <label>API base URL</label>
            <input
              className="text-setting"
              placeholder="https://api.openai.com/v1"
              defaultValue={settings.online.base_url}
              onBlur={(e) =>
                e.target.value !== settings.online.base_url &&
                patch({ online_base_url: e.target.value })
              }
            />
          </div>
        )}
        <div className="setting-row">
          <label>Model</label>
          <select
            value={settings.online.model}
            onChange={(e) => patch({ online_model: e.target.value })}
          >
            {!settings.online.model && <option value="">— choose a model —</option>}
            {onlineOptions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div className="setting-row">
          <label>
            API key {settings.online.has_key && <span className="pill on">set</span>}
          </label>
          <input
            className="text-setting"
            type="password"
            placeholder={settings.online.has_key ? "•••••• (stored in memory)" : "paste key"}
            onBlur={(e) =>
              e.target.value && patch({ online_api_key: e.target.value })
            }
          />
        </div>
        <p className="hint">
          The key is held in memory only (never written to disk). Set it here, or
          via the <code>OPENVAN_ONLINE_API_KEY</code> environment variable.
        </p>
      </section>

      <Personalities />

      <section className="panel span2">
        <h2>Simulation</h2>
        <div className="setting-row">
          <label>Run environment simulation (thermal &amp; water physics)</label>
          <input
            type="checkbox"
            checked={settings.simulate}
            onChange={(e) => patch({ simulate: e.target.checked })}
          />
        </div>
        <p className="hint">
          When off, the twin holds still — useful for testing against fixed state.
        </p>
      </section>

      <section className="panel span2">
        <h2>System</h2>
        <div className="sys-grid">
          <div>
            <span className="sys-k">Version</span>
            {settings.version}
          </div>
          <div>
            <span className="sys-k">Core</span>
            {settings.host}:{settings.port}
          </div>
          <div>
            <span className="sys-k">Plugins</span>
            {settings.plugins.length}
          </div>
        </div>
        <ul className="plugin-list">
          {settings.plugins.map((p) => (
            <li key={p.domain}>
              <strong>{p.name}</strong> <span>v{p.version}</span>
              <span className="plugin-cats">{p.categories.join(", ")}</span>
            </li>
          ))}
        </ul>
        <p className="hint">
          Settings persist across restarts (saved locally). The API key is the
          exception — it stays in memory only and is never written to disk.
        </p>
      </section>

      <div className="save-status">
        {saving ? "Saving…" : saved ? "Saved ✓" : ""}
      </div>
    </div>
  );
}
