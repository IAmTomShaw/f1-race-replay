import type { TrackStatus } from "./api.types";

export interface TrackFrame {
  t: number;
  x: number;
  y: number;
}

export interface DRSZone {
  start_index: number;
  end_index: number;
}

export interface TrackDataResponse {
  frames: { t: number; x: number; y: number }[];
  drs_zones: { start_index: number; end_index: number }[];
  circuit_rotation: number;
  track_statuses: TrackStatus[];
  session_info: {
    event_name: string;
    circuit_name: string;
    country: string;
    year: number;
    round: number;
    date: string;
    total_laps: number | null;
  };
}
