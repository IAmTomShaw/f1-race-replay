export interface DriverMeta {
  code: string;
  number: string;
  full_name: string;
  team: string;
  color: string;
}

export interface DrsZonePolyline {
  x: number[];
  y: number[];
}

export interface TrackGeometry {
  x_ref: number[];
  y_ref: number[];
  x_inner: number[];
  y_inner: number[];
  x_outer: number[];
  y_outer: number[];
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
  rotation_deg: number;
  drs_zones: DrsZonePolyline[];
}

export interface TrackStatusSpan {
  status: string;
  start_time: number;
  end_time: number | null;
}

export type RaceEventType =
  | "dnf"
  | "yellow_flag"
  | "red_flag"
  | "safety_car"
  | "vsc"
  | "lap";

export interface RaceTimelineEvent {
  type: RaceEventType;
  time_s: number;
  end_time_s: number | null;
  label: string;
  lap: number | string | null;
}

export interface RaceControlMessage {
  time: number;
  category: string;
  message: string;
  flag: string;
  scope: string;
  sector: string;
  racing_number: string;
}

export interface SessionInfo {
  event_name: string;
  circuit_name: string;
  country: string;
  year: number;
  round: number;
  session_type: string;
  session_name: string;
  date: string;
  total_laps: number;
  circuit_length_m: number | null;
  fps: number;
  total_frames: number;
  duration_s: number;
}

export interface ReplayManifest {
  schema_version: number;
  session_id: string;
  session_info: SessionInfo;
  track: TrackGeometry;
  drivers: Record<string, DriverMeta>;
  track_statuses: TrackStatusSpan[];
  race_events: RaceTimelineEvent[];
  race_control_messages: RaceControlMessage[];
  standings: {
    current_drivers: Record<string, number>;
    current_constructors: Record<string, number>;
    live_drivers: Record<string, Record<string, number>>;
    live_constructors: Record<string, Record<string, number>>;
  };
}

export interface DriverColumnarSeries {
  x: number[];
  y: number[];
  dist: number[];
  rel_dist: number[];
  lap: number[];
  pos: number[];
  tyre: number[];
  tyre_life: number[];
  speed: number[];
  gear: number[];
  drs: number[];
  throttle: number[];
  brake: number[];
  in_pit: number[];
  is_out: number[];
}

export interface ColumnarFrames {
  fps: number;
  t: number[];
  lap: number[];
  drivers: Record<string, DriverColumnarSeries>;
  weather: {
    track_temp: (number | null)[];
    air_temp: (number | null)[];
    humidity: (number | null)[];
    wind_speed: (number | null)[];
    wind_direction: (number | null)[];
    rain: number[];
  } | null;
  safety_car: {
    active: number[];
    x: number[];
    y: number[];
    phase: string[];
    alpha: number[];
  } | null;
}

export interface InterpolatedDriver {
  code: string;
  x: number;
  y: number;
  dist: number;
  rel_dist: number;
  lap: number;
  position: number;
  tyre: number;
  tyre_life: number;
  speed: number;
  gear: number;
  drsActive: boolean;
  throttle: number;
  brake: number;
  inPit: boolean;
  isOut: boolean;
  gapToLeader: string;
  intervalAhead: string;
}

export interface InterpolatedSafetyCar {
  x: number;
  y: number;
  phase: "deploying" | "on_track" | "returning" | string;
  alpha: number;
}

export interface InterpolatedWeather {
  trackTemp: number | null;
  airTemp: number | null;
  humidity: number | null;
  windSpeed: number | null;
  windDirection: number | null;
  isRaining: boolean;
}

export interface InterpolatedSnapshot {
  timeS: number;
  formattedTime: string;
  leaderLap: number;
  leaderCode: string;
  trackStatusCode: string;
  driversSorted: InterpolatedDriver[];
  driversByCode: Record<string, InterpolatedDriver>;
  safetyCar: InterpolatedSafetyCar | null;
  weather: InterpolatedWeather | null;
  recentMessages: RaceControlMessage[];
}

export interface SeasonEventItem {
  round_number: number;
  event_name: string;
  country: string;
  date: string;
  format: string;
  sessions: string[];
  cached_sessions: string[];
  is_completed?: boolean;
}

export interface SessionBuildStatus {
  session_id: string;
  status: "ready" | "building" | "missing" | "error";
  progress: number;
  message: string;
}
