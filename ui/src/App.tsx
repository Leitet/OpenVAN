import { useEffect, useState } from "react";
import { useVanState } from "@shared/useVanState";
import { VanProvider, useVan, num } from "./state";
import { NavIcon } from "./components/NavIcon";
import { HomeTab } from "./tabs/HomeTab";
import { PowerTab } from "./tabs/PowerTab";
import { ComfortTab } from "./tabs/ComfortTab";
import { JourneyTab } from "./tabs/JourneyTab";
import { AssistantTab } from "./tabs/AssistantTab";
import { SettingsTab } from "./tabs/SettingsTab";

type TabId = "home" | "power" | "comfort" | "journey" | "assistant" | "settings";

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "home", label: "Home", icon: "home" },
  { id: "power", label: "Power", icon: "power" },
  { id: "comfort", label: "Comfort", icon: "comfort" },
  { id: "journey", label: "Journey", icon: "journey" },
  { id: "assistant", label: "Assistant", icon: "assistant" },
  { id: "settings", label: "Settings", icon: "settings" },
];

function StatusBar() {
  const { twin, assistant, connected } = useVan();
  const soc = num(twin["house_battery.soc"]);
  const water = num(twin["fresh_water.level_pct"]);
  const cabin = num(twin["cabin.temperature"]);
  return (
    <header className="statusbar">
      <div className="sb-vitals">
        <span className="sb-stat">
          <b>{soc?.toFixed(0) ?? "—"}%</b> battery
        </span>
        <span className="sb-stat">
          <b>{water?.toFixed(0) ?? "—"}%</b> water
        </span>
        <span className="sb-stat">
          <b>{cabin?.toFixed(0) ?? "—"}°</b> cabin
        </span>
      </div>
      <div className="sb-right">
        <span className={"conn" + (assistant.llm ? " up" : "")}>
          {(assistant.llm
            ? `AI ${assistant.connectivity ?? ""} · ${assistant.model}`
            : "AI offline") + (assistant.personality ? ` · ${assistant.personality}` : "")}
        </span>
        <span className={"conn" + (connected ? " up" : " down")}>
          {connected ? "Core" : "Reconnecting…"}
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
    case "assistant":
      return <AssistantTab />;
    case "settings":
      return <SettingsTab />;
  }
}

export default function App() {
  const van = useVanState();
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
          {TABS.map((t) => (
            <button
              key={t.id}
              className={"rail-tab" + (tab === t.id ? " active" : "")}
              onClick={() => setTab(t.id)}
            >
              <NavIcon name={t.icon} />
              <span>{t.label}</span>
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
