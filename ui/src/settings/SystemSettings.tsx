import { useVan } from "../state";
import { useT } from "../i18n";
import { EventLog } from "../components/EventLog";
import { useSettings } from "./SettingsProvider";

export function SystemSettings() {
  const t = useT();
  const { settings } = useSettings();
  const { log } = useVan();
  if (!settings) return <div className="panel span2">{t("settings.loadingSettings")}</div>;

  return (
    <>
      <section className="panel span2">
        <h2>{t("settings.system")}</h2>
        <div className="sys-grid">
          <div>
            <span className="sys-k">{t("settings.version")}</span>
            {settings.version}
          </div>
          <div>
            <span className="sys-k">{t("status.core")}</span>
            {settings.host}:{settings.port}
          </div>
          <div>
            <span className="sys-k">{t("settings.plugins")}</span>
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
        <p className="hint">{t("settings.persistNote")}</p>
      </section>

      <section className="panel span2">
        <EventLog log={log} />
      </section>
    </>
  );
}
