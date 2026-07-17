import { useVan, num } from "../state";
import { useT } from "../i18n";

// A bubble level: the bubble drifts toward the low side (roll → x, pitch → y), and
// a text line says which ramp to nudge. Mirrors notices.leveling_advice in Core.
const THRESHOLD = 1.5;
const TRACK_M = 2.0;
const WHEELBASE_M = 3.6;

function advice(pitch: number, roll: number, t: (k: string) => string): string {
  if (Math.abs(pitch) < THRESHOLD && Math.abs(roll) < THRESHOLD) return t("level.flat");
  const parts: string[] = [];
  if (Math.abs(roll) >= THRESHOLD) {
    const cm = Math.tan((Math.abs(roll) * Math.PI) / 180) * TRACK_M * 100;
    parts.push(`${roll > 0 ? t("level.right") : t("level.left")} ~${cm.toFixed(0)} cm`);
  }
  if (Math.abs(pitch) >= THRESHOLD) {
    const cm = Math.tan((Math.abs(pitch) * Math.PI) / 180) * WHEELBASE_M * 100;
    parts.push(`${pitch > 0 ? t("level.rear") : t("level.front")} ~${cm.toFixed(0)} cm`);
  }
  return `${t("level.raise")} ${parts.join(" · ")}`;
}

export function Leveling() {
  const { twin } = useVan();
  const t = useT();
  const pitch = num(twin["imu.pitch_deg"]) ?? 0;
  const roll = num(twin["imu.roll_deg"]) ?? 0;
  const isLevel = Math.abs(pitch) < THRESHOLD && Math.abs(roll) < THRESHOLD;

  // Bubble drifts toward the LOW side: roll>0 (right low) → bubble right; pitch>0
  // (nose up → rear low) → bubble toward bottom. ~9px per degree, clamped.
  const clamp = (v: number) => Math.max(-42, Math.min(42, v * 9));
  const bx = clamp(roll);
  const by = clamp(pitch);

  return (
    <section className="panel leveling">
      <h2>{t("level.title")}</h2>
      <div className="level-row">
        <div className={"level-dial" + (isLevel ? " ok" : "")}>
          <div className="level-ring" />
          <div className="level-cross-h" />
          <div className="level-cross-v" />
          <div className="level-bubble" style={{ transform: `translate(${bx}px, ${by}px)` }} />
        </div>
        <div className="level-read">
          <div className="level-figures">
            <span>{t("level.pitch")} <strong>{pitch.toFixed(1)}°</strong></span>
            <span>{t("level.roll")} <strong>{roll.toFixed(1)}°</strong></span>
          </div>
          <p className={"level-advice" + (isLevel ? " ok" : "")}>{advice(pitch, roll, t)}</p>
        </div>
      </div>
    </section>
  );
}
