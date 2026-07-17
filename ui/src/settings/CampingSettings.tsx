import { useEffect, useState } from "react";
import { getCampSources, setCampSource } from "@shared/api";
import type { CampSourceInfo } from "@shared/types";
import { useT } from "../i18n";

// Manage camp-spot sources the same way you'd manage a device: enable/disable each
// provider. The van proposes places to stay from the enabled ones.
export function CampingSettings() {
  const t = useT();
  const [sources, setSources] = useState<CampSourceInfo[]>([]);

  useEffect(() => {
    getCampSources().then(setSources);
  }, []);

  const toggle = async (id: string, enabled: boolean) => {
    setSources(await setCampSource(id, enabled));
  };

  return (
    <section className="panel span2">
      <h2>{t("settings.camping")}</h2>
      <p className="hint">{t("settings.campingNote")}</p>
      {sources.length === 0 ? (
        <p className="companion-quiet">{t("settings.noCampSources")}</p>
      ) : (
        sources.map((s) => (
          <div className="setting-row" key={s.id}>
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
        ))
      )}
    </section>
  );
}
