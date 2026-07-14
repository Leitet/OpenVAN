import { useCallback, useEffect, useState } from "react";
import { getWeather, refreshWeather, simulateWeather } from "../api";
import type { Weather as WeatherData } from "../types";

function hourLabel(iso: string): string {
  const m = iso.match(/T(\d{2}):/);
  return m ? m[1] : "";
}

export function Weather() {
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
        <h2>Weather</h2>
        <span className="pill">
          {w.source === "simulated"
            ? "simulated"
            : w.online
              ? "live"
              : hasData
                ? "cached"
                : "—"}
        </span>
      </div>

      {!hasData ? (
        <p className="companion-quiet">No forecast yet.</p>
      ) : (
        <>
          <div className="wx-current">
            <span className="wx-temp">{cur.temp_c?.toFixed(0) ?? "—"}°C</span>
            <div className="wx-meta">
              <div className="wx-cond">{cur.condition}</div>
              <div className="wx-sub">
                ☁ {cur.cloud_pct ?? "—"}% · 💨 {cur.wind_kmh?.toFixed(0) ?? "—"} km/h
              </div>
            </div>
          </div>

          {rain !== null && rain !== undefined && (
            <div className="wx-rain">
              🌧 Rain expected {rain < 0.5 ? "shortly" : `in about ${rain}h`}
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
          Refresh
        </button>
        <button className="mini" onClick={() => simulateWeather("rain").then(load)}>
          Simulate rain
        </button>
        <button className="mini" onClick={() => simulateWeather("clear").then(load)}>
          Clear
        </button>
      </div>
    </section>
  );
}
