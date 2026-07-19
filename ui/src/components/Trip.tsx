import { useCallback, useEffect, useState } from "react";
import { Route, Moon, MapPin, Sun, CalendarDays, RotateCcw } from "lucide-react";
import { getTrip, resetTrip } from "@shared/api";
import type { TripStats } from "@shared/types";
import { useT } from "../i18n";

// A simple journey ledger: how far, how many nights, where, how much sun — composed
// from the odometer, the travel journal and telemetry, measured from a resettable
// start marker. Nothing new is recorded; it just reads what OpenVan already keeps.
export function Trip() {
  const t = useT();
  const [trip, setTrip] = useState<TripStats | null>(null);
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async () => setTrip(await getTrip()), []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  const doReset = async () => {
    setTrip(await resetTrip());
    setConfirming(false);
  };

  if (!trip) return null;

  const stats = [
    { icon: <Route size={18} />, label: t("trip.distance"), value: `${trip.distance_km.toFixed(0)} km` },
    { icon: <CalendarDays size={18} />, label: t("trip.days"), value: trip.days.toFixed(1) },
    { icon: <Moon size={18} />, label: t("trip.nights"), value: String(trip.nights) },
    { icon: <MapPin size={18} />, label: t("trip.places"), value: String(trip.place_count) },
    ...(trip.solar_wh != null
      ? [{ icon: <Sun size={18} />, label: t("trip.solar"), value: `${(trip.solar_wh / 1000).toFixed(1)} kWh` }]
      : []),
  ];

  return (
    <section className="panel trip-panel">
      <div className="trip-head">
        <h2>{t("trip.title")}</h2>
        {confirming ? (
          <span className="trip-confirm">
            {t("trip.resetConfirm")}
            <button className="mini danger" onClick={doReset}>
              {t("common.yes")}
            </button>
            <button className="mini" onClick={() => setConfirming(false)}>
              {t("common.no")}
            </button>
          </span>
        ) : (
          <button className="mini" onClick={() => setConfirming(true)} title={t("trip.reset")}>
            <RotateCcw size={13} /> {t("trip.reset")}
          </button>
        )}
      </div>

      <div className="energy-stats">
        {stats.map((s) => (
          <div className="energy-stat" key={s.label}>
            <span className="energy-stat-icon">{s.icon}</span>
            <div>
              <div className="energy-stat-value">{s.value}</div>
              <div className="energy-stat-label">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {trip.places.length > 0 && (
        <p className="trip-places">
          <MapPin size={13} /> {trip.places.join(" · ")}
        </p>
      )}
    </section>
  );
}
