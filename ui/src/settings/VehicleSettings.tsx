import { useEffect, useState } from "react";
import { Truck } from "lucide-react";
import { getVehicle, setVehicle } from "@shared/api";
import type { VehicleState, VehicleProfile } from "@shared/types";
import { useT } from "../i18n";

type Field = { k: string; label: string; type?: string; unit?: string; options?: string[] };

// The van's physical facts drive accurate decisions (leveling, low-bridge/weight
// warnings, fitting a pitch) and give the assistant context. Pick a preset to
// auto-fill, then edit anything that differs from your registration.
const GROUPS: { title: string; items: Field[] }[] = [
  {
    title: "Identity",
    items: [
      { k: "make", label: "Make", type: "text" },
      { k: "model", label: "Model", type: "text" },
      { k: "variant", label: "Variant", type: "text" },
      { k: "year", label: "Year", type: "number" },
      { k: "category", label: "Category", type: "category" },
      { k: "fuel", label: "Fuel", type: "select", options: ["diesel", "petrol", "electric", "lpg"] },
    ],
  },
  {
    title: "Dimensions",
    items: [
      { k: "length_mm", label: "Length", unit: "mm", type: "number" },
      { k: "width_mm", label: "Width", unit: "mm", type: "number" },
      { k: "width_mirrors_mm", label: "Width incl. mirrors", unit: "mm", type: "number" },
      { k: "height_mm", label: "Height", unit: "mm", type: "number" },
      { k: "wheelbase_mm", label: "Wheelbase (axelavstånd)", unit: "mm", type: "number" },
      { k: "track_mm", label: "Track width", unit: "mm", type: "number" },
      { k: "turning_circle_m", label: "Turning circle", unit: "m", type: "number" },
      { k: "ground_clearance_mm", label: "Ground clearance", unit: "mm", type: "number" },
    ],
  },
  {
    title: "Weight",
    items: [
      { k: "kerb_weight_kg", label: "Kerb weight", unit: "kg", type: "number" },
      { k: "gross_weight_kg", label: "Gross weight (GVW)", unit: "kg", type: "number" },
      { k: "payload_kg", label: "Payload", unit: "kg", type: "number" },
      { k: "towing_kg", label: "Max towing", unit: "kg", type: "number" },
    ],
  },
  {
    title: "Fuel & range",
    items: [
      { k: "fuel_tank_l", label: "Fuel tank", unit: "L", type: "number" },
      { k: "adblue_l", label: "AdBlue tank", unit: "L", type: "number" },
      { k: "consumption_l_100km", label: "Consumption", unit: "L/100km", type: "number" },
    ],
  },
  {
    title: "Tyres",
    items: [
      { k: "tyre_size", label: "Tyre size", type: "text" },
      { k: "tyre_pressure_front_bar", label: "Pressure front", unit: "bar", type: "number" },
      { k: "tyre_pressure_rear_bar", label: "Pressure rear", unit: "bar", type: "number" },
    ],
  },
  {
    title: "Habitation",
    items: [
      { k: "berths", label: "Berths", type: "number" },
      { k: "seats", label: "Seats", type: "number" },
    ],
  },
];

export function VehicleSettings() {
  const t = useT();
  const [state, setState] = useState<VehicleState | null>(null);
  const [draft, setDraft] = useState<VehicleProfile>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getVehicle().then((s) => {
      setState(s);
      setDraft(s.profile);
    });
  }, []);

  if (!state) return null;

  const set = (k: string, v: string | number) =>
    setDraft((d) => ({ ...d, [k]: v }));
  const applyPreset = (id: string) => {
    const p = state.presets.find((x) => x.id === id);
    if (p) setDraft({ ...p.spec });
  };
  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const s = await setVehicle(draft);
      setState(s);
      setDraft(s.profile);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } finally {
      setSaving(false);
    }
  };

  const name = [draft.make, draft.model, draft.variant].filter(Boolean).join(" ");

  return (
    <div className="vehicle">
      <section className="panel">
        <div className="veh-head">
          <Truck className="veh-head-ico" />
          <div>
            <strong>{name || t("vehicle.untitled")}</strong>
            <span className="veh-sub">
              {draft.height_mm ? `${(Number(draft.height_mm) / 1000).toFixed(2)} m` : "—"} ·{" "}
              {draft.length_mm ? `${(Number(draft.length_mm) / 1000).toFixed(2)} m` : "—"} ·{" "}
              {draft.gross_weight_kg ? `${draft.gross_weight_kg} kg` : "—"}
            </span>
          </div>
        </div>
        <label className="veh-preset">
          <span>{t("vehicle.preset")}</span>
          <select value="" onChange={(e) => e.target.value && applyPreset(e.target.value)}>
            <option value="">{t("vehicle.pick")}</option>
            {state.presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </section>

      {GROUPS.map((g) => (
        <section className="panel veh-group" key={g.title}>
          <h3>{g.title}</h3>
          <div className="veh-grid">
            {g.items.map((f) => (
              <label className="veh-field" key={f.k}>
                <span>{f.label}</span>
                <span className="veh-input">
                  {f.type === "category" ? (
                    <select value={String(draft[f.k] ?? "")} onChange={(e) => set(f.k, e.target.value)}>
                      <option value="">—</option>
                      {state.categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  ) : f.type === "select" ? (
                    <select value={String(draft[f.k] ?? "")} onChange={(e) => set(f.k, e.target.value)}>
                      <option value="">—</option>
                      {f.options!.map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={f.type === "number" ? "number" : "text"}
                      value={draft[f.k] ?? ""}
                      onChange={(e) =>
                        set(f.k, f.type === "number" && e.target.value !== "" ? Number(e.target.value) : e.target.value)
                      }
                    />
                  )}
                  {f.unit && <em>{f.unit}</em>}
                </span>
              </label>
            ))}
          </div>
        </section>
      ))}

      <button className="mini" disabled={saving} onClick={save}>
        {saving ? t("common.saving") : saved ? t("settings.saved") : t("common.save")}
      </button>
    </div>
  );
}
