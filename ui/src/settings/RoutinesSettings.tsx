import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Bell,
  Car,
  Clock,
  DoorOpen,
  Droplet,
  Gauge,
  Hand,
  MessageSquare,
  Moon,
  Play,
  Plus,
  Shield,
  Sun,
  Tent,
  Thermometer,
  Timer,
  X,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { getRoutines, saveRoutines, resetRoutines, runScene } from "@shared/api";
import type { Routine, RoutineStep, RoutineTrigger } from "@shared/types";
import { useVan } from "../state";
import { useT } from "../i18n";

// Routines settings — the automation builder. Deliberately NOT a node graph:
// research on automation editors (Home Assistant's evolution up to plain-
// language building blocks) says vertical, sentence-like blocks are what people
// actually understand. Power comes from the vocabulary: triggers (manual /
// sensor threshold / time), ordered actions, waits, "only continue if" guards
// and notifications. Every action still runs through the safety layer.

const ICONS: Record<string, LucideIcon> = {
  moon: Moon,
  sun: Sun,
  tent: Tent,
  door: DoorOpen,
  zap: Zap,
  bell: Bell,
  droplet: Droplet,
  thermometer: Thermometer,
  shield: Shield,
  car: Car,
};

// The sensors a routine can react to / test — friendly names via existing
// label keys, honest units. Booleans get is-on/is-off operators.
const SIGNALS: { key: string; labelKey?: string; label?: string; unit?: string; bool?: boolean }[] = [
  { key: "house_battery.soc", labelKey: "label.battery", unit: "%" },
  { key: "house_battery.voltage", labelKey: "label.voltage", unit: "V" },
  { key: "solar.power", labelKey: "label.solar", unit: "W" },
  { key: "fresh_water.level_pct", labelKey: "label.freshWater", unit: "%" },
  { key: "grey_water.level_pct", labelKey: "label.greyWater", unit: "%" },
  { key: "cassette.level_pct", labelKey: "label.cassette", unit: "%" },
  { key: "diesel_tank.level_pct", label: "Diesel", unit: "%" },
  { key: "propane.level_pct", labelKey: "label.propane", unit: "%" },
  { key: "cabin.temperature", labelKey: "label.cabin", unit: "°C" },
  { key: "outside.temperature", labelKey: "label.outside", unit: "°C" },
  { key: "cabin.humidity_pct", label: "RH", unit: "%" },
  { key: "vehicle.speed_kmh", label: "Speed", unit: "km/h" },
  { key: "environment.is_day", label: "Daylight", bool: true },
  { key: "vehicle.ignition", label: "Ignition", bool: true },
  { key: "shore.connected", label: "Shore power", bool: true },
  { key: "security.door_open", label: "Door open", bool: true },
];

function RoutineIcon({ icon, size = 16 }: { icon: string; size?: number }) {
  const Icon = ICONS[icon] ?? Zap;
  return <Icon size={size} />;
}

function signalMeta(key: string | undefined) {
  return SIGNALS.find((s) => s.key === key);
}

function useSignalLabel() {
  const t = useT();
  return (key: string | undefined) => {
    const meta = signalMeta(key);
    if (!meta) return key ?? "?";
    if (meta.labelKey) {
      const label = t(meta.labelKey);
      return label === meta.labelKey ? (meta.label ?? meta.key) : label;
    }
    return meta.label ?? meta.key;
  };
}

// One readable phrase per trigger/condition — used in the list summaries and
// as block titles, so a routine reads like a sentence.
function usePhrases() {
  const t = useT();
  const sigLabel = useSignalLabel();
  const opText = (op?: string) =>
    op === "above" ? ">" : op === "below" ? "<" : op === "equals" ? "=" :
    op === "on" ? t("routines.isOn") : t("routines.isOff");
  const conditionPhrase = (c: { signal?: string; op?: string; value?: number }) => {
    const meta = signalMeta(c.signal);
    const value = meta?.bool || c.op === "on" || c.op === "off"
      ? ""
      : ` ${c.value ?? 0}${meta?.unit ?? ""}`;
    return `${sigLabel(c.signal)} ${opText(c.op)}${value}`;
  };
  const triggerPhrase = (trigger: RoutineTrigger) =>
    trigger.type === "manual" ? t("routines.manual")
    : trigger.type === "time" ? `${t("routines.at")} ${trigger.at}`
    : conditionPhrase(trigger);
  return { conditionPhrase, triggerPhrase, opText };
}

// --- condition fragment (shared by signal triggers and condition steps) -----

