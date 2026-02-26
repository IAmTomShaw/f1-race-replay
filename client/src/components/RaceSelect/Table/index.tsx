import { useState } from 'react';
import type { RaceWeekend } from "../../../types/race.types"
import './index.css';

const COUNTRY_FLAGS: Record<string, string> = {
  'Australia': '🇦🇺', 'Austria': '🇦🇹', 'Azerbaijan': '🇦🇿',
  'Bahrain': '🇧🇭', 'Belgium': '🇧🇪', 'Brazil': '🇧🇷',
  'Canada': '🇨🇦', 'China': '🇨🇳', 'France': '🇫🇷',
  'Germany': '🇩🇪', 'Hungary': '🇭🇺', 'Italy': '🇮🇹',
  'Japan': '🇯🇵', 'Mexico': '🇲🇽', 'Monaco': '🇲🇨',
  'Netherlands': '🇳🇱', 'Portugal': '🇵🇹', 'Qatar': '🇶🇦',
  'Saudi Arabia': '🇸🇦', 'Singapore': '🇸🇬', 'Spain': '🇪🇸',
  'United Arab Emirates': '🇦🇪', 'UAE': '🇦🇪',
  'United Kingdom': '🇬🇧', 'United States': '🇺🇸', 'USA': '🇺🇸',
  'Vietnam': '🇻🇳', 'Russia': '🇷🇺', 'Turkey': '🇹🇷',
  'South Africa': '🇿🇦', 'Korea': '🇰🇷', 'India': '🇮🇳',
  'Argentina': '🇦🇷', 'Malaysia': '🇲🇾', 'Kazakhstan': '🇰🇿',
};

function getFlag(country: string): string {
  if (COUNTRY_FLAGS[country]) return COUNTRY_FLAGS[country];
  const match = Object.keys(COUNTRY_FLAGS).find(
    k => country.toLowerCase().includes(k.toLowerCase()) ||
         k.toLowerCase().includes(country.toLowerCase())
  );
  return match ? COUNTRY_FLAGS[match] : '🏁';
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

// ── TrackCell ──────────────────────────────────────────────────────────────────

interface TrackCellProps {
  country: string;
  eventName: string;
  date: string;
}

function TrackCell({ country, eventName, date }: TrackCellProps) {
  return (
    <div className="track-cell">
      <img className="track-cell-image" src={`/src/assets/flags/Flag_of_${country.replace(/\s/g, '_')}.png`} alt={country}></img>
      <div className="track-cell-info">
        <span className="track-cell-name">{country}</span>
        <span className="track-cell-meta">{eventName} · {formatDate(date)}</span>
      </div>
    </div>
  );
}

// ── RaceTable ──────────────────────────────────────────────────────────────────

interface RaceTableProps {
  races: RaceWeekend[];
  selectedYear: number;
  onSelectRace: (year: number, round: number) => void;
}

export default function RaceTable({ races, selectedYear, onSelectRace }: RaceTableProps) {
  const [selectedRound, setSelectedRound] = useState<number | null>(null);

  const handleReplay = () => {
    if (selectedRound !== null) onSelectRace(selectedYear, selectedRound);
  };

  return (
    <div className="race-table-wrapper">
      <div className="race-table-scroll">
        <table className="race-table">
          <thead>
            <tr>
              <th className="col-round">Round</th>
              <th className="col-track">Track</th>
            </tr>
          </thead>
          <tbody>
            {races.map(race => (
              <tr
                key={race.round_number}
                className={`race-row${selectedRound === race.round_number ? ' selected' : ''}`}
                onClick={() => setSelectedRound(race.round_number)}
              >
                <td className="col-round">{race.round_number}</td>
                <td className="col-track">
                  <TrackCell
                    country={race.country}
                    eventName={race.event_name}
                    date={race.date}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="race-table-footer">
        <button
          className={`replay-button${selectedRound !== null ? ' active' : ''}`}
          onClick={handleReplay}
          disabled={selectedRound === null}
        >
          Replay Race
        </button>
      </div>
    </div>
  );
}
