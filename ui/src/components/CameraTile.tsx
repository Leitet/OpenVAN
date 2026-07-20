import { useEffect, useState } from "react";
import type { Entity } from "@shared/types";
import { useVan } from "../state";
import { useT } from "../i18n";
import { CameraScene } from "./CameraScene";

const CONN: Record<string, string> = { wired: "WIRED", wifi: "WI-FI", "4g": "4G LTE" };

// A camera tile. In the simulator the "feed" is a real still (day/IR-night per
// camera position, `ui/public/cameras/<location>-<day|night>.jpg`), switched by
// the sim clock's phase; a real RTSP/ONVIF backend would drop its live
// stream/snapshot in here instead. Cameras without a still (custom locations
// added from the bench) fall back to the stylised SVG scene.
export function CameraTile({ entity }: { entity: Entity }) {
  const t = useT();
  const { twin } = useVan();
  // The sim clock drives day/night; dawn/dusk still use the daylight still.
  const phase = String(twin["environment.phase"] ?? "day");
  const loc0 = String((entity.attributes as Record<string, unknown>).location ?? "cabin");
  // At night every cam switches to its IR still (the cabin one included —
  // lights out when sleeping).
  const nightVision = phase === "night";
  const still = `/cameras/${loc0}-${nightVision ? "night" : "day"}.jpg`;
  const [stillMissing, setStillMissing] = useState(false);
  useEffect(() => setStillMissing(false), [still]);

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
      {/* The green IR filter only dresses up the SVG fallback — the real night
          stills ARE the IR frames, shown as-is. */}
      <div
        className={
          "cam-feed loc-" + loc + " ph-" + phase +
          (nightVision && stillMissing ? " nightvision" : "")
        }
      >
        {!offline &&
          (stillMissing ? (
            <CameraScene location={loc} motion={motion} />
          ) : (
            <img
              className="cam-still"
              src={still}
              alt=""
              onError={() => setStillMissing(true)}
            />
          ))}
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
