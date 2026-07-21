import { useVan } from "../state";
import { useT } from "../i18n";
import { VanTopView, type PlacedCamera } from "./VanTopView";

// Where each camera sits on the van, seen from above — rendered from the same
// x/y/heading the camera integration's settings page edits, so the live map is
// always exactly what was configured. Mounts light up on motion.
export function VanCameraMap() {
  const { entities } = useVan();
  const t = useT();
  const cams = Object.values(entities).filter((e) => e.domain === "camera");
  if (cams.length === 0) return null;

  const num = (v: unknown, fallback: number) =>
    typeof v === "number" && Number.isFinite(v) ? v : Number(v) || fallback;
  const placed: PlacedCamera[] = cams.map((c) => {
    const a = c.attributes as Record<string, unknown>;
    return {
      id: c.entity_id,
      label: c.name,
      x: num(a.x, 50),
      y: num(a.y, 50),
      heading: num(a.heading, 0),
      state: c.state !== "online" ? "off" : a.motion ? "motion" : "on",
    };
  });

  return (
    <section className="panel span2">
      <h2>{t("cam.placement")}</h2>
      <VanTopView cameras={placed} />
    </section>
  );
}