function ConditionFields({
  value,
  onChange,
}: {
  value: { signal?: string; op?: string; value?: number };
  onChange: (patch: Record<string, unknown>) => void;
}) {
  const t = useT();
  const sigLabel = useSignalLabel();
  const meta = signalMeta(value.signal);
  const numeric = !meta?.bool;
  return (
    <>
      <select
        value={value.signal ?? SIGNALS[0].key}
        onChange={(e) => {
          const next = signalMeta(e.target.value);
          onChange({
            signal: e.target.value,
            op: next?.bool ? "on" : value.op === "on" || value.op === "off" ? "below" : value.op,
          });
        }}
      >
        {SIGNALS.map((s) => (
          <option key={s.key} value={s.key}>
            {sigLabel(s.key)}
          </option>
        ))}
      </select>
      <select value={value.op ?? "below"} onChange={(e) => onChange({ op: e.target.value })}>
        {(numeric ? ["below", "above", "equals"] : ["on", "off"]).map((op) => (
          <option key={op} value={op}>
            {op === "above" ? ">" : op === "below" ? "<" : op === "equals" ? "=" :
             op === "on" ? t("routines.isOn") : t("routines.isOff")}
          </option>
        ))}
      </select>
      {numeric && (
        <span className="rt-value">
          <input
            type="number"
            value={value.value ?? 0}
            onChange={(e) => onChange({ value: Number(e.target.value) })}
          />
          <em>{meta?.unit ?? ""}</em>
        </span>
      )}
    </>
  );
}

// --- the editor --------------------------------------------------------------

