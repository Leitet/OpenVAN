import type { Twin } from "@shared/types";
import { useT } from "../i18n";
import { JourneyMap } from "./JourneyMap";

function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

export function Journey({ twin }: { twin: Twin }) {
  const t = useT();
  const speed = num(twin["vehicle.speed_kmh"]);
  const lat = num(twin["gps.lat"]);
  const lon = num(twin["gps.lon"]);

  return (
    <section className="panel span2">
      <h2>{t("journey.title")}</h2>
      <div className="journey-grid">
        <div>
          <JourneyMap />
          <div className="journey-legend">
            <span><i className="dot here" /> {t("journey.position")}</span>
            <span><i className="dot stay" /> {t("journey.pastStay")}</span>
            <span><i className="dot open" /> {t("journey.hereNow")}</span>
          </div>
        </div>
        <div className="journey-side">
          <div className="journey-readouts">
            <div>
              <span className="sys-k">{t("journey.speed")}</span>
              {speed?.toFixed(0) ?? "—"} km/h
            </div>
            <div>
              <span className="sys-k">{t("journey.heading")}</span>
              {num(twin["vehicle.heading"])?.toFixed(0) ?? "—"}°
            </div>
            <div>
              <span className="sys-k">{t("journey.odometer")}</span>
              {num(twin["vehicle.odometer_km"])?.toFixed(1) ?? "—"} km
            </div>
            <div>
              <span className="sys-k">{t("journey.positionLabel")}</span>
              {lat !== undefined && lon !== undefined
                ? `${lat.toFixed(4)}, ${lon.toFixed(4)}`
                : "—"}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
