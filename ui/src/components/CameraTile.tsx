import { useEffect, useState } from "react";
import type { Entity } from "@shared/types";
import { useVan } from "../state";
import { useT } from "../i18n";
import { CameraScene } from "./CameraScene";

const CONN: Record<string, string> = { wired: "WIRED", wifi: "WI-FI", "4g": "4G LTE" };

// A camera tile. In the simulator the "feed" is a stylised placeholder (there's no
// real video); a real RTSP/ONVIF backend would drop its stream/snapshot in here.
export function CameraTile({ entity }: { entity: Entity }) {
  const t = useT();
  const { twin } = useVan();
  // The sim clock drives day/night; interior cabin cam is unaffected by daylight.
  const phase = String(twin["environment.phase"] ?? "day");
  const loc0 = String((entity.attributes as Record<string, unknown>).location ?? "cabin");
  // Interior cabin cam is always lit; exterior cams go IR only at true night.
  const nightVision = loc0 !== "cabin" && phase === "night";

  // Feed clock ticks off the simulated time, sped up by clock.rate.
  const epoch = typeof twin["clock.epoch"] === "number" ? (twin["clock.epoch"] as number) : null;
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const offline = entity.state !== "online";
  const a = entity.attributes as Record<string, unknown>;
  const motion = Boolean(a.motion);
  const recording = Boolean(a.recording);
  const loc = loc0;
  const conn = String(a.connection ?? "wifi");
  const clock = epoch
    ? new Date(epoch * 1000).toUTCString().slice(17, 25)
    : new Date(now).toLocaleTimeString();

  return (
    <div className={"cam-tile" + (offline ? " offline" : "") + (motion ? " motion" : "")}>
      <div className={"cam-feed loc-" + loc + " ph-" + phase + (nightVision ? " nightvision" : "")}>
        {!offline && <CameraScene location={loc} motion={motion} />}
        <div className="cam-scan" />
        {offline ? (
          <div className="cam-nosignal">{t("cam.nosignal")}</div>
        ) : (
          <span className="cam-sim">{nightVision ? "◉ NIGHT VISION" : "SIMULATED FEED"}</span>
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
