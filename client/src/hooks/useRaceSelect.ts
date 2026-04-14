import { useState, useEffect } from 'react';
import { telemetryService } from '../services/telemetryService';
import type { RaceWeekend } from '../types/race.types';

/**
 * Manages year and race selection state for the race picker screen. Handles
 * two sequential data dependencies:
 * 1. **Available years** — fetched once on mount; the most recent year is
 *    auto-selected. Falls back to a hardcoded list if the fetch fails.
 * 2. **Race schedule** — re-fetched whenever `selectedYear` changes.
 *
 * @returns {{
 *   availableYears: number[],
 *   selectedYear: number,
 *   setSelectedYear: (year: number) => void,
 *   races: RaceWeekend[],
 *   loadingYears: boolean,
 *   loadingRaces: boolean,
 *   error: string | null,
 *   retrySchedule: () => void,
 * }}
 */
export function useRaceSelect() {
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number>(2024);
  const [races, setRaces] = useState<RaceWeekend[]>([]);
  const [loadingYears, setLoadingYears] = useState(true);
  const [loadingRaces, setLoadingRaces] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Fetches the list of available season years once on mount.
   * Years are sorted in descending order so the most recent season appears first,
   * and the first entry is automatically set as the selected year.
   *
   * Falls back to a hardcoded four-year list if the request fails, ensuring
   * the UI remains usable even when the service is unavailable.
   */
  useEffect(() => {
    telemetryService.getAvailableYears()
      .then(({ years }) => {
        const sorted = [...years].sort((a, b) => b - a);
        setAvailableYears(sorted);
        setSelectedYear(sorted[0] ?? 2024);
      })
      .catch(() => setAvailableYears([2024, 2023, 2022, 2021]))
      .finally(() => setLoadingYears(false));
  }, []);

  /**
   * Re-fetches the race schedule whenever `selectedYear` changes.
   * Clears any previous error before the new request begins so stale
   * error messages don't persist across year changes.
   */
  useEffect(() => {
    setLoadingRaces(true);
    setError(null);
    telemetryService.getRaceSchedule(selectedYear)
      .then(setRaces)
      .catch((err: Error) => setError(err.message || 'Failed to load schedule'))
      .finally(() => setLoadingRaces(false));
  }, [selectedYear]);

  /**
   * Retries the schedule fetch for the current year by reassigning `selectedYear`
   * to itself, which triggers the schedule effect to re-run.
   */
  const retrySchedule = () => setSelectedYear(selectedYear);

  return {
    availableYears, selectedYear, setSelectedYear,
    races, loadingYears, loadingRaces,
    error, retrySchedule,
  };
}
