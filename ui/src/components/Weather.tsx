import { useCallback, useEffect, useState } from "react";
import { Cloud, Wind, CloudRain } from "lucide-react";
import { getWeather, refreshWeather } from "@shared/api";
import type { Weather as WeatherData } from "@shared/types";
import { useT } from "../i18n";

function hourLabel(iso: string): string {
  const m = iso.match(/T(\d{2}):/);
  return m ? m[1] : "";
}

export function Weather() {
  const t = useT();
  const [w, setW] = useState<WeatherData>({});

  const load = useCallback(async () => {
    setW(await getWeather());
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  const cur = w.current;
  const hasData = !!cur;
  const rain = w.rain_eta_hours;
  const hours = (w.hourly ?? []).slice(0, 12);

  return (
    <section className="panel">
      <div className="companion-head">
        <h2>{t("weather.title")}</h2>
        <span className="pill">
          {w.source === "simulated"
            ? t("weather.simulated")
            : w.online
              ? t("weather.live")
              : hasData
                ? t("weather.cached")
                : "—"}
        </span>
      </div>

      {!hasData ? (
        <p className="companion-quiet">{t("weather.none")}</p>
      ) : (
        <>
          <div className="wx-current">
            <span className="wx-temp">{cur.temp_c?.toFixed(0) ?? "—"}°C</span>
            <div className="wx-meta">
              <div className="wx-cond">{cur.condition}</div>
              <div className="wx-sub">
                <Cloud className="wx-ico" /> {cur.cloud_pct ?? "—"}% ·{" "}
                <Wind className="wx-ico" /> {cur.wind_kmh?.toFixed(0) ?? "—"} km/h
              </div>
            </div>
          </div>

          {rain !== null && rain !== undefined && (
            <div className="wx-rain">
              <CloudRain className="inline-ico" />
              {rain < 0.5 ? t("weather.rainShortly") : t("weather.rainIn", { h: rain })}
            </div>
          )}

          <div className="wx-hours">
            {hours.map((h) => (
              <div key={h.t} className="wx-hour">
                <span className="wx-h-temp">{h.temp_c?.toFixed(0) ?? "—"}°</span>
                <div className="wx-bar-track">
                  <div
                    className="wx-bar"
                    style={{ height: `${h.precip_prob ?? 0}%` }}
                    title={`${h.precip_prob ?? 0}% precip`}
                  />
                </div>
                <span className="wx-h-time">{hourLabel(h.t)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="wx-actions">
        <button className="mini" onClick={() => refreshWeather().then(load)}>
          {t("common.refresh")}
        </button>
      </div>
    </section>
  );
}
