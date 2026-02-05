import React, { useState, useEffect } from 'react';
import { racesAPI } from '../../services/api';
import YearSelector from './YearSelector';
import RaceWeekendList from './RaceWeekendList';
import SessionSelector from './SessionSelector';
import type { RaceWeekend } from '../../types/race.types';

const RaceSelection: React.FC = () => {
  const [selectedYear, setSelectedYear] = useState<number>(2025);
  const [raceWeekends, setRaceWeekends] = useState<RaceWeekend[]>([]);
  const [selectedRace, setSelectedRace] = useState<RaceWeekend | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSchedule(selectedYear);
  }, [selectedYear]);

  const loadSchedule = async (year: number) => {
    setLoading(true);
    setError(null);
    try {
      const schedule = await racesAPI.getSchedule(year);
      setRaceWeekends(schedule);
    } catch (err) {
      setError('Failed to load race schedule');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleRaceSelect = (race: RaceWeekend) => {
    setSelectedRace(race);
  };

  const handleSessionSelect = (sessionType: string) => {
    if (selectedRace) {
      // Navigate to race replay with parameters
      window.location.href = `/replay?year=${selectedYear}&round=${selectedRace.round_number}&session=${sessionType}`;
    }
  };

  return (
    <div className="race-selection">
      <header className="race-selection__header">
        <h1>F1 Race Replay 🏎️</h1>
      </header>

      <YearSelector
        selectedYear={selectedYear}
        onYearChange={setSelectedYear}
      />

      {loading && <div className="loading">Loading schedule...</div>}
      {error && <div className="error">{error}</div>}

      <div className="race-selection__content">
        <RaceWeekendList
          weekends={raceWeekends}
          selectedRace={selectedRace}
          onRaceSelect={handleRaceSelect}
        />

        {selectedRace && (
          <SessionSelector
            raceType={selectedRace.type}
            onSessionSelect={handleSessionSelect}
          />
        )}
      </div>
    </div>
  );
};

export default RaceSelection;
