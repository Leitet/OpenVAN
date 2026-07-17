import { useEffect, useState } from "react";
import { getCampSources, setCampSource, setCampSourceConfig } from "@shared/api";
import type { CampSourceInfo } from "@shared/types";
import { useT } from "../i18n";

// Manage camp-spot sources the same way you'd manage a device: enable/disable each
// provider and, for sources that need credentials (API key, endpoint), edit those
// here. The values are saved in the local config database — never in env vars — so
// they survive restarts. Secrets are write-only: we show whether one is set, never
// the value itself.
export function CampingSettings() {
  const t = useT();
  const [sources, setSources] = useState<CampSourceInfo[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    getCampSources().then(setSources);
  }, []);

  const toggle = async (id: string, enabled: boolean) => {
    setSources(await setCampSource(id, enabled));
  };

  const setField = (sourceId: string, key: string, value: string) =>
    setDrafts((d) => ({ ...d, [sourceId]: { ...(d[sourceId] || {}), [key]: value } }));

  const saveConfig = async (id: string) => {
    setSaving(id);
    try {
      const next = await setCampSourceConfig(id, drafts[id] || {});
      setSources(next);
      setDrafts((d) => ({ ...d, [id]: {} })); // clear the draft (secrets shouldn't linger)
    } finally {
      setSaving(null);
    }
  };

  return (
    <section className="panel span2">
      <h2>{t("settings.camping")}</h2>
      <p className="hint">{t("settings.campingNote")}</p>
      {sources.length === 0 ? (
        <p className="companion-quiet">{t("settings.noCampSources")}</p>
      ) : (
        sources.map((s) => (
          <div className="camp-source" key={s.id}>
            <div className="setting-row">
              <label>
                {s.name}
                {s.requires_internet && (
                  <span className="pill"> {t("settings.needsInternet")}</span>
                )}
                {s.requires_key && <span className="pill"> {t("settings.needsKey")}</span>}
              </label>
              <input
                type="checkbox"
                checked={s.enabled}
                onChange={(e) => toggle(s.id, e.target.checked)}
              />
            </div>
            {s.config.length > 0 && (
              <div className="camp-source-config">
                {s.config.map((f) => (
                  <div className="setting-row" key={f.key}>
                    <label htmlFor={`${s.id}-${f.key}`}>{f.label}</label>
                    <input
                      id={`${s.id}-${f.key}`}
                      type={f.secret ? "password" : "text"}
                      value={drafts[s.id]?.[f.key] ?? (f.secret ? "" : f.value ?? "")}
                      placeholder={f.secret && f.set ? "••••••• (stored)" : ""}
                      autoComplete="off"
                      onChange={(e) => setField(s.id, f.key, e.target.value)}
                    />
                  </div>
                ))}
                <div className="setting-row">
                  <span />
                  <button
                    className="mini"
                    disabled={saving === s.id}
                    onClick={() => saveConfig(s.id)}
                  >
                    {saving === s.id ? t("common.saving") : t("common.save")}
                  </button>
                </div>
              </div>
            )}
          </div>
        ))
      )}
    </section>
  );
}
