import { useEffect, useState } from "react";
import { useT } from "../i18n";
import { clearPendingSettings, peekPendingSettings } from "../navigation";
import { SettingsProvider, useSettings } from "../settings/SettingsProvider";
import { GeneralSettings } from "../settings/GeneralSettings";
import { AssistantSettings } from "../settings/AssistantSettings";
import { CampingSettings } from "../settings/CampingSettings";
import { SystemSettings } from "../settings/SystemSettings";
import { TuningSettings } from "../settings/TuningSettings";
import { VehicleSettings } from "../settings/VehicleSettings";
import { IntegrationsSettings } from "../settings/IntegrationsSettings";
import { Personalities } from "../components/Personalities";

type Category =
  | "general"
  | "assistant"
  | "personalities"
  | "vehicle"
  | "integrations"
  | "camping"
  | "tuning"
  | "system";

// Settings is split into categories, selected by the sub-tab bar. Adding a category
// = one entry here + one panel. Shared state lives in SettingsProvider.
const CATEGORIES: { id: Category; labelKey: string }[] = [
  { id: "general", labelKey: "settings.catGeneral" },
  { id: "assistant", labelKey: "settings.assistant" },
  { id: "personalities", labelKey: "personalities.title" },
  { id: "vehicle", labelKey: "settings.vehicle" },
  { id: "integrations", labelKey: "settings.integrations" },
  { id: "camping", labelKey: "settings.camping" },
  { id: "tuning", labelKey: "settings.tuning" },
  { id: "system", labelKey: "settings.system" },
];

export function SettingsTab() {
  return (
    <SettingsProvider>
      <SettingsCategories />
    </SettingsProvider>
  );
}

function SettingsCategories() {
  const t = useT();
  const { saving, saved } = useSettings();
  // Deep links (e.g. a "no data source" hint) land on a specific category —
  // consumed on mount (the event that opened Settings fired before we existed),
  // and listened for while already open.
  const [cat, setCat] = useState<Category>(
    () => (peekPendingSettings() as Category) ?? "general",
  );
  useEffect(() => {
    clearPendingSettings();
    const onNavigate = (e: Event) => {
      const target = (e as CustomEvent).detail?.settings;
      if (target) setCat(target as Category);
    };
    window.addEventListener("openvan:navigate", onNavigate);
    return () => window.removeEventListener("openvan:navigate", onNavigate);
  }, []);

  return (
    <div className="settings-view">
      <nav className="subtabs">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            className={"subtab" + (cat === c.id ? " active" : "")}
            onClick={() => setCat(c.id)}
          >
            {t(c.labelKey)}
          </button>
        ))}
      </nav>

      <div className="settings-body">
        {cat === "general" && <GeneralSettings />}
        {cat === "assistant" && <AssistantSettings />}
        {cat === "personalities" && <Personalities />}
        {cat === "vehicle" && <VehicleSettings />}
        {cat === "integrations" && <IntegrationsSettings />}
        {cat === "camping" && <CampingSettings />}
        {cat === "tuning" && <TuningSettings />}
        {cat === "system" && <SystemSettings />}
      </div>

      <div className="save-status">
        {saving ? t("common.saving") : saved ? t("settings.saved") : ""}
      </div>
    </div>
  );
}
