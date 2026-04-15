/**
 * Represents a single race entry within a season schedule.
 * Used by the race selection table to display available replays.
 *
 * @property {number} round_number - Round number within the season (1-based).
 * @property {string} event_name - Human-readable event name (e.g. `"Monaco Grand Prix"`).
 * @property {string} circuit_name - Name of the circuit (e.g. `"Circuit de Monaco"`);
 *   used as the key for historical comparison lookups.
 * @property {string} country - Country where the event is held; used to resolve flag images.
 * @property {string} date - ISO 8601 date string of the race day (e.g. `"2024-05-26"`).
 * @property {string} [session_type] - Optional session type identifier (e.g. `"Race"`, `"Sprint"`).
 */
export interface RaceWeekend {
  round_number: number;
  event_name: string;
  circuit_name: string;
  country: string;
  date: string;
  session_type?: string;
}

/**
 * Response shape returned by `telemetryService.getAvailableYears`.
 * Contains the de-duplicated list of seasons that have at least one race record.
 *
 * @property {number[]} years - Distinct season years available in the database,
 *   typically sorted in descending order (most recent first).
 */
export interface AvailableYearsResponse {
  years: number[];
}