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
  personality?: string;
  personality_id?: string;
}

export interface Personality {
  id: string;
  name: string;
  category: string;
  tagline: string;
  traits: string[];
  inspiration: string[];
  style: string;
  model_hint: "cloud" | "offline";
  examples: string[];
  builtin: boolean;
  based_on: string | null;
}

export interface Notice {
  key: string;
  level: "info" | "suggestion" | "warning";
  category: string;
  title: string;
  message: string;
  data: Record<string, unknown>;
}

export interface PluginInfo {
  domain: string;
  name: string;
  version: string;
  categories: string[];
}

export interface Settings {
  version: string;
  host: string;
  port: number;
  ai_enabled: boolean;
  llm_model: string;
  llm_base_url: string;
  llm_active: boolean;
  simulate: boolean;
  plugins: PluginInfo[];
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
