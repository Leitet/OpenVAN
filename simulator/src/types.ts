export interface Entity {
  entity_id: string;
  name: string;
  domain: string;
  category: string;
  state: unknown;
  unit: string | null;
  controllable: boolean;
  commands: string[];
  attributes: Record<string, unknown>;
}

export type Twin = Record<string, number | boolean | string>;

export interface Assistant {
  llm: boolean;
  model: string | null;
}

export interface WsMessage {
  topic: string;
  data: any;
}

export interface LogEntry {
  id: number;
  kind: "intent" | "info";
  text: string;
  allowed?: boolean;
}
