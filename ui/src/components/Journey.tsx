import type { Twin } from "@shared/types";
import { JourneyMap } from "./JourneyMap";

function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

export function Journey({ twin }: { twin: Twin }) {
  const speed = num(twin["vehicle.speed_kmh"]);
  const lat = num(twin["gps.lat"]);
  const lon = num(twin["gps.lon"]);

  return (
    <section className="panel span2">
      <h2>Journey</h2>
      <div className="journey-grid">
        <div>
          <JourneyMap />
          <div className="journey-legend">
            <span><i className="dot here" /> position</span>
            <span><i className="dot stay" /> past stay</span>
            <span><i className="dot open" /> here now</span>
          </div>
        </div>
        <div className="journey-side">
          <div className="journey-readouts">
            <div>
              <span className="sys-k">Speed</span>
              {speed?.toFixed(0) ?? "—"} km/h
            </div>
            <div>
              <span className="sys-k">Heading</span>
              {num(twin["vehicle.heading"])?.toFixed(0) ?? "—"}°
            </div>
            <div>
              <span className="sys-k">Odometer</span>
              {num(twin["vehicle.odometer_km"])?.toFixed(1) ?? "—"} km
            </div>
            <div>
              <span className="sys-k">Position</span>
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
