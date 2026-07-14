import { useEffect, useState } from "react";
import { getModels, getSettings, saveSettings } from "../api";
import type { Settings } from "../types";

export function AdminPanel() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = async () => {
    const [s, m] = await Promise.all([getSettings(), getModels()]);
    setSettings(s);
    setModels(m);
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
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (!settings) return <div className="panel span2">Loading settings…</div>;

  // Always include the currently-configured model, even if Ollama reports it
  // under a different tag (e.g. "llama3.2" vs "llama3.2:latest").
  const modelOptions = Array.from(
    new Set([...models, settings.llm_model].filter(Boolean)),
  );

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
          <label>Model</label>
          <div className="setting-control">
            <select
              value={settings.llm_model}
              disabled={!settings.ai_enabled}
              onChange={(e) => patch({ llm_model: e.target.value })}
            >
              {modelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <span className={"pill" + (settings.llm_active ? " on" : "")}>
              {settings.llm_active ? "active" : "offline / rules"}
            </span>
          </div>
        </div>
        {models.length === 0 && (
          <p className="hint">
            No local models found. Install <code>ollama</code> and run{" "}
            <code>ollama pull llama3.2</code>, then reload.
          </p>
        )}
        <div className="setting-row">
          <label>LLM server URL</label>
          <input
            className="text-setting"
            defaultValue={settings.llm_base_url}
            onBlur={(e) =>
              e.target.value !== settings.llm_base_url &&
              patch({ llm_base_url: e.target.value })
            }
          />
        </div>
      </section>

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
      </section>

      <div className="save-status">
        {saving ? "Saving…" : saved ? "Saved ✓" : ""}
      </div>
    </div>
  );
}
