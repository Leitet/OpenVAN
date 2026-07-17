import { useEffect, useState } from "react";
import { Moon, Sun, DoorOpen, Tent, Sparkles, Check } from "lucide-react";
import { getScenes, runScene } from "@shared/api";
import type { SceneInfo } from "@shared/types";
import { useT } from "../i18n";

const ICON = { moon: Moon, sun: Sun, door: DoorOpen, tent: Tent } as const;

/** One-tap routines. Each scene runs a bundle of safety-checked intents in Core
 * (the same ones the assistant would), so "Goodnight" dims the whole van at once. */
export function Scenes() {
  const t = useT();
  const [scenes, setScenes] = useState<SceneInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    getScenes().then(setScenes);
  }, []);

  const run = async (id: string) => {
    setBusy(id);
    setDone(null);
    try {
      await runScene(id);
      setDone(id);
      setTimeout(() => setDone((d) => (d === id ? null : d)), 2000);
    } finally {
      setBusy(null);
    }
  };

  if (scenes.length === 0) return null;

  return (
    <section className="panel">
      <h2>{t("home.routines")}</h2>
      <div className="scene-grid">
        {scenes.map((s) => {
          const Icon = done === s.id ? Check : ICON[s.icon as keyof typeof ICON] ?? Sparkles;
          return (
            <button
              key={s.id}
              className={"scene-btn" + (done === s.id ? " done" : "")}
              disabled={busy === s.id}
              onClick={() => run(s.id)}
              title={s.description}
            >
              <Icon className="scene-icon" />
              <span className="scene-name">{s.name}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
