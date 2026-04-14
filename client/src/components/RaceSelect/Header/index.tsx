import './index.css';

/**
 * Props for the RaceSelectHeader component.
 *
 * @property {number[]} availableYears - Ordered list of seasons to populate the year dropdown.
 * @property {number} selectedYear - The currently active season year.
 * @property {(year: number) => void} onYearChange - Callback fired with the newly selected year.
 * @property {boolean} loading - When true, the year dropdown is hidden while year data is being fetched.
 */
interface RaceSelectHeaderProps {
  availableYears: number[];
  selectedYear: number;
  onYearChange: (year: number) => void;
  loading: boolean;
}

/**
 * RaceSelectHeader renders the top bar of the race selection screen.
 * It displays the "RACE SELECT" title on the left and, once year data has
 * loaded, a season-year dropdown on the right.
 *
 * The dropdown is intentionally hidden during loading to prevent the user
 * from interacting with an incomplete list of years.
 *
 * @param {RaceSelectHeaderProps} props - Component props.
 * @returns {JSX.Element} The rendered header bar.
 */
export default function RaceSelectHeader({
  availableYears,
  selectedYear,
  onYearChange,
  loading,
}: RaceSelectHeaderProps) {
  return (
    <div className="race-select-header">
      <div className="race-select-header-left">
        <h1 className="race-select-title">
          RACE SELECT
        </h1>
      </div>

      {!loading && (
        <select
          className="year-dropdown"
          value={selectedYear}
          onChange={e => onYearChange(Number(e.target.value))}
        >
          {availableYears.map(y => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
