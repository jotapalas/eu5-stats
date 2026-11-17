/** Response shapes of the backend API (see backend/app/stats/api.py and db.py). */

export type SaveStatus = "pending" | "processing" | "done" | "error";

export interface Campaign {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  sessions: number;
  saves: number;
  saves_done: number;
  saves_pending: number;
  saves_error: number;
  first_date: string | null;
  last_date: string | null;
  countries: string[];
  /** Main player per country (set in the tracked list), keyed by display tag; only those set. */
  main_players: Record<string, string>;
}

export interface Snapshot {
  date: string;
  tag: string;
  country_id: number;
  players: string[];
  metrics: Record<string, number>;
}

export interface CampaignDetail extends Campaign {
  latest: Record<string, Snapshot>;
}

export interface MetricDef {
  name: string;
  category: string;
  description: string;
}

export interface MetricsResponse {
  metrics: MetricDef[];
  history_metrics: string[];
}

/** [game_date, value] per save, or [year, value] for history. */
export type Point<X = string> = [X, number];

export interface SeriesResponse {
  metric: string;
  points: Record<string, Point[]>;
}

export interface HistoryResponse {
  metric: string;
  series: Record<string, Point<number>[]>;
  players: Record<string, string[]>;
}

export interface TimelineEntry {
  save_id: number;
  session_id: number;
  date: string;
  tag: string;
  players: string[];
  metrics: Record<string, number>;
}

export interface CountryTimeline {
  tag: string;
  country_id: number;
  timeline: TimelineEntry[];
}

export interface TrackedCountry {
  tag: string;
  added_as: string;
  country_id: number | null;
  active: boolean;
  /** Main player shown campaign-wide; null: the players from the saves. */
  player: string | null;
  added_at: string;
  tags: string[];
  players: string[];
  snapshots: number;
  last_date: string | null;
}

export interface Session {
  id: number;
  campaign_id: number;
  name: string | null;
  played_on: string | null;
  notes: string | null;
  created_at: string;
  first_date: string | null;
  last_date: string | null;
  saves_by_status: Partial<Record<SaveStatus, number>>;
  saves: number;
}

export interface Save {
  id: number;
  session_id: number;
  campaign_id: number;
  sha256: string;
  file_name: string | null;
  playthrough_id: string | null;
  playthrough_name: string | null;
  version: string | null;
  game_hours: number | null;
  game_date: string | null;
  status: SaveStatus;
  error: string | null;
  warning: string | null;
  uploaded_at: string;
  processed_at: string | null;
}

export interface SessionDetail extends Session {
  save_list: Save[];
}

export interface UploadResult {
  id: number;
  file: string;
  status: SaveStatus | "duplicate";
  session_id: number;
}

export interface UploadResponse {
  session_id: number;
  saves: UploadResult[];
}

export interface MetricDelta {
  start: number | null;
  end: number | null;
  delta: number | null;
}

export interface SessionSummary {
  session_id: number;
  campaign_id: number;
  first_date: string | null;
  last_date: string | null;
  countries: Record<string, Record<string, MetricDelta>>;
  /** Players as written in this session's saves. */
  players: Record<string, string[]>;
}
