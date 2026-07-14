import { injectSignal } from "../api";
import type { Twin } from "../types";
import { SignalSlider } from "./SignalSlider";
import { JourneyMap } from "./JourneyMap";

function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

export function Journey({ twin }: { twin: Twin }) {
  const ignition = Boolean(twin["vehicle.ignition"]);
  const speed = num(twin["vehicle.speed_kmh"]);
  const lat = num(twin["gps.lat"]);
  const lon = num(twin["gps.lon"]);

  return (
    <section className="panel span2">
      <h2>Journey</h2>
      <div className="journey-grid">
        <JourneyMap />
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

          <button
            className={"toggle" + (ignition ? " on" : "")}
            onClick={() => injectSignal("vehicle.ignition", !ignition)}
          >
            {ignition ? "Ignition: ON" : "Ignition: OFF"}
          </button>
          <SignalSlider
            label="Speed"
            signalKey="vehicle.speed_kmh"
            value={speed}
            min={0}
            max={130}
            unit=" km/h"
          />
          <SignalSlider
            label="Heading"
            signalKey="vehicle.heading"
            value={num(twin["vehicle.heading"])}
            min={0}
            max={359}
            unit="°"
          />
          <p className="hint">
            Turn the ignition on and set a speed — the van dead-reckons along its
            heading, the odometer ticks up, and the route traces on the map.
          </p>
        </div>
      </div>
    </section>
  );
}
