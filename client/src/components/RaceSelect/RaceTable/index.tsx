import { useState } from 'react';
import type { RaceWeekend } from '../../../types/race.types';
import TrackCell from '../TrackCell';
import './index.css';

/**
 * Props for the RaceTable component.
 *
 * @property {RaceWeekend[]} races - Ordered list of race weekends to display.
 * @property {number} selectedYear - The active season year, passed through to `onSelectRace`.
 * @property {(year: number, round: number) => void} onSelectRace - Callback fired when the
 *   user confirms their selection via the "Replay Race" button.
 * @property {(filename: string) => string} getFlagUrl - Resolves a flag filename to a URL;
 *   injected so the component remains decoupled from the asset layer.
 */
interface RaceTableProps {
  races: RaceWeekend[];
  selectedYear: number;
  onSelectRace: (year: number, round: number) => void;
  getFlagUrl: (filename: string) => string;
}

/**
 * RaceTable renders a scrollable list of race rounds for the selected season.
 * Clicking a row highlights it as the pending selection; the "Replay Race" button
 * in the sticky footer becomes active and, when clicked, fires `onSelectRace`.
 *
 * Selection state is local — only one round can be pending at a time, and it
 * resets whenever the parent changes the `races` list (e.g. on year change).
 *
 * @param {RaceTableProps} props - Component props.
 * @returns {JSX.Element} The rendered race table with a footer action button.
 *
 * @example
 * <RaceTable
 *   races={races}
 *   selectedYear={2024}
 *   onSelectRace={(year, round) => loadRace(year, round)}
 *   getFlagUrl={flagUrl}
 * />
 */
export default function RaceTable({ races, selectedYear, onSelectRace, getFlagUrl }: RaceTableProps) {
  /**
   * Round number of the row the user has clicked, or null when nothing is selected.
   * Drives both the `selected` row highlight and the `active` state of the replay button.
   */
  const [selectedRound, setSelectedRound] = useState<number | null>(null);

  /**
   * Fires `onSelectRace` with the current year and selected round.
   * No-ops when `selectedRound` is null (button is disabled in that state anyway).
   */
  const handleReplay = () => {
    if (selectedRound !== null) onSelectRace(selectedYear, selectedRound);
  };

  return (
    <div className="race-table-wrapper">
      {/* Scrollable race list */}
      <div className="race-table-scroll">
        <table className="race-table">
          <thead>
            <tr>
              <th className="col-round">Round</th>
              <th className="col-track">Track</th>
            </tr>
          </thead>
          <tbody>
            {/*
             * Each row updates `selectedRound` on click.
             * The `selected` class is applied to the highlighted row for visual feedback.
             */}
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
                    getFlagUrl={getFlagUrl}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/*
       * Footer: the replay button is disabled and unstyled until a round is selected,
       * at which point it gains the `active` class and becomes clickable.
       */}
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
