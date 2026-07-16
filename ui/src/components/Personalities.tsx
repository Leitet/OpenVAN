import { useEffect, useState } from "react";
import {
  deletePersonality,
  forkPersonality,
  getPersonalities,
  setActivePersonality,
  updatePersonality,
} from "@shared/api";
import type { Personality } from "@shared/types";
import { useT } from "../i18n";

const BUILTIN_IDS = new Set(["aurora", "ranger", "scout", "forge", "nomad", "pulse"]);

// Card artwork lives in public/personalities/. Forks inherit their base's art.
function imageFor(p: Personality): string | null {
  if (BUILTIN_IDS.has(p.id)) return `/personalities/${p.id}.jpg`;
  if (p.based_on && BUILTIN_IDS.has(p.based_on)) return `/personalities/${p.based_on}.jpg`;
  return null;
}

export function Personalities() {
  const t = useT();
  const [list, setList] = useState<Personality[]>([]);
  const [active, setActive] = useState<string>("");
  const [forking, setForking] = useState<string | null>(null);
  const [forkName, setForkName] = useState("");
  const [editing, setEditing] = useState<Personality | null>(null);

  const load = async () => {
    const data = await getPersonalities();
    setList(data.personalities);
    setActive(data.active);
  };

  useEffect(() => {
    load();
  }, []);

  const choose = async (id: string) => {
    setActive(id);
    await setActivePersonality(id);
  };

  const doFork = async (baseId: string) => {
    if (!forkName.trim()) return;
    const created = await forkPersonality(baseId, forkName.trim());
    setForking(null);
    setForkName("");
    await load();
    setEditing(created);
  };

  const remove = async (id: string) => {
    await deletePersonality(id);
    if (editing?.id === id) setEditing(null);
    await load();
  };

  return (
    <section className="panel span2">
      <h2>{t("personalities.title")}</h2>
      <p className="hint">{t("personalities.subtitle")}</p>

      <div className="persona-grid">
        {list.map((p) => {
          const img = imageFor(p);
          const isActive = p.id === active;
          return (
            <div
              key={p.id}
              className={"persona-card" + (isActive ? " active" : "")}
            >
              <button
                className="persona-art"
                onClick={() => choose(p.id)}
                title={t("personalities.use", { name: p.name })}
              >
                {img ? (
                  <img src={img} alt={p.name} loading="lazy" />
                ) : (
                  <div className="persona-art-fallback">
                    <strong>{p.name}</strong>
                    <span>{p.category}</span>
                  </div>
                )}
                {!p.builtin && (
                  <span className="persona-custom-tag">{p.name}</span>
                )}
                {isActive && (
                  <span className="persona-active-badge">{t("personalities.active")}</span>
                )}
              </button>

              <div className="persona-bar">
                <span className="persona-tag">{p.category}</span>
                <div className="persona-bar-actions">
                  <button className="mini" onClick={() => setForking(p.id)}>
                    {t("common.fork")}
                  </button>
                  {!p.builtin && (
                    <>
                      <button className="mini" onClick={() => setEditing(p)}>
                        {t("common.edit")}
                      </button>
                      <button className="mini danger" onClick={() => remove(p.id)}>
                        {t("common.delete")}
                      </button>
                    </>
                  )}
                </div>
              </div>

              {forking === p.id && (
                <div className="fork-row">
                  <input
                    autoFocus
                    placeholder={t("personalities.nameFork")}
                    value={forkName}
                    onChange={(e) => setForkName(e.target.value)}
                  />
                  <button className="mini" onClick={() => doFork(p.id)}>
                    {t("common.create")}
                  </button>
                  <button className="mini" onClick={() => setForking(null)}>
                    {t("common.cancel")}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {editing && (
        <PersonalityEditor
          personality={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await load();
          }}
        />
      )}
    </section>
  );
}

function PersonalityEditor({
  personality,
  onClose,
  onSaved,
}: {
  personality: Personality;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useT();
  const [draft, setDraft] = useState(personality);
  const [saving, setSaving] = useState(false);

  const set = (patch: Partial<Personality>) =>
    setDraft((d) => ({ ...d, ...patch }));

  const save = async () => {
    setSaving(true);
    try {
      await updatePersonality(personality.id, {
        name: draft.name,
        category: draft.category,
        tagline: draft.tagline,
        traits: draft.traits,
        style: draft.style,
        examples: draft.examples,
      });
      await onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="editor">
      <h3>
        {t("common.edit")} “{personality.name}”
      </h3>
      <label className="field">
        <span>{t("field.name")}</span>
        <input value={draft.name} onChange={(e) => set({ name: e.target.value })} />
      </label>
      <label className="field">
        <span>{t("field.category")}</span>
        <input
          value={draft.category}
          onChange={(e) => set({ category: e.target.value })}
        />
      </label>
      <label className="field">
        <span>{t("field.signature")}</span>
        <input value={draft.tagline} onChange={(e) => set({ tagline: e.target.value })} />
      </label>
      <label className="field">
        <span>{t("field.traits")}</span>
        <input
          value={draft.traits.join(", ")}
          onChange={(e) =>
            set({ traits: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })
          }
        />
      </label>
      <label className="field">
        <span>{t("field.voice")}</span>
        <textarea
          rows={5}
          value={draft.style}
          onChange={(e) => set({ style: e.target.value })}
        />
      </label>
      <div className="editor-actions">
        <button className="mini" onClick={onClose}>
          {t("common.cancel")}
        </button>
        <button className="briefing-btn" onClick={save} disabled={saving}>
          {saving ? t("common.saving") : t("common.save")}
        </button>
      </div>
    </div>
  );
}
