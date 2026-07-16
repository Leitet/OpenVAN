import { useT } from "../i18n";
import { useSettings } from "./SettingsProvider";

export function AssistantSettings() {
  const t = useT();
  const { settings, offlineModels, onlineModels, loadingModels, patch, refreshModels } =
    useSettings();
  if (!settings) return <div className="panel span2">{t("settings.loadingSettings")}</div>;

  // Keep the current value selectable even if the server tags it differently.
  const offlineOptions = Array.from(
    new Set([...offlineModels, settings.offline.model].filter(Boolean)),
  );
  // Only the models the configured key can access (live /models fetch), plus the
  // current selection so it always shows.
  const onlineOptions = Array.from(
    new Set([...onlineModels, settings.online.model].filter(Boolean)),
  ).sort();
  const a = settings.assistant;

  return (
    <section className="panel span2">
      <h2>{t("settings.assistant")}</h2>
      <div className="setting-row">
        <label>{t("settings.enableAi")}</label>
        <input
          type="checkbox"
          checked={settings.ai_enabled}
          onChange={(e) => patch({ ai_enabled: e.target.checked })}
        />
      </div>
      <h3 className="sub">{t("settings.connectivityHeading")}</h3>
      <div className="mode-switch">
        <button
          className={"mode-btn" + (settings.connectivity === "offline" ? " active" : "")}
          onClick={() => patch({ connectivity: "offline" })}
        >
          <strong>{t("settings.offline")}</strong>
          <span>{t("settings.offlineDesc")}</span>
        </button>
        <button
          className={"mode-btn" + (settings.connectivity === "online" ? " active" : "")}
          onClick={() => patch({ connectivity: "online" })}
        >
          <strong>{t("settings.online")}</strong>
          <span>{t("settings.onlineDesc")}</span>
        </button>
      </div>
      <p className="hint">
        {t("settings.talkingTo")}{" "}
        <strong>
          {a.connectivity === "online" ? t("ai.cloud") : t("ai.local")} · {a.model}
        </strong>{" "}
        <span className={"pill" + (a.llm ? " on" : "")}>
          {a.llm ? t("settings.active") : t("ai.rulesOnly")}
        </span>
        {settings.connectivity === "online" && a.connectivity !== "online"
          ? a.llm
            ? t("settings.cloudFellBackLocal")
            : t("settings.cloudFellBackRules")
          : ""}{" "}
        · {t("settings.voice")}: {a.personality}. {t("settings.connectivityGlobal")}
      </p>

      <div className={"model-card" + (settings.connectivity === "offline" ? " in-use" : "")}>
        <div className="model-card-head">
          <h3 className="sub">{t("settings.localModel")}</h3>
          {settings.connectivity === "offline" && (
            <span className="pill on">{t("settings.inUse")}</span>
          )}
        </div>
        <div className="setting-row">
          <label>{t("settings.model")}</label>
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
          <label>{t("settings.serverUrl")}</label>
          <input
            className="text-setting"
            defaultValue={settings.offline.base_url}
            onBlur={(e) =>
              e.target.value !== settings.offline.base_url &&
              patch({ offline_base_url: e.target.value })
            }
          />
        </div>
      </div>

      <div className={"model-card" + (settings.connectivity === "online" ? " in-use" : "")}>
        <div className="model-card-head">
          <h3 className="sub">{t("settings.cloudModel")}</h3>
          {settings.connectivity === "online" && (
            <span className="pill on">{t("settings.inUse")}</span>
          )}
        </div>
        <div className="setting-row">
          <label>{t("settings.provider")}</label>
          <select
            value={settings.online.provider}
            onChange={(e) =>
              patch({
                online_provider: e.target.value as "openai" | "openai_compatible" | "anthropic",
              })
            }
          >
            <option value="openai">OpenAI</option>
            <option value="openai_compatible">OpenAI-compatible</option>
            <option value="anthropic">Anthropic (Claude)</option>
          </select>
        </div>
        {settings.online.provider === "openai_compatible" && (
          <div className="setting-row">
            <label>{t("settings.apiBaseUrl")}</label>
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
          <label>{t("settings.model")}</label>
          <div className="model-picker">
            <select
              value={settings.online.model}
              onChange={(e) => patch({ online_model: e.target.value })}
              disabled={loadingModels}
            >
              {!settings.online.model && (
                <option value="">
                  {loadingModels
                    ? t("settings.loadingModels")
                    : onlineModels.length
                      ? t("settings.chooseModel")
                      : settings.online.has_key
                        ? t("settings.noModels")
                        : t("settings.pasteKeyToLoad")}
                </option>
              )}
              {onlineOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <button
              className="mini"
              onClick={refreshModels}
              disabled={loadingModels}
              title={t("common.refresh")}
            >
              {loadingModels ? "…" : t("common.refresh")}
            </button>
          </div>
        </div>
        {onlineModels.length > 0 && (
          <p className="hint">
            {onlineModels.length === 1
              ? t("settings.modelsAvailable1", { n: onlineModels.length })
              : t("settings.modelsAvailable", { n: onlineModels.length })}
          </p>
        )}
        <div className="setting-row">
          <label>
            {t("settings.apiKey")}{" "}
            {settings.online.has_key && <span className="pill on">{t("settings.set")}</span>}
          </label>
          <input
            className="text-setting"
            type="password"
            placeholder={settings.online.has_key ? t("settings.keyStored") : t("settings.pasteKey")}
            onBlur={(e) => e.target.value && patch({ online_api_key: e.target.value })}
          />
        </div>
        <p className="hint">{t("settings.keyNote")}</p>
      </div>
    </section>
  );
}
