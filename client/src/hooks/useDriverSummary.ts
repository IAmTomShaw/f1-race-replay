import { useState, useEffect } from 'react';
import { telemetryService } from '../services/telemetryService';

/**
 * A single historical race result for a driver at a specific circuit.
 *
 * @property {number} year - The season year the race took place.
 * @property {number} round - The round number within that season.
 * @property {string} event_name - Human-readable name of the race event.
 * @property {number | null} position - Official finishing position, or null when unavailable.
 * @property {boolean} is_retired - True when the driver did not finish (DNF/DNS/DSQ).
 * @property {string} team - Team name the driver competed for in this race.
 */
interface CircuitResult {
  year: number;
  round: number;
  event_name: string;
  position: number | null;
  is_retired: boolean;
  team: string;
}

/**
 * Fetches and summarises a driver's historical results at a specific circuit.
 * Re-runs whenever `selectedDriver` or `circuitName` changes. Clears previous
 * results immediately on change so stale data is never briefly visible.
 *
 * @param {string} selectedDriver - Driver code to look up (e.g. `"HAM"`). Fetching
 *   is skipped and results are cleared when this is an empty string.
 * @param {string} circuitName - Name of the circuit to filter results by.
 *
 * @returns {{
 *   results: CircuitResult[],
 *   loading: boolean,
 *   error: string | null,
 *   bestResult: number | null,
 *   wins: number,
 *   dnfs: number,
 * }} The raw result list plus pre-computed aggregate statistics.
 */
export function useDriverSummary(selectedDriver: string, circuitName: string) {
  const [results, setResults] = useState<CircuitResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  /**
   * Fetches circuit history whenever the driver or circuit changes.
   * Bails out early (clearing results) when `selectedDriver` is empty,
   * so the panel shows a clean empty state before a driver is chosen.
   */
  useEffect(() => {
    if (!selectedDriver) {
      setResults([]);
      return;
    }
    setLoading(true);
    setError(null);
    setResults([]);

    telemetryService.getDriverCircuitHistory(selectedDriver, circuitName)
      .then(setResults)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedDriver, circuitName]);

  /**
   * Best (lowest) finishing position across all non-retired results.
   * Returns null when there are no results or all results are retirements.
   */
  const bestResult = results.length > 0
    ? Math.min(...results
        .filter(r => r.position !== null && !r.is_retired)
        .map(r => r.position!))
    : null;

  const wins = results.filter(r => r.position === 1 && !r.is_retired).length;
  const dnfs = results.filter(r => r.is_retired).length;

  return { results, loading, error, bestResult, wins, dnfs };
}
