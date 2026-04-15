import type { TrackStatus } from "./api.types";

/**
 * A single positional sample from the raw track-shape data stored in Supabase.
 * These frames are recorded from a reference lap and used by `buildTrackFromFrames`
 * to construct the inner/outer boundary and centre-line geometry of the circuit.
 *
 * @property {number} t - Elapsed time in seconds at which this sample was recorded.
 * @property {number} x - World-space X coordinate of the reference car.
 * @property {number} y - World-space Y coordinate of the reference car.
 */
export interface TrackFrame {
  t: number;
  x: number;
  y: number;
}

/**
 * A raw DRS zone definition as stored in Supabase, using snake_case column names.
 * Converted to `DRSZoneSegment` (camelCase) by `buildTrackFromFrames` before
 * being used by the canvas renderer.
 *
 * @property {number} start_index - Index into the outer boundary point array where the DRS zone begins.
 * @property {number} end_index - Index into the outer boundary point array where the DRS zone ends.
 */
export interface DRSZone {
  start_index: number;
  end_index: number;
}

/**
 * The combined response shape returned by `telemetryService.getTrackData`.
 * Merges data from two Supabase tables (`track_shapes` and `races`) into a
 * single object consumed by `buildTrackFromFrames` and the `SessionBanner`.
 *
 * @property {{ t: number; x: number; y: number }[]} frames - Raw positional samples from the
 *   reference lap, used to construct circuit geometry.
 * @property {{ start_index: number; end_index: number }[]} drs_zones - Raw DRS zone definitions
 *   using snake_case index names, as stored in Supabase.
 * @property {number} circuit_rotation - Pre-computed optimal canvas rotation angle in degrees;
 *   defaults to 0 when the column is null.
 * @property {TrackStatus[]} track_statuses - Ordered intervals of track status changes
 *   (flags, safety cars) for the session; empty array when unavailable.
 * @property {object} session_info - Race session metadata.
 * @property {string} session_info.event_name - Human-readable event name.
 * @property {string} session_info.circuit_name - Circuit name used for comparison lookups.
 * @property {string} session_info.country - Country of the event, used for flag resolution.
 * @property {number} session_info.year - Season year.
 * @property {number} session_info.round - Round number within the season.
 * @property {string} session_info.date - ISO 8601 race day date string.
 * @property {number | null} session_info.total_laps - Total scheduled laps, or null when unavailable.
 */
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