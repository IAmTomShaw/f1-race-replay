import { supabase } from '../lib/supabase';
import type { RaceWeekend } from '../types/race.types';
import type { Frame, RaceFramesResponse } from '../types/api.types';
import type { TrackDataResponse } from '../types/track-api.types';

/**
 * Parses a value that may arrive from Supabase as either a JSON string or a
 * pre-parsed object. Supabase occasionally returns JSONB columns as raw strings
 * depending on the client version and column type.
 *
 * @param {unknown} val - The value to parse.
 * @returns {unknown} The parsed object, or the original value if it was not a string.
 */
const parse = (val: unknown) => typeof val === 'string' ? JSON.parse(val) : val;

/**
 * Collection of async functions that abstract all Supabase queries for race and
 * telemetry data. Each method throws a plain `Error` on failure so callers can
 * handle errors uniformly without inspecting Supabase-specific error objects.
 */
export const telemetryService = {

  /**
   * Returns the distinct set of season years that have at least one race record.
   * Years are returned in descending order (most recent first).
   *
   * @returns {Promise<{ years: number[] }>} Unique season years available in the database.
   * @throws {Error} If the Supabase query fails.
   */
  getAvailableYears: async (): Promise<{ years: number[] }> => {
    const { data, error } = await supabase
      .from('races')
      .select('year')
      .order('year', { ascending: false });

    if (error) throw new Error(error.message);
    /** De-duplicate years since one row exists per race, not per season. */
    const years = [...new Set((data ?? []).map((r: { year: number }) => r.year))];
    return { years };
  },

  /**
   * Returns the full race schedule for a given season, ordered by round number.
   *
   * @param {number} year - The season year to fetch the schedule for.
   * @returns {Promise<RaceWeekend[]>} Ordered list of race weekends in the season.
   * @throws {Error} If the Supabase query fails.
   */
  getRaceSchedule: async (year: number): Promise<RaceWeekend[]> => {
    const { data, error } = await supabase
      .from('races')
      .select('round_number:round, event_name, circuit_name, country, date')
      .eq('year', year)
      .order('round', { ascending: true });

    if (error) throw new Error(error.message);
    return (data ?? []) as RaceWeekend[];
  },

  /**
   * Fetches track geometry and session metadata for a specific race in parallel.
   * Two Supabase tables are queried simultaneously:
   * - `track_shapes` — circuit boundary frames, DRS zone definitions, and rotation angle.
   * - `races` — session metadata including event name, circuit, country, laps, and track statuses.
   *
   * JSONB columns (`frames`, `drs_zones`, `track_statuses`) are parsed from their
   * string representation if necessary.
   *
   * @param {number} year - The season year of the race.
   * @param {number} round - The round number of the race.
   * @returns {Promise<TrackDataResponse>} Combined track geometry and session info.
   * @throws {Error} If either Supabase query fails.
   */
  getTrackData: async (year: number, round: number): Promise<TrackDataResponse> => {
    const [trackRes, raceRes] = await Promise.all([
      supabase
        .from('track_shapes')
        .select('frames, drs_zones, circuit_rotation')
        .eq('year', year)
        .eq('round', round)
        .single(),
      supabase
        .from('races')
        .select('event_name, circuit_name, country, date, total_laps, track_statuses')
        .eq('year', year)
        .eq('round', round)
        .single(),
    ]);

    if (trackRes.error) throw new Error(trackRes.error.message);
    if (raceRes.error)  throw new Error(raceRes.error.message);

    const track = trackRes.data;
    const race  = raceRes.data;

    return {
      frames:           parse(track.frames),
      drs_zones:        parse(track.drs_zones),
      circuit_rotation: track.circuit_rotation ?? 0,
      track_statuses:   parse(race.track_statuses ?? '[]'),
      session_info: {
        event_name:   race.event_name,
        circuit_name: race.circuit_name,
        country:      race.country,
        date:         race.date,
        year,
        round,
        total_laps:   race.total_laps ?? null,
      },
    };
  },

  /**
   * Fetches all telemetry frames for a race by reading driver metadata from the
   * first chunk and then fetching each subsequent chunk sequentially.
   *
   * Frame data is stored in the `race_frames` table as fixed-size chunks to
   * avoid Supabase row-size limits. The first chunk (index 0) additionally holds
   * the `total_chunks` count, driver colors, team mappings, and official positions.
   * Subsequent chunks contain only `frames`.
   *
   * All chunks are fetched sequentially (not in parallel) to avoid overwhelming
   * the Supabase connection pool for large races. Chunks are then flattened into
   * a single ordered frame array.
   *
   * @param {number} year - The season year of the race.
   * @param {number} round - The round number of the race.
   * @returns {Promise<RaceFramesResponse>} All frames plus driver metadata.
   * @throws {Error} If the metadata row is missing or any chunk fetch fails.
   */
  getRaceFrames: async (year: number, round: number): Promise<RaceFramesResponse> => {
    const { data: meta, error: metaErr } = await supabase
      .from('race_frames')
      .select('total_chunks, driver_colors, driver_teams, official_positions')
      .eq('year', year)
      .eq('round', round)
      .eq('chunk_index', 0)
      .single();

    if (metaErr) throw new Error(metaErr.message);
    if (!meta)   throw new Error('No frame data found');

    const totalChunks: number = meta.total_chunks;

    const chunkFrames: unknown[][] = [];
    for (let i = 0; i < totalChunks; i++) {
      const { data, error } = await supabase
        .from('race_frames')
        .select('frames')
        .eq('year', year)
        .eq('round', round)
        .eq('chunk_index', i)
        .single();

      if (error) throw new Error(`Chunk ${i} failed: ${error.message}`);
      chunkFrames.push(parse(data.frames));
    }

    const allFrames = chunkFrames.flat() as Frame[];

    return {
      frames:             allFrames,
      driver_colors:      parse(meta.driver_colors),
      driver_teams:       parse(meta.driver_teams),
      official_positions: parse(meta.official_positions ?? '{}'),
      total_frames:       allFrames.length,
    };
  },

  /**
   * Returns a driver's full historical results at a specific circuit, one entry
   * per race that has telemetry data available.
   *
   * Retirement status (`is_retired`) is derived from the driver's `is_out` flag
   * on their final telemetry frame rather than inferred from finishing position.
   * This correctly identifies classified retirements, where the driver has a
   * position assigned but `is_out === true` on their last recorded frame.
   *
   * Races where the driver has neither a position nor a team entry are silently
   * skipped (the driver did not participate or data is unavailable).
   *
   * @param {string} driverCode - Three-letter driver code (e.g. `"HAM"`).
   * @param {string} circuitName - Circuit name to filter races by.
   * @returns {Promise<Array<{ year, round, event_name, position, is_retired, team }>>}
   *   Chronologically ordered results for the driver at this circuit.
   * @throws {Error} If the initial races query fails.
   */
  getDriverCircuitHistory: async (driverCode: string, circuitName: string) => {
    const { data: races, error: racesErr } = await supabase
      .from('races')
      .select('year, round, event_name')
      .eq('circuit_name', circuitName)
      .order('year', { ascending: true });

    if (racesErr) throw new Error(racesErr.message);
    if (!races || races.length === 0) return [];

    const results = await Promise.all(
      races.map(async race => {
        const { data: meta, error: metaErr } = await supabase
          .from('race_frames')
          .select('official_positions, driver_teams, total_chunks')
          .eq('year', race.year)
          .eq('round', race.round)
          .eq('chunk_index', 0)
          .single();

        if (metaErr || !meta) return null;

        const positions = parse(meta.official_positions ?? '{}');
        const teams     = parse(meta.driver_teams ?? '{}');
        const position  = positions[driverCode] ?? null;
        const team      = teams[driverCode] ?? '';

        if (position === null && !team) return null;

        let is_retired = false;
        const lastChunkIdx = (meta.total_chunks ?? 1) - 1;
        const { data: lastChunk } = await supabase
          .from('race_frames')
          .select('frames')
          .eq('year', race.year)
          .eq('round', race.round)
          .eq('chunk_index', lastChunkIdx)
          .single();

        if (lastChunk) {
          const frames     = parse(lastChunk.frames);
          const lastFrame  = frames[frames.length - 1];
          const driverData = lastFrame?.drivers?.[driverCode];
          is_retired = driverData?.is_out === true;
        }

        return {
          year:       race.year,
          round:      race.round,
          event_name: race.event_name,
          position,
          is_retired,
          team,
        };
      })
    );

    return results.filter(Boolean) as {
      year: number; round: number; event_name: string;
      position: number | null; is_retired: boolean; team: string;
    }[];
  },

  /**
   * Returns all race year/round pairs held at a specific circuit, ordered
   * chronologically. Used by `useComparisonMode` to determine which historical
   * races to fetch frames for.
   *
   * @param {string} circuitName - The circuit name to query.
   * @returns {Promise<Array<{ year: number; round: number }>>} Chronologically
   *   ordered list of races at the given circuit.
   * @throws {Error} If the Supabase query fails.
   */
  getCircuitRaceRounds: async (circuitName: string): Promise<{ year: number; round: number }[]> => {
    const { data, error } = await supabase
      .from('races')
      .select('year, round')
      .eq('circuit_name', circuitName)
      .order('year', { ascending: true });

    if (error) throw new Error(error.message);
    return (data ?? []) as { year: number; round: number }[];
  },
};