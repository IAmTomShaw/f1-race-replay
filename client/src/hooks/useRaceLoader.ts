import { useState, useRef, useEffect } from 'react';
import { telemetryService } from '../services/telemetryService';
import { buildTrackFromFrames } from '../utils/trackDataConverter';
import type { TrackData } from '../types/track.types';
import type { Frame, TrackStatus } from '../types/api.types';

/** A minimal race identifier used to build and navigate the cross-season race list. */
interface RaceRef { year: number; round: number; }

/**
 * Manages the full lifecycle of race data loading: building the cross-season
 * race list, fetching track geometry and telemetry frames for a chosen race,
 * and exposing previous/next navigation based on that list.
 *
 * Two sequential fetches are required per race:
 * 1. `getTrackData` — circuit geometry, session metadata, and track status intervals.
 * 2. `getRaceFrames` — per-frame telemetry, driver colors, teams, and official positions.
 *
 * @returns {{
 *   selectedYear: number,
 *   selectedRound: number,
 *   eventName: string,
 *   circuitName: string,
 *   country: string,
 *   totalLaps: number | undefined,
 *   trackData: TrackData | null,
 *   frames: Frame[],
 *   driverColors: Record<string, [number, number, number]>,
 *   driverTeams: Record<string, string>,
 *   officialPositions: Record<string, number>,
 *   trackStatuses: TrackStatus[],
 *   loading: boolean,
 *   error: string | null,
 *   hasPrevRace: boolean,
 *   hasNextRace: boolean,
 *   prevRace: RaceRef | null,
 *   nextRace: RaceRef | null,
 *   selectRace: (year: number, round: number) => void,
 *   loadRaceData: (year: number, round: number) => Promise<void>,
 *   reset: () => void,
 * }}
 */
export function useRaceLoader() {
  const [selectedYear, setSelectedYear]   = useState(2024);
  const [selectedRound, setSelectedRound] = useState(1);
  const [allRaces, setAllRaces] = useState<RaceRef[]>([]);

  const [trackData, setTrackData]  = useState<TrackData | null>(null);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [driverColors, setDriverColors] = useState<Record<string, [number, number, number]>>({});
  const [driverTeams, setDriverTeams] = useState<Record<string, string>>({});
  const [officialPositions, setOfficialPositions] = useState<Record<string, number>>({});
  const [trackStatuses, setTrackStatuses] = useState<TrackStatus[]>([]);

  const [eventName, setEventName] = useState('');
  const [circuitName, setCircuitName] = useState('');
  const [country, setCountry] = useState('');
  const [totalLaps, setTotalLaps] = useState<number | undefined>(undefined);

  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  /**
   * Ref holding an interval timer ID used during loading animations.
   * Cleared on unmount to prevent updates on an unmounted component.
   */
  const loadingIntervalRef = useRef<number | null>(null);
  useEffect(() => () => {
    if (loadingIntervalRef.current) clearInterval(loadingIntervalRef.current);
  }, []);

  /**
   * Fetches all available season years and their race schedules, then flattens
   * them into a single chronologically ordered `allRaces` list. Falls back to
   * the current year's schedule, then to a single placeholder entry, if either
   * the multi-year fetch or the fallback fails.
   *
   * @param {number} currentYear - The year to use as a fallback if the full
   *   multi-year fetch fails.
   */
  const buildAllRaces = async (currentYear: number) => {
    try {
      const { years } = await telemetryService.getAvailableYears();
      const schedules = await Promise.all(
        [...years].sort((a, b) => a - b).map(y =>
          telemetryService.getRaceSchedule(y)
            .then(races => races.map(r => ({ year: y, round: r.round_number })))
            .catch(() => [] as RaceRef[])
        )
      );
      setAllRaces(schedules.flat());
    } catch {
      try {
        const races = await telemetryService.getRaceSchedule(currentYear);
        setAllRaces(races.map(r => ({ year: currentYear, round: r.round_number })));
      } catch {
        setAllRaces([{ year: currentYear, round: 1 }]);
      }
    }
  };

  /**
   * Fetches and populates all data for the given race. Clears stale state
   * immediately so the UI never briefly shows data from the previous race.
   *
   * The load is split into two sequential requests:
   * 1. Track data — circuit geometry and session metadata are needed first so
   *    the canvas can render the circuit outline before driver positions arrive.
   * 2. Frame data — telemetry frames, colors, teams, and official positions.
   *
   * On failure, extracts the most specific available error message from the
   * response body before falling back to the generic JS error message.
   *
   * @param {number} year - The season year to load.
   * @param {number} round - The round number to load.
   */
  const loadRaceData = async (year: number, round: number) => {
    setLoading(true);
    setError(null);
    setTrackData(null);
    setFrames([]);
    setTotalLaps(undefined);
    setOfficialPositions({});
    setTrackStatuses([]);

    try {
      const trackResponse = await telemetryService.getTrackData(year, round);
      const track = buildTrackFromFrames(trackResponse.frames, trackResponse.drs_zones);
      if (!track) throw new Error('Failed to build track');

      setTrackData(track);
      setEventName(trackResponse.session_info.event_name);
      setCircuitName(trackResponse.session_info.circuit_name);
      setCountry(trackResponse.session_info.country);
      setTotalLaps(trackResponse.session_info.total_laps ?? undefined);
      setTrackStatuses(trackResponse.track_statuses ?? []);

      const framesResponse = await telemetryService.getRaceFrames(year, round);
      setFrames(framesResponse.frames);
      setDriverColors(framesResponse.driver_colors);
      setDriverTeams(framesResponse.driver_teams || {});
      setOfficialPositions(framesResponse.official_positions || {});
    } catch (err: unknown) {
      const msg    = err instanceof Error ? err.message : 'Failed to load';
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || msg);
    } finally {
      setLoading(false);
    }
  };

  const currentRaceIdx = allRaces.findIndex(
    r => r.year === selectedYear && r.round === selectedRound
  );

  const prevRace = currentRaceIdx > 0 ? allRaces[currentRaceIdx - 1] : null;
  const nextRace = currentRaceIdx < allRaces.length - 1 ? allRaces[currentRaceIdx + 1] : null;

  /**
   * Selects a new race, refreshes the full race list, and triggers a data load.
   * This is the primary public entry point for race selection (from the picker or
   * the prev/next navigation buttons).
   *
   * @param {number} year - The season year to select.
   * @param {number} round - The round number to select.
   */
  const selectRace = (year: number, round: number) => {
    setSelectedYear(year);
    setSelectedRound(round);
    buildAllRaces(year);
    loadRaceData(year, round);
  };

  /**
   * Clears all loaded race data and returns the hook to its initial empty state.
   * Used when navigating back to the race selection screen.
   */
  const reset = () => {
    setTrackData(null);
    setFrames([]);
    setError(null);
    setAllRaces([]);
    setTrackStatuses([]);
  };

  return {
    selectedYear, selectedRound,
    eventName, circuitName, country, totalLaps,
    trackData, frames, driverColors, driverTeams, officialPositions, trackStatuses,
    loading, error,
    hasPrevRace: prevRace !== null,
    hasNextRace: nextRace !== null,
    prevRace,
    nextRace,
    selectRace, loadRaceData, reset,
  };
}
