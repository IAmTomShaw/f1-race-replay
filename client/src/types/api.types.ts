export interface DriverPosition {
  x: number;
  y: number;
  dist: number;
  lap: number;
  rel_dist: number;
  tyre: number;
  position: number;
  speed: number;
  gear: number;
  drs: number;
  throttle: number;
  brake: number;
}

export interface WeatherData {
  track_temp: number | null;
  air_temp: number | null;
  humidity: number | null;
  wind_speed: number | null;
  wind_direction: number | null;
  rain_state: 'DRY' | 'RAINING';
}

export interface Frame {
  t: number;
  lap: number;
  drivers: Record<string, DriverPosition>;
  weather?: WeatherData;
}

export interface TrackStatus {
  status: string;
  start_time: number;
  end_time: number | null;
}

export interface SessionInfo {
  event_name: string;
  circuit_name: string;
  country: string;
  year: number;
  round: number;
  date: string;
  total_laps?: number;
}

export interface RawTelemetryData {
  frames: Frame[];
  track_statuses: TrackStatus[];
  driver_colors: Record<string, [number, number, number]>;
  circuit_rotation: number;
  total_laps: number;
  session_info: SessionInfo;
}

export interface RaceFramesResponse {
  frames: Frame[];
  driver_colors: Record<string, [number, number, number]>;
  total_frames: number;
}