function RoutineEditor({
  routine,
  onSave,
  onBack,
  saving,
}: {
  routine: Routine;
  onSave: (r: Routine) => void;
  onBack: () => void;
  saving: boolean;
}) {
  const t = useT();
  const { entities } = useVan();
  const [draft, setDraft] = useState<Routine>(() => JSON.parse(JSON.stringify(routine)));
  const patch = (p: Partial<Routine>) => setDraft((d) => ({ ...d, ...p }));

  const controllable = useMemo(
    () => Object.values(entities).filter((e) => e.controllable && e.commands.length > 0),
    [entities],
  );

  const patchTrigger = (i: number, p: Record<string, unknown>) =>
    patch({ triggers: draft.triggers.map((x, j) => (j === i ? { ...x, ...p } : x)) });
  const removeTrigger = (i: number) =>
    patch({ triggers: draft.triggers.filter((_, j) => j !== i) });
  const addTrigger = (trigger: RoutineTrigger) =>
    patch({ triggers: [...draft.triggers, trigger] });

  const patchStep = (i: number, p: Record<string, unknown>) =>
    patch({ steps: draft.steps.map((x, j) => (j === i ? { ...x, ...p } : x)) });
  const removeStep = (i: number) => patch({ steps: draft.steps.filter((_, j) => j !== i) });
  const moveStep = (i: number, delta: number) => {
    const j = i + delta;
    if (j < 0 || j >= draft.steps.length) return;
    const steps = [...draft.steps];
    [steps[i], steps[j]] = [steps[j], steps[i]];
    patch({ steps });
  };
  const addStep = (step: RoutineStep) => patch({ steps: [...draft.steps, step] });

  const stepIcon = (kind: string) =>
    kind === "action" ? <Zap size={14} /> : kind === "wait" ? <Timer size={14} /> :
    kind === "condition" ? <Gauge size={14} /> : <MessageSquare size={14} />;

  return (
    <section className="panel span2 routine-editor">
      <div className="integration-topbar">
        <h2>
          <RoutineIcon icon={draft.icon} /> {draft.name || t("routines.new")}
        </h2>
        <button className="mini" onClick={onBack}>
          <ArrowLeft size={14} /> {t("common.back")}
        </button>
      </div>

      <div className="rt-basics">
        <label>
          {t("routines.name")}
          <input type="text" value={draft.name} onChange={(e) => patch({ name: e.target.value })} />
        </label>
        <label>
          {t("routines.icon")}
          <select value={draft.icon} onChange={(e) => patch({ icon: e.target.value })}>
            {Object.keys(ICONS).map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </label>
        <label className="rt-check">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) => patch({ enabled: e.target.checked })}
          />
          {t("routines.enabled")}
        </label>
        <label className="rt-check">
          <input
            type="checkbox"
            checked={draft.show_on_home}
            onChange={(e) => patch({ show_on_home: e.target.checked })}
          />
          {t("routines.showOnHome")}
        </label>
      </div>

      <h3 className="rt-section">{t("routines.when")}</h3>
      {draft.triggers.map((trigger, i) => (
        <div className="rt-block" key={i}>
          <span className="rt-block-icon">
            {trigger.type === "manual" ? <Hand size={14} /> :
             trigger.type === "time" ? <Clock size={14} /> : <Gauge size={14} />}
          </span>
          {trigger.type === "manual" && <span>{t("routines.manual")}</span>}
          {trigger.type === "time" && (
            <>
              <span>{t("routines.at")}</span>
              <input
                type="time"
                value={trigger.at ?? "08:00"}
                onChange={(e) => patchTrigger(i, { at: e.target.value })}
              />
            </>
          )}
          {trigger.type === "signal" && (
            <ConditionFields value={trigger} onChange={(p) => patchTrigger(i, p)} />
          )}
          <button className="mini danger rt-x" onClick={() => removeTrigger(i)}>
            <X size={13} />
          </button>
        </div>
      ))}
      <div className="rt-adders">
        <button className="mini" onClick={() => addTrigger({ type: "manual" })}>
          <Hand size={13} /> {t("routines.addManual")}
        </button>
        <button
          className="mini"
          onClick={() => addTrigger({ type: "signal", signal: SIGNALS[0].key, op: "below", value: 20 })}
        >
          <Gauge size={13} /> {t("routines.addSensor")}
        </button>
        <button className="mini" onClick={() => addTrigger({ type: "time", at: "08:00" })}>
          <Clock size={13} /> {t("routines.addTime")}
        </button>
      </div>

      <h3 className="rt-section">{t("routines.do")}</h3>
      {draft.steps.map((step, i) => (
        <div className="rt-block" key={i}>
          <span className="rt-order">{i + 1}</span>
          <span className="rt-block-icon">{stepIcon(step.type)}</span>
          {step.type === "action" && (
            <>
              <select
                value={step.entity_id ?? ""}
                onChange={(e) => {
                  const entity = controllable.find((x) => x.entity_id === e.target.value);
                  patchStep(i, {
                    entity_id: e.target.value,
                    command: entity?.commands[0] ?? "turn_on",
                    params: {},
                  });
                }}
              >
                {controllable.map((entity) => (
                  <option key={entity.entity_id} value={entity.entity_id}>
                    {entity.name}
                  </option>
                ))}
              </select>
              <select
                value={step.command ?? ""}
                onChange={(e) => patchStep(i, { command: e.target.value, params: {} })}
              >
                {(controllable.find((x) => x.entity_id === step.entity_id)?.commands ?? []).map(
                  (c) => (
                    <option key={c} value={c}>
                      {c.replace(/_/g, " ")}
                    </option>
                  ),
                )}
              </select>
              {step.command === "set_temperature" && (
                <span className="rt-value">
                  <input
                    type="number"
                    value={Number(step.params?.temperature ?? 20)}
                    onChange={(e) =>
                      patchStep(i, { params: { temperature: Number(e.target.value) } })
                    }
                  />
                  <em>°C</em>
                </span>
              )}
            </>
          )}
          {step.type === "wait" && (
            <>
              <span>{t("routines.addWait")}</span>
              <span className="rt-value">
                <input
                  type="number"
                  min={0}
                  value={step.seconds ?? 0}
                  onChange={(e) => patchStep(i, { seconds: Number(e.target.value) })}
                />
                <em>s</em>
              </span>
            </>
          )}
          {step.type === "condition" && (
            <>
              <span title={t("routines.stopsHint")}>{t("routines.onlyIf")}</span>
              <ConditionFields value={step} onChange={(p) => patchStep(i, p)} />
            </>
          )}
          {step.type === "notify" && (
            <input
              className="rt-message"
              type="text"
              placeholder={t("routines.message")}
              value={step.message ?? ""}
              onChange={(e) => patchStep(i, { message: e.target.value })}
            />
          )}
          <span className="rt-tools">
            <button className="mini" disabled={i === 0} onClick={() => moveStep(i, -1)}>
              <ArrowUp size={13} />
            </button>
            <button
              className="mini"
              disabled={i === draft.steps.length - 1}
              onClick={() => moveStep(i, 1)}
            >
              <ArrowDown size={13} />
            </button>
            <button className="mini danger" onClick={() => removeStep(i)}>
              <X size={13} />
            </button>
          </span>
        </div>
      ))}
      <div className="rt-adders">
        <button
          className="mini"
          onClick={() =>
            addStep({
              type: "action",
              entity_id: controllable[0]?.entity_id ?? "",
              command: controllable[0]?.commands[0] ?? "turn_on",
              params: {},
            })
          }
        >
          <Zap size={13} /> {t("routines.addAction")}
        </button>
        <button className="mini" onClick={() => addStep({ type: "wait", seconds: 60 })}>
          <Timer size={13} /> {t("routines.addWait")}
        </button>
        <button
          className="mini"
          onClick={() => addStep({ type: "condition", signal: SIGNALS[0].key, op: "below", value: 20 })}
        >
          <Gauge size={13} /> {t("routines.addCondition")}
        </button>
        <button className="mini" onClick={() => addStep({ type: "notify", message: "" })}>
          <MessageSquare size={13} /> {t("routines.addNotify")}
        </button>
      </div>

      {draft.steps.some((s) => s.type === "condition") && (
        <p className="hint">{t("routines.stopsHint")}</p>
      )}

      <div className="setting-row">
        <span />
        <button className="mini primary" disabled={saving} onClick={() => onSave(draft)}>
          {saving ? t("common.saving") : t("common.save")}
        </button>
      </div>
    </section>
  );
}

