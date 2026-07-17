import { useEffect, useState } from "react";
import { useVanState } from "@shared/useVanState";
import { VanProvider, useVan, num } from "./state";
import { useT } from "./i18n";
import { NavIcon } from "./components/NavIcon";
import { HomeTab } from "./tabs/HomeTab";
import { PowerTab } from "./tabs/PowerTab";
import { ComfortTab } from "./tabs/ComfortTab";
import { JourneyTab } from "./tabs/JourneyTab";
import { SecurityTab } from "./tabs/SecurityTab";
import { AssistantTab } from "./tabs/AssistantTab";
import { SettingsTab } from "./tabs/SettingsTab";

type TabId =
  | "home"
  | "power"
  | "comfort"
  | "journey"
  | "security"
  | "assistant"
  | "settings";

const TABS: { id: TabId; labelKey: string; icon: string }[] = [
  { id: "home", labelKey: "nav.home", icon: "home" },
  { id: "power", labelKey: "nav.power", icon: "power" },
  { id: "comfort", labelKey: "nav.comfort", icon: "comfort" },
  { id: "journey", labelKey: "nav.journey", icon: "journey" },
  { id: "security", labelKey: "nav.security", icon: "security" },
  { id: "assistant", labelKey: "nav.assistant", icon: "assistant" },
  { id: "settings", labelKey: "nav.settings", icon: "settings" },
];

function StatusBar() {
  const { twin, assistant, connected } = useVan();
  const t = useT();
  const soc = num(twin["house_battery.soc"]);
  const water = num(twin["fresh_water.level_pct"]);
  const cabin = num(twin["cabin.temperature"]);
  const aiLabel =
    (assistant.llm
      ? `${t("ai.prefix")} · ${assistant.connectivity === "online" ? t("ai.cloud") : t("ai.local")} · ${assistant.model}`
      : `${t("ai.prefix")} · ${t("ai.rulesOnly")}`) +
    (assistant.personality ? ` · ${assistant.personality}` : "");
  return (
    <header className="statusbar">
      <div className="sb-vitals">
        <span className="sb-stat">
          <b>{soc?.toFixed(0) ?? "—"}%</b> {t("status.battery")}
        </span>
        <span className="sb-stat">
          <b>{water?.toFixed(0) ?? "—"}%</b> {t("status.water")}
        </span>
        <span className="sb-stat">
          <b>{cabin?.toFixed(0) ?? "—"}°</b> {t("status.cabin")}
        </span>
      </div>
      <div className="sb-right">
        <span className={"conn" + (assistant.llm ? " up" : "")}>{aiLabel}</span>
        <span className={"conn" + (connected ? " up" : " down")}>
          {connected ? t("status.core") : t("status.reconnecting")}
        </span>
      </div>
    </header>
  );
}

function TabView({ tab }: { tab: TabId }) {
  switch (tab) {
    case "home":
      return <HomeTab />;
    case "power":
      return <PowerTab />;
    case "comfort":
      return <ComfortTab />;
    case "journey":
      return <JourneyTab />;
    case "security":
      return <SecurityTab />;
    case "assistant":
      return <AssistantTab />;
    case "settings":
      return <SettingsTab />;
  }
}

export default function App() {
  const van = useVanState();
  const t = useT();
  const [tab, setTab] = useState<TabId>("home");

  // The whole UI themes to the active persona (design-system [data-theme]).
  useEffect(() => {
    document.documentElement.setAttribute(
      "data-theme",
      van.assistant.personality_id || "aurora",
    );
  }, [van.assistant.personality_id]);

  return (
    <VanProvider value={van}>
      <div className="os">
        <nav className="rail">
          <div className="rail-brand">OV</div>
          {TABS.map((item) => (
            <button
              key={item.id}
              className={"rail-tab" + (tab === item.id ? " active" : "")}
              onClick={() => setTab(item.id)}
            >
              <NavIcon name={item.icon} />
              <span>{t(item.labelKey)}</span>
            </button>
          ))}
        </nav>
        <div className="stage">
          <StatusBar />
          <main className="tabview">
            <TabView tab={tab} />
          </main>
        </div>
      </div>
    </VanProvider>
  );
}
