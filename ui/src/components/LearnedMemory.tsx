import { useEffect, useState } from "react";
import { getAssistantMemory, clearAssistantMemory } from "@shared/api";
import type { AssistantMemory } from "@shared/types";
import { useT } from "../i18n";

/** Shows what the van has learned about the traveller — a rolling summary and the
 * durable preferences that shape its suggestions — with a way to forget it all. */
export function LearnedMemory() {
  const t = useT();
  const [mem, setMem] = useState<AssistantMemory>({ summary: "", preferences: [] });

  useEffect(() => {
    let active = true;
    const load = () => getAssistantMemory().then((m) => active && setMem(m));
    load();
    const timer = setInterval(load, 8000); // pick up newly-learned preferences
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const forget = async () => setMem(await clearAssistantMemory());

  const empty = !mem.summary && mem.preferences.length === 0;

  return (
    <section className="panel learned">
      <div className="learned-head">
        <h2>{t("memory.title")}</h2>
        {!empty && (
          <button className="mini" onClick={forget}>
            {t("memory.forget")}
          </button>
        )}
      </div>
      {empty ? (
        <p className="companion-quiet">{t("memory.empty")}</p>
      ) : (
        <>
          {mem.summary && <p className="learned-summary">{mem.summary}</p>}
          <div className="learned-chips">
            {mem.preferences.map((p, i) => (
              <span className="learned-chip" key={i}>
                {p}
              </span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
