import { useEffect, useMemo, useState } from "react";
import {
  Plug,
  ShieldCheck,
  ShieldAlert,
  Shield,
  AlertTriangle,
  Wifi,
  WifiOff,
} from "lucide-react";
import { getIntegrations, setIntegration } from "@shared/api";
import type { IntegrationInfo } from "@shared/types";
import { useT } from "../i18n";

// The integration catalog. OpenVan supports protocols and ecosystems (Victron,
// ESPHome, MQTT/Home Assistant, Modbus, …), not one bespoke integration per
// device. Every entry is honest about how robust it is (status), how it connects
// (transport) and how risky control is (safety class), so a user can tell solid
// support from fragile at a glance. Enabling one turns its driver on; in sim mode
// the driver injects the raw signals real hardware would emit (Rule 1).

// Status → how robust, most trustworthy first. Colour + label.
const STATUS_LABEL: Record<string, string> = {
  native: "Native",
  certified: "Certified",
  open: "Open",
  community: "Community",
  experimental: "Experimental",
  reverse_engineered: "Reverse-engineered",
  cloud_dependent: "Cloud only",
  read_only: "Read-only",
  unsupported: "Unsupported",
};

// Green = robust, amber = works-but-caveats, red = fragile.
const STATUS_TONE: Record<string, "good" | "warn" | "bad"> = {
  native: "good",
  certified: "good",
  open: "good",
  community: "warn",
  experimental: "warn",
  read_only: "warn",
  reverse_engineered: "bad",
  cloud_dependent: "bad",
  unsupported: "bad",
};

const TRANSPORT_LABEL: Record<string, string> = {
  mqtt: "MQTT",
  modbus_tcp: "Modbus-TCP",
  modbus_rtu: "Modbus-RTU",
  ve_direct: "VE.Direct",
  ble: "BLE",
  serial: "Serial",
  http: "HTTP",
  websocket: "WebSocket",
  canbus: "CAN",
  rv_c: "RV-C",
  nmea2000: "NMEA 2000",
  signalk: "Signal K",
  cloud_rest: "Cloud REST",
  native_api: "Native API",
  zigbee: "Zigbee",
};

// Safety class 0..4 — how much damage a wrong command could do.
const SAFETY_LABEL = ["Read-only", "Low", "Moderate", "High", "Critical"];

function SafetyIcon({ level }: { level: number }) {
  if (level <= 0) return <ShieldCheck size={14} />;
  if (level >= 4) return <ShieldAlert size={14} />;
  if (level >= 3) return <ShieldAlert size={14} />;
  return <Shield size={14} />;
}

function IntegrationCard({
  it,
  busy,
  onToggle,
}: {
  it: IntegrationInfo;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  const tone = STATUS_TONE[it.status] ?? "warn";
  const safetyTone = it.safety_class >= 3 ? "bad" : it.safety_class >= 2 ? "warn" : "good";
  return (
    <div className={"integration-card" + (it.enabled ? " on" : "")}>
      <div className="integration-head">
        <div className="integration-title">
          <Plug size={16} className="integration-glyph" />
          <div>
            <strong>{it.name}</strong>
            {it.vendor && <span className="integration-vendor">{it.vendor}</span>}
          </div>
        </div>
        <label className="switch" title={it.enabled ? "Enabled" : "Disabled"}>
          <input
            type="checkbox"
            checked={it.enabled}
            disabled={busy}
            onChange={(e) => onToggle(e.target.checked)}
          />
          <span className="slider" />
        </label>
      </div>

      {it.description && <p className="integration-desc">{it.description}</p>}

      <div className="integration-badges">
        <span className={`badge badge-${tone}`} title="Support status">
          {STATUS_LABEL[it.status] ?? it.status}
        </span>
        <span className={`badge badge-${safetyTone}`} title="Safety class">
          <SafetyIcon level={it.safety_class} />
          {SAFETY_LABEL[it.safety_class] ?? `class ${it.safety_class}`}
        </span>
        <span className="badge badge-line" title="Priority">
          {it.priority}
        </span>
        <span className="badge badge-line" title={it.offline_capable ? "Works offline" : "Needs internet"}>
          {it.offline_capable ? <Wifi size={13} /> : <WifiOff size={13} />}
          {it.offline_capable ? "Offline" : "Online"}
        </span>
        {it.transports.map((tr) => (
          <span key={tr} className="badge badge-transport" title="Transport">
            {TRANSPORT_LABEL[tr] ?? tr}
          </span>
        ))}
      </div>

      {it.warning && (
        <p className="integration-warning">
          <AlertTriangle size={13} /> {it.warning}
        </p>
      )}
    </div>
  );
}

export function IntegrationsSettings() {
  const t = useT();
  const [items, setItems] = useState<IntegrationInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    getIntegrations().then(setItems);
  }, []);

  const toggle = async (id: string, enabled: boolean) => {
    setBusy(id);
    try {
      setItems(await setIntegration(id, enabled));
    } finally {
      setBusy(null);
    }
  };

  // Group by category so related ecosystems sit together (energy, climate, …).
  const groups = useMemo(() => {
    const by: Record<string, IntegrationInfo[]> = {};
    for (const it of items) (by[it.category] ??= []).push(it);
    return Object.entries(by).sort(([a], [b]) => a.localeCompare(b));
  }, [items]);

  return (
    <section className="panel span2">
      <h2>{t("settings.integrations")}</h2>
      <p className="hint">{t("settings.integrationsNote")}</p>

      {groups.map(([cat, list]) => (
        <div className="integration-group" key={cat}>
          <h3 className="integration-cat">{cat}</h3>
          <div className="integration-grid">
            {list.map((it) => (
              <IntegrationCard
                key={it.id}
                it={it}
                busy={busy === it.id}
                onToggle={(enabled) => toggle(it.id, enabled)}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
