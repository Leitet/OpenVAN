import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { campSearch, getSeries, getStays } from "@shared/api";

// A recent strong-coverage spot the locator points back to (from the connectivity
// notice's better_spot). Shown as a marker so you can navigate toward it.
export interface CoverageSpot {
  lat: number;
  lon: number;
  signal_pct: number;
  distance_m: number;
  direction: string;
}

function distancePhrase(m: number): string {
  return m < 950 ? `${m.toFixed(0)} m` : `${(m / 1000).toFixed(1)} km`;
}

/**
 * Live OpenStreetMap of the journey: the GPS track (which now follows real roads,
 * because Core snaps the simulated drive onto the OSM road graph), the current
 * position, past stays and nearby camp spots. Auto-follows the van while driving;
 * drag to explore, then tap ◎ to re-follow.
 */
export function JourneyMap({ coverage }: { coverage: CoverageSpot | null }) {
  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const trackRef = useRef<L.Polyline | null>(null);
  const vanRef = useRef<L.Marker | null>(null);
  const staysRef = useRef<L.LayerGroup | null>(null);
  const campsRef = useRef<L.LayerGroup | null>(null);
  const coverageRef = useRef<L.LayerGroup | null>(null);
  const followRef = useRef(true);
  const fittedRef = useRef(false);
  const programmaticRef = useRef(false); // true while *we* move the map, not the user
  const [empty, setEmpty] = useState(true);

  // Move the map without it counting as a user "I want to look elsewhere" gesture.
  const jump = (fn: () => void) => {
    programmaticRef.current = true;
    fn();
    programmaticRef.current = false;
  };

  // init the map once
  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    // Attribution shown as our own caption below the map (see JSX) instead of the
    // floating in-map box, so it blends with the card.
    const map = L.map(elRef.current, { zoomControl: true, attributionControl: false }).setView(
      [46.5, 11.3],
      13,
    );
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(map);
    // Only a *user* pan/zoom drops follow — programmatic moves (fit, follow) don't.
    map.on("movestart zoomstart", () => {
      if (!programmaticRef.current) followRef.current = false;
    });

    staysRef.current = L.layerGroup().addTo(map);
    campsRef.current = L.layerGroup().addTo(map);
    coverageRef.current = L.layerGroup().addTo(map);

    // "re-follow the van" control
    const Recenter = L.Control.extend({
      options: { position: "topright" },
      onAdd() {
        const btn = L.DomUtil.create("button", "journey-recenter");
        btn.innerHTML = "◎";
        btn.title = "Follow the van";
        L.DomEvent.on(btn, "click", (e) => {
          L.DomEvent.stop(e);
          followRef.current = true;
          const van = vanRef.current;
          if (van) jump(() => map.setView(van.getLatLng(), Math.max(map.getZoom(), 14)));
        });
        return btn;
      },
    });
    map.addControl(new Recenter());
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // poll data and render
  useEffect(() => {
    let active = true;
    const load = async () => {
      const [lat, lon, mem, camp] = await Promise.all([
        getSeries("gps.lat", 300),
        getSeries("gps.lon", 300),
        getStays(),
        campSearch().catch(() => ({ spots: [] })),
      ]);
      if (!active || !mapRef.current) return;

      const map = mapRef.current;
      const n = Math.min(lat.length, lon.length);
      const track: [number, number][] = [];
      for (let i = 0; i < n; i++) track.push([lat[i].v, lon[i].v]);
      const stays = mem.stays.filter((s) => s.lat !== null && s.lon !== null);
      const camps = camp.spots ?? [];
      setEmpty(track.length === 0 && stays.length === 0 && camps.length === 0);

      // track polyline
      if (track.length >= 2) {
        if (trackRef.current) trackRef.current.setLatLngs(track);
        else trackRef.current = L.polyline(track, { className: "journey-line" }).addTo(map);
      }

      // van marker at the latest fix
      if (track.length) {
        const here = track[track.length - 1];
        const icon = L.divIcon({
          className: "",
          html: '<div class="van-dot"></div>',
          iconSize: [18, 18],
          iconAnchor: [9, 9], // centre the dot on the fix
        });
        if (vanRef.current) vanRef.current.setLatLng(here);
        else vanRef.current = L.marker(here, { icon, zIndexOffset: 1000 }).addTo(map);
        // While following, keep the whole framed view until the van nears the
        // edge, then recenter — so you see the travelled track *and* the position.
        if (followRef.current && fittedRef.current) {
          const inner = map.getBounds().pad(-0.2);
          if (!inner.contains(L.latLng(here))) {
            jump(() => map.setView(here, map.getZoom(), { animate: false }));
          }
        }
      }

      // stays
      staysRef.current?.clearLayers();
      for (const s of stays) {
        const m = L.circleMarker([s.lat as number, s.lon as number], {
          radius: 6,
          className: s.open ? "journey-stay open" : "journey-stay",
        });
        m.bindTooltip(
          (s.place || `${(s.lat as number).toFixed(4)}, ${(s.lon as number).toFixed(4)}`) +
            (s.condition ? ` · ${s.condition}` : ""),
        );
        staysRef.current?.addLayer(m);
      }

      // camps
      campsRef.current?.clearLayers();
      for (const c of camps) {
        // Lucide "tent" glyph (inline SVG so it themes via currentColor).
        const icon = L.divIcon({
          className: "",
          html:
            '<div class="camp-pin"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M3.5 21 14 3"/><path d="M20.5 21 10 3"/>' +
            '<path d="M15.5 21 12 15l-3.5 6"/><path d="M2 21h20"/></svg></div>',
          iconSize: [22, 22],
          iconAnchor: [11, 20],
        });
        const m = L.marker([c.lat, c.lon], { icon });
        m.bindTooltip(`${c.name} · ${c.kind}${c.distance_km != null ? ` · ${c.distance_km} km` : ""}`);
        campsRef.current?.addLayer(m);
      }

      // one-time fit to everything we know about
      if (!fittedRef.current) {
        const pts = [
          ...track,
          ...stays.map((s) => [s.lat, s.lon] as [number, number]),
          ...camps.map((c) => [c.lat, c.lon] as [number, number]),
        ];
        if (pts.length) {
          jump(() => map.fitBounds(L.latLngBounds(pts).pad(0.3), { maxZoom: 15 }));
          fittedRef.current = true;
        }
      }
    };
    load();
    const timer = setInterval(load, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  // Better-coverage marker: appears while a weak-signal notice knows a stronger
  // spot nearby, and clears when the signal recovers.
  useEffect(() => {
    const layer = coverageRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!coverage) return;
    const icon = L.divIcon({
      className: "",
      // Lucide "signal" glyph, inline so it themes via currentColor.
      html:
        '<div class="coverage-pin"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M2 20h.01"/><path d="M7 20v-4"/><path d="M12 20v-8"/><path d="M17 20V8"/>' +
        '<path d="M22 4v16"/></svg></div>',
      iconSize: [24, 24],
      iconAnchor: [12, 22],
    });
    const m = L.marker([coverage.lat, coverage.lon], { icon, zIndexOffset: 900 });
    m.bindTooltip(
      `Better coverage: ${coverage.signal_pct.toFixed(0)}% · ${distancePhrase(coverage.distance_m)} ${coverage.direction}`,
    );
    layer.addLayer(m);
    // If we've no route to frame yet (e.g. parked with telemetry just started),
    // bring the spot into view — being parked in a dead zone is the main use case.
    if (mapRef.current && !fittedRef.current) {
      jump(() => mapRef.current!.setView([coverage.lat, coverage.lon], 15));
    }
  }, [coverage?.lat, coverage?.lon, coverage?.signal_pct]);

  return (
    <div className="journey-map-wrap">
      <div ref={elRef} className="journey-leaflet" />
      {empty && !coverage && (
        <div className="journey-map-empty">Start driving or bookmark a spot to see your route.</div>
      )}
    </div>
  );
}
