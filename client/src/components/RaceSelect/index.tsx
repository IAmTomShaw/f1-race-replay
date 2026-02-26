import { useState, useEffect } from 'react';
import { telemetryService } from '../../services/telemetryService';
import type { RaceWeekend } from '../../types/race.types';
import RaceSelectHeader from './Header';
import RaceTable from './Table';
import './index.css';

interface RaceSelectProps {
  onSelectRace: (year: number, round: number) => void;
}

export default function RaceSelect({ onSelectRace }: RaceSelectProps) {
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [selectedYear, setSelectedYear] = useState<number>(2024);
  const [races, setRaces] = useState<RaceWeekend[]>([]);
  const [loadingYears, setLoadingYears] = useState(true);
  const [loadingRaces, setLoadingRaces] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      .catch(err => setError(err.message || 'Failed to load schedule'))
      .finally(() => setLoadingRaces(false));
  }, [selectedYear]);

  return (
    <div className="race-select">
      <RaceSelectHeader
        availableYears={availableYears}
        selectedYear={selectedYear}
        onYearChange={setSelectedYear}
        loading={loadingYears}
      />

      {loadingRaces ? (
        <div className="race-select-loading">
          <div className="spinner" />
          <p>Loading {selectedYear} schedule…</p>
        </div>
      ) : error ? (
        <div className="race-select-error">
          <p>{error}</p>
          <button onClick={() => setSelectedYear(selectedYear)}>Retry</button>
        </div>
      ) : (
        <RaceTable
          races={races}
          selectedYear={selectedYear}
          onSelectRace={onSelectRace}
        />
      )}
    </div>
  );
}
