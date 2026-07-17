import { AlertTriangle, ShieldCheck, Check } from "lucide-react";
import { useVan, num } from "../state";
import { useT } from "../i18n";

// Air quality + the life-critical safety alarms. CO/gas/smoke are shown with hard
// thresholds (deterministic edge alarms in Core); any active safety notice raises a
// prominent banner. Everything reads from the live twin + notice feed.
function level(value: number | undefined, warn: number, danger: number): string {
  if (value === undefined) return "";
  if (value >= danger) return " danger";
  if (value >= warn) return " warn";
  return "";
}

export function AirSafety() {
  const { twin, notices } = useVan();
  const t = useT();

  const co = num(twin["air.co_ppm"]);
  const lpg = num(twin["air.lpg_pct_lel"]);
  const co2 = num(twin["air.co2_ppm"]);
  const humidity = num(twin["cabin.humidity_pct"]);
  const smoke = Boolean(twin["air.smoke"]);

  const alarms = notices.filter(
    (n) => n.category === "safety" && n.level === "warning",
  );

  return (
    <section className="panel air-safety">
      <h2>{t("comfort.airSafety")}</h2>

      {alarms.length > 0 ? (
        <div className="safety-alarm">
          {alarms.map((a) => (
            <div key={a.key} className="safety-alarm-row">
              <strong>
                <AlertTriangle className="inline-ico" /> {a.title}
              </strong>
              <span>{a.message}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="safety-ok">
          <ShieldCheck className="inline-ico" /> {t("safety.allClear")}
        </div>
      )}

      <div className="air-grid">
        <div className={"air-cell" + level(co, 35, 70)}>
          <span className="air-k">{t("label.co")}</span>
          <strong>{co?.toFixed(0) ?? "—"}</strong>
          <span className="air-u">ppm</span>
        </div>
        <div className={"air-cell" + level(lpg, 10, 20)}>
          <span className="air-k">{t("label.lpg")}</span>
          <strong>{lpg?.toFixed(0) ?? "—"}</strong>
          <span className="air-u">%LEL</span>
        </div>
        <div className={"air-cell" + level(co2, 1500, 2500)}>
          <span className="air-k">{t("label.co2")}</span>
          <strong>{co2?.toFixed(0) ?? "—"}</strong>
          <span className="air-u">ppm</span>
        </div>
        <div className={"air-cell" + level(humidity, 70, 85)}>
          <span className="air-k">{t("label.humidity")}</span>
          <strong>{humidity?.toFixed(0) ?? "—"}</strong>
          <span className="air-u">%</span>
        </div>
        <div className={"air-cell" + (smoke ? " danger" : "")}>
          <span className="air-k">{t("safety.smoke")}</span>
          <strong>{smoke ? <AlertTriangle className="cell-ico" /> : <Check className="cell-ico" />}</strong>
          <span className="air-u">{smoke ? "detected" : "clear"}</span>
        </div>
      </div>
    </section>
  );
}
