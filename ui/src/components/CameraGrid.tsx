import { useVan } from "../state";
import { useT } from "../i18n";
import { CameraTile } from "./CameraTile";

export function CameraGrid() {
  const { entities } = useVan();
  const t = useT();
  const cams = Object.values(entities).filter((e) => e.domain === "camera");

  return (
    <section className="panel span2">
      <h2>{t("cam.title")}</h2>
      {cams.length === 0 ? (
        <p className="companion-quiet">{t("cam.none")}</p>
      ) : (
        <div className="cam-grid">
          {cams.map((c) => (
            <CameraTile key={c.entity_id} entity={c} />
          ))}
        </div>
      )}
    </section>
  );
}
