import { useEffect, useState } from "react";
import {
  Battery,
  Droplet,
  Thermometer,
  Sun,
  Moon,
  Sunrise,
  Sunset,
  Clock,
  Sparkles,
  Cloud,
  Cpu,
  Signal,
  SignalZero,
  SunMoon,
} from "lucide-react";
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

const PHASE_ICON = { day: Sun, night: Moon, dawn: Sunrise, dusk: Sunset } as const;

// Night / driving mode: "auto" follows the van's real day/night state; "day"/"night"
// force it. Persisted per device (it's a property of this screen, not the van).
type NightMode = "auto" | "day" | "night";
const NIGHT_KEY = "openvan.nightMode";
const NIGHT_ICON = { auto: SunMoon, day: Sun, night: Moon } as const;
const NIGHT_NEXT: Record<NightMode, NightMode> = { auto: "night", night: "day", day: "auto" };

function StatusBar() {
  const { twin, assistant, connected } = useVan();
  const t = useT();
  const [nightMode, setNightMode] = useState<NightMode>(
    () => (localStorage.getItem(NIGHT_KEY) as NightMode) || "auto",
  );
  const isDay = twin["environment.is_day"] !== false;
  const nightOn = nightMode === "night" || (nightMode === "auto" && !isDay);
  useEffect(() => {
    document.documentElement.setAttribute("data-night", nightOn ? "on" : "off");
  }, [nightOn]);
  const cycleNight = () => {
    const next = NIGHT_NEXT[nightMode];
    setNightMode(next);
    localStorage.setItem(NIGHT_KEY, next);
  };
  const NightIcon = NIGHT_ICON[nightMode];
  const soc = num(twin["house_battery.soc"]);
  const water = num(twin["fresh_water.level_pct"]);
  const cabin = num(twin["cabin.temperature"]);
  const online = twin["connectivity.online"] !== false && twin["connectivity.online"] !== undefined;
  const signal = num(twin["connectivity.signal_pct"]);
  const network = String(twin["connectivity.network"] ?? "");
  const signalWeak = online && signal !== undefined && signal < 25;
  const epoch = num(twin["clock.epoch"]);
  const phase = String(twin["environment.phase"] ?? "day");
  const clock = epoch ? new Date(epoch * 1000).toUTCString().slice(5, 22) : null;
  const PhaseIcon = PHASE_ICON[phase as keyof typeof PHASE_ICON] ?? Clock;
  const aiTitle =
    (assistant.llm
      ? `${t("ai.prefix")} · ${assistant.connectivity === "online" ? t("ai.cloud") : t("ai.local")} · ${assistant.model}`
      : `${t("ai.prefix")} · ${t("ai.rulesOnly")}`) +
    (assistant.personality ? ` · ${assistant.personality}` : "");

  return (
    <header className="statusbar">
      <div className="sb-vitals">
        <span className="sb-stat">
          <Battery className="sb-ico" style={{ color: soc != null && soc < 20 ? "var(--warn)" : undefined }} />
          <b>{soc?.toFixed(0) ?? "—"}</b>
          <i>%</i>
        </span>
        <span className="sb-stat">
          <Droplet className="sb-ico" style={{ color: water != null && water < 15 ? "var(--warn)" : undefined }} />
          <b>{water?.toFixed(0) ?? "—"}</b>
          <i>%</i>
        </span>
        <span className="sb-stat">
          <Thermometer className="sb-ico" />
          <b>{cabin?.toFixed(0) ?? "—"}</b>
          <i>°</i>
        </span>
        <span
          className="sb-stat"
          title={
            online
              ? `${network || t("nav.journey")} · ${signal?.toFixed(0) ?? "—"}%`
              : t("connectivity.offline")
          }
        >
          {online ? (
            <Signal
              className="sb-ico"
              style={{ color: signalWeak ? "var(--warn)" : undefined }}
            />
          ) : (
            <SignalZero className="sb-ico" style={{ color: "var(--muted)" }} />
          )}
          <b>{online ? (signal?.toFixed(0) ?? "—") : t("connectivity.off")}</b>
          {online && <i>%</i>}
        </span>
      </div>
      <div className="sb-right">
        {clock && (
          <span className="sb-clock" title={phase}>
            <PhaseIcon className="sb-ico" />
            <span>{clock}</span>
          </span>
        )}
        <button
          className="sb-night"
          data-on={nightOn}
          onClick={cycleNight}
          title={t(`night.${nightMode}`)}
        >
          <NightIcon className="sb-ico" />
        </button>
        <span className="sb-chip sb-ai" data-on={assistant.llm} title={aiTitle}>
          <Sparkles className="sb-ico sb-ai-spark" />
          {assistant.llm ? (
            <>
              {assistant.connectivity === "online" ? (
                <Cloud className="sb-ico" />
              ) : (
                <Cpu className="sb-ico" />
              )}
              <span className="sb-ai-model">{assistant.model}</span>
            </>
          ) : (
            <span className="sb-ai-model">{t("ai.rulesOnly")}</span>
          )}
        </span>
        <span
          className="sb-conn"
          data-on={connected}
          title={connected ? t("status.coreHint") : t("status.reconnecting")}
        >
          <span className="sb-conn-dot" />
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
