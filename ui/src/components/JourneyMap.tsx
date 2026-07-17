import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { campSearch, getSeries, getStays } from "@shared/api";

/**
 * Live OpenStreetMap of the journey: the GPS track (which now follows real roads,
 * because Core snaps the simulated drive onto the OSM road graph), the current
 * position, past stays and nearby camp spots. Auto-follows the van while driving;
 * drag to explore, then tap ◎ to re-follow.
 */
export function JourneyMap() {
  const elRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const trackRef = useRef<L.Polyline | null>(null);
  const vanRef = useRef<L.Marker | null>(null);
  const staysRef = useRef<L.LayerGroup | null>(null);
  const campsRef = useRef<L.LayerGroup | null>(null);
  const followRef = useRef(true);
  const fittedRef = useRef(false);
  const [empty, setEmpty] = useState(true);

  // init the map once
  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const map = L.map(elRef.current, { zoomControl: true, attributionControl: true }).setView(
      [46.5, 11.3],
      13,
    );
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    map.on("dragstart zoomstart", () => (followRef.current = false));

    staysRef.current = L.layerGroup().addTo(map);
    campsRef.current = L.layerGroup().addTo(map);

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
          if (van) map.setView(van.getLatLng(), Math.max(map.getZoom(), 14));
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
        const icon = L.divIcon({ className: "", html: '<div class="van-dot"></div>', iconSize: [18, 18] });
        if (vanRef.current) vanRef.current.setLatLng(here);
        else vanRef.current = L.marker(here, { icon, zIndexOffset: 1000 }).addTo(map);
        if (followRef.current) map.setView(here, map.getZoom(), { animate: true });
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
        const icon = L.divIcon({ className: "", html: '<div class="camp-pin">⛺</div>', iconSize: [22, 22] });
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
          map.fitBounds(L.latLngBounds(pts).pad(0.3), { maxZoom: 15 });
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

  return (
    <div className="journey-map-wrap">
      <div ref={elRef} className="journey-leaflet" />
      {empty && (
        <div className="journey-map-empty">Start driving or bookmark a spot to see your route.</div>
      )}
    </div>
  );
}
