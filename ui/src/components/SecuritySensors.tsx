import { useVan } from "../state";
import { useT } from "../i18n";

// Door/motion sensor status + any active intrusion alert, for the Security tab.
export function SecuritySensors() {
  const { twin, notices } = useVan();
  const t = useT();
  const door = Boolean(twin["security.door_open"]);
  const motion = Boolean(twin["security.motion"]);
  const camMotion = Object.keys(twin).filter(
    (k) => k.startsWith("camera.") && k.endsWith(".motion") && twin[k],
  ).length;
  const alerts = notices.filter((n) => n.key === "intrusion");

  return (
    <section className="panel">
      <h2>{t("sec.sensors")}</h2>
      {alerts.map((a) => (
        <div className="safety-alarm" key={a.key}>
          <div className="safety-alarm-row">
            <strong>⚠ {a.title}</strong>
            <span>{a.message}</span>
          </div>
        </div>
      ))}
      <div className="sec-pills">
        <span className={"sec-pill" + (door ? " on" : "")}>
          {t("sec.door")}: {door ? t("sec.open") : t("sec.closed")}
        </span>
        <span className={"sec-pill" + (motion ? " on" : "")}>
          {t("sec.motion")}: {motion ? t("sec.detected") : t("sec.none")}
        </span>
        <span className={"sec-pill" + (camMotion ? " on" : "")}>
          {t("sec.camMotion")}: {camMotion}
        </span>
      </div>
    </section>
  );
}
