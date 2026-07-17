import { useVan } from "../state";
import { useT } from "../i18n";

// Where each camera actually sits on the van (side view, cab on the left): the rear
// cam high on the back, the awning cam up on the side/roofline, the door cam by the
// sliding door, and the cabin cam inside. Each mount shows its field-of-view and
// lights up on motion — so the placement reads like a real install.
// Keyed by camera *location* so any camera set maps onto the van.
const MOUNTS: Record<
  string,
  { x: number; y: number; fov: string; lx: number; ly: number; anchor: "start" | "middle" | "end" }
> = {
  rear: { x: 296, y: 54, fov: "296,54 322,62 322,96", lx: 300, ly: 47, anchor: "end" },
  awning: { x: 208, y: 42, fov: "208,42 186,86 230,86", lx: 208, ly: 35, anchor: "middle" },
  door: { x: 250, y: 66, fov: "250,66 232,106 268,106", lx: 258, ly: 62, anchor: "start" },
  cabin: { x: 140, y: 60, fov: "140,60 126,92 154,92", lx: 140, ly: 53, anchor: "middle" },
};

function stateOf(entity: { state: unknown; attributes: Record<string, unknown> }): string {
  if (entity.state !== "online") return "off";
  if (entity.attributes.motion) return "motion";
  return "on";
}

export function VanCameraMap() {
  const { entities } = useVan();
  const t = useT();
  const cams = Object.values(entities).filter((e) => e.domain === "camera");
  if (cams.length === 0) return null;

  return (
    <section className="panel span2">
      <h2>{t("cam.placement")}</h2>
      <svg className="vcm-svg" viewBox="0 0 330 140" aria-hidden="true">
        {/* ground */}
        <line className="vcm-ground" x1="8" y1="122" x2="322" y2="122" />
        {/* van body (cab on the left, rear on the right) */}
        <path
          className="vcm-van"
          d="M300 48 Q300 44 296 44 L74 44 L74 60 L36 74 Q30 76 30 84 L30 108 Q30 112 34 112 L296 112 Q300 112 300 108 Z"
        />
        {/* windscreen */}
        <path className="vcm-glass" d="M74 60 L74 82 L44 82 L74 60 Z" />
        {/* wheels */}
        <circle className="vcm-wheel" cx="96" cy="112" r="14" />
        <circle className="vcm-wheel" cx="252" cy="112" r="14" />

        {cams.map((c) => {
          const loc = String((c.attributes as Record<string, unknown>).location ?? "");
          const m = MOUNTS[loc];
          if (!m) return null;
          const s = stateOf(c);
          return (
            <g key={c.entity_id}>
              <polygon className={"vcm-fov " + s} points={m.fov} />
              <circle className={"vcm-dot " + s} cx={m.x} cy={m.y} r="4.5" />
              <text className="vcm-label" x={m.lx} y={m.ly} textAnchor={m.anchor}>
                {c.name}
              </text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}
