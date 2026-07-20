import { useEffect, useMemo, useState } from "react";
import {
  Plug,
  ShieldCheck,
  ShieldAlert,
  Shield,
  AlertTriangle,
  Wifi,
  WifiOff,
  Search,
  ArrowLeft,
  Plus,
  Check,
  Lock,
  Settings2,
  Radio,
  FlaskConical,
  Pause,
  Play,
  BadgeCheck,
  Users,
  ShieldQuestion,
} from "lucide-react";
import { getIntegrations, setIntegration, setIntegrationConfig } from "@shared/api";
import type { IntegrationInfo } from "@shared/types";
import { useT } from "../i18n";

// OpenVan will support thousands of integrations, so we don't show them all at once.
// Two surfaces: "Your integrations" (the small standard/installed set — just the
// simulator out of the box) and a searchable, filterable **library** the user opens
// to add more. Adding one turns its driver on; in sim mode it injects the raw signals
// real hardware would emit (Rule 1). Built-ins (the simulator) can't be removed.

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

const SAFETY_LABEL = ["Read-only", "Low", "Moderate", "High", "Critical"];

// Driver provenance (the signing/trust chain). "bundled" ships with core and
// needs no badge; everything installed from outside shows where it came from.
const TRUST_BADGE: Record<string, { label: string; tone: "good" | "warn"; icon: "check" | "users" | "question" }> = {
  official: { label: "Official", tone: "good", icon: "check" },
  community: { label: "Community-signed", tone: "good", icon: "users" },
  unknown_signer: { label: "Unknown signer", tone: "warn", icon: "question" },
  unsigned: { label: "Unsigned", tone: "warn", icon: "question" },
};