// --- the list ----------------------------------------------------------------

export function RoutinesSettings() {
  const t = useT();
  const { triggerPhrase } = usePhrases();
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);

  useEffect(() => {
    getRoutines().then(setRoutines);
  }, []);

  const persist = async (next: Routine[]) => {
    setSaving(true);
    try {
      const saved = await saveRoutines(next);
      if (saved.length || next.length === 0) setRoutines(saved);
    } finally {
      setSaving(false);
    }
  };

  const newRoutine = (): Routine => ({
    id: "",
    name: "",
    icon: "zap",
    description: "",
    enabled: true,
    show_on_home: false,
    triggers: [{ type: "manual" }],
    steps: [],
  });

  const target = editing === "__new__" ? newRoutine() : routines.find((r) => r.id === editing);
  if (editing && target) {
    return (
      <RoutineEditor
        routine={target}
        saving={saving}
        onBack={() => setEditing(null)}
        onSave={async (draft) => {
          const next =
            editing === "__new__"
              ? [...routines, draft]
              : routines.map((r) => (r.id === editing ? draft : r));
          await persist(next);
          setEditing(null);
        }}
      />
    );
  }

  return (
    <section className="panel span2">
      <div className="integration-topbar">
        <h2>{t("settings.routines")}</h2>
        <div className="integration-actions">
          <button className="mini" onClick={() => resetRoutines().then(setRoutines)}>
            {t("routines.reset")}
          </button>
          <button className="mini primary" onClick={() => setEditing("__new__")}>
            <Plus size={13} /> {t("routines.new")}
          </button>
        </div>
      </div>
      <p className="hint">{t("routines.note")}</p>

      {routines.length === 0 ? (
        <p className="companion-quiet">{t("routines.empty")}</p>
      ) : (
        routines.map((routine) => (
          <div className={"rt-row" + (routine.enabled ? "" : " off")} key={routine.id}>
            <span className="rt-row-icon">
              <RoutineIcon icon={routine.icon} />
            </span>
            <div className="rt-row-main">
              <strong>{routine.name}</strong>
              <span className="rt-row-when">
                {routine.triggers.map((trg, i) => (
                  <em key={i}>{triggerPhrase(trg)}</em>
                ))}
                <em className="rt-count">
                  {routine.steps.length} {t("routines.steps")}
                </em>
              </span>
            </div>
            <label className="rt-check" title={t("routines.enabled")}>
              <input
                type="checkbox"
                checked={routine.enabled}
                onChange={(e) =>
                  persist(
                    routines.map((r) =>
                      r.id === routine.id ? { ...r, enabled: e.target.checked } : r,
                    ),
                  )
                }
              />
            </label>
            <button
              className="mini"
              title={t("routines.test")}
              disabled={testing === routine.id}
              onClick={async () => {
                setTesting(routine.id);
                try {
                  await runScene(routine.id);
                } finally {
                  setTesting(null);
                }
              }}
            >
              <Play size={13} />
            </button>
            <button className="mini" onClick={() => setEditing(routine.id)}>
              {t("integrations.configure")}
            </button>
            <button
              className="mini danger"
              onClick={() => persist(routines.filter((r) => r.id !== routine.id))}
            >
              <X size={13} />
            </button>
          </div>
        ))
      )}
    </section>
  );
}
