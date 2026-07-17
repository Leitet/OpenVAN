import { useEffect, useState } from "react";
import type { Entity } from "@shared/types";
import { useT } from "../i18n";

const LOC_ICON: Record<string, string> = { rear: "🛣️", cabin: "🛋️", door: "🚪", awning: "⛺" };
const CONN: Record<string, string> = { wired: "WIRED", wifi: "WI-FI", "4g": "4G LTE" };

// A camera tile. In the simulator the "feed" is a stylised placeholder (there's no
// real video); a real RTSP/ONVIF backend would drop its stream/snapshot in here.
export function CameraTile({ entity }: { entity: Entity }) {
  const t = useT();
  const [clock, setClock] = useState("");
  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const offline = entity.state !== "online";
  const a = entity.attributes as Record<string, unknown>;
  const motion = Boolean(a.motion);
  const recording = Boolean(a.recording);
  const loc = String(a.location ?? "cabin");
  const conn = String(a.connection ?? "wifi");

  return (
    <div className={"cam-tile" + (offline ? " offline" : "") + (motion ? " motion" : "")}>
      <div className={"cam-feed loc-" + loc}>
        <div className="cam-scan" />
        <span className="cam-wm">{LOC_ICON[loc] ?? "📷"}</span>
        {offline ? (
          <div className="cam-nosignal">{t("cam.nosignal")}</div>
        ) : (
          <span className="cam-sim">SIMULATED FEED</span>
        )}
      </div>
      <div className="cam-top">
        <span className="cam-name">{entity.name}</span>
        <span className="cam-badges">
          <span className="cam-conn">{CONN[conn] ?? conn}</span>
          {recording && <span className="cam-rec">● REC</span>}
          {!offline && <span className="cam-live">● LIVE</span>}
        </span>
      </div>
      {motion && !offline && <div className="cam-motion-badge">{t("cam.motion")}</div>}
      {!offline && <span className="cam-clock">{clock}</span>}
    </div>
  );
}