function TrustBadge({ trust }: { trust: string }) {
  const meta = TRUST_BADGE[trust];
  if (!meta) return null; // bundled → the default, no badge noise
  const Icon = meta.icon === "check" ? BadgeCheck : meta.icon === "users" ? Users : ShieldQuestion;
  return (
    <span className={`badge badge-${meta.tone}`} title="Driver provenance">
      <Icon size={13} />
      {meta.label}
    </span>
  );
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function SafetyIcon({ level }: { level: number }) {
  if (level <= 0) return <ShieldCheck size={14} />;
  if (level >= 3) return <ShieldAlert size={14} />;
  return <Shield size={14} />;
}

function IntegrationCard({
  it,
  busy,
  action,
  status,
  footer,
}: {
  it: IntegrationInfo;
  busy: boolean;
  action: React.ReactNode;
  status?: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const tone = STATUS_TONE[it.status] ?? "warn";
  const safetyTone = it.safety_class >= 3 ? "bad" : it.safety_class >= 2 ? "warn" : "good";
  return (
    <div className={"integration-card" + (it.installed ? " on" : "") + (busy ? " busy" : "")}>
      <div className="integration-head">
        <div className="integration-title">
          <Plug size={16} className="integration-glyph" />
          <div>
            <strong>{it.name}</strong>
            {it.vendor && <span className="integration-vendor">{it.vendor}</span>}
          </div>
        </div>
        {action}
      </div>

      {it.description && <p className="integration-desc">{it.description}</p>}

      <div className="integration-badges">
        {status}
        <TrustBadge trust={it.trust} />
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
        <span
          className="badge badge-line"
          title={it.offline_capable ? "Works offline" : "Needs internet"}
        >
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

      {footer}
    </div>
  );
}

// Connection editor for an installed integration that can point at real hardware.
// Fields come from the descriptor (mode/host/port/…); saving reconnects the driver.
function ConfigEditor({
  it,
  onSave,
  saving,
}: {
  it: IntegrationInfo;
  onSave: (values: Record<string, string>) => void;
  saving: boolean;
}) {
  const t = useT();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const field = (k: string, v: string) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div className="integration-config">
      {it.config.map((f) => (
        <div className="setting-row" key={f.key}>
          <label htmlFor={`${it.id}-${f.key}`}>{f.label}</label>
          {f.type === "select" ? (
            <select
              id={`${it.id}-${f.key}`}
              value={draft[f.key] ?? String(f.value ?? "")}
              onChange={(e) => field(f.key, e.target.value)}
            >
              {f.options.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={`${it.id}-${f.key}`}
              type={f.secret ? "password" : "text"}
              value={draft[f.key] ?? (f.secret ? "" : String(f.value ?? ""))}
              placeholder={f.secret && f.set ? "••••••• (stored)" : ""}
              autoComplete="off"
              onChange={(e) => field(f.key, e.target.value)}
            />
          )}
        </div>
      ))}
      <div className="setting-row">
        <span />
        <button className="mini primary" disabled={saving} onClick={() => onSave(draft)}>
          {saving ? t("common.saving") : t("common.save")}
        </button>
      </div>
    </div>
  );
}

export function IntegrationsSettings() {
  const t = useT();
  const [items, setItems] = useState<IntegrationInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [mode, setMode] = useState<"installed" | "library">("installed");

  // Library filters.
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [status, setStatus] = useState("");
  const [transport, setTransport] = useState("");
  const [offlineOnly, setOfflineOnly] = useState(false);
  const [configOpen, setConfigOpen] = useState<string | null>(null);

  useEffect(() => {
    getIntegrations().then(setItems);
  }, []);

  const set = async (id: string, enabled: boolean) => {
    setBusy(id);
    try {
      const next = await setIntegration(id, enabled);
      if (next.length) setItems(next);
    } finally {
      setBusy(null);
    }
  };

  const saveConfig = async (id: string, values: Record<string, string>) => {
    setBusy(id);
    try {
      const next = await setIntegrationConfig(id, values);
      if (next.length) setItems(next);
    } finally {
      setBusy(null);
    }
  };

  const statusBadge = (it: IntegrationInfo) =>
    it.builtin ? (
      // The simulator card: shows whether the environment physics runs.
      it.sim_engine ? (
        <span className="badge badge-good" title={t("integrations.simRunning")}>
          <FlaskConical size={12} /> {t("integrations.simRunning")}
        </span>
      ) : (
        <span className="badge badge-warn" title={t("integrations.simPaused")}>
          <Pause size={12} /> {t("integrations.simPaused")}
        </span>
      )
    ) : it.live ? (
      <span className="badge badge-good" title={t("integrations.connected")}>
        <Radio size={12} /> {it.mode}
      </span>
    ) : it.config.length > 0 ? (
      <span className="badge badge-line" title={t("integrations.simulated")}>
        <FlaskConical size={12} /> {t("integrations.simulated")}
      </span>
    ) : undefined;

  const installed = useMemo(() => items.filter((i) => i.installed), [items]);

  // Filter option lists derived from the whole catalog.
  const categories = useMemo(
    () => [...new Set(items.map((i) => i.category))].sort(),
    [items],
  );
  const statuses = useMemo(() => [...new Set(items.map((i) => i.status))].sort(), [items]);
  const transports = useMemo(
    () => [...new Set(items.flatMap((i) => i.transports))].sort(),
    [items],
  );

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return items
      .filter((i) => {
        if (cat && i.category !== cat) return false;
        if (status && i.status !== status) return false;
        if (transport && !i.transports.includes(transport)) return false;
        if (offlineOnly && !i.offline_capable) return false;
        if (needle) {
          const hay = `${i.name} ${i.vendor} ${i.description} ${i.category} ${i.id}`.toLowerCase();
          if (!hay.includes(needle)) return false;
        }
        return true;
      })
      .sort((a, b) => a.priority.localeCompare(b.priority) || a.name.localeCompare(b.name));
  }, [items, q, cat, status, transport, offlineOnly]);

  return (
    <section className="panel span2">
      <div className="integration-topbar">
        <h2>{t("settings.integrations")}</h2>
        {mode === "installed" ? (
          <button className="mini primary" onClick={() => setMode("library")}>
            <Search size={14} /> {t("integrations.browse")}
          </button>
        ) : (
          <button className="mini" onClick={() => setMode("installed")}>
            <ArrowLeft size={14} /> {t("integrations.back")}
          </button>
        )}
      </div>
      <p className="hint">{t("settings.integrationsNote")}</p>

      {mode === "installed" ? (
        <>
          <h3 className="integration-cat">
            {t("integrations.installed")} ({installed.length})
          </h3>
          {installed.length === 0 ? (
            <p className="companion-quiet">{t("integrations.none")}</p>
          ) : (
            <div className="integration-grid">
              {installed.map((it) => (
                <IntegrationCard
                  key={it.id}
                  it={it}
                  busy={busy === it.id}
                  status={statusBadge(it)}
                  action={
                    it.builtin ? (
                      // Built-in = never removed; the button pauses/resumes the
                      // environment physics instead (real van: pause; per-driver
                      // sim modes keep working for trials).
                      <div className="integration-actions">
                        <button
                          className={"mini" + (it.sim_engine ? "" : " primary")}
                          disabled={busy === it.id}
                          onClick={() => set(it.id, !it.sim_engine)}
                        >
                          {it.sim_engine ? <Pause size={13} /> : <Play size={13} />}
                          {t(it.sim_engine ? "integrations.pauseSim" : "integrations.resumeSim")}
                        </button>
                        <span className="badge badge-line" title={t("integrations.builtin")}>
                          <Lock size={12} /> {t("integrations.builtin")}
                        </span>
                      </div>
                    ) : (
                      <div className="integration-actions">
                        {it.config.length > 0 && (
                          <button
                            className={"mini" + (configOpen === it.id ? " primary" : "")}
                            onClick={() => setConfigOpen(configOpen === it.id ? null : it.id)}
                            title={t("integrations.configure")}
                          >
                            <Settings2 size={13} />
                          </button>
                        )}
                        <button
                          className="mini danger"
                          disabled={busy === it.id}
                          onClick={() => set(it.id, false)}
                        >
                          {t("integrations.remove")}
                        </button>
                      </div>
                    )
                  }
                  footer={
                    configOpen === it.id && it.config.length > 0 ? (
                      <ConfigEditor
                        it={it}
                        saving={busy === it.id}
                        onSave={(values) => saveConfig(it.id, values)}
                      />
                    ) : undefined
                  }
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <div className="integration-searchbar">
            <Search size={15} className="integration-search-glyph" />
            <input
              type="text"
              placeholder={t("integrations.search")}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              autoFocus
            />
          </div>
          <div className="integration-filters">
            <select value={cat} onChange={(e) => setCat(e.target.value)}>
              <option value="">{t("integrations.allCategories")}</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {titleCase(c)}
                </option>
              ))}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{t("integrations.allStatus")}</option>
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s] ?? s}
                </option>
              ))}
            </select>
            <select value={transport} onChange={(e) => setTransport(e.target.value)}>
              <option value="">{t("integrations.allTransports")}</option>
              {transports.map((tr) => (
                <option key={tr} value={tr}>
                  {TRANSPORT_LABEL[tr] ?? tr}
                </option>
              ))}
            </select>
            <label className="integration-offline">
              <input
                type="checkbox"
                checked={offlineOnly}
                onChange={(e) => setOfflineOnly(e.target.checked)}
              />
              {t("integrations.offlineOnly")}
            </label>
            <span className="integration-resultcount">
              {results.length} {t("integrations.count")}
            </span>
          </div>

          {results.length === 0 ? (
            <p className="companion-quiet">{t("integrations.noResults")}</p>
          ) : (
            <div className="integration-grid">
              {results.map((it) => (
                <IntegrationCard
                  key={it.id}
                  it={it}
                  busy={busy === it.id}
                  action={
                    it.installed ? (
                      it.builtin ? (
                        <span className="badge badge-line" title={t("integrations.builtin")}>
                          <Lock size={12} /> {t("integrations.builtin")}
                        </span>
                      ) : (
                        <span className="badge badge-good" title={t("integrations.added")}>
                          <Check size={12} /> {t("integrations.added")}
                        </span>
                      )
                    ) : (
                      <button
                        className="mini primary"
                        disabled={busy === it.id}
                        onClick={() => set(it.id, true)}
                      >
                        <Plus size={13} /> {t("integrations.add")}
                      </button>
                    )
                  }
                />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
