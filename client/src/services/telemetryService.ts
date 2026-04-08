import { supabase } from '../lib/supabase';
import type { RaceWeekend } from '../types/race.types';
import type { RaceFramesResponse } from '../types/api.types';
import type { TrackDataResponse } from '../types/track-api.types';

const parse = (val: any) => typeof val === 'string' ? JSON.parse(val) : val;

export const telemetryService = {

  getAvailableYears: async (): Promise<{ years: number[] }> => {
    const { data, error } = await supabase
      .from('races')
      .select('year')
      .order('year', { ascending: false });

    if (error) throw new Error(error.message);
    const years = [...new Set((data ?? []).map((r: any) => r.year as number))];
    return { years };
  },

  getRaceSchedule: async (year: number): Promise<RaceWeekend[]> => {
    const { data, error } = await supabase
      .from('races')
      .select('round_number:round, event_name, circuit_name, country, date')
      .eq('year', year)
      .order('round', { ascending: true });

    if (error) throw new Error(error.message);
    return (data ?? []) as RaceWeekend[];
  },

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

    const chunkFrames: any[][] = [];
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

    const allFrames = chunkFrames.flat();

    return {
      frames:             allFrames,
      driver_colors:      parse(meta.driver_colors),
      driver_teams:       parse(meta.driver_teams),
      official_positions: parse(meta.official_positions ?? '{}'),
      total_frames:       allFrames.length,
    };
  },

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

        // Derive is_out from the driver's final frame rather than
        // inferring from position — classified retirements have a
        // position set but is_out = true on their last frame.
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
          const frames = parse(lastChunk.frames);
          const lastFrame = frames[frames.length - 1];
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