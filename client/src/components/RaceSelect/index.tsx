import { flagUrl } from '../../lib/assets';
import { useRaceSelect } from '../../hooks/useRaceSelect';
import RaceSelectHeader from './Header';
import RaceTable from './RaceTable';
import './index.css';

/**
 * Props for the RaceSelect component.
 *
 * @property {(year: number, round: number) => void} onSelectRace - Callback fired when the
 *   user confirms a race selection; receives the chosen season year and round number.
 */
interface RaceSelectProps {
  onSelectRace: (year: number, round: number) => void;
}

/**
 * RaceSelect is the race-picker screen. It composes three content states
 * driven by the `useRaceSelect` hook:
 * - **Loading** — a spinner while the selected year's race schedule is being fetched.
 * - **Error** — an error message with a retry button if the fetch fails.
 * - **Table** — the full `RaceTable` listing all rounds once data is available.
 *
 * The `RaceSelectHeader` is always rendered and manages year selection independently.
 *
 * @param {RaceSelectProps} props - Component props.
 * @returns {JSX.Element} The rendered race selection screen.
 */
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
