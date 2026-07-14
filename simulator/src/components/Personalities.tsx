import { useEffect, useState } from "react";
import {
  deletePersonality,
  forkPersonality,
  getPersonalities,
  setActivePersonality,
  updatePersonality,
} from "../api";
import type { Personality } from "../types";

export function Personalities() {
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
      <h2>Personalities</h2>
      <p className="hint">
        The companion's voice — how it phrases briefings, never what it decides.
        Pick one, or fork it to make your own.
      </p>

      <div className="persona-grid">
        {list.map((p) => (
          <div
            key={p.id}
            className={"persona-card" + (p.id === active ? " active" : "")}
            onClick={() => choose(p.id)}
          >
            <div className="persona-head">
              <strong>{p.name}</strong>
              <span className={"pill hint-pill " + p.connectivity}>
                {p.connectivity}
                {p.model !== "inherit" ? ` · ${p.model}` : ""}
              </span>
            </div>
            <div className="persona-cat">{p.category}</div>
            <div className="persona-traits">
              {p.traits.map((t) => (
                <span key={t} className="chip">
                  {t}
                </span>
              ))}
            </div>
            <div className="persona-line">“{p.tagline}”</div>
            <div className="persona-actions" onClick={(e) => e.stopPropagation()}>
              {p.id === active && <span className="persona-active">✓ active</span>}
              <button className="mini" onClick={() => setForking(p.id)}>
                Fork
              </button>
              {!p.builtin && (
                <>
                  <button className="mini" onClick={() => setEditing(p)}>
                    Edit
                  </button>
                  <button className="mini danger" onClick={() => remove(p.id)}>
                    Delete
                  </button>
                </>
              )}
            </div>
            {forking === p.id && (
              <div className="fork-row" onClick={(e) => e.stopPropagation()}>
                <input
                  autoFocus
                  placeholder="Name your fork"
                  value={forkName}
                  onChange={(e) => setForkName(e.target.value)}
                />
                <button className="mini" onClick={() => doFork(p.id)}>
                  Create
                </button>
                <button className="mini" onClick={() => setForking(null)}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        ))}
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
        connectivity: draft.connectivity,
        model: draft.model,
        examples: draft.examples,
      });
      await onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="editor">
      <h3>Edit “{personality.name}”</h3>
      <label className="field">
        <span>Name</span>
        <input value={draft.name} onChange={(e) => set({ name: e.target.value })} />
      </label>
      <label className="field">
        <span>Category</span>
        <input
          value={draft.category}
          onChange={(e) => set({ category: e.target.value })}
        />
      </label>
      <label className="field">
        <span>Signature line</span>
        <input value={draft.tagline} onChange={(e) => set({ tagline: e.target.value })} />
      </label>
      <label className="field">
        <span>Traits (comma-separated)</span>
        <input
          value={draft.traits.join(", ")}
          onChange={(e) =>
            set({ traits: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })
          }
        />
      </label>
      <label className="field">
        <span>Connectivity</span>
        <select
          value={draft.connectivity}
          onChange={(e) =>
            set({ connectivity: e.target.value as Personality["connectivity"] })
          }
        >
          <option value="inherit">inherit (use default)</option>
          <option value="offline">offline</option>
          <option value="online">online</option>
        </select>
      </label>
      <label className="field">
        <span>Model (or “inherit”)</span>
        <input value={draft.model} onChange={(e) => set({ model: e.target.value })} />
      </label>
      <label className="field">
        <span>Voice / persona (how it speaks)</span>
        <textarea
          rows={5}
          value={draft.style}
          onChange={(e) => set({ style: e.target.value })}
        />
      </label>
      <div className="editor-actions">
        <button className="mini" onClick={onClose}>
          Cancel
        </button>
        <button className="briefing-btn" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
