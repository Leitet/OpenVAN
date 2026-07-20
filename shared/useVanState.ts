import { useCallback, useEffect, useRef, useState } from "react";
import type { Assistant, Entity, LogEntry, Notice, Twin, WsMessage } from "./types";

const MAX_LOG = 40;

/**
 * Live connection to OpenVan Core. Subscribes to every Core event over the
 * WebSocket and keeps a local mirror of entities + the raw twin signals.
 * Reconnects automatically so the simulator survives Core restarts.
 */
export function useVanState() {
  const [entities, setEntities] = useState<Record<string, Entity>>({});
  const [twin, setTwin] = useState<Twin>({});
  // Last writer per signal key (integration id / plugin domain / "seed" / "sim").
  const [sources, setSources] = useState<Record<string, string>>({});
  const [log, setLog] = useState<LogEntry[]>([]);
  const [assistant, setAssistant] = useState<Assistant>({ llm: false, model: null });
  const [notices, setNotices] = useState<Record<string, Notice>>({});
  const [connected, setConnected] = useState(false);
  const logId = useRef(0);

  const pushLog = useCallback((entry: Omit<LogEntry, "id">) => {
    setLog((prev) => {
      const next = [{ ...entry, id: logId.current++ }, ...prev];
      return next.slice(0, MAX_LOG);
    });
  }, []);

  const handle = useCallback(
    (msg: WsMessage) => {
      switch (msg.topic) {
        case "snapshot": {
          const map: Record<string, Entity> = {};
          for (const e of msg.data.entities as Entity[]) map[e.entity_id] = e;
          setEntities(map);
          setTwin(msg.data.twin as Twin);
          setSources((msg.data.sources ?? {}) as Record<string, string>);
          if (msg.data.assistant) setAssistant(msg.data.assistant as Assistant);
          {
            const map2: Record<string, Notice> = {};
            for (const n of (msg.data.notices ?? []) as Notice[]) map2[n.key] = n;
            setNotices(map2);
          }
          break;
        }
        case "entity.registered":
        case "entity.state_changed": {
          const e = msg.data.entity as Entity;
          setEntities((prev) => ({ ...prev, [e.entity_id]: e }));
          break;
        }
        case "entity.removed": {
          const id = msg.data.entity_id as string;
          setEntities((prev) => {
            const next = { ...prev };
            delete next[id];
            return next;
          });
          break;
        }
        case "twin.signal_changed": {
          setTwin((prev) => ({ ...prev, [msg.data.key]: msg.data.value }));
          if (msg.data.source) {
            setSources((prev) => ({ ...prev, [msg.data.key]: msg.data.source }));
          }
          break;
        }
        case "assistant.changed": {
          setAssistant(msg.data as Assistant);
          break;
        }
        case "notice.created": {
          const n = msg.data.notice as Notice;
          setNotices((prev) => ({ ...prev, [n.key]: n }));
          break;
        }
        case "notice.cleared": {
          const n = msg.data.notice as Notice;
          setNotices((prev) => {
            const next = { ...prev };
            delete next[n.key];
            return next;
          });
          break;
        }
        case "intent.evaluated": {
          const { intent, allowed, reason } = msg.data;
          pushLog({
            kind: "intent",
            allowed,
            text: `${intent.command} ${intent.entity_id}${reason ? " — " + reason : ""}`,
          });
          break;
        }
      }
    },
    [pushLog],
  );

  useEffect(() => {
    let closed = false;
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${location.host}/ws`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = (ev) => handle(JSON.parse(ev.data));
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1000);
      };
      socket.onerror = () => socket?.close();
    };
    connect();

    return () => {
      closed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [handle]);

  return {
    entities,
    twin,
    sources,
    log,
    assistant,
    notices: Object.values(notices),
    connected,
  };
}
