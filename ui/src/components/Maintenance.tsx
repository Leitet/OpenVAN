import { useEffect, useState } from "react";
import { getMaintenance, completeMaintenance } from "@shared/api";
import type { MaintenanceItem } from "@shared/types";
import { useT } from "../i18n";

// Service schedule: odometer- and date-based reminders with a one-tap "done" that
// resets the next-due. Overdue items are flagged.
function remaining(item: MaintenanceItem, t: (k: string) => string): string {
  if (item.kind === "odometer") {
    const km = item.remaining_km ?? 0;
    return km <= 0 ? t("maint.overdue") : `${km.toLocaleString()} km`;
  }
  const d = item.remaining_days ?? 0;
  return d <= 0 ? t("maint.overdue") : `${d} ${t("maint.days")}`;
}

export function Maintenance() {
  const t = useT();
  const [items, setItems] = useState<MaintenanceItem[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    getMaintenance().then(setItems);
  }, []);

  const done = async (id: string) => {
    setBusy(id);
    try {
      setItems(await completeMaintenance(id));
    } finally {
      setBusy(null);
    }
  };

  if (items.length === 0) return null;

  return (
    <section className="panel maintenance">
      <h2>{t("maint.title")}</h2>
      <div className="maint-list">
        {items.map((item) => (
          <div key={item.id} className={"maint-row" + (item.due ? " due" : "")}>
            <div className="maint-info">
              <span className="maint-label">{item.label}</span>
              <span className="maint-remaining">{remaining(item, t)}</span>
            </div>
            <button className="mini" disabled={busy === item.id} onClick={() => done(item.id)}>
              {t("maint.done")}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
