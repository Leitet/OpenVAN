import { useEffect, useState } from "react";
import { getSeries, getStays } from "@shared/api";
import type { Stay } from "@shared/types";

const W = 320;
const H = 190;
const PAD = 14;

/** Breadcrumb map: the GPS track plus markers for past stays (offline, no tiles). */
export function JourneyMap() {
  const [track, setTrack] = useState<{ lat: number; lon: number }[]>([]);
  const [stays, setStays] = useState<Stay[]>([]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      const [lat, lon, mem] = await Promise.all([
        getSeries("gps.lat", 120),
        getSeries("gps.lon", 120),
        getStays(),
      ]);
      if (!active) return;
      const n = Math.min(lat.length, lon.length);
      const pts = [];
      for (let i = 0; i < n; i++) pts.push({ lat: lat[i].v, lon: lon[i].v });
      setTrack(pts);
      setStays(mem.stays.filter((s) => s.lat !== null && s.lon !== null));
    };
    load();
    const timer = setInterval(load, 4000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const stayPts = stays.map((s) => ({ lat: s.lat as number, lon: s.lon as number }));
  const all = [...track, ...stayPts];

  if (all.length === 0) {
    return (
      <div className="journey-map empty">
        Start driving or bookmark a spot to see your route and stays.
      </div>
    );
  }

  let minLat = Math.min(...all.map((p) => p.lat));
  let maxLat = Math.max(...all.map((p) => p.lat));
  let minLon = Math.min(...all.map((p) => p.lon));
  let maxLon = Math.max(...all.map((p) => p.lon));
  // Centre a single cluster instead of pinning it to a corner.
  if (maxLat - minLat < 1e-5) (minLat -= 0.002), (maxLat += 0.002);
  if (maxLon - minLon < 1e-5) (minLon -= 0.002), (maxLon += 0.002);
  const spanLat = maxLat - minLat;
  const spanLon = maxLon - minLon;

  const project = (p: { lat: number; lon: number }) => {
    const x = PAD + ((p.lon - minLon) / spanLon) * (W - 2 * PAD);
    const y = H - PAD - ((p.lat - minLat) / spanLat) * (H - 2 * PAD);
    return [x, y];
  };

  const path = track.map((p) => project(p).join(",")).join(" ");
  const here = track.length ? project(track[track.length - 1]) : null;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="journey-map">
      <rect x="0" y="0" width={W} height={H} className="journey-bg" rx="10" />
      {track.length >= 2 && <polyline points={path} className="journey-track" />}
      {stays.map((s) => {
        const [x, y] = project({ lat: s.lat as number, lon: s.lon as number });
        return (
          <circle key={s.id} cx={x} cy={y} r="4" className={"journey-stay" + (s.open ? " open" : "")}>
            <title>
              {(s.place || `${(s.lat as number).toFixed(4)}, ${(s.lon as number).toFixed(4)}`) +
                (s.condition ? ` · ${s.condition}` : "")}
            </title>
          </circle>
        );
      })}
      {here && <circle cx={here[0]} cy={here[1]} r="5" className="journey-here" />}
    </svg>
  );
}
