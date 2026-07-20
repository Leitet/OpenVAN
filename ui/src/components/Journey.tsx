import { TriangleAlert } from "lucide-react";
import type { Twin } from "@shared/types";
import { useT } from "../i18n";
import { useVan } from "../state";
import { JourneyMap, type CoverageSpot } from "./JourneyMap";

function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

// Pull the "better coverage back there" spot out of the live connectivity notice,
// if one is active — it's what the coverage locator recorded (see coverage.py).
function coverageSpot(
  notices: { key: string; data: Record<string, unknown> }[],
): CoverageSpot | null {
  const n = notices.find((x) => x.key === "connectivity");
  const spot = n?.data?.better_spot as Record<string, unknown> | undefined;
  if (!spot || typeof spot.lat !== "number" || typeof spot.lon !== "number") return null;
  return {
    lat: spot.lat,
    lon: spot.lon,
    signal_pct: Number(spot.signal_pct) || 0,
    distance_m: Number(spot.distance_m) || 0,
    direction: String(spot.direction ?? ""),
  };
}

/** A compass whose needle points in the van's direction of travel; ring is fixed
 * (N up). Styled from the active profile's theme vars, like the rest of the UI. */
function Compass({ heading }: { heading: number | undefined }) {
  const h = heading ?? 0;
  const ticks = Array.from({ length: 12 }, (_, i) => i * 30);
  return (
    <svg className="compass" viewBox="-50 -50 100 100" aria-hidden="true">
      <circle className="compass-ring" r="46" />
      {ticks.map((a) => {
        const rad = (a * Math.PI) / 180;
        const r1 = a % 90 === 0 ? 38 : 42;
        return (
          <line
            key={a}
            className={a % 90 === 0 ? "compass-tick major" : "compass-tick"}
            x1={Math.sin(rad) * r1}
            y1={-Math.cos(rad) * r1}
            x2={Math.sin(rad) * 46}
            y2={-Math.cos(rad) * 46}
          />
        );
      })}
      <text className="compass-label" x="0" y="-30">
        N
      </text>
      {/* needle rotated by heading via SVG transform (origin = viewBox centre) */}
      <g transform={`rotate(${h})`}>
        <polygon className="compass-n" points="0,-32 6,2 0,-4 -6,2" />
        <polygon className="compass-s" points="0,32 6,-2 0,4 -6,-2" />
      </g>
      <circle className="compass-hub" r="3.5" />
    </svg>
  );
}

export function Journey({ twin }: { twin: Twin }) {
  const t = useT();
  const { notices } = useVan();
  const speed = num(twin["vehicle.speed_kmh"]);
  const heading = num(twin["vehicle.heading"]);
  const lat = num(twin["gps.lat"]);
  const lon = num(twin["gps.lon"]);
  const coverage = coverageSpot(notices);

  return (
    <section className="panel span2 journey-panel">
      <div className="journey-head">
        <h2>{t("journey.title")}</h2>
        <span className="journey-attrib">
          ©{" "}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
            OpenStreetMap
          </a>{" "}
          contributors
        </span>
      </div>
      <JourneyMap coverage={coverage} />
      <div className="journey-legend">
        <span><i className="dot here" /> {t("journey.position")}</span>
        <span><i className="dot stay" /> {t("journey.pastStay")}</span>
        <span><i className="dot open" /> {t("journey.hereNow")}</span>
        <span><i className="dot camp" /> {t("journey.camp")}</span>
        {coverage && <span><i className="dot coverage" /> {t("journey.coverage")}</span>}
      </div>
      {(num(twin["road.max_height_m"]) || num(twin["road.max_weight_t"]) || num(twin["road.max_width_m"])) ? (
        <div className="restrictions-strip">
          <TriangleAlert size={15} />
          <span>{t("journey.restrictions")}:</span>
          {Boolean(num(twin["road.max_height_m"])) && (
            <span className="restriction">{num(twin["road.max_height_m"])?.toFixed(1)} m {t("journey.maxHeight")}</span>
          )}
          {Boolean(num(twin["road.max_weight_t"])) && (
            <span className="restriction">{num(twin["road.max_weight_t"])?.toFixed(1)} t {t("journey.maxWeight")}</span>
          )}
          {Boolean(num(twin["road.max_width_m"])) && (
            <span className="restriction">{num(twin["road.max_width_m"])?.toFixed(1)} m {t("journey.maxWidth")}</span>
          )}
        </div>
      ) : null}
      <div className="journey-readouts">
        <div className="stat">
          <span className="sys-k">{t("journey.speed")}</span>
          <strong>{speed?.toFixed(0) ?? "—"}</strong>
          <span className="stat-unit">km/h</span>
        </div>
        <div className="stat stat-compass">
          <Compass heading={heading} />
          <div className="stat-compass-read">
            <span className="sys-k">{t("journey.heading")}</span>
            <strong>{heading?.toFixed(0) ?? "—"}°</strong>
          </div>
        </div>
        <div className="stat">
          <span className="sys-k">{t("journey.odometer")}</span>
          <strong>{num(twin["vehicle.odometer_km"])?.toFixed(1) ?? "—"}</strong>
          <span className="stat-unit">km</span>
        </div>
        <div className="stat stat-pos">
          <span className="sys-k">{t("journey.positionLabel")}</span>
          <strong>
            {lat !== undefined && lon !== undefined
              ? `${lat.toFixed(4)}, ${lon.toFixed(4)}`
              : "—"}
          </strong>
        </div>
      </div>
    </section>
  );
}
