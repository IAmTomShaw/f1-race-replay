import { useState, useRef, useEffect } from 'react';
import { telemetryService } from '../services/telemetryService';
import { buildTrackFromFrames } from '../utils/trackDataConverter';
import type { TrackData } from '../types/track.types';
import type { Frame, TrackStatus } from '../types/api.types';

interface RaceRef { year: number; round: number; }

export function useRaceLoader() {
  const [selectedYear, setSelectedYear]       = useState(2024);
  const [selectedRound, setSelectedRound]     = useState(1);
  const [allRaces, setAllRaces]               = useState<RaceRef[]>([]);

  const [trackData, setTrackData]             = useState<TrackData | null>(null);
  const [frames, setFrames]                   = useState<Frame[]>([]);
  const [driverColors, setDriverColors]       = useState<Record<string, [number, number, number]>>({});
  const [driverTeams, setDriverTeams]         = useState<Record<string, string>>({});
  const [officialPositions, setOfficialPositions] = useState<Record<string, number>>({});
  const [trackStatuses, setTrackStatuses]     = useState<TrackStatus[]>([]);

  const [eventName, setEventName]             = useState('');
  const [circuitName, setCircuitName]         = useState('');
  const [country, setCountry]                 = useState('');
  const [totalLaps, setTotalLaps]             = useState<number | undefined>(undefined);

  const [loading, setLoading]                 = useState(false);
  const [error, setError]                     = useState<string | null>(null);

  const loadingIntervalRef = useRef<number | null>(null);
  useEffect(() => () => {
    if (loadingIntervalRef.current) clearInterval(loadingIntervalRef.current);
  }, []);

  // ── Build the full ordered race list across all available years ──────────
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
        setAllRaces([{ year: currentYear, round: selectedRound }]);
      }
    }
  };

  // ── Load track + frame data for a specific race ──────────────────────────
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
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  // ── Public navigation handlers ────────────────────────────────────────────
  const currentRaceIdx = allRaces.findIndex(
    r => r.year === selectedYear && r.round === selectedRound
  );

  const selectRace = (year: number, round: number) => {
    setSelectedYear(year);
    setSelectedRound(round);
    buildAllRaces(year);
    loadRaceData(year, round);
  };

  const goToPrevRace = () => {
    if (currentRaceIdx <= 0) return;
    const { year, round } = allRaces[currentRaceIdx - 1];
    setSelectedYear(year);
    setSelectedRound(round);
    loadRaceData(year, round);
  };

  const goToNextRace = () => {
    if (currentRaceIdx < 0 || currentRaceIdx >= allRaces.length - 1) return;
    const { year, round } = allRaces[currentRaceIdx + 1];
    setSelectedYear(year);
    setSelectedRound(round);
    loadRaceData(year, round);
  };

  const reset = () => {
    setTrackData(null);
    setFrames([]);
    setError(null);
    setAllRaces([]);
    setTrackStatuses([]);
  };

  return {
    // race metadata
    selectedYear, selectedRound,
    eventName, circuitName, country, totalLaps,
    // data
    trackData, frames, driverColors, driverTeams, officialPositions, trackStatuses,
    // status
    loading, error,
    // nav
    hasPrevRace: currentRaceIdx > 0,
    hasNextRace: currentRaceIdx >= 0 && currentRaceIdx < allRaces.length - 1,
    // handlers
    selectRace, goToPrevRace, goToNextRace, loadRaceData, reset,
  };
}
