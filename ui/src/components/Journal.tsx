import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import {
  addStayNote,
  bookmarkHere,
  deleteStay,
  getStays,
  nameStay,
} from "@shared/api";
import type { Stay } from "@shared/types";
import { useT, type TFn } from "../i18n";

function when(ts: number | null): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function duration(h: number | null): string {
  if (h === null) return "";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${h.toFixed(1)} h`;
  return `${(h / 24).toFixed(1)} days`;
}

function coords(s: Stay, t: TFn): string {
  return s.lat !== null && s.lon !== null
    ? `${s.lat.toFixed(4)}, ${s.lon.toFixed(4)}`
    : t("journal.unknown");
}

export function Journal() {
  const t = useT();
  const [stays, setStays] = useState<Stay[]>([]);
  const [current, setCurrent] = useState<Stay | null>(null);
  const [note, setNote] = useState("");
  const [place, setPlace] = useState("");

  const load = useCallback(async () => {
    const data = await getStays();
    setStays(data.stays);
    setCurrent(data.current);
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  const saveNote = async () => {
    if (!note.trim()) return;
    await addStayNote(note.trim());
    setNote("");
    load();
  };
  const savePlace = async () => {
    if (!place.trim()) return;
    await nameStay(place.trim());
    setPlace("");
    load();
  };

  return (
    <section className="panel span2">
      <div className="companion-head">
        <h2>{t("journal.title")}</h2>
        <button className="mini" onClick={() => bookmarkHere("").then(load)}>
          {t("journal.bookmark")}
        </button>
      </div>

      {current && (
        <div className="stay-current">
          <strong>{current.place || t("journal.here")}</strong> — {t("journal.campedSince")}{" "}
          {when(current.started_at)} · {duration(current.duration_hours)}
          {current.condition ? ` · ${current.condition}` : ""}
        </div>
      )}

      {stays.length > 0 && (
        <div className="stay-annotate">
          <span className="stay-annotate-label">
            {t("journal.annotateLatest")} · {stays[0].place || coords(stays[0], t)}
          </span>
          <div className="stay-forms">
            <input
              placeholder={t("journal.namePlace")}
              value={place}
              onChange={(e) => setPlace(e.target.value)}
            />
            <button className="mini" onClick={savePlace}>
              {t("journal.nameBtn")}
            </button>
            <input
              placeholder={t("journal.addNote")}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button className="mini" onClick={saveNote}>
              {t("journal.noteBtn")}
            </button>
          </div>
        </div>
      )}

      {stays.length === 0 ? (
        <p className="companion-quiet">{t("journal.none")}</p>
      ) : (
        <ul className="stay-list">
          {stays.map((s) => (
            <li key={s.id} className={"stay" + (s.open ? " open" : "")}>
              <div className="stay-main">
                <strong>{s.place || coords(s, t)}</strong>
                <span className="stay-meta">
                  {when(s.started_at)}
                  {s.open ? ` · ${t("journal.hereNow")}` : ` · ${duration(s.duration_hours)}`}
                  {s.condition ? ` · ${s.condition}` : ""}
                  {s.soc_used_pct !== null ? ` · ${t("journal.used", { n: s.soc_used_pct })}` : ""}
                  {s.solar_wh ? ` · ${t("journal.solar", { n: s.solar_wh.toFixed(0) })}` : ""}
                </span>
                {s.notes && <div className="stay-notes">{s.notes}</div>}
              </div>
              <button
                className="mini danger icon-btn"
                aria-label="Delete"
                onClick={() => deleteStay(s.id).then(load)}
              >
                <X className="btn-ico" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
