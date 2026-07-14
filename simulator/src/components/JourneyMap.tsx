import { useEffect, useState } from "react";
import { getSeries } from "../api";

const W = 320;
const H = 190;

/** Breadcrumb map: plots the GPS track from telemetry (offline, no tiles). */
export function JourneyMap() {
  const [track, setTrack] = useState<{ lat: number; lon: number }[]>([]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      const [lat, lon] = await Promise.all([
        getSeries("gps.lat", 120),
        getSeries("gps.lon", 120),
      ]);
      const n = Math.min(lat.length, lon.length);
      const pts = [];
      for (let i = 0; i < n; i++) pts.push({ lat: lat[i].v, lon: lon[i].v });
      if (active) setTrack(pts);
    };
    load();
    const timer = setInterval(load, 4000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  if (track.length < 2) {
    return (
      <div className="journey-map empty">
        Start driving (ignition on + speed) to trace your route.
      </div>
    );
  }

  const lats = track.map((p) => p.lat);
  const lons = track.map((p) => p.lon);
  const minLat = Math.min(...lats);
  const minLon = Math.min(...lons);
  const spanLat = Math.max(...lats) - minLat || 1e-4;
  const spanLon = Math.max(...lons) - minLon || 1e-4;
  const pad = 12;

  const project = (p: { lat: number; lon: number }) => {
    const x = pad + ((p.lon - minLon) / spanLon) * (W - 2 * pad);
    const y = H - pad - ((p.lat - minLat) / spanLat) * (H - 2 * pad);
    return [x, y];
  };

  const path = track.map((p) => project(p).join(",")).join(" ");
  const [lx, ly] = project(track[track.length - 1]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="journey-map">
      <rect x="0" y="0" width={W} height={H} className="journey-bg" rx="10" />
      <polyline points={path} className="journey-track" />
      <circle cx={lx} cy={ly} r="5" className="journey-here" />
    </svg>
  );
}
