import './index.css';

interface RaceSelectHeaderProps {
  availableYears: number[];
  selectedYear: number;
  onYearChange: (year: number) => void;
  loading: boolean;
}

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
