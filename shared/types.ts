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

// The single global connectivity mode — which model answers, local or cloud.
// It is NOT a property of a personality (personalities are voice only).
export type Connectivity = "online" | "offline";

export interface Personality {
  id: string;
  name: string;
  category: string;
  tagline: string;
  traits: string[];
  inspiration: string[];
  style: string;
  examples: string[];
  builtin: boolean;
  based_on: string | null;
}

export interface Settings {
  version: string;
  host: string;
  port: number;
  ai_enabled: boolean;
  connectivity: Connectivity;
  language: "en" | "sv" | "de";
  offline: { base_url: string; model: string };
  online: {
    provider: "openai" | "openai_compatible" | "anthropic";
    base_url: string;
    model: string;
    has_key: boolean;
  };
  assistant: Assistant;
  simulate: boolean;
  personality: string;
  tuning: Record<string, number>;
  tuning_defaults: Record<string, number>;
  maintenance_intervals: Record<string, number>;
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

export interface Stay {
  id: number;
  lat: number | null;
  lon: number | null;
  place: string | null;
  started_at: number | null;
  ended_at: number | null;
  open: boolean;
  duration_hours: number | null;
  soc_used_pct: number | null;
  solar_wh: number | null;
  condition: string | null;
  notes: string;
}

export interface CampSpot {
  id: string;
  source: string;
  name: string;
  lat: number;
  lon: number;
  kind: string;
  amenities: string[];
  rating: number | null;
  price: string | null;
  description: string | null;
  url: string | null;
  distance_km: number | null;
}

export interface CampSourceConfigField {
  key: string;
  label: string;
  secret: boolean;
  value?: string; // present for non-secret fields
  set?: boolean; // present for secret fields — whether a value is stored
}

export interface CampSourceInfo {
  id: string;
  name: string;
  enabled: boolean;
  requires_internet: boolean;
  requires_key: boolean;
  config: CampSourceConfigField[];
}

export interface AssistantMemory {
  summary: string;
  preferences: string[];
}

export interface SceneInfo {
  id: string;
  name: string;
  icon: string; // "moon" | "sun" | "door" | "tent"
  description: string;
}

export type VehicleProfile = Record<string, string | number>;

export interface VehicleState {
  profile: VehicleProfile;
  presets: { id: string; name: string; spec: VehicleProfile }[];
  categories: { id: string; label: string }[];
}

export interface CameraDef {
  id: string;
  label: string;
  location: string; // rear | cabin | door | awning
  connection: string; // wired | wifi | 4g
}

// The machine-readable integration descriptor + live enabled state, mirroring
// openvan_core.integrations.IntegrationInfo.
export interface IntegrationPermissions {
  read: boolean | "limited";
  control: boolean | "limited";
  configure: boolean | "limited";
}

export interface IntegrationInfo {
  id: string;
  name: string;
  category: string;
  vendor: string;
  transports: string[];
  local: boolean;
  offline_capable: boolean;
  discovery: string;
  permissions: IntegrationPermissions;
  safety_class: number; // 0 safest … 4 critical
  status: string; // native | certified | open | community | experimental | …
  priority: string; // P0 … P3
  provides: string[];
  description: string;
  warning: string;
  enabled: boolean; // alias of installed, kept for back-compat
  installed: boolean; // added by the user (or built-in)
  builtin: boolean; // part of the platform, can't be removed (the simulator)
  mode: string; // "sim" | "modbus_tcp" | "mqtt" | … — the active transport
  live: boolean; // connected to real hardware (vs. simulated)
  sim_engine: boolean; // environment physics running (the simulator card is its switch)
  world_sim: boolean; // a simulated data-source card (grouped apart from hardware)
  config: IntegrationConfigField[]; // connection settings the user can fill in
  trust: string; // bundled | official | community | unknown_signer | unsigned
  driver_version: string; // the driver package version from its manifest
}

export interface VoiceCaps {
  stt: { available: boolean; engine: string | null };
  tts: { available: boolean; engine: string | null };
}

export interface TripStats {
  started_at: number | null;
  days: number;
  distance_km: number;
  nights: number;
  places: string[];
  place_count: number;
  solar_wh: number | null;
}

// Row schema of a "list" config field (raw from the driver's descriptor).
export interface IntegrationConfigItemField {
  key: string;
  label: string;
  type: string; // text | select | number
  options?: string[];
  hidden?: boolean; // managed by a dedicated editor (e.g. van placement), not the table
  default?: string | number;
}

export interface IntegrationConfigField {
  key: string;
  label: string;
  type: string; // text | select | list
  options: string[];
  secret: boolean;
  set: boolean; // a value is stored (used for secrets, which aren't echoed)
  value?: string | number | Record<string, unknown>[]; // omitted for secrets
  item_fields?: IntegrationConfigItemField[]; // for type "list": the row schema
  van_placement?: boolean; // list rows are placed/aimed on a top-down van view
}

export interface MaintenanceItem {
  id: string;
  label: string;
  kind: "odometer" | "date";
  due: boolean;
  remaining_km?: number;
  next_km?: number;
  remaining_days?: number;
  next_iso?: string;
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
