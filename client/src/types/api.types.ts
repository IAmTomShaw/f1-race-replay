/**
 * The position and telemetry state of a single driver within a telemetry frame.
 * All positional values are in the circuit's native coordinate space.
 *
 * @property {number} x - World-space X coordinate of the car.
 * @property {number} y - World-space Y coordinate of the car.
 * @property {number} dist - Cumulative track distance from the start line in metres.
 * @property {number} lap - Current lap number.
 * @property {number} rel_dist - Fractional progress through the current lap (0–1).
 * @property {number} tyre - Tyre compound ID (0 = Soft, 1 = Medium, 2 = Hard, 3 = Inter, 4 = Wet).
 * @property {number} position - Current race position.
 * @property {number} speed - Car speed in km/h.
 * @property {number} gear - Current gear (0 = neutral).
 * @property {number} drs - DRS state (0 = closed, 1 = open).
 * @property {number} throttle - Throttle application as a percentage (0–100).
 * @property {number} brake - Brake application as a percentage (0–100).
 * @property {boolean} [is_out] - True when the driver has retired and left the track.
 * @property {boolean} [finished] - True when the driver has taken the chequered flag.
 */
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
  is_out?: boolean;
  finished?: boolean;
}

/**
 * A snapshot of circuit weather conditions recorded within a telemetry frame.
 * All numeric fields are nullable to handle sessions where sensor data is
 * partially unavailable.
 *
 * @property {number | null} track_temp - Track surface temperature in °C.
 * @property {number | null} air_temp - Ambient air temperature in °C.
 * @property {number | null} humidity - Relative humidity as a percentage (0–100).
 * @property {number | null} wind_speed - Wind speed in km/h.
 * @property {number | null} wind_direction - Wind direction in degrees (0–360, meteorological).
 * @property {'DRY' | 'RAINING'} rain_state - Whether rain is currently falling.
 */
export interface WeatherData {
  track_temp: number | null;
  air_temp: number | null;
  humidity: number | null;
  wind_speed: number | null;
  wind_direction: number | null;
  rain_state: 'DRY' | 'RAINING';
}

/**
 * A single telemetry snapshot capturing all driver positions and optional
 * weather data at a given point in race time.
 *
 * @property {number} t - Elapsed race time in seconds at which this frame was recorded.
 * @property {number} lap - The lap number that was active when this frame was captured.
 * @property {Record<string, DriverPosition>} drivers - Map of three-letter driver code to position data.
 * @property {WeatherData} [weather] - Weather conditions at this frame; absent when not recorded.
 */
export interface Frame {
  t: number;
  lap: number;
  drivers: Record<string, DriverPosition>;
  weather?: WeatherData;
}

/**
 * A time interval during which a specific track status (flag or safety car) was active.
 * Used to render colored segments on the progress bar and to trigger the `RaceEventPopup`.
 *
 * @property {string} status - Status code (e.g. `'1'` = clear, `'2'` = yellow, `'4'` = SC,
 *   `'5'` = red, `'6'` = VSC, `'7'` = VSC ending).
 * @property {number} start_time - Race time in seconds at which this status began.
 * @property {number | null} end_time - Race time in seconds at which this status ended,
 *   or null if the status persisted to the end of the session.
 */
export interface TrackStatus {
  status: string;
  start_time: number;
  end_time: number | null;
}

/**
 * Metadata about a race session, included in telemetry responses to provide
 * context for the data (circuit name, event name, country, etc.).
 *
 * @property {string} event_name - Human-readable event name (e.g. `"Monaco Grand Prix"`).
 * @property {string} circuit_name - Name of the circuit (e.g. `"Circuit de Monaco"`).
 * @property {string} country - Country where the event is held.
 * @property {number} year - Season year.
 * @property {number} round - Round number within the season.
 * @property {string} date - ISO 8601 date string of the race day (e.g. `"2024-05-26"`).
 * @property {number} [total_laps] - Total scheduled laps; absent when not available in the data.
 */
export interface SessionInfo {
  event_name: string;
  circuit_name: string;
  country: string;
  year: number;
  round: number;
  date: string;
  total_laps?: number;
}

/**
 * The raw combined telemetry payload, as originally fetched from the API.
 * Superseded in most consumers by the split `TrackDataResponse` + `RaceFramesResponse`
 * pattern but retained for compatibility.
 *
 * @property {Frame[]} frames - Ordered array of telemetry frames for the race.
 * @property {TrackStatus[]} track_statuses - Track status intervals for the session.
 * @property {Record<string, [number, number, number]>} driver_colors - Map of driver code to RGB tuple.
 * @property {number} circuit_rotation - Pre-computed optimal rotation angle for the circuit map, in degrees.
 * @property {number} total_laps - Total scheduled laps in the race.
 * @property {SessionInfo} session_info - Session metadata.
 */
export interface RawTelemetryData {
  frames: Frame[];
  track_statuses: TrackStatus[];
  driver_colors: Record<string, [number, number, number]>;
  circuit_rotation: number;
  total_laps: number;
  session_info: SessionInfo;
}

/**
 * The response shape returned by `telemetryService.getRaceFrames`, containing
 * all telemetry frames for a race alongside driver metadata.
 *
 * @property {Frame[]} frames - Full ordered array of telemetry frames for the race.
 * @property {Record<string, [number, number, number]>} driver_colors - Map of driver code to RGB color tuple.
 * @property {Record<string, string>} driver_teams - Map of driver code to team name.
 * @property {Record<string, number>} official_positions - Map of driver code to official finishing position;
 *   empty during the race, populated once results are confirmed.
 * @property {number} total_frames - Total number of frames in the response (convenience count).
 */
export interface RaceFramesResponse {
  frames: Frame[];
  driver_colors: Record<string, [number, number, number]>;
  driver_teams: Record<string, string>;
  official_positions: Record<string, number>;
  total_frames: number;
}