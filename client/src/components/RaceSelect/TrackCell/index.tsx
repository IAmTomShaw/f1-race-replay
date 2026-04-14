import './index.css';

/**
 * Props for the TrackCell sub-component.
 *
 * @property {string} country - Country name used as the flag alt text and primary label.
 * @property {string} eventName - Full event name displayed as secondary metadata.
 * @property {string} date - ISO date string for the race; formatted before display.
 * @property {(filename: string) => string} getFlagUrl - Resolves a flag filename to a fully qualified URL.
 */
export interface TrackCellProps {
  country: string;
  eventName: string;
  date: string;
  getFlagUrl: (filename: string) => string;
}

/**
 * Formats an ISO date string into a short, human-readable date.
 * Returns an empty string when `dateStr` is falsy.
 *
 * @param {string} dateStr - ISO 8601 date string (e.g. `"2024-05-26"`).
 * @returns {string} Localised short date (e.g. `"26 May"`), or `""` if input is empty.
 */
function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

/**
 * TrackCell renders the flag, country name, event name, and formatted race date
 * for a single row in the race table.
 *
 * The flag image is hidden (not removed) on load error to preserve cell layout.
 * The flag filename is derived by replacing spaces in the country name with underscores.
 *
 * @param {TrackCellProps} props - Component props.
 * @returns {JSX.Element} The rendered track cell.
 */
export default function TrackCell({ country, eventName, date, getFlagUrl }: TrackCellProps) {
  /** Derive the flag asset filename from the country name. */
  const filename = `Flag_of_${country.replace(/\s/g, '_')}.png`;

  return (
    <div className="track-cell">
      <img
        className="track-cell-image"
        src={getFlagUrl(filename)}
        alt={country}
        onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }}
      />
      <div className="track-cell-info">
        <span className="track-cell-name">{country}</span>
        <span className="track-cell-meta">
          {eventName} · {formatDate(date)}
        </span>
      </div>
    </div>
  );
}