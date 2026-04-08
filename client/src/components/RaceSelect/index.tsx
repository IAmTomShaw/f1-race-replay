import { flagUrl } from '../../lib/assets';
import { useRaceSelect } from '../../hooks/useRaceSelect';
import RaceSelectHeader from './Header';
import RaceTable from './Table';
import './index.css';

interface RaceSelectProps {
  onSelectRace: (year: number, round: number) => void;
}

export default function RaceSelect({ onSelectRace }: RaceSelectProps) {
  const {
    availableYears, selectedYear, setSelectedYear,
    races, loadingYears, loadingRaces,
    error, retrySchedule,
  } = useRaceSelect();

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
          <button onClick={retrySchedule}>Retry</button>
        </div>
      ) : (
        <RaceTable
          races={races}
          selectedYear={selectedYear}
          onSelectRace={onSelectRace}
          getFlagUrl={flagUrl}
        />
      )}
    </div>
  );
}
