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
  connectivity?: "online" | "offline";
  personality?: string;
  personality_id?: string;
}

export type Connectivity = "online" | "offline" | "inherit";

export interface Personality {
  id: string;
  name: string;
  category: string;
  tagline: string;
  traits: string[];
  inspiration: string[];
  style: string;
  connectivity: Connectivity;
  model: string;
  examples: string[];
  builtin: boolean;
  based_on: string | null;
}

export interface Settings {
  version: string;
  host: string;
  port: number;
  ai_enabled: boolean;
  default_connectivity: "online" | "offline";
  offline: { base_url: string; model: string };
  online: {
    provider: "openai" | "anthropic";
    base_url: string;
    model: string;
    has_key: boolean;
  };
  assistant: Assistant;
  simulate: boolean;
  personality: string;
  plugins: PluginInfo[];
}

export interface TelemetryPoint {
  t: number;
  v: number;
}

export interface WeatherHour {
  t: string;
  temp_c: number | null;
  precip_mm: number | null;
  precip_prob: number | null;
  cloud_pct: number | null;
}

export interface Weather {
  source?: string;
  online?: boolean;
  updated_at?: number;
  current?: {
    temp_c: number | null;
    precip_mm: number | null;
    cloud_pct: number | null;
    wind_kmh: number | null;
    code: number | null;
    condition: string | null;
  };
  hourly?: WeatherHour[];
  rain_eta_hours?: number | null;
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
