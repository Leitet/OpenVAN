import { useT, LANGS, LANG_NATIVE, type Lang } from "../i18n";
import { useSettings } from "./SettingsProvider";

export function GeneralSettings() {
  const t = useT();
  const { settings, lang, asstOverride, changeAppLang, changeAsstLang } = useSettings();
  if (!settings) return <div className="panel span2">{t("settings.loadingSettings")}</div>;

  return (
    <section className="panel span2">
      <h2>{t("settings.language")}</h2>
      <div className="setting-row">
        <label>{t("settings.appLanguage")}</label>
        <select value={lang} onChange={(e) => changeAppLang(e.target.value as Lang)}>
          {LANGS.map((l) => (
            <option key={l} value={l}>
              {LANG_NATIVE[l]}
            </option>
          ))}
        </select>
      </div>
      <div className="setting-row">
        <label>{t("settings.assistantLanguage")}</label>
        <select
          value={asstOverride ? settings.language : "auto"}
          onChange={(e) => changeAsstLang(e.target.value)}
        >
          <option value="auto">{t("settings.sameAsApp")}</option>
          {LANGS.map((l) => (
            <option key={l} value={l}>
              {LANG_NATIVE[l]}
            </option>
          ))}
        </select>
      </div>
      <p className="hint">{t("settings.languageNote")}</p>
    </section>
  );
}
