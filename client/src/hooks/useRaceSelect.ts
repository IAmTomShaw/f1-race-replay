import { useState, useEffect } from 'react';
import { telemetryService } from '../services/telemetryService';
import type { RaceWeekend } from '../types/race.types';

export function useRaceSelect() {
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear]     = useState<number>(2024);
  const [races, setRaces]                   = useState<RaceWeekend[]>([]);
  const [loadingYears, setLoadingYears]     = useState(true);
  const [loadingRaces, setLoadingRaces]     = useState(false);
  const [error, setError]                   = useState<string | null>(null);

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

  useEffect(() => {
    setLoadingRaces(true);
    setError(null);
    telemetryService.getRaceSchedule(selectedYear)
      .then(setRaces)
      .catch((err: Error) => setError(err.message || 'Failed to load schedule'))
      .finally(() => setLoadingRaces(false));
  }, [selectedYear]);

  const retrySchedule = () => setSelectedYear(selectedYear);

  return {
    availableYears, selectedYear, setSelectedYear,
    races, loadingYears, loadingRaces,
    error, retrySchedule,
  };
}
